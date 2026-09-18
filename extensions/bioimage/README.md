# bioimage STAC extension (experimental)

Describes a bioimage (OME-Zarr) asset in STAC Item properties: its axes and sizes, and ontology terms for the specimen and the imaging method.

Physical units and pixel sizes are left out: they live in the image's own `zarr.json`, one asset away.

- **Schema:** `v0.1.0/schema.json`
- **Identifier:** `https://example.org/stac/bioimage/v0.1.0/schema.json`

The identifier is a placeholder and is not hosted; the build validates against the local file. The `bioimage:` prefix was not in use on [stac-extensions.github.io](https://stac-extensions.github.io/) when this was written.

The `ontology_term` and axes structures follow the shapes used by [bioparquet](https://github.com/bioparquet), so the two stay convertible.

## Item properties

| Field | Type | Description |
|---|---|---|
| `bioimage:source` | string | Resource that published the image, e.g. `bia` |
| `bioimage:ngff_version` | string \| null | OME-NGFF version from `zarr.json` |
| `bioimage:size_bytes` | integer \| null | Size of the written Zarr |
| `bioimage:axes` | array | One entry per axis, in storage order: `{name, type, size}` |
| `bioimage:size_<name>` | integer | Flat size per axis (`bioimage:size_x`, …), for simple queries |
| `bioimage:organism` | ontology term | Specimen taxon, e.g. `NCBITaxon:9606` |
| `bioimage:imaging_method` | ontology term | Imaging method, e.g. `FBbi:00000251` |

On the Collection, `bioimage:organisms` and `bioimage:imaging_methods` list the term labels found in its Items, so a reader sees what is inside without opening them.

An ontology term is `{ontology_source, term_id, term_label}`. Labels are resolved from the [EBI OLS4](https://www.ebi.ac.uk/ols4) API at build time and may be null.

Title, description and license use the core STAC fields, not new ones.
