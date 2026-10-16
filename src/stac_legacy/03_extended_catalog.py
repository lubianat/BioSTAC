import marimo

app = marimo.App()


@app.cell
def _():
    import csv
    import datetime
    import json

    import marimo as mo
    import pystac
    from pystac.summaries import Summarizer
    from pystac.validation import JsonSchemaSTACValidator, set_validator

    OME_EXT = "https://example.org/stac/ome-ngff/v0.1.0/schema.json"
    SUMMARY_FIELDS = {"idr:study": "v", "license": "v", "ome:axes": "v", "ome:has_labels": "v", "ome:plate": "v",
                      **{f"ome:size_{d}": "r" for d in "xyzct"}}
    LICENSES = {"CC BY 4.0": "CC-BY-4.0", "CC BY-NC-SA 3.0": "CC-BY-NC-SA-3.0", "CC0 1.0": "CC0-1.0"}
    return LICENSES, OME_EXT, JsonSchemaSTACValidator, SUMMARY_FIELDS, Summarizer, csv, datetime, json, mo, pystac, set_validator


@app.cell
def _(mo):
    mo.md(r"""
# 3. Extended catalog

Same Items as notebook 1, plus:

- **Searchable properties** from `samples.csv`, described by an experimental `ome-ngff` extension (`extensions/ome-ngff/`)
- **One Collection per OME-NGFF version**, with summaries generated from the Items
- **A placeholder geometry** at (0,0), so the catalog can be loaded into a STAC API later (notebook 5)

Output: `catalogs/extended/`.
""")
    return


@app.cell
def _(csv):
    with open("samples.csv", newline="") as _f:
        rows = list(csv.DictReader(_f))
    return (rows,)


@app.cell
def _(LICENSES, OME_EXT, datetime, pystac):
    def as_int(v):
        return int(v) if v.strip() else None

    def make_item(row):
        href = row["File Path"].rstrip("/")
        item_id = href.split("/zarr/", 1)[1].removesuffix(".zarr").removesuffix(".ome")
        item = pystac.Item(
            id=item_id.replace("/", "-").replace(" ", "_"),
            # ponytail: placeholder at (0,0), not a location; null is valid STAC but pgstac/geoparquet require geometry
            geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            datetime=datetime.datetime.fromisoformat(row["Date added"]).replace(tzinfo=datetime.timezone.utc),
            properties={
                "license": LICENSES[row["License"]],
                "idr:study": row["Study"],
                "ome:version": row["OME-NGFF version"],
                "ome:axes": row["Axes"].strip() or None,
                **{f"ome:size_{d}": as_int(row[f"Size{d.upper()}"]) for d in "xyzct"},
                "ome:has_labels": "labels" in row["Keywords"],
                "ome:plate": bool(row["Wells"].strip()),
            },
            stac_extensions=[OME_EXT],
        )
        item.add_asset("data", pystac.Asset(href=href, media_type="application/vnd.zarr", roles=["data"]))
        item.add_asset("thumbnail", pystac.Asset(
            href=f"https://idr.openmicroscopy.org/webclient/render_thumbnail/{row['Representative Image ID']}/",
            media_type="image/jpeg", roles=["thumbnail"]))
        if "bioformats2raw.layout" in row["Keywords"]:
            item.add_asset("metadata", pystac.Asset(
                href=f"{href}/OME/METADATA.ome.xml", media_type="application/xml", roles=["metadata"]))
        return item
    return (make_item,)


@app.cell
def _(SUMMARY_FIELDS, Summarizer, make_item, pystac, rows):
    catalog = pystac.Catalog(
        id="idr-ome-zarr-extended",
        description="IDR OME-Zarr samples with an experimental ome-ngff STAC extension. One Collection per NGFF version.",
    )
    items = [make_item(r) for r in rows]

    for version in sorted({i.properties["ome:version"] for i in items}):
        members = [i for i in items if i.properties["ome:version"] == version]
        dates = sorted(i.datetime for i in members)
        collection = pystac.Collection(
            id=f"ome-ngff-v{version}",
            description=f"IDR sample images stored as OME-NGFF {version}.",
            license="various",
            extent=pystac.Extent(
                # ponytail: STAC requires a spatial extent; microscopy has none, so the same (0,0) placeholder
                pystac.SpatialExtent([[0.0, 0.0, 0.0, 0.0]]),
                pystac.TemporalExtent([[dates[0], dates[-1]]]),
            ),
            # built-in: lists for categorical fields, min/max ranges for numeric ones
            summaries=Summarizer(SUMMARY_FIELDS).summarize(members),
        )
        collection.add_items(members)
        catalog.add_child(collection)

    catalog.normalize_hrefs("catalogs/extended")
    catalog.save(pystac.CatalogType.SELF_CONTAINED)
    return catalog, items


@app.cell
def _(JsonSchemaSTACValidator, OME_EXT, catalog, json, set_validator):
    # the extension URI is not hosted: hand the local schema to the validator
    validator = JsonSchemaSTACValidator()
    with open("extensions/ome-ngff/v0.1.0/schema.json") as _f:
        validator.schema_cache[OME_EXT] = json.load(_f)
    set_validator(validator)
    n_valid = catalog.validate_all()
    return (n_valid,)


@app.cell
def _(catalog, items, json, mo, n_valid):
    mo.md(
        f"Saved **{len(items)}** items in **{len(list(catalog.get_children()))}** collections "
        f"to `catalogs/extended/` ({n_valid} validated).\n\n"
        f"```json\n{json.dumps(items[0].properties, indent=2)}\n```"
    )
    return


if __name__ == "__main__":
    app.run()
