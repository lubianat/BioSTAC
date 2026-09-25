import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import collections
    import concurrent.futures
    import csv
    import hashlib
    import os
    import pathlib
    import re
    import time

    import marimo as mo

    import biostac_build as bb

    SAMPLES = pathlib.Path("ome2024-ngff-challenge/samples")
    INDEX_URL = "https://github.com/ome/ome2024-ngff-challenge/blob/main/samples/idr_samples.csv"
    STUDY_CRATES = "German-BioImaging/idr_study_crates/main/ro-crates"
    CACHE = bb.CACHE / "idr"
    return (
        CACHE,
        INDEX_URL,
        SAMPLES,
        STUDY_CRATES,
        bb,
        collections,
        concurrent,
        csv,
        hashlib,
        mo,
        os,
        re,
        time,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # IDR samples from the OME 2024 NGFF challenge

    Second source of the federated pilot, built the same way as BIA (`10_bia_catalog.py`,
    shared steps in `biostac_build.py`): one STAC Item per OME-Zarr, each with an RO-Crate twin,
    grouped into one Collection per IDR study, with the study's RO-Crate from
    [idr_study_crates](https://github.com/German-BioImaging/idr_study_crates) shipped next to it.

    What differs from BIA:

    - **Three Zarr layouts.** HCS plates (the image is the first well's first field), bioformats2raw
      (the image is under `0/`), and plain images. One Item per plate, as the challenge lists them;
      the plate's crate mirrors the Zarr down to its wells.
    - **Thumbnails.** Where the challenge links an IDR image, IDR's own thumbnail is used; otherwise
      the lowest pyramid level is rendered, as for BIA.
    - **Terms.** Organism and imaging method come from the CSV, or from the study crate where the CSV
      has none (idr0015).
    - **Scope.** The 14 study CSVs listed in `samples/idr_samples.csv`. The IDR test rows in
      `other_samples.csv` and the CSVs the index does not list are left out.

    Output: `catalogs/challenge/idr/` (not in git; ~5,700 files). The first run fetches ~10k
    small files from EBI and takes about half an hour; later runs read `build_cache/` and take minutes.
    """)
    return


@app.cell
def _(SAMPLES, csv, os, re):
    index = [r["url"].rsplit("/", 1)[-1] for r in csv.DictReader(open(SAMPLES / "idr_samples.csv")) if r.get("url")]
    study_csvs = sorted(name for name in index if re.match(r"idr\d{4}_samples\.csv$", name))
    skipped_csvs = sorted(set(index) - set(study_csvs))
    unlisted_csvs = sorted(
        p.name for p in SAMPLES.glob("idr*_samples.csv") if p.name not in index and p.name != "idr_samples.csv"
    )
    # IDR_SAMPLE=2 keeps the first 2 images of each study: a quick run for trying the build
    sample = int(os.environ.get("IDR_SAMPLE", 0)) or None
    rows = []
    for _name in study_csvs:
        with open(SAMPLES / _name, newline="") as _f:
            for _row in list(csv.DictReader(_f))[:sample]:
                _row["study"] = _name.split("_")[0]
                rows.append(_row)
    return rows, skipped_csvs, study_csvs, unlisted_csvs


@app.cell
def _(CACHE, STUDY_CRATES, bb, rows):
    def study_crate(accession):
        url = f"https://raw.githubusercontent.com/{STUDY_CRATES}/{accession}-ro-crate-metadata.json"
        path = CACHE.parent / "idr_study_crates" / f"{accession}.json"
        crate = bb.fetch_json_or_none(url, path)
        return (crate, path) if crate else None

    def study_terms(crate):
        """Taxa and imaging methods the study crate lists, as fallbacks for rows that have none."""
        if not crate:
            return [], []
        root = bb.crate_root(crate)[1]
        ids = lambda key: [x["@id"] for x in (root.get(key) or []) if isinstance(x, dict)]
        return [i for i in ids("about") if "NCBITaxon_" in i], [i for i in ids("measurementMethod") if "FBbi_" in i]

    study_crates = {s: study_crate(s) for s in sorted({r["study"] for r in rows})}
    fallback_terms = {s: study_terms((c or (None,))[0]) for s, c in study_crates.items()}
    return fallback_terms, study_crates


@app.cell
def _(CACHE, bb, fallback_terms, re):
    HARVESTED = bb.now()

    def item_id(row):
        """From the Zarr path: .../idr0004/P170.ome.zarr -> idr0004-p170 (60 chars at most)."""
        rel = row["url"].rstrip("/").split("/ome2024-ngff-challenge/", 1)[1]
        return bb.slug(rel.removesuffix(".zarr").removesuffix(".ome"), limit=60)

    def build_item(row, id_):
        zarr_url = bb.web_url(row["url"].rstrip("/"))
        layout, group_url, group, root = bb.image_group(zarr_url, CACHE / id_)
        names = (row.get("dimension_names") or "").split(",") if row.get("dimension_names") else bb.axis_names(group)
        # 4 rows write the shape as "[1, 1, 2, 520, 696]" instead of "1,1,2,520,696"
        shape = [int(n) for n in re.findall(r"\d+", row.get("shape") or "")]
        taxa, methods = fallback_terms[row["study"]]
        organism_raw = row.get("organismId") or (taxa[0] if taxa else None)
        method_raw = row.get("fbbiId") or (methods[0] if methods else None)

        properties = {
            "title": row["name"],
            "description": row.get("description") or None,  # STAC: omit rather than empty
            "license": bb.LICENSES.get(row.get("license"), "other"),
            "bioimage:source": "idr",
            "bioimage:ngff_version": root["attributes"]["ome"].get("version"),
            "bioimage:size_bytes": int(float(row["written"])) if row.get("written") else None,
            **{f"bioimage:size_{n.strip()}": s for n, s in zip(names, shape)},
            "bioimage:organism": bb.ontology_term(organism_raw, "ncbitaxon"),
            "bioimage:imaging_method": bb.ontology_term(method_raw, "fbbi"),
        }
        wells = []
        if layout == "plate":
            plate = root["attributes"]["ome"]["plate"]
            # field_count is the plate's maximum per the NGFF spec, not the count in every well;
            # the CSV's "images" is only wells x field_count, so it is not carried
            properties |= {"bioimage:wells": len(plate["wells"]),
                           "bioimage:field_count_max": plate.get("field_count")}
            wells = [(f"{zarr_url}/{w['path']}/", f"Well {w['path'].replace('/', '')}") for w in plate["wells"]]
        properties = {k: v for k, v in properties.items() if v is not None or k in ("bioimage:organism", "bioimage:imaging_method")}

        origin = row.get("origin") or None
        item = bb.make_item(id_, zarr_url, properties, HARVESTED, origin=origin, license_url=row.get("license"),
                            level="plate" if layout == "plate" else "image")
        image = re.search(r"show=image-(\d+)", origin or "")
        if image:  # IDR renders its own thumbnails
            bb.add_thumbnail(item, remote=f"https://idr.openmicroscopy.org/webgateway/render_thumbnail/{image.group(1)}/")
        else:
            bb.add_thumbnail(item, rendered=bb.render_thumbnail(group_url, f"idr-{id_}"))
        bb.add_crate_link(item)
        organism_from_study = not row.get("organismId") and bool(organism_raw)
        return item, layout, wells, organism_from_study

    return HARVESTED, build_item, item_id


@app.cell
def _(build_item, collections, concurrent, hashlib, item_id, mo, rows, time):
    ids = [item_id(r) for r in rows]
    _counts = collections.Counter(ids)
    # ids come from the Zarr path; a hash suffix only where the cut at 60 characters makes two collide
    ids = [i if _counts[i] == 1 else f"{i}-{hashlib.sha1(r['url'].encode()).hexdigest()[:8]}" for i, r in zip(ids, rows)]
    assert len(set(ids)) == len(ids)

    results, failures = {}, {}
    _started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(8) as _pool:  # polite to EBI; the cache makes re-runs offline
        _futures = {_pool.submit(build_item, r, i): (r, i) for r, i in zip(rows, ids)}
        for _future in concurrent.futures.as_completed(_futures):
            _row, _id = _futures[_future]
            try:
                results[_id] = (_row, *_future.result())
            except Exception as error:  # one broken image must not stop the other 1,897
                failures[_id] = f"{type(error).__name__}: {error}"[:200]
    build_seconds = round(time.perf_counter() - _started)
    mo.md(f"Built **{len(results)}** items, **{len(failures)}** failed, in {build_seconds} s.")
    return build_seconds, failures, ids, results


@app.cell
def _(HARVESTED, INDEX_URL, STUDY_CRATES, bb, ids, results, study_crates):
    items = [results[i][1] for i in ids if i in results]
    extra_parts = {i: results[i][3] for i in ids if i in results and results[i][3]}
    members = {}
    for _id in ids:
        if _id in results:
            members.setdefault(results[_id][0]["study"], []).append(results[_id][1])

    def study_page(accession):
        crate = (study_crates.get(accession) or (None,))[0]
        return bb.crate_root(crate)[1]["@id"] if crate else f"https://idr.openmicroscopy.org/search/?query=Name:{accession}"

    for accession, _members in members.items():
        published = bb.crate_published((study_crates.get(accession) or (None,))[0])
        if published:
            for _item in _members:
                if _item.datetime == HARVESTED:
                    _item.datetime = published

    study_collections = [
        bb.study_collection(
            accession, members[accession], (study_crates.get(accession) or (None,))[0], HARVESTED,
            study_page(accession),
            crate_source=(
                f"https://github.com/{STUDY_CRATES.replace('/main/', '/blob/main/', 1)}/{accession}-ro-crate-metadata.json",
                "IDR study crate (source; descriptor renamed, context compacted)",
            ),
            crate_title="IDR study RO-Crate",
        )
        for accession in sorted(members)
    ]
    resource = bb.resource_catalog(
        "idr", "IDR — OME 2024 NGFF challenge",
        "Images the Image Data Resource (IDR) converted to OME-NGFF 0.5 for the OME 2024 NGFF challenge. "
        "Harvested from the challenge sample lists; the OME-Zarr data stays on EBI servers.",
        study_collections, items, HARVESTED,
        links=[(INDEX_URL, "Challenge sample list (IDR)"), ("https://idr.openmicroscopy.org/", "IDR")],
        extra_fields={"bioimage:source_csv": INDEX_URL},
    )
    crate_sizes, item_crates = bb.save_resource(resource, items, study_collections, study_crates, extra_parts)
    n_valid = bb.validate(resource)
    return resource, crate_sizes, item_crates, items, n_valid, study_collections


@app.cell
def _(bb, collections, items, mo, n_valid, results, study_collections):
    def label(term):
        return f"{term['term_label'] or '?'}" if term else "—"

    per_study = []
    for _study in study_collections:
        _members = list(_study.get_items())
        _layouts = collections.Counter(results[m.id][2] for m in _members)
        per_study.append({
            "study": _study.id,
            "title": _study.title[:50],
            "items": len(_members),
            "layout": ", ".join(f"{k} {v}" for k, v in _layouts.items()),
            "organism": ", ".join(sorted({label(m.properties.get("bioimage:organism")) for m in _members})),
            "imaging method": ", ".join(sorted({label(m.properties.get("bioimage:imaging_method")) for m in _members})),
            "study license": _study.license,
            "item license": ", ".join(sorted({m.properties["license"] for m in _members})),
            "thumbnails": collections.Counter(
                "remote" if not m.assets["thumbnail"].href.startswith("./") else "rendered"
                for m in _members if "thumbnail" in m.assets).most_common(),
        })
    mo.vstack([
        mo.md(f"## Studies\n{len(items)} items in {len(study_collections)} studies; {n_valid} STAC objects validated."),
        mo.ui.table(per_study, selection=None, pagination=False),
    ])
    return (per_study,)


@app.cell
def _(crate_sizes, failures, item_crates, items, mo, per_study, results, skipped_csvs, unlisted_csvs):
    _fallback = [i for i, r in results.items() if r[4]]
    _license_mismatch = [s["study"] for s in per_study if s["study license"] not in s["item license"].split(", ")]
    _no_thumb = [i.id for i in items if "thumbnail" not in i.assets]
    _biggest = max(crate_sizes.items(), key=lambda kv: kv[1][1])
    mo.md(
        "## Findings\n"
        + f"- failed images: {len(failures)}" + ("".join(f"\n  - `{k}`: {v}" for k, v in sorted(failures.items())[:20]))
        + f"\n- organism taken from the study crate (none in the CSV): {len(_fallback)} items"
        + f"\n- item license (CSV) differs from study license (crate): {', '.join(_license_mismatch) or 'none'}"
        + f"\n- items without a thumbnail: {len(_no_thumb)}"
        + f"\n- study crates shipped: {len(crate_sizes)}; largest {_biggest[0]} at {_biggest[1][1]:,} bytes"
        + " (one nested-crate entry per image)"
        + f"\n- item crates written: {len(item_crates)}"
        + f"\n- left out: {', '.join(skipped_csvs)} (IDR test exports) and CSVs the index does not list: "
        + ", ".join(unlisted_csvs)
    )
    return


if __name__ == "__main__":
    app.run()
