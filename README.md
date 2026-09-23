# BioSTAC

A small demo of [STAC](https://stacspec.org) catalogs for bioimaging data.

STAC (SpatioTemporal Asset Catalog) is a simple JSON format for describing data files and the metadata used
to find them. It comes from the Earth observation community. This repository tries it on OME-Zarr images,
first on a handful of [IDR samples](https://idr.github.io/ome-ngff-samples/), then on the
[OME 2024 NGFF challenge](https://ome.github.io/ome2024-ngff-challenge/) submissions.

Nothing here copies pixel data. Every Item points at the original OME-Zarr where it already lives.

## Setup

```bash
uv venv
uv pip install -r requirements.txt
git submodule update --init      # the challenge repository, read in place
```

The notebooks are [marimo](https://marimo.io) notebooks:

```bash
.venv/bin/marimo edit 01_basic_catalog.py
```

## The warm-up

`samples.csv` lists 33 IDR OME-Zarr samples, versions 0.4 and 0.5. Each row becomes one Item.

| Notebook | What it shows |
|---|---|
| `01_basic_catalog.py` | A minimal catalog: one Item per OME-Zarr, with data, thumbnail and OME-XML assets. |
| `02_browse.py` | Browsing it: a thumbnail grid that opens images in Vizarr, and a link to STAC Browser. |
| `03_extended_catalog.py` | Searchable properties, one Collection per OME-NGFF version, schema validation. |
| `04_search.py` | Searching it locally with CQL2, the STAC filter language. No server. |
| `05_api.py` | Searching the same catalog through a real STAC API. |

Notebook 5 needs that API running:

```bash
docker compose -f api/docker-compose.yml up -d   # http://localhost:8082
api/load.sh                                       # load catalogs/extended/ into it
```

## The pilot: the OME 2024 NGFF challenge

The pilot builds one catalog over the challenge submissions, with a Collection per contributing resource,
so that the resources can live in separate buckets and still be searched together.

```bash
.venv/bin/marimo edit 10_bia_catalog.py     # BIA / EMBL-EBI, 10 images
.venv/bin/marimo edit 14_idr_catalog.py     # IDR, 1,898 images and plates
```

Both builds read the challenge's own sample lists, fetch each image's `zarr.json` and RO-Crate for the
OME-NGFF version, axes, specimen and imaging method, and cache everything under `build_cache/` so re-runs
are offline. Items carry the experimental [`bioimage` extension](extensions/bioimage/). Items are grouped
by study, and where [GIDE](https://github.com/foundingGIDE/gide-data-deliverable) or
[IDR](https://github.com/German-BioImaging/idr_study_crates) publish a study RO-Crate, the study takes its
title, authors, license and thumbnail from it — and **ships that crate** beside its `collection.json`.

`catalogs/challenge/idr/` is not in git: 146 MB, built locally in about a minute from a warm cache.

### Readable as STAC or as RO-Crate

```bash
.venv/bin/marimo edit 13_ro_crate.py
```

Every Item has an **RO-Crate twin** next to it, describing the same image: its remote parts, its taxon and
imaging method, its license, the study it belongs to. The Item links to the crate with `rel: alternate`,
the crate points back with `seeAlso`, and the crates nest the way the Collections do — a study crate lists
each image folder as a nested crate, each image crate points at its parent.

```
catalogs/challenge/catalog.json
└─ bia/collection.json                          the resource (+ items.parquet, studies.parquet)
   └─ S-BIAD963/
      ├─ collection.json                        a study, as STAC
      ├─ ro-crate-metadata.json                 the same study, as RO-Crate
      └─ bia-mouse-cns-mesospim/
         ├─ bia-mouse-cns-mesospim.json         an image, as STAC
         ├─ ro-crate-metadata.json              the same image, as RO-Crate
         └─ thumbnail.png
```

The whole tree passes the REQUIRED checks of the RO-Crate 1.2 profile, and the notebook checks that the
two views agree on title, license, taxon, imaging method and data location for every image.

### Four levels, four tables

Each Collection also gets a [stac-geoparquet](https://github.com/stac-utils/stac-geoparquet) file, linked
from its `collection.json`. The JSON stays canonical; the Parquet makes a Collection queryable with no STAC
library and no server, and it is what a federated query reads across buckets.

```bash
.venv/bin/marimo edit 11_parquet_build.py   # items.parquet per Collection
.venv/bin/marimo edit 12_parquet_query.py   # queries them with DuckDB and rustac
.venv/bin/marimo edit 15_plate_wells.py     # wells.parquet: 139,286 wells of the 635 plates
.venv/bin/marimo edit 16_study_parquet.py   # studies.parquet: one row per study, from its crate
```

Every row says what it is in `bioimage:level` — `image`, `plate` or `well` — so all of them can be searched
together and told apart afterwards.

**A plate is one Item, and its wells are rows.** IDR's screen annotations are keyed by plate and well, and
the field images of a well share them, so the well is the smallest unit that carries anything to search.
Each well row adds a curated part of those annotations, the [`idr:` extension](extensions/idr/): gene,
siRNA, compound, cell line, control type, phenotypes. IDR's tables are not republished.

This is what makes IDR-style search work on the catalog. `idr:gene_symbol = 'PAU8'` returns idr0004 plate
P101 well A2 — the same hit IDR's own search gives.

### Searching what is actually published

```bash
.venv/bin/marimo edit 17_search_deployed.py
```

The closing notebook knows one thing, the URL of the deployed root catalog, and discovers the rest: it
crawls the federation with pystac, takes the Parquet hrefs from the catalog itself, and queries them over
HTTPS with DuckDB. Nothing local is read. The buckets serve range requests, so a query fetches only the
column chunks it names.

Its queries are grouped by how many files each one needs, because that is the point of a federated catalog:
the gene search reads one file, the plate-to-well join reads two, the count by level reads them all, and
the study join reaches four files in two buckets. Six queries, about 15 seconds over the network.

### Browsing it

```bash
cd browser && npm install && npm run dev
```

`browser/` is the challenge's own gallery, forked from [zowser](https://github.com/lubianat/zowser) and
rewired to read this catalog: its `config.yaml` names the root URL, and it follows that to each
Collection's `items.parquet`. No Zarr is opened — the rows already carry shape, organism, imaging method,
size and a thumbnail, so 1,908 images and plates arrive in a handful of requests, where the upstream
gallery fetched a `zarr.json` per image. See [browser/README.md](browser/README.md).

## Repository layout

```
samples.csv                     input: IDR OME-Zarr samples (v0.4, v0.5)
01_ … 05_*.py                   notebooks (IDR samples warm-up)
10_bia_catalog.py               pilot: BIA source
14_idr_catalog.py               pilot: IDR source
15_plate_wells.py               plate wells as Parquet rows, annotated from IDR
16_study_parquet.py             studies as a table, from the Collections and their crates
17_search_deployed.py           queries the published catalog from its root URL
11_parquet_build.py             writes stac-geoparquet per collection
12_parquet_query.py             queries it with DuckDB and rustac
13_ro_crate.py                  reads the same tree as RO-Crate; checks the two views agree
biostac_build.py                build steps shared by the BIA and IDR notebooks
readable_stac_io.py             writes STAC JSON with short objects on one line
extensions/                     experimental STAC extensions: ome-ngff, bioimage, idr
catalogs/                       basic/ and extended/ (warm-up), challenge/ (pilot)
browser/                        the challenge gallery, reading this catalog's Parquet
api/                            Docker setup and loader for the STAC API
ome2024-ngff-challenge/         submodule: the challenge repo and its sample lists
build_cache/                    cached zarr.json / RO-Crate / OLS4 responses
```

[AGENTS.md](AGENTS.md) has the operational detail: build costs, the conventions the catalog relies on,
and the mistakes already made.

## Notes on fitting microscopy into STAC

STAC was designed for geospatial data, so a few things need a workaround:

- **Geometry.** Items may have `geometry: null`, and pystac and STAC Browser accept that, but the databases
  behind STAC APIs require one. Every Item sits at a placeholder point (0,0). It is not a location.
- **Spatial extent.** Collections must declare one. They use the same placeholder.
- **One parent per Item.** An Item belongs to one Collection, so only one grouping can be the hierarchy.
  Here that is the study. Everything else is a searchable property.
- **Empty values.** Some images have no Z, C or T size. A local CQL2 search counts comparisons on missing
  values as "no match"; the API leaves missing properties out of its results.

Two things the sources themselves taught us, kept here because they are about the data and not about this
repository: OME-NGFF's `field_count` is the *maximum* number of fields in any well of a plate, not the
count in each; and ontology terms are only as good as the submission — one challenge image is tagged
*Pongo abelii* where *Homo sapiens* is meant.
