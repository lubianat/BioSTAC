import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import http.server
    import json
    import pathlib
    import threading
    import urllib.parse
    from functools import partial

    import duckdb
    import marimo as mo
    from rocrate.rocrate import ROCrate

    BIA = pathlib.Path("catalogs/challenge/bia")
    CRATE = "ro-crate-metadata.json"
    return BIA, CRATE, ROCrate, duckdb, http, mo, partial, threading, urllib


@app.cell
def _(mo):
    mo.md(r"""
    # The BIA export, read as RO-Crate

    `10_bia_catalog.py` writes a tree of crates, with the rows a search needs in Parquet beside them:

    ```
    bia/
    ├─ ro-crate-metadata.json          the resource: nests one crate per study
    └─ S-BIAD963/
       ├─ ro-crate-metadata.json       the study (the GIDE study crate), listing item-list.parquet
       ├─ item-list.parquet            one row per image
       └─ bia-mouse-cns-mesospim/
          ├─ ro-crate-metadata.json    the same image, as a crate
          └─ thumbnail.png
    ```

    This notebook reads the tree with RO-Crate tooling only:
    [ro-crate-py](https://github.com/ResearchObject/ro-crate-py) to walk it, and the
    [RO-Crate Explorer](https://github.com/arunaengine/ro-crate-explorer) to browse it.
    Then it checks that each item crate says what its row in `item-list.parquet` says.

    The crates also pass the REQUIRED checks of the RO-Crate 1.2 profile of
    [rocrate-validator](https://github.com/crs4/rocrate-validator). That check is slow, so it runs
    from the command line rather than here; see the README.
    """)
    return


@app.cell
def _(BIA, CRATE, ROCrate, mo):
    def props(crate, entity_id):
        entity = crate.get(entity_id)
        return entity.properties() if entity is not None else {}

    def ids(value):
        return [v["@id"] for v in (value if isinstance(value, list) else [value]) if isinstance(v, dict)]

    # start from the resource crate and follow its nested crates down, as any RO-Crate client would
    _resource = ROCrate(BIA)
    studies = []
    for _entity in _resource.data_entities:
        if (_entity.properties().get("conformsTo") or {}).get("@id") != "https://w3id.org/ro/crate":
            continue
        _crate = ROCrate(BIA / _entity.id.strip("/"))
        _root = _crate.root_dataset.properties()
        studies.append({
            "study crate": _entity.id,
            "name": _root.get("name", "")[:60],
            "identifier": _root.get("identifier", ""),
            "keywords": ", ".join(_root.get("keywords", []))[:50],
            "from the source": "isBasedOn" in _root,
            "data files": ", ".join(e.id for e in _crate.data_entities),
        })

    mo.vstack([
        mo.md(f"## Study crates\nThe `bia` crate nests {len(studies)} study crates in `hasPart` (a folder id, "
              "`conformsTo` RO-Crate, `subjectOf` its metadata file). Each lists one data file, its item list; "
              "where GIDE publishes a crate it is that crate (`from the source`), otherwise BioSTAC wrote one."),
        mo.ui.table(studies, selection=None, pagination=False),
    ])
    return ids, props


@app.cell
def _(BIA, CRATE, ROCrate, ids, mo, props):
    images = []
    for _path in sorted(BIA.glob(f"*/*/{CRATE}")):
        _crate = ROCrate(_path.parent)
        _root = _crate.root_dataset.properties()
        _parent = ids(_root.get("isPartOf"))
        _up = props(_crate, _parent[0]) if _parent else {}
        images.append({
            "image crate": _path.parent.name,
            "name": _root.get("name"),
            "part of": _up.get("name", _parent[0] if _parent else "—")[:45],
            "study crate": "../" + CRATE if _up.get("subjectOf") else "—",
            "taxon": " / ".join(props(_crate, t).get("scientificName", t) for t in ids(_root.get("about"))),
            "imaging method": " / ".join(props(_crate, t).get("name", t) for t in ids(_root.get("measurementMethod"))),
            "remote parts": sum(i.startswith("http") for i in ids(_root.get("hasPart"))),
            "local parts": ", ".join(i for i in ids(_root.get("hasPart")) if not i.startswith("http")),
        })

    mo.vstack([
        mo.md("## Image crates\nOne per image, read without looking at its row in the item list. "
              "`remote parts` are the OME-Zarr, its `zarr.json` and the image's own challenge crate, "
              "all on EBI servers; the thumbnail ships locally."),
        mo.ui.table(images, selection=None, pagination=False),
    ])
    return


@app.cell
def _(BIA, CRATE, ROCrate, duckdb, ids, mo, props):
    # both views of each image, side by side: its row, and its crate
    _result = duckdb.sql(f"SELECT * FROM read_parquet('{BIA}/*/item-list.parquet', union_by_name := true) ORDER BY id")
    agreement = []
    for _row in (dict(zip(_result.columns, r)) for r in _result.fetchall()):
        _crate = ROCrate(BIA / _row["study"] / _row["id"])
        _root = _crate.root_dataset.properties()
        _checks = {
            "title": _row["title"] == _root.get("name"),
            "license": _row["license_url"] in ids(_root.get("license")),
            "taxon": (_row.get("bioimage:organism") or {}).get("term_label")
            in [props(_crate, t).get("scientificName") for t in ids(_root.get("about"))],
            "imaging method": (_row.get("bioimage:imaging_method") or {}).get("term_label")
            in [props(_crate, t).get("name") for t in ids(_root.get("measurementMethod"))],
            # the row's URL has no trailing slash; the crate's Zarr Dataset id does
            "OME-Zarr": _row["zarr_url"].rstrip("/") + "/" in ids(_root.get("hasPart")),
            "row names its crate": (BIA / _row["study"] / _row["crate_href"]).name == CRATE,
        }
        agreement.append({"image": _row["id"], **{k: "✓" if v else "✗" for k, v in _checks.items()}})

    _all = all(v == "✓" for row in agreement for k, v in row.items() if k != "image")
    mo.vstack([
        mo.md(f"## Both views agree\nFor every image, the row in `item-list.parquet` and the item crate carry the "
              f"same title, license, taxon, imaging method and data location. "
              f"**{'All match.' if _all else 'Mismatches below.'}**"),
        mo.ui.table(agreement, selection=None, pagination=False),
    ])
    return (agreement,)


@app.cell
def _(BIA, CRATE, http, mo, partial, threading, urllib):
    # serve the repo over HTTP with CORS, so the web explorer can fetch the crates
    class CORS(http.server.SimpleHTTPRequestHandler):
        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            super().end_headers()

        def log_message(self, *args):
            pass

    try:
        _server = http.server.ThreadingHTTPServer(("localhost", 8000), partial(CORS, directory="."))
        threading.Thread(target=_server.serve_forever, daemon=True).start()
    except OSError:
        pass  # already serving (cell re-run, or another notebook serving)

    def explorer(path):
        crate_url = f"http://localhost:8000/{path.as_posix()}"
        return "https://arunaengine.github.io/ro-crate-explorer/?crateUrl=" + urllib.parse.quote(crate_url, safe="")

    _study_links = [f"- [resource crate]({explorer(BIA / CRATE)})"] + [
        f"- **{p.parent.name}** — [study crate]({explorer(p)})"
        + "".join(f" · [{c.parent.name}]({explorer(c)})" for c in sorted(p.parent.glob(f"*/{CRATE}")))
        for p in sorted(BIA.glob(f"*/{CRATE}"))
    ]
    mo.md(
        "## Browse the crates\n"
        "Serving the repo on `localhost:8000`. Each link opens a crate in the "
        "[RO-Crate Explorer](https://arunaengine.github.io/ro-crate-explorer/). From a study crate, the "
        "resource crate, the study crates open as sub-crates; from an image crate, `isPartOf` leads back up.\n\n"
        + "\n".join(_study_links)
    )
    return


if __name__ == "__main__":
    app.run()
