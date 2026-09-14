# BioSTAC

A small demo of [STAC](https://stacspec.org) catalogs for bioimaging data.

STAC (SpatioTemporal Asset Catalog) is a simple JSON format for describing data files and the metadata used to find them. It comes from the Earth observation community. This repository tries it on OME-Zarr images from the [IDR OME-NGFF samples](https://idr.github.io/ome-ngff-samples/).

The notebooks go step by step, from a plain catalog to a searchable API.

## Data

`samples.csv` lists the IDR OME-Zarr samples in OME-NGFF versions 0.4 and 0.5 (33 images). Each row becomes one STAC Item.

## Setup

```bash
uv venv
uv pip install -r requirements.txt
```

The notebooks are [marimo](https://marimo.io) notebooks. Open one with:

```bash
.venv/bin/marimo edit 01_basic_catalog.py
```

## Notebooks

Run them in order: 1 and 3 write the catalogs the others read.

| Notebook | What it shows |
|---|---|
| `01_basic_catalog.py` | Builds a minimal catalog with pystac: one Item per OME-Zarr, with data, thumbnail and OME-XML assets. Writes `catalogs/basic/`. |
| `02_browse.py` | Browses that catalog: a thumbnail grid that opens images in Vizarr, and a link to view the catalog in STAC Browser. |
| `03_extended_catalog.py` | Adds searchable image properties (sizes, axes, labels, plate, study, license), one Collection per OME-NGFF version, and schema validation. Writes `catalogs/extended/`. |
| `04_search.py` | Searches the extended catalog locally with CQL2, the STAC filter language. No server needed. |
| `05_api.py` | Searches the same catalog through a real STAC API, with pystac-client and STAC Browser. |

## Serving the catalog as an API (notebook 5)

Notebook 5 needs a running STAC API. This uses [stac-fastapi-pgstac](https://github.com/stac-utils/stac-fastapi-pgstac) in Docker:

```bash
docker compose -f api/docker-compose.yml up -d   # API on http://localhost:8082
api/load.sh                                       # load catalogs/extended/ into it
```

Stop it with `docker compose -f api/docker-compose.yml down`.

Once loaded, the API can also be searched from the command line:

```bash
.venv/bin/stac-client search http://localhost:8082 \
  --filter '{"op": ">=", "args": [{"property": "ome:size_c"}, 6]}'
```

## Repository layout

```
samples.csv                     input: IDR OME-Zarr samples (v0.4, v0.5)
01_ … 05_*.py                   notebooks
catalogs/basic/                 written by notebook 1
catalogs/extended/              written by notebook 3
extensions/ome-ngff/            experimental STAC extension (schema + notes)
api/                            Docker setup and loader for the STAC API
```

## Notes on fitting microscopy into STAC

STAC was designed for geospatial data, so a few things need a workaround:

- **Geometry.** Items may have `geometry: null`, and pystac and STAC Browser accept that. The databases behind STAC APIs (pgstac, stac-geoparquet) require a geometry, though. The extended catalog places every Item at a placeholder point (0,0). It is not a location.
- **Spatial extent.** Collections must declare one. They use the same (0,0) placeholder.
- **One parent per Item.** An Item belongs to one Collection, so only one grouping can be the hierarchy. Here that is OME-NGFF version. Study is a searchable property instead.
- **Empty values.** Some images have no Z, C or T size. The local CQL2 search counts comparisons on missing values as "no match". The API leaves missing properties out of its results.
