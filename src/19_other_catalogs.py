import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import csv
    import io
    import pathlib
    import urllib.error
    from concurrent.futures import ThreadPoolExecutor

    import marimo as mo

    import biostac_build as bb

    SAMPLES = pathlib.Path("ome2024-ngff-challenge/samples")
    SAMPLES_URL = "https://github.com/ome/ome2024-ngff-challenge/blob/main/samples/"
    return SAMPLES, SAMPLES_URL, ThreadPoolExecutor, bb, csv, io, mo, pathlib, urllib


@app.cell
def _(mo):
    mo.md(r"""
    # The other challenge sources: JAX, NFDI4BIOIMAGE, Webknossos, Crick, SSBD

    None of these ship a study crate, but each groups its images into collections, as the challenge
    site shows them ("Data from collection KOMP_adult_lacZ provided by JAX"). A collection is one
    provider CSV, so it becomes one Collection, with the CSV's name as its id:

    - **JAX**: `jax_samples.csv` lists the URLs of JAX's own CSVs (`KOMP_adult_lacZ`, `KOMP_histopathology`).
    - **NFDI4BIOIMAGE**: `n4bi.csv` lists one CSV per site (Jülich, Göttingen, Münster, Magdeburg).
    - **Webknossos**, **Crick**, **SSBD**: one CSV, one collection.

    Each collection gets a study-level RO-Crate that BioSTAC writes itself (`bb.generated_crate`):
    its organisms and imaging methods are those of its images, taken from the CSV or, where the CSV
    leaves them empty, from the image's own `ro-crate-metadata.json` (the challenge converter writes
    one; not every provider kept it).
    """)
    return


@app.cell
def _(SAMPLES, SAMPLES_URL, bb, csv, io):
    def read_csv(url):
        """Rows of a CSV in the submodule if it is one of the challenge's, else fetched once and cached."""
        local = SAMPLES / url.rsplit("/", 1)[-1]
        if "ome/ome2024-ngff-challenge" in url and local.exists():
            text = local.read_text()
        else:
            path = bb.CACHE / "provider_csvs" / url.rsplit("/", 1)[-1]
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(bb.fetch_bytes(url))
            text = path.read_text()
        return list(csv.DictReader(io.StringIO(text)))

    def stem(url):
        return url.rsplit("/", 1)[-1].removesuffix(".csv")

    _jax = [line.strip() for line in (SAMPLES / "jax_samples.csv").read_text().splitlines() if line.strip()]
    _n4bi = [r["url"].strip() for r in csv.DictReader(open(SAMPLES / "n4bi.csv")) if r.get("url")]
    # resource -> (title, description, [(collection id, csv url)], [(href, title)])
    SOURCES = {
        "jax": ("JAX — OME 2024 NGFF challenge",
                "Images submitted by The Jackson Laboratory to the OME 2024 NGFF challenge.",
                [(stem(u), u) for u in _jax],
                [("https://github.com/TheJacksonLaboratory/jax-ngff-challenge-2024", "JAX conversion repository")]),
        "nfdi4bioimage": ("NFDI4BIOIMAGE — OME 2024 NGFF challenge",
                          "Images submitted by NFDI4BIOIMAGE partners (Jülich, Göttingen, Münster, Magdeburg) "
                          "to the OME 2024 NGFF challenge.",
                          [(stem(u), u) for u in _n4bi],
                          [("https://nfdi4bioimage.de/", "NFDI4BIOIMAGE")]),
        "webknossos": ("Webknossos — OME 2024 NGFF challenge",
                       "Datasets published on webknossos.org, as submitted to the OME 2024 NGFF challenge.",
                       [("webknossos", SAMPLES_URL + "webknossos_samples.csv")],
                       [("https://webknossos.org/publications", "webknossos publications")]),
        "crick": ("Crick — OME 2024 NGFF challenge",
                  "Images submitted by the Francis Crick Institute to the OME 2024 NGFF challenge.",
                  [("crick", SAMPLES_URL + "crick.csv")],
                  [("https://www.crick.ac.uk/", "Francis Crick Institute")]),
        "ssbd": ("SSBD — OME 2024 NGFF challenge",
                 "Images submitted by SSBD (RIKEN) to the OME 2024 NGFF challenge.",
                 [("ssbd", SAMPLES_URL + "ssbd_samples.csv")],
                 [("https://ssbd.riken.jp/", "SSBD")]),
    }
    return SOURCES, read_csv


@app.cell
def _(bb, urllib):
    HARVESTED = bb.now()

    def build_item(resource, row):
        """One item row, or (None, reason) when the zarr cannot be read."""
        zarr_url = row["url"].strip().rstrip("/")
        path = zarr_url.split("://", 1)[-1].split("/", 1)[-1]
        uid = f"{resource}-{bb.slug(path, 80)}"
        cache = bb.CACHE / resource / uid
        try:
            layout, group_url, group, _root = bb.image_group(zarr_url, cache)
            axes = bb.axis_names(group)
        except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as error:
            return None, f"{zarr_url}: {error!r}"[:200]
        crate = bb.fetch_json_or_none(f"{zarr_url}/ro-crate-metadata.json", cache / "ro-crate-metadata.json")
        taxon, fbbi, crate_license = bb.image_crate_terms(crate)
        license_url = row.get("license") or crate_license
        shape = [int(n) for n in row["shape"].split(",")] if row.get("shape") else []
        # the CSV's shape follows its own dimension_names when it has them (Webknossos: c,x,y,z)
        dims = [d.strip() for d in row["dimension_names"].split(",")] if row.get("dimension_names") else axes
        # a name is not always there, nor unique: the last two path parts are
        title = row.get("name") or "/".join(path.removesuffix("/").rsplit("/", 2)[-2:])
        properties = {
            "title": title,
            **({"description": row["description"]} if row.get("description") else {}),
            "license": bb.LICENSES.get(license_url, "other"),
            "bioimage:source": resource,
            "bioimage:ngff_version": group["attributes"]["ome"].get("version"),
            "bioimage:size_bytes": int(float(row["written"])) if row.get("written") else None,
            **{f"bioimage:size_{name}": size for name, size in zip(dims, shape)},
            "bioimage:organism": bb.ontology_term(row.get("organismId") or taxon, "ncbitaxon"),
            "bioimage:imaging_method": bb.ontology_term(row.get("fbbiId") or fbbi, "fbbi"),
        }
        item = bb.make_item(uid, zarr_url, properties, HARVESTED, origin=row.get("origin") or None,
                            license_url=license_url, level="plate" if layout == "plate" else "image")
        if crate is None:
            item["ro_crate_url"] = None  # the zarr ships none: do not link a 404
        try:
            bb.add_thumbnail(item, rendered=bb.render_thumbnail(group_url, uid))
        except Exception as error:  # ponytail: a thumbnail is nice to have; the item stands without it
            print("no thumbnail:", uid, repr(error)[:120])
        return item, None
    return HARVESTED, build_item


@app.cell
def _(HARVESTED, SOURCES, ThreadPoolExecutor, bb, build_item, read_csv):
    report, skipped = [], []
    for resource, (title, description, collections, links) in SOURCES.items():
        ids, studies = set(), []
        for cid, csv_url in collections:
            rows = [r for r in read_csv(csv_url) if (r.get("url") or "").strip()]
            with ThreadPoolExecutor(8) as pool:
                built = list(pool.map(lambda r: build_item(resource, r), rows))
            skipped += [reason for _, reason in built if reason]
            members = [i for i, _ in built if i]
            if not members:
                continue
            assert not ids & {i["id"] for i in members} and len({i["id"] for i in members}) == len(members), \
                f"duplicate ids in {cid}"
            ids |= {i["id"] for i in members}
            origins = {i["origin_url"] for i in members if i.get("origin_url")}
            studies.append({
                "id": cid, "items": members, "crate_source": csv_url,
                "page": origins.pop() if len(origins) == 1 else None,
                "description": f"Collection {cid}, {len(members)} images, as listed in the provider's CSV for the "
                               "OME 2024 NGFF challenge. This crate was generated by BioSTAC from the images' own metadata.",
            })
            report.append({"resource": resource, "collection": cid, "rows": len(rows), "items": len(members),
                           "with image crate": sum(bool(i.get("ro_crate_url")) for i in members)})
        if studies:
            bb.save_resource(resource, title, description, studies, HARVESTED, links=links)
    return report, skipped


@app.cell
def _(mo, report, skipped):
    mo.vstack([
        mo.md(f"**{sum(r['items'] for r in report)}** items in **{len(report)}** collections; "
              f"**{len(skipped)}** rows skipped."),
        mo.ui.table(report, selection=None, pagination=False),
        mo.md("\n".join(f"- {s}" for s in skipped) or "Nothing skipped."),
    ])
    return


if __name__ == "__main__":
    app.run()
