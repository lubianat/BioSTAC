# ome-ngff STAC extension (experimental)

A draft extension for describing OME-Zarr images in STAC Item properties, so they can be searched.

- **Schema:** `v0.1.0/schema.json`
- **Identifier:** `https://example.org/stac/ome-ngff/v0.1.0/schema.json`

The identifier is a placeholder and is not hosted. Notebook 3 validates against the local file.

## Item properties

| Field | Type | Description |
|---|---|---|
| `ome:version` | string | OME-NGFF version (`0.4`, `0.5`) |
| `ome:axes` | string \| null | Axes present, e.g. `XYZCT` |
| `ome:size_x` | integer \| null | Width in pixels |
| `ome:size_y` | integer \| null | Height in pixels |
| `ome:size_z` | integer \| null | Number of Z planes |
| `ome:size_c` | integer \| null | Number of channels |
| `ome:size_t` | integer \| null | Number of timepoints |
| `ome:has_labels` | boolean | Whether the image has label (segmentation) images |
| `ome:plate` | boolean | Whether it is a high-content screening plate |
| `idr:study` | string | IDR study accession, e.g. `idr0062` |

Licenses use the core STAC `license` field with SPDX identifiers (`CC-BY-4.0`, `CC0-1.0`).

For the API, the same fields are registered as queryables in `api/queryables.json`.
