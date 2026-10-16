# BioSTAC specification

A BioSTAC catalog describes OME-Zarr images held elsewhere. It is a tree of
[RO-Crates](https://www.researchobject.org/ro-crate/) (RO-Crate 1.2) with Parquet lists for search. It
copies no pixels.

## Levels

```
CATALOG   ro-crate-metadata.json   nests other catalogs or studies
          study-list.parquet       one row per study (in a catalog that holds studies)
STUDY     ro-crate-metadata.json   the study's crate
          item-list.parquet        one row per image, plate or well
ITEM      a row of item-list.parquet, pointing by absolute URL at an OME-Zarr
```

- A **catalog** organizes and holds no data. The root is a catalog. It nests one catalog per resource
  (`bia/`, `idr/`, …), and each of those nests its studies.
- A **study** is never nested in another study. Its crate lists exactly one data file, `item-list.parquet`.
  If the source publishes a study crate, that crate is used: renamed to `ro-crate-metadata.json`, with root
  `./` and `isBasedOn` pointing to the original. Otherwise the builder writes one.
- An **item** is one OME-Zarr: an image, a plate, or one well of a plate. A builder may also write a crate
  per item, at `<study>/<item>/ro-crate-metadata.json`, with `isPartOf` pointing to `../`.

## Rules

- **Nesting.** A crate nests another as RO-Crate 1.2 "Referencing other RO-Crates": a `Dataset` in
  `hasPart`, its `@id` the child folder ending in `/`, `conformsTo` `https://w3id.org/ro/crate`, and
  `subjectOf` the child's `ro-crate-metadata.json`.
- **Files.** Each Parquet list is a `File` in its crate's `hasPart`, with `encodingFormat`, `contentSize`
  and `sha256`. Rewriting a list means updating its entry.
- **References** between crates and lists are relative, so a tree can move. Item URLs are absolute, except
  files shipped with the catalog (thumbnails, item crates), which are relative to the list that names them.
- **Every root** has `name`, `description`, `datePublished` and `license`. Catalog crates use CC0 for their
  own metadata; each study keeps its own license.
- **No empty strings.** A missing value is null or absent.
- **Sort order.** `item-list.parquet` is sorted by `bioimage:level`, then `id`. Images and plates come
  first, so a reader takes them as a row range and skips the wells.

## item-list.parquet

| Column | Description |
|---|---|
| `id` | unique in the catalog, e.g. `idr0004-p101`, `idr0004-p101-a2` |
| `study` | the study folder |
| `bioimage:level` | `image`, `plate` or `well`. Always set by the builder, never derived from other columns |
| `title`, `description` | from the source |
| `license`, `license_url` | SPDX id (or `other`), and the license as the source gives it |
| `date_published` | the study's publication date, else the harvest date |
| `bioimage:source` | the resource, e.g. `bia` |
| `bioimage:ngff_version` | from `zarr.json` |
| `bioimage:size_bytes` | size of the Zarr |
| `bioimage:size_t/c/z/y/x` | size of each axis present. For a plate, the size of one field image |
| `bioimage:organism`, `bioimage:imaging_method` | `{ontology_source, term_id, term_label}` |
| `bioimage:ncbitaxon`, `bioimage:fbbi` | the same term ids, flat, so Parquet keeps statistics on them |
| `bioimage:wells`, `bioimage:field_count_max` | plates: number of wells, and the OME-NGFF `field_count` (a maximum; some wells hold fewer fields) |
| `bioimage:plate_id`, `bioimage:well` | wells: the plate row's `id`, and the position, e.g. `A/10` |
| `zarr_url`, `zarr_metadata_url` | the OME-Zarr and its `zarr.json` |
| `ro_crate_url` | the image's own crate inside the Zarr, if it has one |
| `crate_href`, `thumbnail_url` | the builder's item crate and thumbnail |
| `origin_url` | the study or image page at the source |
| `idr:*` | wells from IDR: a curated subset of IDR's annotation columns (gene, siRNA, compound, cell line, control, phenotypes). Each comes from one named source column. The full annotation tables stay at IDR |

A well inherits its plate's columns, so filter on `bioimage:level` when counting.

## study-list.parquet

| Column | Description |
|---|---|
| `study`, `source` | the study folder and its resource |
| `title`, `description`, `keywords`, `date_published`, `study_url`, `license` | from the study crate |
| `source_crate` | whether the source published the crate |
| `crate_href`, `item_list_href` | relative to this file |
| `items`, `wells` | row counts of the item list: images and plates, then wells |
| `thumbnail` | the crate's thumbnail, else the first item's |
| `organisms`, `imaging_methods` (+ `_terms`) | labels and ids from the crate |
| `authors`, `author_ids`, `publisher`, `publication_title`, `publication_doi`, `size_bytes`, `file_count` | from the crate, where it has them |

## Reading a catalog

1. Fetch the root `ro-crate-metadata.json` and follow nested crates through `hasPart`, `conformsTo` and
   `subjectOf`.
2. In a resource crate, find `study-list.parquet` in `hasPart` and read it.
3. For each study you want, read `item_list_href`: rows `[0, items)` are the images and plates, and the
   remaining rows are the wells.

Parquet is read in place with HTTP range requests, so the host must serve ranged GETs with CORS.

## Scale

The gallery holds every row in the browser tab. That works for hundreds of thousands of rows, but a tab
will not hold ten million. Past that point, query the lists in place (e.g. DuckDB-wasm), start from
`study-list.parquet`, and partition large studies further. The flat id columns and the sort order exist
so readers can skip row groups.
