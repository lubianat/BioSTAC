import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import json
    import pathlib
    import time

    import marimo as mo
    import pystac
    import rustac

    from readable_stac_io import ReadableStacIO

    pystac.StacIO.set_default(ReadableStacIO)  # keep re-saved collections human-readable
    return json, mo, pathlib, pystac, rustac, time


@app.cell
def _(mo):
    mo.md(r"""
    # Collections as stac-geoparquet

    Every Collection's Items also written as one **stac-geoparquet** file, `items.parquet`, next to
    `collection.json` and linked from it as an asset.

    The JSON stays canonical; the Parquet is a derived convenience layer. It makes a Collection queryable
    by anything that reads Parquet — DuckDB, pandas, R — with no STAC library and no server, and it is the
    file a federated query will reach across buckets later.

    This notebook only **writes** the files. Querying them is `12_parquet_query.py`.
    """)
    return


@app.cell
def _(json, pathlib, pystac, rustac, time):
    def collection_dirs():
        return sorted(p.parent for p in pathlib.Path("catalogs").glob("*/*/collection.json"))

    async def write_parquet(directory):
        """Write items.parquet for one Collection and register it as a Collection asset."""
        collection = pystac.Collection.from_file(str(directory / "collection.json"))
        # items may sit one level down (IDR demo) or under study sub-collections (challenge)
        # only Items: skip collection.json files and the study RO-Crates shipped next to them
        candidates = {p: json.loads(p.read_text()) for p in sorted(directory.rglob("*.json"))}
        item_files = [p for p, doc in candidates.items() if doc.get("type") == "Feature"]
        items = [candidates[p] for p in item_files]
        target = directory / "items.parquet"

        started = time.perf_counter()
        await rustac.write(str(target), items)  # async cell: rustac needs a running loop
        elapsed = time.perf_counter() - started

        collection.add_asset("items", pystac.Asset(
            href="./items.parquet",
            media_type="application/vnd.apache.parquet",
            roles=["data"],
            title="Items as stac-geoparquet",
        ))
        collection.save_object(include_self_link=False, dest_href=str(directory / "collection.json"))
        return {
            "collection": collection.id,
            "items": len(items),
            "JSON files": len(list(directory.rglob("*.json"))),
            "JSON KB": round(sum(p.stat().st_size for p in item_files) / 1024, 1),
            "Parquet KB": round(target.stat().st_size / 1024, 1),
            "write s": round(elapsed, 2),
        }
    return collection_dirs, write_parquet


@app.cell
async def _(collection_dirs, mo, write_parquet):
    sizes = [await write_parquet(d) for d in collection_dirs()]
    for _row in sizes:
        _row["ratio"] = f"{_row['JSON KB'] / _row['Parquet KB']:.1f}×"
    mo.vstack([mo.md("## What it costs"), mo.ui.table(sizes, selection=None, pagination=False)])
    return


if __name__ == "__main__":
    app.run()
