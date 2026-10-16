import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import json
    import time
    import urllib.parse
    import urllib.request

    import duckdb
    import marimo as mo

    # the one thing this notebook knows: where the published catalog starts
    ROOT = "https://huggingface.co/buckets/tiagolubiana/RO-BioSTAC_demo/resolve/challenge/ro-crate-metadata.json"
    return ROOT, duckdb, json, mo, time, urllib


@app.cell
def _(ROOT, mo):
    mo.md(f"""
    # Searching the published catalog

    Everything here reads the catalog **as deployed**, starting from one URL:

    `{ROOT}`

    The root crate lives in one Hugging Face bucket and nests its resource crates by absolute URL in others,
    so this is a genuine cross-bucket crawl rather than a folder convention. Nothing local is read, no
    credentials are used, and the OME-Zarr data itself still sits on EBI servers.

    The buckets answer range requests, so DuckDB reads only the parts of each Parquet file a query needs.
    """)
    return


@app.cell
def _(ROOT, json, mo, urllib):
    def crate(url):
        """The root entity of a crate, and its graph by @id."""
        with urllib.request.urlopen(url, timeout=60) as response:
            graph = {node["@id"]: node for node in json.load(response)["@graph"]}
        return graph["./"], graph

    def ids(value):
        return [v["@id"] for v in (value if isinstance(value, list) else [value] if value else [])]

    def nested(url):
        """The crates a crate nests (RO-Crate 1.2 'Referencing other RO-Crates'), as metadata URLs."""
        root, graph = crate(url)
        return [urllib.parse.urljoin(url, graph[i]["subjectOf"]["@id"]) for i in ids(root.get("hasPart"))
                if "ro/crate" in str(graph.get(i, {}).get("conformsTo", {}).get("@id", ""))]

    catalog = crate(ROOT)[0]
    resources = {}
    for _url in nested(ROOT):
        _root, _graph = crate(_url)
        resources[_root.get("identifier", _root["name"])] = {
            "title": _root["name"], "url": _url,
            "studies": len(nested(_url)),
            "study-list": next((urllib.parse.urljoin(_url, i) for i in ids(_root.get("hasPart"))
                                if i.endswith("study-list.parquet")), None),
        }
    mo.vstack([
        mo.md(f"## One catalog, several buckets\n`{catalog['name']}` → **{len(resources)}** resources, each in "
              "its own bucket, reached by absolute URL from the root crate."),
        mo.ui.table([{"resource": k, **{f: v[f] for f in ("title", "studies")},
                      "bucket": v["url"].split("/resolve/")[0].rsplit("/", 1)[-1]} for k, v in resources.items()],
                    selection=None, pagination=False),
    ])
    return crate, resources


@app.cell
def _(duckdb, mo, resources):
    duckdb.sql("INSTALL httpfs")  # one-off download; reading https parquet needs it
    duckdb.sql("LOAD httpfs")

    STUDIES = [r["study-list"] for r in resources.values() if r["study-list"]]
    # each study-list names its studies' item lists, relative to itself
    _lists = duckdb.sql(f"""SELECT filename, item_list_href, wells > 0
                            FROM read_parquet({STUDIES}, union_by_name := true, filename := true)""").fetchall()
    ITEMS = [f.rsplit("/", 1)[0] + "/" + href for f, href, _ in _lists]
    WELLS = [f.rsplit("/", 1)[0] + "/" + href for f, href, has_wells in _lists if has_wells]

    def bucket_of(url):
        return url.split("/resolve/")[0].rsplit("/", 1)[-1]

    mo.md(
        "## The files it found\n"
        f"- **study lists** — {len(STUDIES)}, one per resource: "
        + ", ".join(f"`{bucket_of(u)}`" for u in STUDIES)
        + f"\n- **item lists** — {len(ITEMS)}, one per study; {len(WELLS)} of them also hold plate wells\n\n"
        "Every item list holds images, plates and wells, told apart by `bioimage:level`. The queries below "
        "are grouped by how many of those files each one needs."
    )
    return ITEMS, STUDIES, WELLS, bucket_of


@app.cell
def _(bucket_of, duckdb, mo, time):
    timings = []

    def table(title, query, files):
        started = time.perf_counter()
        result = duckdb.sql(query)
        rows = [dict(zip(result.columns, r)) for r in result.fetchall()]
        elapsed = round((time.perf_counter() - started) * 1000)
        timings.append({"query": title, "files read": len(set(files)), "ms": elapsed, "rows": len(rows)})
        buckets = ", ".join(sorted({bucket_of(f) for f in files}))
        return mo.vstack([mo.md(f"**{title}** — {len(rows)} rows in {elapsed} ms, from {len(set(files))} "
                                f"files in {buckets}"),
                          mo.md(f"```sql\n{query.strip()}\n```"),
                          mo.ui.table(rows, selection=None, pagination=False)])

    return table, timings


@app.cell
def _(WELLS, mo, table):
    mo.vstack([
        mo.md("## The well annotations\n"
              "IDR's own search finds images by gene. The study list says which studies hold wells, so this "
              "query opens only their item lists, and no other bucket is touched."),
        table("Gene PAU8", f"""
    SELECT study, "idr:plate_name" AS plate, "idr:well" AS well,
           "idr:gene_identifier" AS gene_id, "idr:organism" AS organism, zarr_url AS url
    FROM read_parquet({WELLS}, union_by_name := true)
    WHERE "bioimage:level" = 'well' AND "idr:gene_symbol" = 'PAU8'
    """, WELLS),
        table("The most screened compounds", f"""
    SELECT study, "idr:compound_name" AS compound, count(*) AS wells
    FROM read_parquet({WELLS}, union_by_name := true)
    WHERE "bioimage:level" = 'well' AND "idr:compound_name" IS NOT NULL
    GROUP BY 1, 2 ORDER BY wells DESC LIMIT 8
    """, WELLS),
    ])
    return


@app.cell
def _(WELLS, mo, table):
    mo.vstack([
        mo.md("## A plate and what is inside it\n"
              "The plate is the thing you open in a viewer; the well is the thing that carries the "
              "biology. Both are rows of the same list: each well row names its plate in "
              "`bioimage:plate_id`, the id of the plate row."),
        table("Plates with the most distinct genes", f"""
    SELECT p.study, p.id AS plate, p."bioimage:wells" AS wells_in_plate,
           count(DISTINCT w."idr:gene_symbol") AS genes, count(w.id) AS wells_indexed, p.zarr_url AS plate_url
    FROM read_parquet({WELLS}, union_by_name := true) p
    JOIN read_parquet({WELLS}, union_by_name := true) w ON w."bioimage:plate_id" = p.id
    WHERE p."bioimage:level" = 'plate'
    GROUP BY ALL ORDER BY genes DESC LIMIT 8
    """, WELLS),
    ])
    return


@app.cell
def _(ITEMS, mo, table):
    mo.vstack([
        mo.md("## Every file: one question, every bucket\n"
              "`bioimage:level` says what a row denotes, so images, plates and wells can be counted "
              "side by side even though they were built by different notebooks into different buckets."),
        table("What the catalog indexes", f"""
    SELECT "bioimage:source" AS resource, "bioimage:level" AS row_denotes,
           count(*) AS rows, count(DISTINCT study) AS studies
    FROM read_parquet({ITEMS}, union_by_name := true)
    GROUP BY 1, 2 ORDER BY rows DESC
    """, ITEMS),
        table("Human samples, wherever they are", f"""
    SELECT "bioimage:source" AS resource, "bioimage:level" AS row_denotes, count(*) AS rows,
           count(DISTINCT study) AS studies
    FROM read_parquet({ITEMS}, union_by_name := true)
    WHERE "bioimage:ncbitaxon" = 'NCBITaxon:9606' OR "idr:organism_term" = 'NCBITaxon:9606'
    GROUP BY 1, 2 ORDER BY rows DESC
    """, ITEMS),
    ])
    return


@app.cell
def _(ITEMS, STUDIES, mo, table):
    mo.vstack([
        mo.md("## Studies, joined to their data"),
        table("Who published the largest studies", f"""
    SELECT s.source, s.study, left(s.title, 40) AS title, s.authors[1] AS first_author, s.license, s.items
    FROM read_parquet({STUDIES}, union_by_name := true) s
    ORDER BY s.items DESC LIMIT 8
    """, STUDIES),
    ])
    return


@app.cell
def _(STUDIES, duckdb, mo, table):
    # search by study: the small study list is the index, then only the chosen studies' files are read
    _hits = duckdb.sql(f"""
        SELECT study, item_list_href, filename FROM read_parquet({STUDIES}, union_by_name := true, filename := true)
        WHERE list_contains(organisms, 'Saccharomyces cerevisiae')""").fetchall()
    _files = [f.rsplit("/", 1)[0] + "/" + href for _, href, f in _hits]
    mo.vstack([
        mo.md("## By study: index first, then one small file each\n"
              f"`study-list.parquet` names each study's `item-list.parquet`; yeast studies: "
              f"{', '.join(s for s, _, _ in _hits) or 'none'}."),
        table("Images of the yeast studies", f"""
    SELECT study, id, "bioimage:level" AS row_denotes, zarr_url AS url
    FROM read_parquet({_files}, union_by_name := true)
    WHERE "bioimage:level" <> 'well'
    ORDER BY study, id LIMIT 8
    """, STUDIES + _files),
    ]) if _files else mo.md("## By study\nNo deployed study is about yeast.")
    return


@app.cell
def _(mo, resources, timings):
    _resource = resources.get("idr") or next(iter(resources.values()))
    _explorer = "https://arunaengine.github.io/ro-crate-explorer/?crateUrl=" + _resource["url"]
    mo.vstack([
        mo.md("## The same data, in a browser\n"
              f"- [RO-Crate Explorer on the {_resource['title']} crate]({_explorer}); its studies open as "
              "nested crates\n\n"
              "## What it cost\n"
              "Each query ran against the buckets over HTTPS. Parquet is columnar and the buckets "
              "serve range requests, so only the column chunks a query names are fetched — not the files."),
        mo.ui.table(timings, selection=None, pagination=False),
    ])
    return


if __name__ == "__main__":
    app.run()
