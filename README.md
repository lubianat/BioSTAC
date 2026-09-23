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

### Second source: IDR, 1,898 images

```bash
.venv/bin/marimo edit 14_idr_catalog.py     # writes catalogs/challenge/idr/ (not in git)
.venv/bin/python 11_parquet_build.py        # adds idr/items.parquet
```

Built like BIA, from the shared steps in `biostac_build.py`: one STAC Item per OME-Zarr, each with an
RO-Crate twin, grouped into one Collection per IDR study, with that study's RO-Crate from
[idr_study_crates](https://github.com/German-BioImaging/idr_study_crates) shipped next to it. All 14
studies have one.

The scope is the 14 study CSVs listed in the challenge's `samples/idr_samples.csv`. The IDR rows of
`other_samples.csv` (test exports named "dataset name") and four CSVs the index does not list (idr0013,
idr0016, idr0025, idr0044) are left out.

What differs from BIA:

- **Three Zarr layouts**: 635 HCS plates, 121 bioformats2raw images (the image is under `0/`), and 1,142
  plain images. **A plate is one Item**, as the challenge lists them, with `bioimage:plate`,
  `bioimage:wells` and `bioimage:fields`; its size fields describe one field image. The plate's RO-Crate
  mirrors the Zarr down to the wells: the OME-Zarr Dataset lists every well (`…/P144.ome.zarr/E/3/`) as a
  remote part, taken from the plate's own `zarr.json`.
- **Thumbnails**: 136 images link IDR's own thumbnail, where the challenge points at an IDR image; the other
  1,762 are rendered from the lowest pyramid level, as for BIA.
- **Terms**: organism and imaging method come from the CSV, or from the study crate when the CSV has none
  (82 idr0015 plates).
- **Study crates**: IDR's name their metadata descriptor `idr0004-ro-crate-metadata.json`; RO-Crate 1.2
  requires `ro-crate-metadata.json`, so the shipped copy renames it. As with GIDE's, the root becomes `./`
  and the IDR study URL is kept as `url`.

Size and cost of the build: 1,898 Items, 5,588 files, 146 MB (thumbnails 84 MB, item crates 56 MB, STAC JSON
6 MB); `items.parquet` is 108 KB. The first run fetched ~10k small files from EBI in 15 minutes with 8
threads; rebuilds from `build_cache/` (112 MB) take under a minute. That is why `catalogs/challenge/idr/` is
not in git: build it locally. The root `catalogs/challenge/catalog.json` lists both resources.

`IDR_SAMPLE=2 .venv/bin/python 14_idr_catalog.py` keeps the first 2 images per study, for a quick try.

A study crate and one image crate from each of the 14 studies pass the RO-Crate 1.2 REQUIRED checks.

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

### Below a plate: wells, annotated from IDR

```bash
.venv/bin/marimo edit 15_plate_wells.py     # writes catalogs/challenge/idr/wells.parquet
```

A plate is one STAC Item, and its **wells** are indexed as rows in `wells.parquet`: **139,286 wells** of the
635 plates, 1.5 MB, sorted by study, plate and well. The individual field images are deliberately not
indexed, for two reasons:

- **Metadata lives at well level.** IDR's screen annotations are keyed `Plate, Well`; the several field
  images of a well share one gene or compound. A well is the smallest unit that carries anything to search.
- **Fields cannot be listed without a request per well.** OME-NGFF defines `field_count` as the *maximum*
  number of fields per well, and idr0011 wells hold fewer, so deriving field paths from it invents URLs that
  404. To list a well's images, read that well's own `zarr.json` — one request, on demand, and each row links
  it as its `zarr-metadata` asset.

Each row carries the plate's properties plus a curated set of IDR's annotations, the
[`idr:` extension](extensions/idr/): gene symbol and identifier, siRNA, compound, organism and cell line with
their ontology ids, control type and phenotypes. The eight annotated studies use 172 distinct column names
between them, so only the shared, searchable ones are carried; **IDR's tables are not republished**, and the
annotation files are read from `IDR/idr-metadata` (and the per-study repos of idr0012, idr0033 and idr0090)
into `build_cache/` alone.

Coverage: every well of the eight annotated studies joins (idr0004 3,679, idr0010 56,448, idr0011 7,800 using
all five of its screens, idr0012 22,847, idr0033 4,608, idr0035 3,300, idr0036 7,680, idr0090 544). idr0015
has no annotation file, so its 32,380 wells carry none.

This is what makes IDR-style search possible on the catalog. `idr:gene_symbol = 'PAU8'` returns
idr0004 plate P101 well A2 (gene YAL068C), the same hit IDR's own search gives for that gene in that study:

```sql
SELECT collection, "idr:plate_name", "idr:well", assets.data.href
FROM 'catalogs/challenge/idr/wells.parquet'
WHERE "idr:gene_symbol" = 'PAU8'
```

### Findings from the IDR harvest

- OME-NGFF's `field_count` is the **maximum** fields per well, not the count in every well: in idr0011, 114
  of 546 sampled wells hold fewer. The challenge CSV's `images` column is just wells × `field_count`, so it
  cannot detect this either. Plate Items therefore carry `bioimage:field_count_max`, named for what it is.
- 4 of 1,905 sampled wells are listed in IDR's plate metadata but return 404 on the server.
- Four rows write `shape` as a bracketed list, `"[1, 1, 2, 520, 696]"`, where every other row uses
  `"1,1,1,520,696"` (idr0010 47-35, 69-49 and 96-14, and one idr0015 plate).
- Licenses disagree between the CSV and the study crate: idr0004 is CC BY 4.0 in the CSV but CC BY-NC-SA 3.0
  in its study crate; idr0036 is CC BY 4.0 versus CC0 1.0. Items keep the CSV's license, and study
  Collections the crate's.
- idr0015 has no organism or imaging method in the CSV; the study crate gives NCBITaxon:1427524 ("mixed
  sample") and confocal microscopy.
- Some images have no description; STAC forbids an empty one and RO-Crate requires one, so the Item leaves
  it out and the item crate says the source gives none.
- The per-image crates in the IDR Zarrs carry no taxon, unlike BIA's.
- IDR study crates name their descriptor `<accession>-ro-crate-metadata.json`, which RO-Crate 1.2 does not
  allow.
- idr0157's study crate is 770 KB once it lists its 1,127 image crates. Large studies are better browsed
  through the Parquet file or an API than through the static tree.
- A plate is one Item here. Treating each field image as an Item, so it could carry its own metadata, would
  mean 290,587 Items and ~870k files (~2.5–3 GB). It needs no extra requests, because all 635 plates have a
  fixed number of fields per well. It is the next step if per-image metadata becomes available.

### The studies themselves, as a table

```bash
.venv/bin/marimo edit 16_study_parquet.py   # writes catalogs/challenge/<resource>/studies.parquet
```

Images, plates and wells are all queryable as Parquet; the study was not, living only in its Collection
JSON and in the RO-Crate shipped beside it. This notebook reads both and writes one row per study — title,
license, keywords, publication date, authors and their ORCIDs, publisher, publication and DOI, taxa and
imaging methods with their ontology ids, size in bytes and file count — and registers it as the `studies`
asset on each resource Collection.

It is deliberately **not** stac-geoparquet: that format holds STAC Items as rows, and a Collection is not
an Item. It is a plain derived table whose `study` column joins to the `collection` column of
`items.parquet` and `wells.parquet`. The JSON Collections and the crates stay canonical.

24 studies, 19 of which ship a crate (BIA 5 of 10, IDR 14 of 14). The five without still get a row, from
their Collection alone. GIDE's crates spell the size node `QuantitiveValue` and IDR's
`QuantitativeValue`, so both spellings are accepted.

### Searching what is actually published

```bash
.venv/bin/marimo edit 17_search_deployed.py  # reads the web, writes nothing
```

The closing notebook knows one thing — the URL of the deployed root catalog — and discovers the rest. It
crawls the federation with pystac, takes the Parquet asset hrefs from the catalog itself, and queries them
over HTTPS with DuckDB. Nothing local is read and no credentials are used; the buckets serve range
requests, so only the column chunks a query names are fetched.

The queries are grouped by how many files each one needs, because that is the point of a federated catalog:

- **One file** — `idr:gene_symbol = 'PAU8'` reads `wells.parquet` alone and returns idr0004 plate P101
  well A2. The other buckets are never opened.
- **Two files** — plates joined to their wells: each well row names its plate in `bioimage:plate_id`,
  which is the id of the plate Item in `items.parquet`. A single flat table could not hold both without
  repeating every plate a few hundred times.
- **Every file** — a count by `bioimage:level` across both resources in one statement: 139,286 wells,
  1,263 images and 635 plates from IDR, 10 images from BIA.
- **Studies joined to their data** — `studies.parquet` against `items.parquet`, across four files in two
  buckets.

Each query reports its wall time; the six together take about 15 seconds over the network.

Still to do: the other five sources, and hosting each resource in its own bucket so the federation is
structural rather than a folder convention.

## Browsing it

```bash
cd browser && npm install && npm run dev
```

`browser/` is the challenge's own gallery, forked from [zowser](https://github.com/lubianat/zowser)
and rewired to read this catalog. Its `config.yaml` names one URL — the published root catalog — and
`src/stacStore.js` follows it to each resource Collection and reads the `items.parquet` each one
advertises, with [hyparquet](https://github.com/hyparam/hyparquet) over HTTP range requests.

Nothing opens a Zarr. The rows already carry shape, organism, imaging method, data size, well count
and a thumbnail, so 1,908 images and plates arrive in a handful of requests, where the upstream
gallery fetched a `zarr.json` per image and rendered each thumbnail in the browser. It is the same
argument the Parquet files make in `17_search_deployed.py`, with a UI on top.

See [browser/README.md](browser/README.md) to point it at another catalog.

## Repository layout

```
samples.csv                     input: IDR OME-Zarr samples (v0.4, v0.5)
01_ … 05_*.py                   notebooks (IDR samples warm-up)
10_bia_catalog.py               challenge pilot: BIA source
readable_stac_io.py             writes STAC JSON with short objects on one line
11_parquet_build.py             writes stac-geoparquet per collection
12_parquet_query.py             queries it with DuckDB and rustac
13_ro_crate.py                  reads the same tree as RO-Crate; checks STAC and RO-Crate agree
14_idr_catalog.py               challenge pilot: IDR source (1,898 images)
15_plate_wells.py               plate wells as Parquet rows, annotated from IDR
16_study_parquet.py             studies as a table, from the Collections and their crates
17_search_deployed.py           queries the published catalog from its root URL
biostac_build.py                build steps shared by the BIA and IDR notebooks
catalogs/basic/                 written by notebook 1
catalogs/extended/              written by notebook 3
extensions/ome-ngff/            experimental STAC extension for the IDR demo
extensions/bioimage/            experimental STAC extension for the challenge pilot
extensions/idr/                 experimental STAC extension for IDR well annotations
catalogs/challenge/bia/         written by 10_bia_catalog.py
catalogs/challenge/idr/         written by 14_idr_catalog.py (not in git)
ome2024-ngff-challenge/         submodule: the challenge repo and its sample lists
build_cache/                    cached zarr.json / RO-Crate / OLS4 responses
api/                            Docker setup and loader for the STAC API
browser/                        the challenge gallery, reading this catalog's Parquet
```

## Notes on fitting microscopy into STAC

STAC was designed for geospatial data, so a few things need a workaround:

- **Geometry.** Items may have `geometry: null`, and pystac and STAC Browser accept that. The databases behind STAC APIs (pgstac, stac-geoparquet) require a geometry, though. The extended catalog places every Item at a placeholder point (0,0). It is not a location.
- **Spatial extent.** Collections must declare one. They use the same (0,0) placeholder.
- **One parent per Item.** An Item belongs to one Collection, so only one grouping can be the hierarchy. Here that is OME-NGFF version. Study is a searchable property instead.
- **Empty values.** Some images have no Z, C or T size. The local CQL2 search counts comparisons on missing values as "no match". The API leaves missing properties out of its results.
