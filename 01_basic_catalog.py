import marimo

app = marimo.App()


@app.cell
def _():
    import csv
    import datetime
    import json

    import marimo as mo
    import pystac
    return csv, datetime, json, mo, pystac


@app.cell
def _(mo):
    mo.md(r"""
# 1. Basic catalog

One STAC Item per OME-Zarr sample in `samples.csv`. Each Item has:

- an `id` built from the Zarr path, e.g. `v0.4-idr0062A-6001240`
- the date it was added
- a `data` asset pointing at the OME-Zarr on the IDR server
- a `thumbnail` asset from the IDR web client
- a `metadata` asset (`OME/METADATA.ome.xml`) when the Zarr uses the bioformats2raw layout

No geometry, no extensions. Output: `catalogs/basic/`.
""")
    return


@app.cell
def _(csv):
    with open("samples.csv", newline="") as f:
        rows = list(csv.DictReader(f))
    return (rows,)


@app.cell
def _(datetime, pystac, rows):
    catalog = pystac.Catalog(
        id="idr-ome-zarr-demo",
        description="Basic STAC catalog of IDR OME-Zarr samples. One Item per OME-Zarr.",
    )

    for row in rows:
        href = row["File Path"].rstrip("/")
        # v0.4/idr0062A/6001240.zarr -> v0.4-idr0062A-6001240 (version prefix keeps ids unique)
        item_id = href.split("/zarr/", 1)[1].removesuffix(".zarr").removesuffix(".ome")
        item_id = item_id.replace("/", "-").replace(" ", "_")
        item = pystac.Item(
            id=item_id,
            geometry=None,  # not geospatial
            bbox=None,
            datetime=datetime.datetime.fromisoformat(row["Date added"]).replace(tzinfo=datetime.timezone.utc),
            properties={},
        )
        item.add_asset("data", pystac.Asset(href=href, media_type="application/vnd.zarr", roles=["data"]))
        item.add_asset("thumbnail", pystac.Asset(
            href=f"https://idr.openmicroscopy.org/webclient/render_thumbnail/{row['Representative Image ID']}/",
            media_type="image/jpeg", roles=["thumbnail"]))
        if "bioformats2raw.layout" in row["Keywords"]:
            item.add_asset("metadata", pystac.Asset(
                href=f"{href}/OME/METADATA.ome.xml", media_type="application/xml", roles=["metadata"]))
        catalog.add_item(item)

    catalog.normalize_hrefs("catalogs/basic")
    catalog.save(pystac.CatalogType.SELF_CONTAINED)
    return (catalog,)


@app.cell
def _(catalog, json, mo):
    items = list(catalog.get_items())
    mo.md(
        f"Saved **{len(items)}** items to `catalogs/basic/catalog.json`.\n\n"
        f"```json\n{json.dumps(items[0].to_dict(), indent=2)}\n```"
    )
    return


if __name__ == "__main__":
    app.run()
