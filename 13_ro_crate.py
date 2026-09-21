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

    import marimo as mo
    import pystac
    from pystac.validation import JsonSchemaSTACValidator, set_validator
    from rocrate.rocrate import ROCrate

    BIA = pathlib.Path("catalogs/challenge/bia")
    CRATE = "ro-crate-metadata.json"
    return (
        BIA,
        CRATE,
        JsonSchemaSTACValidator,
        ROCrate,
        http,
        json,
        mo,
        partial,
        pystac,
        set_validator,
        threading,
        urllib,
    )


@app.cell
def _(mo):
    mo.md(r"""
    # The BIA export as RO-Crate

    `10_bia_catalog.py` writes one tree that is two things at once:

    ```
    bia/S-BIAD963/
    ├─ collection.json                 STAC Collection
    ├─ ro-crate-metadata.json          RO-Crate (the GIDE study crate)
    └─ bia-mouse-cns-mesospim/
       ├─ bia-mouse-cns-mesospim.json  STAC Item
       ├─ ro-crate-metadata.json       RO-Crate (the same image)
       └─ thumbnail.png
    ```

    This notebook ignores the STAC files and reads the tree with RO-Crate tooling only:
    [ro-crate-py](https://github.com/ResearchObject/ro-crate-py) to walk it, and the
    [RO-Crate Explorer](https://github.com/arunaengine/ro-crate-explorer) to browse it.
    Then it validates the same tree as STAC, and checks that both views say the same thing.

    All 15 crates also pass the REQUIRED checks of the RO-Crate 1.2 profile of
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

    # start from the study crates and follow their nested crates down, as any RO-Crate client would
    studies = []
    for _path in sorted(BIA.glob(f"*/{CRATE}")):
        _crate = ROCrate(_path.parent)
        _root = _crate.root_dataset.properties()
        _nested = [
            e.id for e in _crate.data_entities
            if (e.properties().get("conformsTo") or {}).get("@id") == "https://w3id.org/ro/crate"
        ]
        studies.append({
            "study crate": _path.parent.name,
            "name": _root.get("name", "")[:60],
            "identifier": _root.get("identifier", ""),
            "keywords": ", ".join(_root.get("keywords", []))[:50],
            "nested image crates": ", ".join(_nested),
        })

    mo.vstack([
        mo.md(f"## Study crates\n{len(studies)} studies have a GIDE crate. Each lists its images as "
              "nested crates in `hasPart` (a folder id, `conformsTo` RO-Crate, `subjectOf` its metadata file)."),
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
            "study crate": "../" + CRATE if _up.get("subjectOf") else "— (study page)",
            "taxon": " / ".join(props(_crate, t).get("scientificName", t) for t in ids(_root.get("about"))),
            "imaging method": " / ".join(props(_crate, t).get("name", t) for t in ids(_root.get("measurementMethod"))),
            "remote parts": sum(i.startswith("http") for i in ids(_root.get("hasPart"))),
            "local parts": ", ".join(i for i in ids(_root.get("hasPart")) if not i.startswith("http")),
        })

    mo.vstack([
        mo.md("## Image crates\nOne per image, read without looking at the STAC Item next to it. "
              "`remote parts` are the OME-Zarr, its `zarr.json` and the image's own challenge crate, "
              "all on EBI servers; the thumbnail ships locally."),
        mo.ui.table(images, selection=None, pagination=False),
    ])
    return


@app.cell
def _(JsonSchemaSTACValidator, json, mo, pystac, set_validator):
    # the bioimage extension URI is not hosted: hand the local schema to the validator
    _validator = JsonSchemaSTACValidator()
    with open("extensions/bioimage/v0.1.0/schema.json") as _f:
        _validator.schema_cache["https://example.org/stac/bioimage/v0.1.0/schema.json"] = json.load(_f)
    set_validator(_validator)

    stac_catalog = pystac.Catalog.from_file("catalogs/challenge/catalog.json")
    stac_items = {i.id: i for i in stac_catalog.get_items(recursive=True)}
    _collections = list(stac_catalog.get_all_collections())
    _validated = stac_catalog.validate_all()
    mo.md(f"## Valid as STAC\n`validate_all()` passes on the same tree: {len(_collections)} Collections "
          f"and {len(stac_items)} Items ({_validated} objects checked), including the `bioimage` extension schema.")
    return (stac_items,)


@app.cell
def _(BIA, CRATE, ROCrate, ids, mo, props, stac_items):
    # both views of each image, side by side
    agreement = []
    for _item_id, _item in sorted(stac_items.items()):
        _crate = ROCrate(BIA / _item.get_parent().id / _item_id)
        _root = _crate.root_dataset.properties()
        _p = _item.properties
        _license = next((l.href for l in _item.links if l.rel == "license"), None)
        _checks = {
            "title": _p["title"] == _root.get("name"),
            "license": _license in ids(_root.get("license")),
            "taxon": (_p.get("bioimage:organism") or {}).get("term_label")
            in [props(_crate, t).get("scientificName") for t in ids(_root.get("about"))],
            "imaging method": (_p.get("bioimage:imaging_method") or {}).get("term_label")
            in [props(_crate, t).get("name") for t in ids(_root.get("measurementMethod"))],
            # STAC href has no trailing slash; the crate's Zarr Dataset id does
            "OME-Zarr": _item.assets["data"].href.rstrip("/") + "/" in ids(_root.get("hasPart")),
            "links to each other": f"./{_item_id}.json" in ids(_root.get("seeAlso"))
            and any(l.rel == "alternate" and l.href.endswith(CRATE) for l in _item.links),
        }
        agreement.append({"image": _item_id, **{k: "✓" if v else "✗" for k, v in _checks.items()}})

    _all = all(v == "✓" for row in agreement for k, v in row.items() if k != "image")
    mo.vstack([
        mo.md(f"## Both views agree\nFor every image, the STAC Item and its RO-Crate twin carry the same title, "
              f"license, taxon, imaging method and data location, and link to each other. "
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
        pass  # already serving (cell re-run, or 02_browse / 04_search running)

    def explorer(path):
        crate_url = f"http://localhost:8000/{path.as_posix()}"
        return "https://arunaengine.github.io/ro-crate-explorer/?crateUrl=" + urllib.parse.quote(crate_url, safe="")

    _study_links = [
        f"- **{p.parent.name}** — [study crate]({explorer(p)})"
        + "".join(f" · [{c.parent.name}]({explorer(c)})" for c in sorted(p.parent.glob(f"*/{CRATE}")))
        for p in sorted(BIA.glob(f"*/{CRATE}"))
    ]
    _orphans = [
        f"- **{p.parent.parent.name}** (no study crate) — [{p.parent.name}]({explorer(p)})"
        for p in sorted(BIA.glob(f"*/*/{CRATE}")) if not (p.parent.parent / CRATE).exists()
    ]
    mo.md(
        "## Browse the crates\n"
        "Serving the repo on `localhost:8000`. Each link opens a crate in the "
        "[RO-Crate Explorer](https://arunaengine.github.io/ro-crate-explorer/). From a study crate, the "
        "nested image crates open as sub-crates; from an image crate, `isPartOf` leads back up.\n\n"
        + "\n".join(_study_links + _orphans)
    )
    return


if __name__ == "__main__":
    app.run()
