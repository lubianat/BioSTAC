import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import json
    import pathlib
    import time

    import marimo as mo
    import pystac

    import biostac_build as bb  # sets the readable StacIO, so re-saved collections stay readable
    return bb, json, mo, pathlib, pystac, time


@app.cell
def _(mo):
    mo.md(r"""
    # Collections as stac-geoparquet

    Every Collection's Items also written as one **stac-geoparquet** file, `items.parquet`, next to
    `collection.json` and linked from it as an asset. In the challenge catalog the Collections are the
    studies; each resource Catalog then links one `items.parquet` merged from its studies' files — the
    same rows, consolidated, so a query across a resource opens one file instead of one per study.

    The JSON stays canonical; the Parquet is a derived convenience layer. It makes a Collection queryable
    by anything that reads Parquet — DuckDB, pandas, R — with no STAC library and no server, and it is the
    file a federated query will reach across buckets later.

    Each file is written sorted by collection and id, and with statistics on every column, so a reader can
    skip whole row groups instead of scanning: see `write_geoparquet` in `biostac_build.py`.

    This notebook only **writes** the files. Querying them is `12_parquet_query.py`.
    """)
    return


@app.cell
def _(bb, json, pathlib, pystac, time):
    def collection_dirs():
        """Leaf Collections: the warm-up ones, and every study under a challenge resource."""
        return sorted(p.parent for p in pathlib.Path("catalogs").glob("*/*/collection.json")) + \
            sorted(p.parent for p in pathlib.Path("catalogs/challenge").glob("*/*/collection.json"))

    async def write_parquet(directory):
        """Write items.parquet for one Collection and register it as a Collection asset."""
        collection = pystac.Collection.from_file(str(directory / "collection.json"))
        # only Items: skip collection.json files and the RO-Crates shipped next to them
        candidates = {p: json.loads(p.read_text()) for p in sorted(directory.rglob("*.json"))}
        item_files = [p for p, doc in candidates.items() if doc.get("type") == "Feature"]
        items = [candidates[p] for p in item_files]
        target = directory / "items.parquet"

        started = time.perf_counter()
        # async cell: rustac needs a running loop. Sorted, with statistics: see biostac_build
        await bb.write_geoparquet(items, target)
        elapsed = time.perf_counter() - started

        bb.add_parquet_asset(collection, "items", target, "Items as stac-geoparquet")
        collection.save_object(include_self_link=False, dest_href=str(directory / "collection.json"))
        return {
            "collection": collection.id,
            "items": len(items),
            "JSON KB": round(sum(p.stat().st_size for p in item_files) / 1024, 1),
            "Parquet KB": round(target.stat().st_size / 1024, 1),
            "write s": round(elapsed, 2),
        }

    def consolidate(resource_dir):
        """A resource's items.parquet is only ever the merge of its studies' files, so the two cannot drift."""
        catalog = pystac.Catalog.from_file(str(resource_dir / "catalog.json"))
        target = bb.merge_geoparquet(f"{resource_dir}/*/items.parquet", resource_dir / "items.parquet")
        bb.link_table(catalog, "items", target, "All items of this resource, as stac-geoparquet")
        catalog.save_object(include_self_link=False, dest_href=str(resource_dir / "catalog.json"))
        return {"resource": catalog.id, "studies": len(list(resource_dir.glob("*/items.parquet"))),
                "Parquet KB": round(target.stat().st_size / 1024, 1)}
    return collection_dirs, consolidate, write_parquet


@app.cell
async def _(collection_dirs, consolidate, mo, pathlib, write_parquet):
    sizes = [await write_parquet(d) for d in collection_dirs()]
    for _row in sizes:
        _row["ratio"] = f"{_row['JSON KB'] / _row['Parquet KB']:.1f}×"
    merged = [consolidate(p.parent) for p in sorted(pathlib.Path("catalogs/challenge").glob("*/catalog.json"))]
    mo.vstack([mo.md("## What it costs"), mo.ui.table(sizes, selection=None, pagination=False),
               mo.md("## Consolidated per resource"), mo.ui.table(merged, selection=None, pagination=False)])
    return


if __name__ == "__main__":
    app.run()
