# IDR well annotation extension (experimental)

Carries a small, curated part of the [Image Data Resource](https://idr.openmicroscopy.org)'s **well-level**
screen annotations, so that a well can be found by gene, compound, cell line or control type.

- **Schema:** `v0.1.0/schema.json`
- **Identifier:** `https://example.org/stac/idr/v0.1.0/schema.json` (a placeholder; not hosted)

## Fields

| Field | Type | From the annotation file |
|---|---|---|
| `idr:plate_name` | string | `Plate`, e.g. `Plate1-Blue-A` |
| `idr:well` | string | `Well`, e.g. `A1` |
| `idr:screen` | string | which screen the row came from, e.g. `screenA` |
| `idr:gene_symbol` | string \| null | `Gene Symbol` or `Comment [Gene Symbol]` |
| `idr:gene_identifier` | string \| null | `Gene Identifier` or `Comment [Gene Identifier]` |
| `idr:sirna_identifier` | string \| null | `siRNA Identifier` |
| `idr:compound_name` | string \| null | `Compound Name` or `Compound 1 Name` |
| `idr:organism` | string \| null | `Characteristics [Organism]` |
| `idr:organism_term` | string \| null | its `Term Source` pair, as a CURIE such as `NCBITaxon:4932` |
| `idr:cell_line` | string \| null | `Characteristics [Cell Line]` |
| `idr:cell_line_term` | string \| null | its `Term Source` pair |
| `idr:control_type` | string \| null | `Control Type` |
| `idr:has_phenotype` | boolean \| null | `Has Phenotype` |
| `idr:phenotypes` | array of strings \| null | the non-empty `Phenotype N` values |

## Why only these

The eight annotated studies in this pilot use **172 distinct column names** between them, and only about 31
appear in more than one study: idr0012 alone has 102 columns, idr0033 77, mostly `Phenotype 1…22` triples.
Carrying all of them would mean 172 mostly-empty columns, several of which mean nothing on their own —
`Term Source 1 REF` qualifies whichever `Characteristics [...]` column precedes it, and `Phenotype 19` needs
its own term name and accession beside it.

So this extension keeps what is shared and searchable, and **does not republish IDR's annotation tables**.
The full annotations stay at IDR: each study Collection links to its study page, and the fields above name
their source columns so the original row can be looked up there.

Two shape decisions:

- **Flat fields rather than structs.** A label and its ontology id are paired by the `_term` suffix
  (`idr:organism` / `idr:organism_term`) instead of nesting. Nested values are exactly what `rustac`'s CQL2
  filter silently fails to match, and they are clumsier in SQL. Flat columns also carry Parquet statistics,
  so a reader can skip row groups on them.
- **One list.** `idr:phenotypes` is an array because a well can have several. Lists cannot be filtered by
  CQL2 either, so use DuckDB (`list_contains`) for that one.

## Where it is used

On the well rows in `catalogs/challenge/idr/wells.parquet`, built by `15_plate_wells.py`. Those rows exist
only as Parquet today, so the schema is documentation rather than something a validator runs; it applies as
soon as a well row is written as JSON.
