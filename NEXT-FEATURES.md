
# To the future

- Add the other OME-NGFF Challenge datasets (e.g. the 3D datasets) to the demo.

- Align with https://github.com/AllenNeuralDynamics/bioparquet-sandbox


– Search directly the parquets on S3 (scalability) and similar scalability improvements. Maybe use DuckDB WASM or similar to query the parquets directly in S3.


– leverage the ontologies for filtering e.g. upper-level taxa and aggregating the fbbi terms. Maybe load ontologies as a parquet that can be joined. Maybe something else more efficient. Maybe some predefined "top level" taxa (iNaturalist style) and FBbi terms ("fluorescence microscopy", "electron microscopy", etc.)

– On-demand thumbnails: clicking the "No thumbnail available" placeholder renders a low-resolution level of the OME-Zarr in the browser (e.g. with ome-zarr.js), for wells and items without a pre-rendered PNG. Not by default: at scale that is one Zarr read per row.

- Make a RO-Crate-on-STAC-model mode (works 100% on RO-Crates, no catalog.json or collection.json, but using the STAC ideas for items/collections/catalogs)
