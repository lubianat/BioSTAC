# Working in this repository

Notes for whoever (or whatever) picks this up next. The [README](README.md) says what BioSTAC is and how
to run it; this file holds the things that are easy to get wrong.

## Shape of the repo

Numbered marimo notebooks, run in order, each writing what the next one reads. `biostac_build.py` holds
the steps 10 and 14 share; `readable_stac_io.py` makes the written JSON readable (any container that
fits in 100 characters stays on one line). Nothing is a package; notebooks import the two modules
directly from the repository root, so commands are run from there.

```
01_ … 05_*.py        warm-up on samples.csv: basic catalog, browse, extended catalog, search, API
10_bia_catalog.py    pilot: BIA, 10 images       → catalogs/challenge/bia/
14_idr_catalog.py    pilot: IDR, 1,898 images    → catalogs/challenge/idr/   (not in git)
15_plate_wells.py    139,286 wells               → catalogs/challenge/idr/wells.parquet
11/12_parquet_*.py   build and query stac-geoparquet
13_ro_crate.py       reads the same tree as RO-Crate and checks the two views agree
16_study_parquet.py  studies as a table          → catalogs/challenge/<resource>/studies.parquet
17_search_deployed.py  queries the published catalog over HTTPS, reading nothing local
browser/             the gallery, reading the deployed Parquet (hard fork of zowser, via git subtree)
```

`catalogs/challenge/idr/` and `build_cache/` are gitignored: 146 MB and 112 MB. Build them locally.

## Running things

```bash
uv venv && uv pip install -r requirements.txt
git submodule update --init                 # the challenge repo, read in place
.venv/bin/marimo edit 10_bia_catalog.py     # or: .venv/bin/python 10_bia_catalog.py
.venv/bin/marimo export html 16_study_parquet.py -o /tmp/16.html   # runs every cell; the usual check
IDR_SAMPLE=2 .venv/bin/python 14_idr_catalog.py                    # first 2 images per study
cd browser && npm install && npm run dev
```

The IDR build is the expensive one: ~10k small files from EBI, 15 minutes with 8 threads on a cold
`build_cache/`, under a minute warm. `15_plate_wells.py` once froze a machine — it now streams one study
at a time into part files and merges them; keep it that way, and cap it with `ulimit -v` when in doubt.

## Conventions that are load-bearing

- **`bioimage:level`** (`image`, `plate`, `well`) says what a row denotes. Every row has it; queries that
  mix files group by it. Do not derive it from other columns — fix the build instead.
- **Ontology ids are also flat**, `bioimage:ncbitaxon` / `bioimage:fbbi` next to the structs, because
  Parquet keeps statistics on flat strings and CQL2 cannot reach into nested ones. `with_flat_terms()`
  writes each flat id right after its struct; that ordering is deliberate, for the JSON.
- **Placeholder geometry.** Items sit at (0,0) with `bbox [0,0,0,0]`. It is not a location; STAC API
  backends simply require one.
- **No empty strings.** STAC forbids `description: ""` and RO-Crate requires a description, so an Item
  omits it and its crate says the source gives none.
- **Crate links are relative.** BioStudies spells its URLs inconsistently (`/bioimages/` and
  `/BioImages/`), so absolute ids break silently; relative ones also survive a move to another bucket.
- **Shipped crates are attached**, root `@id` `./`, descriptor renamed to `ro-crate-metadata.json`
  (IDR ships `idr0004-ro-crate-metadata.json`, which RO-Crate 1.2 disallows). The source's `url` and
  `identifier` are preserved — use `setdefault`, or GIDE's accession is overwritten.
- **IDR's annotation tables are not republished.** The `idr:` extension carries a curated subset; the
  full tables stay at IDR, and each field names the column it came from.
- **Commits are small and human-readable**, present tense, saying why. One concern per commit.

## Things that bit us

- **`field_count` is a maximum**, not a count: OME-NGFF defines it as the largest number of fields in any
  well of the plate, and idr0011 wells hold fewer. Deriving field paths from it invents URLs that 404
  (2 of 20 sampled). Hence `bioimage:field_count_max`, and wells — not fields — as the unit below a plate.
- **`rustac` silently misses nested fields** in CQL2: no rows, no error, for
  `bioimage:organism.term_id`. pgstac and the local `cql2` handle it. Query nested values with DuckDB.
- **GIDE's `@context` cannot be listed by URL.** It imports the RO-Crate 1.2 context, so listing both
  makes rdflib fail with "recursive context inclusion"; listing it alone drops the required RO-Crate URL.
  Crates inline only the GIDE terms they use.
- **DuckDB**: `level` is a reserved word (alias it); `num_values`, not `stats_num_values`; `UNNEST` needs
  a subquery; writing a Parquet that already has a `geo` key duplicates it — pass only `stac-geoparquet`
  in `KV_METADATA` and let DuckDB write `geo`.
- **`rustac` infers the format from the extension**, so a temp file must end in `.parquet`.
- **marimo**: variable names are global across cells (prefix cell-local ones with `_`), and a cell that
  awaits must be `async def` — `asyncio.run()` throws inside the kernel.
- **hyparquet returns BigInt** for integer columns; the browser converts with `Number()`.
- **ro-crate-py appends a trailing slash** to `Dataset` ids, so a Zarr id must already end in `/` or the
  two views appear to disagree.

## Checking work

```bash
# RO-Crate 1.2, REQUIRED only (slow, so not in a notebook)
uv run --with roc-validator rocrate-validator validate --profile-identifier ro-crate-1.2 \
  --requirement-severity REQUIRED catalogs/challenge/bia/S-BIAD963

# the deployed catalog still answers the queries the notebooks claim
.venv/bin/marimo export html 17_search_deployed.py -o /tmp/17.html
```

Known-good answers: `idr:gene_symbol = 'PAU8'` → idr0004, plate P101, well A2, gene YAL068C (the same hit
IDR's own search gives). Counts by level across the deployed files: 139,286 wells, 1,263 images and 635
plates from IDR, 10 images from BIA. Studies: 24, of which 19 ship a crate.

## Deployment

Three Hugging Face buckets, one per resource plus the root, e.g.
`https://huggingface.co/buckets/tiagolubiana/ome2024-challenge-STAC/resolve/catalog.json`. They serve
anonymous ranged GETs with CORS (302 → 206), which is what lets DuckDB and the browser read the Parquet
in place. After rebuilding a resource, re-upload it, or `17_search_deployed.py` and `browser/` will show
the older columns.

## Left for later, deliberately

- Per-study `items.parquet` / `wells.parquet` and `table`-extension pointers from a study to its data.
- Field-level Items (~290k Items, ~870k files): they carry no metadata of their own today.
- The other five challenge sources.
- `browser/`'s viewer buttons still hardcode NGFF version 0.5 and `image`, though the rows now carry
  `bioimage:ngff_version` and `bioimage:level`.
