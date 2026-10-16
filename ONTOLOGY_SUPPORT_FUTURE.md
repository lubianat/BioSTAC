# Ontology support (future): search by parent term


## Context
Goal: search by a parent term, for example "Mammalia" or "electron microscopy", with autocomplete over labels and synonyms.
Ontology IDs stay the source of truth. We don't change the item spec (no denormalized ancestor columns), because catalogs are decentralized.
The hierarchy comes from Parquet files published at `tiagolubiana/ontology_parquets` and is resolved at page-build time or at query time.

## Verified query layer
- The browser reads Parquet with **hyparquet** (`asyncBufferFromUrl` + `parquetReadObjects`, ranged GETs), see `browser/src/crateStore.js:10,94`. No DuckDB.
- Items carry `organismId` / `fbbiId` (`crateStore.js:48-50`). Collections carry `organism_terms[]` / `imaging_method_terms[]` (`:81-83`).
- Labels live in `browser/src/ontologyStore.js`. It holds the catalog label plus an OLS4 fallback, and `olsUrl()` already normalizes ID forms (`NCBI:txid…`, `obo:FBbi_…`). The new code reuses that normalization.
- Filters are wired in `Main.svelte:26` (`organism: "organismId", modality: "fbbiId"`).

## Key fact: the tree in use is small
The catalogs reference perhaps a few hundred leaf taxa. Their combined lineages come to roughly 2–5k NCBITaxon nodes, plus about 50 FBbi nodes.
That fits as a few hundred KB of JSON. The 2.7M-node NCBITaxon is needed only to *derive* this subtree.

## Published dataset (HF bucket `tiagolubiana/ontology_parquets`)
Per ontology, versioned by release (`ncbitaxon/<release>/`, plus a `latest/` alias):
- `lineage.parquet`: one row per term. Columns: `id` (int local id, the source of truth), `label`, `rank`, `synonyms list<str>`, `ancestors list<int>` (root→parent), `ancestor_labels list<str>` (aligned with `ancestors`).
  - Sorted by `id`, with small row groups (about 2k rows), so column min/max stats let a reader fetch one row group per lookup.
  - One row gives the full labelled lineage, so a lookup needs a single round trip. Dictionary encoding absorbs the repeated labels.
  - NCBITaxon estimate: about 100–200 MB. FBbi: KB.
- `edges.parquet` (`child, parent`): for anyone who wants the raw graph. Cheap.
- Built by `scripts/build_ontology_parquets.py`: OBO → DuckDB recursive CTE → `COPY … (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE 2000)`. It includes an assert self-check: 9606 has 40674 (Mammalia) among its ancestors.

## Integration: two tiers, no spec change
1. **Page-build prefetch (main path).** A browser build step (`browser/scripts/prefetch-tree.mjs` or Python) does three things:
   - crawls the configured root crates for every distinct organism and FBbi ID, using the same crawl as `crateStore.js`
   - reads those rows from `lineage.parquet` with range reads
   - writes `public/ontology-tree.json`: `{id: {label, rank, synonyms, parents}}`, covering only the used subtree.
   The browser loads it once.
2. **Query-time fallback** for IDs the prefetch didn't see, for example a catalog added at runtime: hyparquet `parquetQuery({ filter: { id } })` against the bucket URL. It touches one row group of about 2k rows, roughly 50–100 KB.
   Results merge into the same in-memory tree. OLS4 `hierarchicalAncestors` is the last-resort fallback, next to the existing `lookupOntologyTerm`.

## Search / autocomplete
- Build the index in memory from the tree: `label + synonyms → id`, including every ancestor. Typing "mamm" suggests Mammalia (class) and shows the count of items under it.
- The suggestion list contains only terms that have items under them. That falls out of the subtree for free.
- Selecting a term stores the **id** in the filter state and URL. The filter is `item ∈ descendants(id)`, computed once from the tree as a `Set` of leaf IDs and checked against `organismId` / `organism_terms`.
- The same code serves FBbi, under its own namespace.

## Alternative: Wikidata (and OLS4) for resolving upper terms
| | Parquet on HF bucket | Wikidata SPARQL (WDQS) | OLS4 API (already used) |
|---|---|---|---|
| Query | `lineage` row by id | `?item wdt:P685 "9606"; wdt:P171* ?anc` (P685 = NCBI taxon ID, P171 = parent taxon) | `/terms/{iri}/hierarchicalAncestors` |
| Same tree as the source ontology | yes (exact release) | **no**: Wikidata's own taxonomy, mixed sources, multiple parents, some P171 gaps | yes |
| FBbi | yes | poor / likely absent (no reliable FBbi mapping) | yes |
| Labels / aliases | OBO synonyms | **best**: multilingual labels plus `skos:altLabel` aliases, common names | OBO synonyms |
| Versioned / reproducible | yes | no (moving target) | partly (OLS tracks latest) |
| Runtime dependency | static file, CDN | WDQS: rate limits, 60 s timeout, outages | EBI uptime |
| Batch ("all used leaves at once") | prefetch reads N rows | one `VALUES` query, good at prefetch | one call per term |
| Hosting cost / effort | build script + ~200 MB | none | none |

Verdict: Parquet is the source of truth for the tree. Wikidata is an **optional enrichment at prefetch time**: one batched SPARQL call over the used ancestors, mapped back by P685, that adds multilingual labels and common-name aliases to `ontology-tree.json`. It never decides the hierarchy. OLS4 remains the last-resort fallback at query time.
Zero-hosting MVP: build the prefetch from OLS4 `hierarchicalAncestors` alone, then switch to Parquet when the call count or latency hurts.

## Steps
0. Write `ONTOLOGY_SUPPORT_FUTURE.md` at the repo root: this whole plan (context, verified layer, dataset design, two tiers, autocomplete, Wikidata/OLS4 comparison, feasibility checks). It is a design log only; no code yet.
1. `scripts/build_ontology_parquets.py`: build and self-check the Parquets, then `hf` upload to the bucket.
2. Feasibility checks (must pass before step 3):
   - `curl -I -H 'Origin: http://localhost' -H 'Range: bytes=0-99' <bucket-url>` returns 206 plus `Access-Control-Allow-Origin` and exposes `Content-Range`. If not, fall back to an HF dataset repo `resolve/main` URL.
   - hyparquet `parquetQuery` with an `id` filter fetches only one row group. Watch the network tab.
3. Prefetch script and `public/ontology-tree.json`.
4. `ontologyStore.js`: load the tree, add the fallback lookup, and add `descendants(id)`.
5. `Main.svelte`: replace the organism and modality selects with an autocomplete that filters by subtree.

## Verification
- Selecting Hominidae shows exactly the human and great-ape items. Selecting Mammalia ⊇ Hominidae.
- Typing a synonym ("human", "mouse") resolves to 9606 / 10090.
- A cold load does not request `lineage.parquet` when the prefetch covers every ID. A catalog with a novel taxon triggers exactly one ranged request.

Skipped: part_of / other relations and other ontologies. The same script handles them with a different relation filter.
