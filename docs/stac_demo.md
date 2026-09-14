# Barebones STAC catalog for IDR OME-Zarr samples (marimo)

## Context
Demo: a minimal STAC Catalog where each OME-Zarr sample is one Item. No extensions, no extra metadata.

## Files
- `samples.csv`: the CSV from the prompt, pasted as-is.
- `stac_demo.py`: marimo notebook.
- `docs/stac_demo.md`: this plan, copied as design notes. It also covers why the catalog is `SELF_CONTAINED`: CatalogType only changes the links between STAC JSON files, and asset hrefs stay absolute IDR URLs.

## Notebook cells
1. `import marimo as mo, csv, pystac, datetime`
2. Read `samples.csv` with `csv.DictReader`.
3. Build `pystac.Catalog(id="idr-ome-zarr-demo", description=...)`.
   For each row, create a `pystac.Item`:
   - `id`: path after `/zarr/`, with `/` swapped for `-` and `.zarr`/`.ome.zarr` stripped. Example: `v0.4-idr0062A-6001240`. The version prefix is needed because the same image appears under several versions.
   - `geometry=None`, `bbox=None`. Allowed for non-geospatial items.
   - `datetime` = "Date added"
   - `properties={}`
   - one asset `"data"`: href = File Path, `media_type="application/vnd.zarr"`, `roles=["data"]`
4. `catalog.normalize_hrefs("catalog")` + `catalog.save(pystac.CatalogType.SELF_CONTAINED)`
5. `mo.md` showing the item count, plus `catalog.describe()` or a JSON preview of one item.

## Dependency
`pystac` (plus `marimo`). If pystac isn't installed, `pip install pystac`.

## Verification
`python stac_demo.py` (or `marimo run`) writes `catalog/catalog.json` plus 100 item JSONs. Run `pystac.Catalog.from_file("catalog/catalog.json").validate_all()` as the check. It needs `jsonschema`, so skip it if that isn't installed.

## Update: extra assets
Each Item now also has:
- `thumbnail`: `https://idr.openmicroscopy.org/webclient/render_thumbnail/<Representative Image ID>/`. This is how the IDR samples page builds thumbnails; the CSV `Thumbnail` column is not used.
- `metadata` (only when Keywords contain `bioformats2raw.layout`): `<File Path>/OME/METADATA.ome.xml`.

## Usage notebook: `stac_usage.py`
- **pystac browse:** loads `catalog/catalog.json` and shows a thumbnail grid filtered by NGFF version. Each thumbnail opens the Zarr in Vizarr, and there's an OME-XML link where one exists.
- **STAC Browser:** serves the project dir on `localhost:8000` with CORS headers, then links to `https://radiantearth.github.io/stac-browser/#/external/http://localhost:8000/catalog/catalog.json`.

Run `bio_stac_demo.py` first to generate `catalog/`, then `.venv/bin/marimo edit stac_usage.py`.
