# Scalability

What the current design survives, and what replaces it, from 100k to 1B searchable rows (images + wells).
These are estimates to reason with, not benchmarks: each figure traces back to the baseline and assumptions
below, so when one of those is measured, the table can be redone.

## The current design

The gallery (`browser/`) reads every row of every table into the tab: items and collections at startup,
wells right after. It filters and counts them in JavaScript. The Parquet files, the static JSON catalog and
DuckDB over HTTP range requests (`17_search_deployed.py`) are separate from this. They do not hold rows in
memory, and they scale much further.

## Baseline (measured in this repo)

| Table | Rows | Size | Per row |
|---|---|---|---|
| `idr/wells.parquet` | 139,286 | 1.5 MB | ~11 B |
| `idr/items.parquet` | 1,898 | 104 KB | ~55 B |
| `*/studies.parquet` | 24 | 26 KB | ~1 KB |

Wells compress well because neighbouring rows repeat almost everything (plate, study, organism, method) and
IDR's annotations are sparse. Richer per-row metadata lands nearer the items figure.

## Assumptions (not yet measured)

- **Heap:** ~1 KB of JS heap per row object (about 40 fields, the lowercased search text, the strings).
  *Measure: DevTools heap snapshot with wells loaded, divided by 141k.*
- **Tab limit:** a tab gets 2–4 GB before it crashes or the OS kills it, and less on phones.
- **Filter cost:** one predicate over one row costs ~10–50 ns. The text filter (`includes` on the search
  string) is at the top of that range.
- **Crossfilter cost:** crossfiltering multiplies that pass by the number of dropdowns (~6).
- **Download:** ~50 Mbit/s, about 6 MB/s.

## Estimates by scale

| Rows | Parquet | Download | Heap (all in tab) | One filter pass | Crossfilter pass |
|---|---|---|---|---|---|
| 100k | 1–5 MB | < 1 s | ~100 MB | ~5 ms | ~30 ms |
| 1M | 11–55 MB | 2–9 s | ~1 GB | ~50 ms | ~300 ms |
| 10M | 0.1–0.5 GB | 20–90 s | ~10 GB ✗ | ~0.5 s | ~3 s |
| 100M | 1–5 GB | minutes | ~100 GB ✗ | — | — |
| 1B | 11–55 GB | hours | ~1 TB ✗ | — | — |

✗ = does not fit in a tab. The pilot sits at ~141k.

## What works at each scale

**100k: the current design.** Everything in the tab, and crossfiltering is affordable. The only real cost is
wells arriving a second or two after the first render.

**1M: the current design, with care.**
- Heap is the limit, not speed.
  - Read only the columns the gallery shows. hyparquet can project columns.
  - Drop the per-row objects in favour of column arrays.
  - Build the search string lazily.
- Keep crossfiltering off by default (as now); a pass of a few hundred ms per click is noticeable.
- The `idr:gene` suggestion lists reach tens of thousands of values and need a prefix search, not a full `<datalist>`.

**10M: stop loading rows; query them.**
- DuckDB-wasm in the tab, over HTTP range requests, against the same Parquet.
  - Filters on the flat columns (`bioimage:ncbitaxon`, `bioimage:fbbi`, `idr:gene_symbol`, `collection`) are pushed
    down, and row-group statistics skip most of the file. This is what the flat ontology columns exist for.
  - Lists are paged with `LIMIT/OFFSET`.
- Dropdown options and counts come from small precomputed tables, per collection and per facet value, written at
  build time next to `studies.parquet`, not by scanning.
- Free text over all rows becomes slow: every row group has to be read. Limit it to the collection level, or give
  it an index (below).
- Sort each Parquet by collection, then plate, so row groups line up with the filters people use.

**100M: partition, and enter through collections.**
- One file per collection already exists (`<study>/items.parquet`, `<study>/wells.parquet`). Keep the merged file
  only as a convenience for small resources.
- Split large collections further by level (and by plate for HCS), hive-style.
- The browser starts at Collections (tens of thousands of rows at most, even here), then reads only the chosen
  collections' files.
- Cross-collection facets ("every well with gene X") need a prebuilt inverted index as static files, e.g.
  gene → list of collection/plate files, sharded by prefix. Otherwise it needs a query service.
- Everything stays static and range-readable; build time grows, serving cost doesn't.

**1B: static files plus a search service.**
- The partitioned Parquet stays the source of truth and the bulk-access path (DuckDB, Spark, Python).
- Interactive cross-resource search needs a server:
  - pgstac or a search engine for text and facets over Items, or
  - a hosted DuckDB-style query endpoint over the same files.
- STAC API Collection Search and Item Search federate the resources.
- MINI-PORTOLAN's "no API" holds for access, but not for global free-text search at this size.
- Collection-first browsing still works without a server, because collections stay small.

## What scales for free, and what doesn't

- **Scales:**
  - static catalog JSON, which stays one level deep with collections as studies
  - per-collection Parquet with flat, pushdown-friendly columns
  - range GETs with CORS from the buckets
  - `studies.parquet` as the entry point: it grows with the number of studies, not images
- **Doesn't:**
  - loading every row
  - the per-row search string
  - crossfiltering by scanning
  - `<datalist>` suggestions
  - size ranges computed in the browser, which should move into `studies.parquet`

## Levels to watch

Collections and plates stay small. Wells are the first level to explode: 139k from 14 IDR studies here. Fields
(~290k Items for these same studies, per `AGENTS.md`) would be next. That is one more reason fields are not Items
yet.

## To check next

1. Heap per row at 141k (DevTools) → replaces the 1 KB assumption.
2. Filter and crossfilter time on wells (`performance.now()` around `applyFilters`) → replaces the ns/row assumption.
3. DuckDB-wasm over `wells.parquet` in the tab: time to first page for `idr:gene_symbol = 'PAU8'`.
