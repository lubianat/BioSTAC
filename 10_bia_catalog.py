import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import csv
    import pathlib

    import marimo as mo

    import biostac_build as bb

    SOURCE_CSV = "ome2024-ngff-challenge/samples/ebi-ngff-challenge-samples.csv"
    SOURCE_CSV_URL = "https://github.com/ome/ome2024-ngff-challenge/blob/main/samples/ebi-ngff-challenge-samples.csv"
    GIDE_CRATES = "foundingGIDE/gide-data-deliverable/main/data_deliverable/GIDE_crates"
    CACHE = bb.CACHE / "bia"
    return CACHE, GIDE_CRATES, SOURCE_CSV, SOURCE_CSV_URL, bb, csv, mo, pathlib


@app.cell
def _(mo):
    mo.md(r"""
    # BIA samples from the OME 2024 NGFF challenge

    First source of the federated pilot: the 10 EBI/BIA images submitted to the
    [OME 2024 NGFF challenge](https://ome.github.io/ome2024-ngff-challenge/).

    For each row of the challenge CSV the build fetches, from the EBI server:

    - `zarr.json` — OME-NGFF version and the multiscales axes
    - `ro-crate-metadata.json` — specimen taxon and imaging method

    and turns it into one STAC Item, described by the experimental
    `bioimage` extension in `extensions/bioimage/`.

    Items are grouped into one sub-Collection per study (`S-BIAD606`, `EMPIAR-10310`, …). Where
    [GIDE](https://github.com/foundingGIDE/gide-data-deliverable) publishes a study-level RO-Crate,
    the study Collection takes its title, description, keywords, license and publication date from it,
    and the crate itself is shipped with the catalog as `ro-crate-metadata.json`, a collection-level asset.
    Study metadata stays at the Collection level, so it is not repeated in every Item (or in `items.parquet`).

    The build steps shared with the IDR catalog live in `biostac_build.py`.

    ```
    catalogs/challenge/catalog.json
    └─ bia/collection.json                 the resource
       └─ S-BIAD606/collection.json        a study
          ├─ ro-crate-metadata.json         its GIDE crate, shipped as a collection asset
          └─ bia-3d-micro-ct-image-…/…json  an image
    ```
    """)
    return


@app.cell
def _(CACHE, SOURCE_CSV, bb, csv):
    HARVESTED = bb.now()

    def build_item(row):
        zarr_url = row["url"].rstrip("/")
        uid = zarr_url.rsplit("/", 1)[-1].removesuffix(".zarr")
        layout, group_url, group, _root = bb.image_group(zarr_url, CACHE / uid)
        crate = bb.fetch_json(f"{zarr_url}/ro-crate-metadata.json", CACHE / uid / "ro-crate-metadata.json")
        # the CSV shape is positional: it only means something next to the axis names from zarr.json
        shape = [int(n) for n in row["shape"].split(",")] if row["shape"] else []

        # the crate says organism/method too, but the CSV columns are the challenge's own summary of it
        properties = {
            "title": row["name"],
            "description": row["description"],
            "license": bb.LICENSES.get(row["license"], "other"),
            "bioimage:source": "bia",
            "bioimage:ngff_version": group["attributes"]["ome"].get("version"),
            "bioimage:size_bytes": int(row["written"]) if row["written"] else None,
            **{f"bioimage:size_{name}": size for name, size in zip(bb.axis_names(group), shape)},
            "bioimage:organism": bb.ontology_term(row["organismId"], "ncbitaxon"),
            "bioimage:imaging_method": bb.ontology_term(row["fbbiId"], "fbbi"),
        }
        item = bb.make_item(f"bia-{bb.slug(row['name'])}", zarr_url, properties, HARVESTED,
                            origin=row["origin"], license_url=row["license"])
        bb.add_thumbnail(item, rendered=bb.render_thumbnail(group_url, uid))
        bb.add_crate_link(item)
        return item, crate

    with open(SOURCE_CSV, newline="") as _f:
        rows = list(csv.DictReader(_f))
    return HARVESTED, build_item, rows


@app.cell
def _(CACHE, GIDE_CRATES, HARVESTED, SOURCE_CSV_URL, bb, build_item, rows):
    items, crates, studies = [], {}, {}
    for _row in rows:
        _item, _crate = build_item(_row)
        items.append(_item)
        crates[_item.id] = _crate
        _accession = _row["origin"].rstrip("/").rsplit("/", 1)[-1]  # S-BIAD606, EMPIAR-10310
        studies.setdefault((_accession, _row["origin"]), []).append(_item)
    # ids come from titles, so they must stay unique
    assert len(crates) == len(items), "two titles produced the same item id"

    def gide_crate(accession):
        """The GIDE study-level RO-Crate for a BIA/EMPIAR accession, or None if GIDE has none."""
        url = f"https://raw.githubusercontent.com/{GIDE_CRATES}/{accession}-ro-crate-metadata.json"
        path = CACHE.parent / "gide" / f"{accession}.json"
        crate = bb.fetch_json_or_none(url, path)
        return (crate, path) if crate else None

    study_crates = {accession: gide_crate(accession) for accession, _ in studies}
    study_collections = [
        bb.study_collection(
            accession, members, (study_crates[accession] or (None,))[0], HARVESTED, origin,
            crate_source=(
                f"https://github.com/{GIDE_CRATES.replace('/main/', '/blob/main/', 1)}/{accession}-ro-crate-metadata.json",
                "GIDE study crate (source; context compacted)",
            ),
            crate_title="GIDE study RO-Crate",
            fallback_description=f"{accession}. No GIDE study crate is available for this study.",
        )
        for (accession, origin), members in sorted(studies.items())
    ]
    collection = bb.resource_collection(
        "bia", "BIA / EBI — OME 2024 NGFF challenge",
        "Images submitted by the BioImage Archive (EMBL-EBI) to the OME 2024 NGFF challenge. "
        "Harvested from the challenge sample list; the OME-Zarr data stays on EBI servers.",
        study_collections, items, HARVESTED,
        links=[(SOURCE_CSV_URL, "Challenge sample list"),
               ("https://www.ebi.ac.uk/bioimage-archive/", "BioImage Archive")],
        extra_fields={"bioimage:source_csv": SOURCE_CSV_URL},
    )
    crate_sizes, item_crates = bb.save_resource(collection, items, study_collections, study_crates)
    n_valid = bb.validate(collection)
    return crate_sizes, crates, item_crates, items, n_valid, study_crates


@app.cell
def _(crates, items, mo, n_valid, rows):
    def term(item, field):
        value = item.properties.get(field)
        return f"{value['term_id']} ({value['term_label']})" if value else "—"

    findings = [
        {
            "item": i.id,
            "title": i.properties["title"][:40],
            "axes": "".join(k.removeprefix("bioimage:size_") for k in i.properties
                            if k.startswith("bioimage:size_") and k != "bioimage:size_bytes"),
            "MB": round((i.properties["bioimage:size_bytes"] or 0) / 1e6, 1),
            "organism": term(i, "bioimage:organism"),
            "imaging method": term(i, "bioimage:imaging_method"),
            "crate graph nodes": len(crates[i.id]["@graph"]),
        }
        for i in items
    ]
    mo.vstack([
        mo.md(f"**{len(rows)}** rows → **{len(items)}** items, {n_valid} objects validated."),
        mo.ui.table(findings, selection=None, pagination=False),
    ])
    return


@app.cell
def _(crate_sizes, item_crates, items, mo, study_crates):
    missing = {
        field: [i.id for i in items if not i.properties.get(field)]
        for field in ["bioimage:ngff_version", "bioimage:organism", "bioimage:imaging_method", "description"]
    }
    unlabelled = [i.id for i in items if (i.properties.get("bioimage:organism") or {}).get("term_label") is None]
    mo.md(
        "## Findings\n"
        + "\n".join(f"- missing `{k}`: {v or 'none'}" for k, v in missing.items())
        + f"\n- organism terms OLS4 could not label: {unlabelled or 'none'}"
        + f"\n- studies with a GIDE study crate: {sum(c is not None for c in study_crates.values())} of {len(study_crates)}"
        + f"; without: {sorted(a for a, c in study_crates.items() if c is None) or 'none'}"
        + "\n- study crates, bytes as published → as shipped with the compact context: "
        + ", ".join(f"{k} {a:,} → {b:,}" for k, (a, b) in sorted(crate_sizes.items()))
        + f"\n- item crates written: {len(item_crates)}, "
        + f"{min(p.stat().st_size for p in item_crates):,}–{max(p.stat().st_size for p in item_crates):,} bytes each"
    )
    return


if __name__ == "__main__":
    app.run()
