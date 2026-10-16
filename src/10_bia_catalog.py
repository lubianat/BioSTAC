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

    and turns it into one row of the study's `item-list.parquet`, plus an item RO-Crate beside it.
    The columns are documented in `SPECIFICATION.md`.

    Items are grouped by study (`S-BIAD606`, `EMPIAR-10310`, …). Where
    [GIDE](https://github.com/foundingGIDE/gide-data-deliverable) publishes a study-level RO-Crate, it
    *is* the study crate, attached here as `ro-crate-metadata.json`; otherwise BioSTAC writes one from the
    images. Either way the study crate lists one data file, `item-list.parquet`. Study metadata stays in the
    crate, so it is not repeated in every row.

    The build steps shared with the other sources live in `biostac_build.py`.

    ```
    catalogs/challenge/ro-crate-metadata.json      the root: one nested crate per resource
    └─ bia/ro-crate-metadata.json                  the resource: nested study crates (+ study-list.parquet, 16)
       └─ S-BIAD606/ro-crate-metadata.json         a study: its GIDE crate, listing item-list.parquet
          ├─ item-list.parquet                      its images, one row each
          └─ bia-3d-micro-ct-image-…/               an image: its crate and thumbnail
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
        crates[_item["id"]] = _crate
        _accession = _row["origin"].rstrip("/").rsplit("/", 1)[-1]  # S-BIAD606, EMPIAR-10310
        studies.setdefault((_accession, _row["origin"]), []).append(_item)
    # ids come from titles, so they must stay unique
    assert len(crates) == len(items), "two titles produced the same item id"

    def gide_crate(accession):
        """The GIDE study-level RO-Crate for a BIA/EMPIAR accession, or None if GIDE has none."""
        url = f"https://raw.githubusercontent.com/{GIDE_CRATES}/{accession}-ro-crate-metadata.json"
        return bb.fetch_json_or_none(url, CACHE.parent / "gide" / f"{accession}.json")

    study_crates = {accession: gide_crate(accession) for accession, _ in studies}
    for (accession, _origin), members in studies.items():
        published = bb.crate_published(study_crates[accession])
        for _item in members:
            if published:
                _item["date_published"] = published.date().isoformat()
    bb.save_resource(
        "bia", "BIA / EBI — OME 2024 NGFF challenge",
        "Images submitted by the BioImage Archive (EMBL-EBI) to the OME 2024 NGFF challenge. "
        "Harvested from the challenge sample list; the OME-Zarr data stays on EBI servers.",
        [{"id": accession, "items": members, "crate": study_crates[accession], "page": origin,
          "crate_source": f"https://github.com/{GIDE_CRATES.replace('/main/', '/blob/main/', 1)}/{accession}-ro-crate-metadata.json"
          if study_crates[accession] else None,
          "description": f"{accession}. No GIDE study crate is available for this study."}
         for (accession, origin), members in sorted(studies.items())],
        HARVESTED,
        links=[(SOURCE_CSV_URL, "Challenge sample list"),
               ("https://www.ebi.ac.uk/bioimage-archive/", "BioImage Archive")],
    )
    return crates, items, study_crates


@app.cell
def _(crates, items, mo, rows):
    def term(item, field):
        value = item.get(field)
        return f"{value['term_id']} ({value['term_label']})" if value else "—"

    findings = [
        {
            "item": i["id"],
            "title": i["title"][:40],
            "axes": "".join(k.removeprefix("bioimage:size_") for k in i
                            if k.startswith("bioimage:size_") and k != "bioimage:size_bytes"),
            "MB": round((i["bioimage:size_bytes"] or 0) / 1e6, 1),
            "organism": term(i, "bioimage:organism"),
            "imaging method": term(i, "bioimage:imaging_method"),
            "crate graph nodes": len(crates[i["id"]]["@graph"]),
        }
        for i in items
    ]
    mo.vstack([
        mo.md(f"**{len(rows)}** rows → **{len(items)}** items."),
        mo.ui.table(findings, selection=None, pagination=False),
    ])
    return


@app.cell
def _(bb, items, mo, study_crates):
    missing = {
        field: [i["id"] for i in items if not i.get(field)]
        for field in ["bioimage:ngff_version", "bioimage:organism", "bioimage:imaging_method", "description"]
    }
    unlabelled = [i["id"] for i in items if (i.get("bioimage:organism") or {}).get("term_label") is None]
    _crates = sorted((bb.CHALLENGE / "bia").glob("*/*/ro-crate-metadata.json"))
    mo.md(
        "## Findings\n"
        + "\n".join(f"- missing `{k}`: {v or 'none'}" for k, v in missing.items())
        + f"\n- organism terms OLS4 could not label: {unlabelled or 'none'}"
        + f"\n- studies with a GIDE study crate: {sum(c is not None for c in study_crates.values())} of {len(study_crates)}"
        + f"; without (crate generated): {sorted(a for a, c in study_crates.items() if c is None) or 'none'}"
        + f"\n- item crates written: {len(_crates)}, "
        + f"{min(p.stat().st_size for p in _crates):,}–{max(p.stat().st_size for p in _crates):,} bytes each"
    )
    return


if __name__ == "__main__":
    app.run()
