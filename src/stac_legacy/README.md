# The STAC era of BioSTAC (frozen)

BioSTAC began as a [STAC](https://stacspec.org) catalog of bioimages: a root `catalog.json`, one Catalog per
resource, one Collection per study, one Item per OME-Zarr, and the Items again as stac-geoparquet. The
repository root has since moved to an RO-Crate-native layout (see the main [README](../../README.md)). This
folder keeps the STAC version as it last worked, so it can be read and rerun without digging through git.

**Not maintained.** Nothing here is imported by the notebooks at the repository root, and nothing at the
root is imported from here.

## What is here

| file | what it did |
|---|---|
| `01_basic_catalog.py` | one STAC Item per row of `samples.csv` → `catalogs/basic/` |
| `02_browse.py` | serves `catalogs/basic/` locally and opens it in STAC Browser |
| `03_extended_catalog.py` | the same Items with the `bioimage` extension, grouped in Collections → `catalogs/extended/` |
| `04_search.py` | CQL2 search over the extended catalog, locally |
| `05_api.py` | the same searches against a STAC API (stac-fastapi + pgstac, `api/docker-compose.yml`) |
| `10_bia_catalog.py` | the BIA pilot as STAC: Catalog → study Collections → Items, with study crates beside them |
| `11_parquet_build.py` | merges the Items into stac-geoparquet (`items.parquet`) per resource |
| `12_parquet_query.py` | queries that Parquet with DuckDB and with `rustac` (CQL2 without a server) |
| `13_ro_crate.py` | reads the STAC tree as RO-Crate and checks the two views agree |
| `14_idr_catalog.py` | the IDR pilot as STAC (1,898 images) |
| `15_plate_wells.py` | one stac-geoparquet row per plate well, with IDR annotations |
| `16_study_parquet.py` | `studies.parquet`, linked from each resource `catalog.json` |
| `17_search_deployed.py` | queries the deployed STAC tree over HTTPS, starting from `catalog.json` |
| `biostac_build.py`, `readable_stac_io.py` | the shared build steps and the readable JSON writer, as they were |
| `extensions/` | JSON Schemas of the `bioimage`, `idr` and `ome-ngff` STAC extensions |
| `api/` | the pgstac/stac-fastapi setup used by `05_api.py` |
| `catalogs/basic`, `catalogs/extended`, `catalogs/federated` | the small catalogs written by 01–05 |

`19_other_catalogs.py` was never committed in STAC form and is not here.

## Running it

Its dependencies are pinned in `requirements.txt` here (pystac, pystac-client, rustac, pgstac, …), which the
root no longer installs. Run from this folder, so the relative paths (`samples.csv`, `extensions/`,
`catalogs/`) resolve here and nothing at the root is overwritten:

```bash
cd stac_legacy
uv venv && uv pip install -r requirements.txt
.venv/bin/marimo edit 01_basic_catalog.py
```

The challenge notebooks (10–17) also read the challenge submodule and the build cache of the root:

```bash
ln -s ../ome2024-ngff-challenge ../build_cache .
.venv/bin/python 10_bia_catalog.py   # → stac_legacy/catalogs/challenge/bia/
```

Build order was 10, 14, 11, 15, 16. `17_search_deployed.py` reads the STAC tree that was deployed to Hugging
Face; once the buckets hold the RO-Crate layout, it no longer finds a `catalog.json`.

## Why it moved on

STAC is built around space and time. Bioimages have neither in the STAC sense: every Item sat at a
placeholder point `(0,0)` with `bbox [0,0,0,0]`, `datetime` meant "harvested", and the study-level
metadata that matters (authors, organisms, methods, publications) already came as RO-Crates. The RO-Crate
layout keeps what worked here — Parquet lists for search, studies one level deep, flat ontology ids,
`bioimage:level` — and drops the scaffolding.
