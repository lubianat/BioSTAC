import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import json
    import pathlib
    import tempfile

    import duckdb
    import marimo as mo
    import pystac

    import biostac_build as bb  # sets the readable StacIO, so re-saved collections stay readable

    CHALLENGE = pathlib.Path("catalogs/challenge")
    return CHALLENGE, bb, duckdb, json, mo, pathlib, pystac, tempfile


@app.cell
def _(mo):
    mo.md(r"""
    # Studies as a table

    Images, plates and wells are all queryable as Parquet. The **study** is not: its metadata lives in the
    Collection JSON and in the RO-Crate shipped beside it, so "which studies are light-sheet, CC-BY, from
    2023, and who wrote them" means crawling JSON or parsing crates.

    This notebook writes one row per study into `catalogs/challenge/<resource>/studies.parquet`, taking what
    the study crates already say: authors, publisher, publication, taxa, imaging methods, size and file count.

    **It is not stac-geoparquet.** That format holds STAC Items as rows, and a Collection is not an Item.
    This is a plain derived table: its `study` column joins to the `collection` column of `items.parquet`
    and `wells.parquet`. The Collection JSON and the crates stay canonical.
    """)
    return


@app.cell
def _(bb, json):
    def crate_index(crate):
        """The crate's nodes by @id, and its root entity."""
        nodes = {node["@id"]: node for node in crate["@graph"]}
        descriptor = next(n for n in crate["@graph"] if str(n["@id"]).endswith("ro-crate-metadata.json") and "about" in n)
        return nodes, nodes[descriptor["about"]["@id"]]

    def referenced(nodes, root, key):
        """The nodes a root property points at, whether it holds one reference or several."""
        value = root.get(key) or []
        value = value if isinstance(value, list) else [value]
        return [nodes.get(v["@id"], {"@id": v["@id"]}) for v in value if isinstance(v, dict)]

    def has_type(node, *names):
        kinds = node.get("@type", [])
        kinds = kinds if isinstance(kinds, list) else [kinds]
        return any(k in names for k in kinds)

    def quantity(nodes, root, unit):
        """GIDE and IDR both record size as QuantitativeValue nodes, but GIDE spells it QuantitiveValue."""
        for node in referenced(nodes, root, "size"):
            if has_type(node, "QuantitativeValue", "QuantitiveValue") and unit in (node.get("unitText") or ""):
                try:
                    return int(node["value"])
                except (KeyError, TypeError, ValueError):
                    return None
        return None

    def from_crate(crate):
        """The curated study fields a crate can give, whichever flavour it is."""
        nodes, root = crate_index(crate)
        taxa = [n for n in referenced(nodes, root, "about") if has_type(n, "Taxon")]
        methods = [n for n in referenced(nodes, root, "measurementMethod") if has_type(n, "DefinedTerm")]
        people = [n for n in referenced(nodes, root, "author") if has_type(n, "Person")]
        article = next((n for n in referenced(nodes, root, "citation") + referenced(nodes, root, "seeAlso")
                        if has_type(n, "ScholarlyArticle")), {})
        publisher = next((n.get("name") for n in referenced(nodes, root, "publisher") if n.get("name")), None)
        keywords = root.get("keywords")
        return {
            "title": root.get("name"),
            "description": root.get("description"),
            "date_published": root.get("datePublished"),
            "keywords": keywords if isinstance(keywords, list) else [keywords] if keywords else None,
            "study_url": root.get("url") if isinstance(root.get("url"), str) else None,
            "organisms": [n.get("scientificName") for n in taxa if n.get("scientificName")] or None,
            "organism_terms": [bb.to_curie(n["@id"]) for n in taxa] or None,
            "imaging_methods": [n.get("name") for n in methods if n.get("name")] or None,
            "imaging_method_terms": [bb.to_curie(n["@id"]) for n in methods] or None,
            "authors": [n.get("name") for n in people if n.get("name")] or None,
            "author_ids": [n["@id"] for n in people if str(n["@id"]).startswith("http")] or None,
            "publisher": publisher,
            "publication_title": article.get("name"),
            "publication_doi": article.get("@id") if str(article.get("@id", "")).startswith("http") else None,
            "size_bytes": quantity(nodes, root, "byte"),
            "file_count": quantity(nodes, root, "file"),
        }
    return (from_crate,)


@app.cell
def _(CHALLENGE, from_crate, json):
    def study_rows(resource):
        """One row per study Collection of a resource, from its JSON and its crate."""
        for path in sorted((CHALLENGE / resource).glob("*/collection.json")):
            collection = json.loads(path.read_text())
            crate_path = path.parent / "ro-crate-metadata.json"
            crate = from_crate(json.loads(crate_path.read_text())) if crate_path.exists() else {}
            assets = collection.get("assets", {})
            via = [link for link in collection["links"] if link["rel"] == "via"]
            row = {
                "study": collection["id"],
                "source": resource,
                "title": collection.get("title") or crate.get("title"),
                "description": collection.get("description"),
                "license": collection.get("license"),
                "keywords": collection.get("keywords") or crate.get("keywords"),
                "date_published": crate.get("date_published"),
                "study_url": crate.get("study_url") or next((v["href"] for v in via if v.get("title") == "Study page"), None),
                "crate_path": f"{resource}/{path.parent.name}/ro-crate-metadata.json" if crate_path.exists() else None,
                "thumbnail": assets.get("thumbnail", {}).get("href"),
                "items": sum(1 for link in collection["links"] if link["rel"] == "item"),
                # the index to each study's own Parquet, relative to this studies.parquet, so it resolves
                # in whichever bucket the resource is deployed to
                "items_href": f"{path.parent.name}/items.parquet" if "items" in assets else None,
                "wells_href": f"{path.parent.name}/wells.parquet" if "wells" in assets else None,
                "has_crate": crate_path.exists(),
                **{key: crate.get(key) for key in (
                    "organisms", "organism_terms", "imaging_methods", "imaging_method_terms",
                    "authors", "author_ids", "publisher", "publication_title", "publication_doi",
                    "size_bytes", "file_count")},
            }
            yield row

    resources = sorted(p.parent.name for p in CHALLENGE.glob("*/catalog.json"))
    return resources, study_rows


@app.cell
def _(CHALLENGE, duckdb, json, mo, pathlib, resources, study_rows, tempfile):
    def write_studies(resource):
        """DuckDB reads the rows as NDJSON, so the list columns keep their type without a new dependency."""
        rows = list(study_rows(resource))
        target = CHALLENGE / resource / "studies.parquet"
        with tempfile.TemporaryDirectory() as scratch:
            source = pathlib.Path(scratch) / "studies.ndjson"
            source.write_text("".join(json.dumps(row) + "\n" for row in rows))
            # a column that is null in every row is read as JSON; the hrefs must stay strings across files
            duckdb.sql(f"""COPY (SELECT * REPLACE (items_href::VARCHAR AS items_href, wells_href::VARCHAR AS wells_href)
                                 FROM read_json_auto('{source}') ORDER BY study)
                           TO '{target}' (FORMAT parquet, COMPRESSION zstd)""")
        return rows, target

    written = {resource: write_studies(resource) for resource in resources}
    mo.md("## Written\n" + "\n".join(
        f"- `{target}`: **{len(rows)}** studies, {sum(r['has_crate'] for r in rows)} with a crate "
        f"({target.stat().st_size / 1024:.1f} KB)"
        for rows, target in written.values()))
    return (written,)


@app.cell
def _(CHALLENGE, bb, mo, pystac, resources):
    for _resource in resources:
        _catalog = pystac.Catalog.from_file(str(CHALLENGE / _resource / "catalog.json"))
        bb.link_table(_catalog, "studies", CHALLENGE / _resource / "studies.parquet",
                      "Studies of this resource as a table, indexing each study's own Parquet")
        _catalog.save_object(include_self_link=False, dest_href=str(CHALLENGE / _resource / "catalog.json"))
    mo.md("Linked as the `studies` table from each resource Catalog. The build notebooks rewrite "
          "`catalog.json`, so run this again after a rebuild.")
    return


@app.cell
def _(CHALLENGE, duckdb, mo, resources):
    STUDIES = [str(CHALLENGE / r / "studies.parquet") for r in resources]
    ITEMS = [str(CHALLENGE / r / "items.parquet") for r in resources]

    def table(title, query):
        result = duckdb.sql(query)
        rows = [dict(zip(result.columns, r)) for r in result.fetchall()]
        return mo.vstack([mo.md(f"**{title}**"), mo.md(f"```sql\n{query.strip()}\n```"),
                          mo.ui.table(rows, selection=None, pagination=False)])

    mo.vstack([
        mo.md("## Searching studies"),
        table("Every study, with what its crate gave", f"""
SELECT source, study, left(title, 44) AS title, license, date_published AS published,
       items, len(authors) AS authors, round(size_bytes / 1e9, 1) AS GB, file_count AS files
FROM read_parquet({STUDIES}, union_by_name := true)
ORDER BY source, study
"""),
        table("Studies by license and year", f"""
SELECT license, year(date_published) AS year, count(*) AS studies, sum(items) AS items
FROM read_parquet({STUDIES}, union_by_name := true)
GROUP BY 1, 2 ORDER BY studies DESC
"""),
        table("Imaging methods across studies", f"""
SELECT method, count(*) AS studies, sum(items) AS images
FROM (SELECT unnest(imaging_methods) AS method, items
      FROM read_parquet({STUDIES}, union_by_name := true)
      WHERE imaging_methods IS NOT NULL)
GROUP BY 1 ORDER BY studies DESC
"""),
        table("Studies joined to their images", f"""
SELECT s.study, left(s.title, 40) AS title, s.authors[1] AS first_author,
       count(i.id) AS images, round(sum(i."bioimage:size_bytes") / 1e9, 1) AS GB
FROM read_parquet({STUDIES}, union_by_name := true) s
JOIN read_parquet({ITEMS}, union_by_name := true) i ON i.collection = s.study
GROUP BY 1, 2, 3 ORDER BY images DESC LIMIT 8
"""),
    ])
    return (STUDIES,)


@app.cell
def _(STUDIES, duckdb, mo, written):
    _rows = [row for rows, _ in written.values() for row in rows]
    _no_crate = [r["study"] for r in _rows if not r["has_crate"]]
    _missing = {
        field: sorted(r["study"] for r in _rows if r["has_crate"] and not r.get(field))
        for field in ("authors", "publication_title", "keywords", "size_bytes", "date_published", "organisms")
    }
    _total = duckdb.sql(f"SELECT count(*), sum(items) FROM read_parquet({STUDIES}, union_by_name := true)").fetchone()
    mo.md(
        f"## Findings\n- {_total[0]} studies covering {_total[1]:,} items\n"
        f"- without a crate (so only Collection fields): {', '.join(_no_crate) or 'none'}\n"
        + "\n".join(f"- crate has no `{field}`: {', '.join(studies) or 'none'}" for field, studies in _missing.items())
    )
    return


if __name__ == "__main__":
    app.run()
