import marimo

__generated_with = "0.24.2"
app = marimo.App(width="full")


@app.cell
def _():
    import time
    import urllib.parse

    import duckdb
    import marimo as mo
    import pystac

    # the one thing this notebook knows: where the published catalog starts
    ROOT = "https://huggingface.co/buckets/tiagolubiana/ome2024-challenge-STAC/resolve/catalog.json"
    return ROOT, duckdb, mo, pystac, time, urllib


@app.cell
def _(ROOT, mo):
    mo.md(f"""
    # Searching the published catalog

    Everything here reads the catalog **as deployed**, starting from one URL:

    `{ROOT}`

    The root lives in one Hugging Face bucket and links its two resources by absolute URL into two others,
    so this is a genuine cross-bucket crawl rather than a folder convention. Nothing local is read, no
    credentials are used, and the OME-Zarr data itself still sits on EBI servers.

    The buckets answer range requests, so DuckDB reads only the parts of each Parquet file a query needs.
    """)
    return


@app.cell
def _(ROOT, mo, pystac, urllib):
    catalog = pystac.Catalog.from_file(ROOT)
    resources = list(catalog.get_children())

    def parquet_assets(resource):
        """The consolidated Parquet files a resource Catalog links, keyed by bioimage:table, as absolute URLs.
        A Catalog has no assets, so these are links; each study also carries its own files as assets."""
        return {
            link.extra_fields["bioimage:table"]: link.get_absolute_href()
            for link in resource.links
            if "bioimage:table" in link.extra_fields
        }

    deployed = {c.id: parquet_assets(c) for c in resources}
    overview = [
        {
            "resource": c.id,
            "title": c.title,
            "bucket": urllib.parse.urlparse(c.get_self_href()).path.split("/")[3],
            "studies": len(list(c.get_children())),
            "parquet tables": ", ".join(deployed[c.id]) or "—",
        }
        for c in resources
    ]
    mo.vstack([
        mo.md(f"## One catalog, three buckets\n`{catalog.id}` → **{len(resources)}** resources, each in its "
              "own bucket, reached by absolute URL from the root."),
        mo.ui.table(overview, selection=None, pagination=False),
    ])
    return catalog, deployed, resources


@app.cell
def _(deployed, duckdb, mo):
    duckdb.sql("INSTALL httpfs")  # one-off download; reading https parquet needs it
    duckdb.sql("LOAD httpfs")

    def urls(key):
        """Every deployed file published as one table, as absolute URLs."""
        return [assets[key] for assets in deployed.values() if key in assets]

    ITEMS, WELLS, STUDIES = urls("items"), urls("wells"), urls("studies")
    # the wells of a resource join to that same resource's items, so the other bucket stays unopened
    PLATE_ITEMS = [assets["items"] for assets in deployed.values() if "wells" in assets]

    def bucket_of(url):
        return url.split("/resolve/")[0].rsplit("/", 1)[-1]

    mo.md(
        "## The files it found\n"
        + "\n".join(f"- **{key}** — " + ", ".join(f"`{bucket_of(u)}`" for u in found)
                    for key, found in (("items", ITEMS), ("wells", WELLS), ("studies", STUDIES)) if found)
        + "\n\nThese are not one table. They live in different buckets and hold different things, and the "
        "queries below are grouped by how many of them each one needs."
    )
    return ITEMS, PLATE_ITEMS, STUDIES, WELLS, bucket_of


@app.cell
def _(bucket_of, duckdb, mo, time):
    timings = []

    def table(title, query, files):
        started = time.perf_counter()
        result = duckdb.sql(query)
        rows = [dict(zip(result.columns, r)) for r in result.fetchall()]
        elapsed = round((time.perf_counter() - started) * 1000)
        read = ", ".join(sorted({f"{bucket_of(f)}/{f.rsplit('/', 1)[-1]}" for f in files}))
        timings.append({"query": title, "files read": len(set(files)), "ms": elapsed, "rows": len(rows)})
        return mo.vstack([mo.md(f"**{title}** — {len(rows)} rows in {elapsed} ms, reading {read}"),
                          mo.md(f"```sql\n{query.strip()}\n```"),
                          mo.ui.table(rows, selection=None, pagination=False)])

    return table, timings


@app.cell
def _(WELLS, mo, table):
    mo.vstack([
        mo.md("## One file: the well annotations\n"
              "IDR's own search finds images by gene. The catalog says which file holds well-level "
              "annotations, so this query opens that one file and no other bucket is touched."),
        table("Gene PAU8", f"""
    SELECT collection AS study, "idr:plate_name" AS plate, "idr:well" AS well,
           "idr:gene_identifier" AS gene_id, "idr:organism" AS organism, assets.data.href AS url
    FROM read_parquet({WELLS})
    WHERE "idr:gene_symbol" = 'PAU8'
    """, WELLS),
        table("The most screened compounds", f"""
    SELECT collection AS study, "idr:compound_name" AS compound, count(*) AS wells
    FROM read_parquet({WELLS})
    WHERE "idr:compound_name" IS NOT NULL
    GROUP BY 1, 2 ORDER BY wells DESC LIMIT 8
    """, WELLS),
    ])
    return


@app.cell
def _(PLATE_ITEMS, WELLS, mo, table):
    mo.vstack([
        mo.md("## Two files: a plate and what is inside it\n"
              "The plate is the thing you open in a viewer; the well is the thing that carries the "
              "biology. They are different rows in different files: each well row names its plate in "
              "`bioimage:plate_id`, which is the id of the plate Item in the other file. A single flat "
              "table could not hold both without repeating every plate 200 times."),
        table("Plates with the most distinct genes", f"""
    SELECT p.collection AS study, p.id AS plate, p."bioimage:wells" AS wells_in_plate,
           count(DISTINCT w."idr:gene_symbol") AS genes, count(w.id) AS wells_indexed,
           p.assets.data.href AS plate_url
    FROM read_parquet({PLATE_ITEMS}, union_by_name := true) p
    JOIN read_parquet({WELLS}) w ON w."bioimage:plate_id" = p.id
    GROUP BY ALL ORDER BY genes DESC LIMIT 8
    """, PLATE_ITEMS + WELLS),
    ])
    return


@app.cell
def _(ITEMS, WELLS, mo, table):
    _all_rows = ITEMS + WELLS
    mo.vstack([
        mo.md("## Every file: one question, three buckets\n"
              "`bioimage:level` says what a row denotes, so images, plates and wells can be counted "
              "side by side even though they were built by different notebooks into different buckets."),
        table("What the catalog indexes", f"""
    SELECT "bioimage:source" AS resource, "bioimage:level" AS row_denotes,
           count(*) AS rows, count(DISTINCT collection) AS studies
    FROM read_parquet({_all_rows}, union_by_name := true)
    GROUP BY 1, 2 ORDER BY rows DESC
    """, _all_rows),
        table("Human samples, wherever they are", f"""
    SELECT "bioimage:source" AS resource, "bioimage:level" AS row_denotes, count(*) AS rows,
           count(DISTINCT collection) AS studies
    FROM read_parquet({_all_rows}, union_by_name := true)
    WHERE "bioimage:ncbitaxon" = 'NCBITaxon:9606' OR "idr:organism_term" = 'NCBITaxon:9606'
    GROUP BY 1, 2 ORDER BY rows DESC
    """, _all_rows),
    ])
    return


@app.cell
def _(ITEMS, STUDIES, mo, table):
    mo.vstack([
        mo.md("## Studies, joined to their data"),
        table("Who published the largest studies", f"""
    SELECT s.source, s.study, left(s.title, 40) AS title, s.authors[1] AS first_author,
           s.license, count(i.id) AS images
    FROM read_parquet({STUDIES}, union_by_name := true) s
    JOIN read_parquet({ITEMS}, union_by_name := true) i ON i.collection = s.study
    GROUP BY ALL ORDER BY images DESC LIMIT 8
    """, STUDIES + ITEMS),
    ]) if STUDIES else mo.md(
        "## Studies, joined to their data\n"
        "No `studies` asset is deployed yet — run `16_study_parquet.py` and upload the result, and this "
        "cell joins study metadata to the image rows."
    )
    return


@app.cell
def _(STUDIES, duckdb, mo, table):
    # search by study: the small studies table is the index, then only the chosen study's file is read
    _hits = duckdb.sql(f"""
        SELECT study, items_href, filename FROM read_parquet({STUDIES}, union_by_name := true, filename := true)
        WHERE list_contains(organisms, 'Saccharomyces cerevisiae') AND items_href IS NOT NULL""").fetchall()
    _files = [f.rsplit("/", 1)[0] + "/" + href for _, href, f in _hits]
    mo.vstack([
        mo.md("## By study: index first, then one small file each
"
              f"`studies.parquet` names each study's own `items.parquet`; yeast studies: "
              f"{', '.join(s for s, _, _ in _hits) or 'none'}."),
        table("Images of the yeast studies", f"""
    SELECT collection AS study, id, "bioimage:level" AS row_denotes, assets.data.href AS url
    FROM read_parquet({_files}, union_by_name := true)
    ORDER BY study, id LIMIT 8
    """, STUDIES + _files),
    ]) if _files else mo.md("## By study
No deployed study lists its own `items.parquet` yet.")
    return


@app.cell
def _(catalog, mo, resources, timings):
    _study = next(iter(resources[-1].get_children()))
    _crate = _study.assets.get("ro-crate")
    _browser = "https://radiantearth.github.io/stac-browser/#/external/" + catalog.get_self_href().split("://")[1]
    _explorer = ("https://arunaengine.github.io/ro-crate-explorer/?crateUrl=" + _crate.get_absolute_href()) if _crate else None
    mo.vstack([
        mo.md("## The same data, in a browser\n"
              f"- [STAC Browser on the published root]({_browser})\n"
              + (f"- [RO-Crate Explorer on {_study.id}'s study crate]({_explorer})\n" if _explorer else "")
              + "- every image row carries a Vizarr link, in the query above\n\n"
              "## What it cost\n"
              "Each query below ran against the buckets over HTTPS. Parquet is columnar and the buckets "
              "serve range requests, so only the column chunks a query names are fetched — not the files."),
        mo.ui.table(timings, selection=None, pagination=False),
    ])
    return


if __name__ == "__main__":
    app.run()
