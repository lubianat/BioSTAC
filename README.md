# BioSTAC

A catalog of bioimaging data made of RO-Crates and Parquet lists. It is tried out on the
[OME 2024 NGFF challenge](https://ome.github.io/ome2024-ngff-challenge/) submissions. The format is
described in [SPECIFICATION.md](SPECIFICATION.md).

The catalog is published at
`https://huggingface.co/buckets/tiagolubiana/RO-BioSTAC_demo/resolve/challenge/ro-crate-metadata.json`
and browsed with the gallery in `browser/`.

BioSTAC started as a [STAC](https://stacspec.org) catalog. That version is kept, still runnable, in
`src/stac_legacy/`.

## Layout

```
SPECIFICATION.md   the format
browser/           the gallery (Svelte, forked from zowser), reads the published catalog
src/               the builder: marimo notebooks, run in order
  10_bia_catalog.py      BIA, 10 images
  14_idr_catalog.py      IDR, 1,898 images and plates
  15_plate_wells.py      adds 139,286 IDR plate wells, with IDR annotations
  19_other_catalogs.py   JAX, NFDI4BIOIMAGE, Webknossos, Crick
  16_study_parquet.py    study-list.parquet per resource (run last)
  13_ro_crate.py         checks the BIA crates against their item lists
  17_search_deployed.py  queries the published catalog over HTTPS
  biostac_build.py       shared build steps
  deploy.sh              uploads catalogs/challenge to the bucket
  catalogs/challenge/    the output (idr/ is not in git)
  stac_legacy/           the STAC version, frozen
```

## Running

```bash
uv venv && uv pip install -r src/requirements.txt
git submodule update --init                       # the challenge's sample lists
cd src
../.venv/bin/python 10_bia_catalog.py             # or: ../.venv/bin/marimo edit 10_bia_catalog.py
../.venv/bin/python 14_idr_catalog.py             # ~15 min cold, <1 min warm (build_cache/)
../.venv/bin/python 15_plate_wells.py
../.venv/bin/python 19_other_catalogs.py          # JAX is slow on a cold cache
../.venv/bin/python 16_study_parquet.py
./deploy.sh
```

Gallery: `cd browser && npm install && npm run dev`. Its `config.yaml` names the catalog to read.

To check the crates: `uv run --with roc-validator rocrate-validator validate --profile-identifier
ro-crate-1.2 --requirement-severity REQUIRED src/catalogs/challenge`.

Known-good result: `idr:gene_symbol = 'PAU8'` finds idr0004, plate P101, well A2. That is the same hit
IDR's own search gives.

## Things that bit us

- OME-NGFF's `field_count` is the *maximum* number of fields per well, not the count. Wells, not fields,
  are the smallest unit indexed.
- GIDE's JSON-LD context cannot be listed by URL next to RO-Crate's ("recursive context inclusion"), so
  crates inline the GIDE terms they use.
- DuckDB: `level` is a reserved word. A glob over item lists needs `union_by_name := true`.
- marimo: variable names are global across cells, so prefix cell-local ones with `_`.
- hyparquet returns BigInt for integer columns.
- ro-crate-py adds a trailing `/` to `Dataset` ids, so Zarr ids end in `/`.
- One challenge image is tagged *Pongo abelii* where *Homo sapiens* is meant. Terms are only as good as the
  submission.

## Next

- Add the remaining challenge datasets; align with
  [bioparquet](https://github.com/AllenNeuralDynamics/bioparquet-sandbox).
- Query the lists in place (DuckDB-wasm) instead of loading every row into the tab.
- Filter by higher-level taxa and imaging-method groups using the ontologies.
- Render thumbnails on demand for rows without one.
- Viewer buttons in the gallery still hardcode NGFF 0.5.
