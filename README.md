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

## Challenge pilot: federated catalog over the OME 2024 NGFF challenge

The notebooks above are the warm-up on IDR samples. The pilot proper builds a catalog over the
[OME 2024 NGFF challenge](https://ome.github.io/ome2024-ngff-challenge/) submissions, one Collection per
contributing resource, with the aim of federating them across separately hosted buckets later.

The challenge repository is pinned as a submodule, so its sample lists are read in place and never copied:

```bash
git submodule update --init
```

**First source: BIA / EMBL-EBI, 10 images.**

```bash
.venv/bin/marimo edit 10_bia_catalog.py     # writes catalogs/challenge/bia/
```

For each row of `samples/ebi-ngff-challenge-samples.csv` the build fetches the image's `zarr.json` (OME-NGFF
version, axes) and `ro-crate-metadata.json` (specimen, imaging method) from the EBI server, caching both under
`build_cache/` so re-runs are offline. Ontology labels come from [EBI OLS4](https://www.ebi.ac.uk/ols4).
Items carry the experimental [`bioimage` extension](extensions/bioimage/), and the pixel data is untouched:
the `data` asset points at the original `.zarr` on EBI infrastructure.

Items are grouped by study. Each study is a sub-Collection named by its accession, and where
[GIDE](https://github.com/foundingGIDE/gide-data-deliverable) publishes a study-level RO-Crate, the study
takes its title, description, keywords, license, publication date and thumbnail from it. The crate itself
is **shipped with the catalog** next to the study's `collection.json` as a collection-level `ro-crate`
asset, with a `via` link back to the GIDE source.

Every Item also has an **RO-Crate twin**: `ro-crate-metadata.json` next to the Item JSON, playing the role
the STAC Item plays. It describes one image and lists its remote parts (the OME-Zarr, its `zarr.json`, the
image's own challenge crate), its taxon and imaging method, its license and the study it belongs to. The
Item links to it with `rel: alternate`, and the crate points back to the Item with `seeAlso`. So the whole
tree can be read as STAC or as RO-Crate, at every level.

The crates also link to each other, mirroring the STAC tree, with relative paths only:

- **Down:** the study crate lists each image folder in its `hasPart` as a nested crate:
  `{"@id": "bia-mouse-cns-mesospim/", "@type": "Dataset", "conformsTo": {"@id": "https://w3id.org/ro/crate"},
  "subjectOf": {"@id": "bia-mouse-cns-mesospim/ro-crate-metadata.json"}}`. This is RO-Crate 1.2's
  "Referencing other RO-Crates" pattern.
- **Up:** each image crate has `isPartOf: {"@id": "../"}`, where `../` is a `CreativeWork` with
  `subjectOf: ../ro-crate-metadata.json`. It is not a `Dataset`, because a parent is not a data entity of
  the image crate (the validator would then require it in the image crate's `hasPart`). The spec defines no
  parent link, so this one is our convention.
- Images in the five studies without a GIDE crate keep `isPartOf` pointing at the study web page.

Relative folder ids were chosen over absolute ones on purpose: the BioStudies URLs are not spelled
consistently (`…/bioimages/…` and `…/BioImages/…` both appear), so matching on them breaks silently.
Relative links also survive moving the catalog to another bucket.

```
catalogs/challenge/catalog.json
└─ bia/collection.json                          the resource (+ items.parquet)
   └─ S-BIAD963/
      ├─ collection.json                        a study (STAC)
      ├─ ro-crate-metadata.json                 the same study as RO-Crate (GIDE); hasPart → image crates
      └─ bia-mouse-cns-mesospim/
         ├─ bia-mouse-cns-mesospim.json         an image (STAC Item)
         ├─ ro-crate-metadata.json              the same image as RO-Crate; isPartOf → ../
         └─ thumbnail.png
```

### Valid as both STAC and RO-Crate

```bash
.venv/bin/marimo edit 13_ro_crate.py
```

The notebook reads the tree with RO-Crate tooling only ([ro-crate-py](https://github.com/ResearchObject/ro-crate-py)),
walking from the study crates down to the image crates, then validates the same tree as STAC and checks that,
for every image, the STAC Item and its crate agree on title, license, taxon, imaging method and data location.
It also links every crate into the [RO-Crate Explorer](https://arunaengine.github.io/ro-crate-explorer/),
served from `localhost:8000`, where the nested image crates open as sub-crates.

All 15 crates (5 study, 10 image) pass every REQUIRED check of the RO-Crate 1.2 profile of
[rocrate-validator](https://github.com/crs4/rocrate-validator). The check is slow, so it is not in the notebook:

```bash
uv run --with roc-validator rocrate-validator validate --profile-identifier ro-crate-1.2 \
  --requirement-severity REQUIRED catalogs/challenge/bia/S-BIAD963
```

Getting there took four changes, each forced by the validator:

- **`@context`.** Every crate uses `["https://w3id.org/ro/crate/1.2/context", {…}]`, with only the GIDE term
  definitions that crate uses inlined from GIDE's published context. GIDE's context URL cannot be used: on
  its own, the crate fails the rule that the RO-Crate context URL must be listed; next to the RO-Crate URL,
  rdflib (which the validator uses) fails with "recursive context inclusion", because GIDE's context itself
  imports the RO-Crate one.
- **Study crates are attached.** GIDE's root `@id` is the BioStudies URL, which makes a crate "detached", and a
  detached crate cannot hold local entities such as the nested image folders. Shipped in a folder, the root
  is `./`; the BioStudies URL is kept as `url`, and GIDE's `identifier` (the accession) is untouched. Apart
  from that rename, every one of GIDE's triples is kept (checked with pyld), plus 8 new triples per study for
  the links down. The shipped crates are 0.5–2.7 KB smaller than GIDE's originals.
- **The Zarr is a folder.** Its id in the image crate ends in `/` (`….zarr/`), as RO-Crate expects for a
  `Dataset`; ro-crate-py adds the slash anyway, so without it the two views seemed to disagree.
- **Local files are references.** `thumbnailUrl` is `{"@id": "thumbnail.png"}`, not a plain string.

Image crates are about 3 KB each.

**Thumbnails.** The challenge has no thumbnail files: its site renders each image in the browser from the
lowest-resolution pyramid level. The build does the same once, with `zarr` + Pillow: first timepoint, middle
Z plane, active OMERO channels in their colours and windows, auto-contrast when a window shows nothing. The
PNG ships next to each Item as its `thumbnail` asset, and is listed in the item crate. A study Collection
uses GIDE's study thumbnail when there is one, otherwise its first image's.

Study metadata lives only at the study level, so it is not repeated per Item or in `items.parquet`, which
keeps one row per image with the study id in its `collection` column.

Both existing viewers work on it:

```bash
.venv/bin/marimo edit 04_search.py          # pick "NGFF challenge (BIA)" in the catalog dropdown
api/load.sh catalogs/challenge              # or load it into the STAC API
```

Example searches, identical locally and through the API:

```
"bioimage:organism.term_id" = 'NCBITaxon:9606'          → 1 image
"bioimage:imaging_method.term_label" LIKE '%electron%'  → 3 images
"bioimage:size_z" > 100                                 → 6 images
```

### Parquet: each Collection as one queryable file

```bash
.venv/bin/marimo edit 11_parquet_build.py    # writes items.parquet next to every collection.json
.venv/bin/marimo edit 12_parquet_query.py    # queries them with DuckDB and rustac
```

Each Collection also gets a [stac-geoparquet](https://github.com/stac-utils/stac-geoparquet) file, linked
from `collection.json` as an `items` asset. The JSON stays canonical; the Parquet is a derived layer that
makes a Collection queryable with no STAC library and no server, and it is what a federated query will read
across buckets later.

| Collection | Items | JSON | Parquet | Ratio |
|---|---|---|---|---|
| `challenge/bia` | 10 | 31.3 KB in 11 files | 21.8 KB in 1 file | 1.4× |
| `extended/ome-ngff-v0.4` | 23 | 32.3 KB in 24 files | 14.6 KB in 1 file | 2.2× |
| `extended/ome-ngff-v0.5` | 10 | 14.7 KB in 11 files | 14.4 KB in 1 file | 1.0× |

At this size the byte savings are beside the point: the win is **one request instead of one per item**, plus
aggregates. Queries run in single-digit milliseconds, e.g. images grouped by imaging method with their total
size, or one statement across all three Collections using `read_parquet([...], union_by_name := true)` —
swap those paths for `https://` URLs and the same statement is the federated query.

So the same Items are now queryable three ways: crawling the JSON (`04_search.py`), the Parquet file
(`12_parquet_query.py`), and the STAC API (`05_api.py`). CQL2 text is identical across the API, the local `cql2`
search and `rustac`.

**Finding:** `rustac` matches flat properties over Parquet but returns **no rows and no error** for nested
ones such as `bioimage:organism.term_id`, which the pgstac API and the local `cql2` search both handle.
DuckDB handles nested fields fine (`"bioimage:organism".term_label`). Keep values that must be searchable
flat, or query nested ones with DuckDB.

### Findings from the BIA harvest

- All 10 images resolved: `zarr.json`, `ro-crate-metadata.json` and the study `via` links returned 200,
  and the EBI server sends permissive CORS headers, so browser clients can read them directly.
- All are OME-NGFF 0.5, and every image has both a specimen taxon and an imaging method term.
- One metadata error: the "HeLa cells" image is tagged `NCBI:txid9601` (*Pongo abelii*) where
  *Homo sapiens* (`9606`) is meant. Ontology terms are only as good as the submission.
- OLS4 dropped ~3 of 20 lookups on the first pass, so the build retries once. Labels resolve for all terms.
- The CSV's `shape` column is positional and only meaningful next to the axes from `zarr.json`; the two must
  be read together.
- Only 5 of the 10 studies have a GIDE study crate (S-BIAD606, S-BIAD963, S-BIAD1083, EMPIAR-10310,
  EMPIAR-10442). S-BIAD144, S-BIAD464, S-BIAD501, EMPIAR-10392 and EMPIAR-11830 have none, so their study
  Collections are titled from the image and carry no study description.
- Each study contributes a single image here, so the study level adds structure but no grouping yet. It
  starts to pay off with sources such as IDR, where one study has hundreds of images.
- The GIDE search context (`https://www.gide-project.org/ro-crate/search/1.0/context`) cannot be used by
  URL in a crate that passes RO-Crate tooling: it imports the RO-Crate 1.2 context itself, so listing both
  makes rdflib fail with "recursive context inclusion", and listing it alone drops the required RO-Crate
  context URL. If GIDE's context stopped importing RO-Crate's, crates could list both URLs. It also declares
  its own `@id` as `https://gide-search/1.0/context`, not its URL, and is served as `application/json` rather
  than `application/ld+json`. The GIDE crates inline `seeAlso` as `rdf:seeAlso` where the context says
  `rdfs:seeAlso`. None of the shipped crates uses `seeAlso`, so nothing changes here, but the two should agree.
- One image (mouse CNS, mesoSPIM) renders black with its own OMERO window; it needs auto-contrast, as the
  challenge site's `autoBoost` does.

Still to do: the other six sources, and hosting each resource in its own bucket so the federation is
structural rather than a folder convention.

## Repository layout

```
samples.csv                     input: IDR OME-Zarr samples (v0.4, v0.5)
01_ … 05_*.py                   notebooks (IDR samples warm-up)
10_bia_catalog.py               challenge pilot: BIA source
readable_stac_io.py             writes STAC JSON with short objects on one line
11_parquet_build.py             writes stac-geoparquet per collection
12_parquet_query.py             queries it with DuckDB and rustac
13_ro_crate.py                  reads the same tree as RO-Crate; checks STAC and RO-Crate agree
catalogs/basic/                 written by notebook 1
catalogs/extended/              written by notebook 3
extensions/ome-ngff/            experimental STAC extension for the IDR demo
extensions/bioimage/            experimental STAC extension for the challenge pilot
catalogs/challenge/bia/         written by 10_bia_catalog.py
ome2024-ngff-challenge/         submodule: the challenge repo and its sample lists
build_cache/                    cached zarr.json / RO-Crate / OLS4 responses
api/                            Docker setup and loader for the STAC API
```

## Notes on fitting microscopy into STAC

STAC was designed for geospatial data, so a few things need a workaround:

- **Geometry.** Items may have `geometry: null`, and pystac and STAC Browser accept that. The databases behind STAC APIs (pgstac, stac-geoparquet) require a geometry, though. The extended catalog places every Item at a placeholder point (0,0). It is not a location.
- **Spatial extent.** Collections must declare one. They use the same (0,0) placeholder.
- **One parent per Item.** An Item belongs to one Collection, so only one grouping can be the hierarchy. Here that is OME-NGFF version. Study is a searchable property instead.
- **Empty values.** Some images have no Z, C or T size. The local CQL2 search counts comparisons on missing values as "no match". The API leaves missing properties out of its results.
