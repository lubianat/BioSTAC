import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import json
    import pathlib
    import tempfile

    import duckdb
    import marimo as mo

    import biostac_build as bb

    CHALLENGE = bb.CHALLENGE
    return CHALLENGE, bb, duckdb, json, mo, pathlib, tempfile


@app.cell
def _(mo):
    mo.md(r"""
    # Studies as a table

    Images, plates and wells are all queryable as Parquet: each study's `item-list.parquet`. The **study**
    is not: its metadata lives in its RO-Crate, so "which studies are light-sheet, CC-BY, from 2023, and who
    wrote them" means fetching and parsing every crate.

    This notebook writes one row per study into `catalogs/challenge/<resource>/study-list.parquet`, taking
    what the study crates say: authors, publisher, publication, taxa, imaging methods, size and file count.
    It also counts each study's rows by level and names its list (`item_list_href`, relative to the
    study-list), so a reader goes from the resource crate to any study's items without opening the study crate.

    It is a derived table, registered as a File in the resource crate; the crates stay canonical.
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
def _(CHALLENGE, bb, duckdb, from_crate, json):
    def study_rows(resource):
        """One row per study crate of a resource, with its rows counted by level."""
        for path in sorted((CHALLENGE / resource).glob(f"*/{bb.CRATE}")):
            folder = path.parent
            crate = json.loads(path.read_text())
            fields = from_crate(crate)
            root = bb.crate_root(crate)[1]
            license_ = root.get("license")
            license_ = license_.get("@id") if isinstance(license_, dict) else license_
            thumbnail = (bb.as_list(root.get("thumbnailUrl")) or [None])[0]
            thumbnail = thumbnail.get("@id") if isinstance(thumbnail, dict) else thumbnail
            counts = dict(duckdb.sql(f"""SELECT "bioimage:level", count(*) FROM '{folder}/item-list.parquet'
                                         GROUP BY 1""").fetchall())
            yield {
                "study": folder.name,
                "source": resource,
                **{key: fields[key] for key in ("title", "description", "keywords", "date_published", "study_url")},
                "license": bb.LICENSES.get(license_, license_),
                # BioSTAC writes a crate for every study; this says whether the source published one
                "source_crate": str((root.get("isBasedOn") or {}).get("@id", "")).endswith(bb.CRATE),
                # relative to this study-list, so it resolves in whichever bucket the resource is deployed to
                "crate_href": f"{folder.name}/{bb.CRATE}",
                "item_list_href": f"{folder.name}/item-list.parquet",
                # the list is sorted by level, so its first `items` rows are the images and plates
                "items": counts.get("image", 0) + counts.get("plate", 0),
                "wells": counts.get("well", 0),
                "thumbnail": thumbnail if not thumbnail or thumbnail.startswith("http") else f"{folder.name}/{thumbnail}",
                **{key: fields.get(key) for key in (
                    "organisms", "organism_terms", "imaging_methods", "imaging_method_terms",
                    "authors", "author_ids", "publisher", "publication_title", "publication_doi",
                    "size_bytes", "file_count")},
            }

    resources = sorted(p.parent.name for p in CHALLENGE.glob(f"*/{bb.CRATE}"))
    return resources, study_rows


@app.cell
def _(CHALLENGE, bb, duckdb, json, mo, pathlib, resources, study_rows, tempfile):
    STUDY_TYPES = {
        **{k: "VARCHAR" for k in ("title", "description", "study_url", "license", "thumbnail", "publisher",
                                  "publication_title", "publication_doi")},
        **{k: "VARCHAR[]" for k in ("keywords", "organisms", "organism_terms", "imaging_methods",
                                    "imaging_method_terms", "authors", "author_ids")},
        "date_published": "DATE", "size_bytes": "BIGINT", "file_count": "BIGINT",
    }

    def write_studies(resource):
        """DuckDB reads the rows as NDJSON, so the list columns keep their type without a new dependency."""
        rows = list(study_rows(resource))
        target = CHALLENGE / resource / "study-list.parquet"
        with tempfile.TemporaryDirectory() as scratch:
            source = pathlib.Path(scratch) / "studies.ndjson"
            source.write_text("".join(json.dumps(row) + "\n" for row in rows))
            # a column null in every row is read as JSON; generated crates leave many empty, so type them all
            casts = ", ".join(
                f'"{name}"::{kind} AS "{name}"' for name, kind in STUDY_TYPES.items() if name in rows[0])
            duckdb.sql(f"""COPY (SELECT * REPLACE ({casts}) FROM read_json_auto('{source}') ORDER BY study)
                           TO '{target}' (FORMAT parquet, COMPRESSION zstd)""")
        bb.register_file(CHALLENGE / resource, target, "Studies of this resource, one row each, naming each "
                         "study's crate and item-list.parquet")
        return rows, target

    written = {resource: write_studies(resource) for resource in resources}
    mo.md("## Written\n" + "\n".join(
        f"- `{target}`: **{len(rows)}** studies, {sum(r['source_crate'] for r in rows)} with the source's own crate "
        f"({target.stat().st_size / 1024:.1f} KB), registered in the resource crate"
        for rows, target in written.values()))
    return (written,)


@app.cell
def _(CHALLENGE, duckdb, mo, resources):
    STUDIES = [str(CHALLENGE / r / "study-list.parquet") for r in resources]
    ITEMS = str(CHALLENGE / "*" / "*" / "item-list.parquet")

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
JOIN read_parquet('{ITEMS}', union_by_name := true) i ON i.study = s.study AND i."bioimage:level" <> 'well'
GROUP BY 1, 2, 3 ORDER BY images DESC LIMIT 8
"""),
    ])
    return (STUDIES,)


@app.cell
def _(STUDIES, duckdb, mo, written):
    _rows = [row for rows, _ in written.values() for row in rows]
    _no_crate = [r["study"] for r in _rows if not r["source_crate"]]
    _missing = {
        field: sorted(r["study"] for r in _rows if r["source_crate"] and not r.get(field))
        for field in ("authors", "publication_title", "keywords", "size_bytes", "date_published", "organisms")
    }
    _total = duckdb.sql(f"SELECT count(*), sum(items) FROM read_parquet({STUDIES}, union_by_name := true)").fetchone()
    mo.md(
        f"## Findings\n- {_total[0]} studies covering {_total[1]:,} items\n"
        f"- without a source crate (so only what BioSTAC generated): {', '.join(_no_crate) or 'none'}\n"
        + "\n".join(f"- crate has no `{field}`: {', '.join(studies) or 'none'}" for field, studies in _missing.items())
    )
    return


if __name__ == "__main__":
    app.run()
