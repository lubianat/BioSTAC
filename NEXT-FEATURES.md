– Separate the ABOUT in two sections:
   - About BIOSTAC explains the overall structure of STAC: Catalog, Collection (catalog + metadata), Item and Asset (data). How they are materialized in JSON and parquet components. One simple diagram to illustrate the structure.

   - About the OME-NGFF-Challenge, explaining the context of the challenge. Similar to current about.

– Search by study (collection right before the leaf item nodes)

– Search wells (optional may blow up search)


– Search directly the parquets on S3 (scalability)


# To the future


– leverage the ontologies for filtering e.g. upper-level taxa and aggregating the fbbi terms. Maybe load ontologies as a parquet that can be joined. Maybe something else more efficient.

– On-demand thumbnails: clicking the "No thumbnail available" placeholder renders a low-resolution level of the OME-Zarr in the browser (e.g. with ome-zarr.js), for wells and items without a pre-rendered PNG. Not by default: at scale that is one Zarr read per row.
