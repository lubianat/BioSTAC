import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import time

    import duckdb
    import marimo as mo
    import rustac
    return duckdb, mo, rustac, time


@app.cell
def _(mo):
    mo.md(r"""
    # Querying the Collections as Parquet

    The `items.parquet` files written by `11_parquet_build.py`, queried two ways: with DuckDB (plain SQL,
    no STAC library) and with `rustac` (STAC API CQL2 filters, no server). Run the build notebook first.
    """)
    return


@app.cell
def _(duckdb, mo, time):
    def sql(query):
        started = time.perf_counter()
        result = duckdb.sql(query)
        rows = [dict(zip([c for c in result.columns], r)) for r in result.fetchall()]
        return rows, round((time.perf_counter() - started) * 1000, 1)

    def show(title, query):
        rows, ms = sql(query)
        return mo.vstack([
            mo.md(f"**{title}** — {len(rows)} rows in {ms} ms"),
            mo.md(f"```sql\n{query.strip()}\n```"),
            mo.ui.table(rows, selection=None, pagination=False),
        ])
    return (show,)


@app.cell
def _(mo, show):
    BIA = "'catalogs/challenge/bia/items.parquet'"
    mo.vstack([
        mo.md("## Querying with DuckDB — no STAC library involved\n"
              "Property names contain `:`, so they need double quotes; nested fields use dot access."),
        show("Deep stacks", f'''
SELECT id, "bioimage:organism".term_label AS organism, "bioimage:size_z" AS z
FROM {BIA}
WHERE "bioimage:size_z" > 100
ORDER BY z DESC
'''),
        show("Imaging methods across the collection (an aggregate, cheap here, expensive over JSON)", f'''
SELECT "bioimage:imaging_method".term_label AS method,
       count(*) AS images,
       round(sum("bioimage:size_bytes") / 1e6, 1) AS total_MB
FROM {BIA}
GROUP BY 1
ORDER BY images DESC
'''),
    ])
    return


@app.cell
def _(mo, show):
    # the shape a federated query takes: one statement over several files, later several bucket URLs
    mo.vstack([
        mo.md("## One query across Collections\n"
              "`union_by_name` lets Collections with different extensions sit in the same result set. "
              "Swap the paths for `https://…` URLs and this is the federated query."),
        show("Largest image per collection", '''
SELECT collection,
       count(*) AS items,
       round(max("bioimage:size_bytes") / 1e6, 1) AS largest_MB
FROM read_parquet([
        'catalogs/challenge/bia/items.parquet',
        'catalogs/extended/ome-ngff-v0.4/items.parquet',
        'catalogs/extended/ome-ngff-v0.5/items.parquet'
     ], union_by_name := true)
GROUP BY 1
ORDER BY items DESC
'''),
    ])
    return


@app.cell
async def _(mo, rustac, time):
    async def cql2(path, filter_text):
        started = time.perf_counter()
        found = await rustac.search(path, filter=filter_text)
        return [f["id"] for f in found], round((time.perf_counter() - started) * 1000, 1)

    queries = [
        '"bioimage:size_z" > 100',
        '"bioimage:source" = \'bia\'',
        '"bioimage:organism.term_id" = \'NCBITaxon:9606\'',
    ]
    results = []
    for _q in queries:
        _ids, _ms = await cql2("catalogs/challenge/bia/items.parquet", _q)
        results.append({"CQL2": _q, "ids": ", ".join(_ids) or "—", "ms": _ms})
    mo.vstack([
        mo.md("## The same CQL2 as the API, straight against the file\n"
              "`rustac` runs STAC API filter syntax over stac-geoparquet with no server."),
        mo.ui.table(results, selection=None, pagination=False),
        mo.callout(
            "Finding: rustac matches flat properties but returns **no rows, without an error**, for nested "
            "ones such as `bioimage:organism.term_id` — the same filter that works against pgstac and in "
            "`cql2` locally. Use DuckDB for nested fields, or keep searchable values flat.",
            kind="warn",
        ),
    ])
    return


if __name__ == "__main__":
    app.run()
