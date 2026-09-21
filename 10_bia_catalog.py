import marimo

app = marimo.App(width="full")


@app.cell
def _():
    import csv
    import datetime
    import json
    import pathlib
    import re
    import urllib.error
    import urllib.request

    import marimo as mo
    import pystac
    from pystac.summaries import Summarizer
    from pystac.validation import JsonSchemaSTACValidator, set_validator

    from readable_stac_io import ReadableStacIO
    from readable_stac_io import dumps as readable_dumps

    pystac.StacIO.set_default(ReadableStacIO)  # short objects on one line, for human readers

    BIOIMAGE_EXT = "https://example.org/stac/bioimage/v0.1.0/schema.json"
    SOURCE_CSV = "ome2024-ngff-challenge/samples/ebi-ngff-challenge-samples.csv"
    SOURCE_CSV_URL = "https://github.com/ome/ome2024-ngff-challenge/blob/main/samples/ebi-ngff-challenge-samples.csv"
    CACHE = pathlib.Path("build_cache/bia")
    LICENSES = {
        "https://creativecommons.org/licenses/by/4.0/": "CC-BY-4.0",
        "https://creativecommons.org/publicdomain/zero/1.0/": "CC0-1.0",
    }
    return (
        BIOIMAGE_EXT,
        CACHE,
        JsonSchemaSTACValidator,
        LICENSES,
        SOURCE_CSV,
        SOURCE_CSV_URL,
        Summarizer,
        csv,
        datetime,
        json,
        mo,
        pathlib,
        pystac,
        re,
        readable_dumps,
        set_validator,
        urllib,
    )


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
    and the crate itself is shipped with the catalog as `ro-crate-metadata.json`, a collection-level asset. Study metadata stays at the Collection level, so it is not
    repeated in every Item (or in `items.parquet`).

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
def _(CACHE, json, pathlib, urllib):
    def fetch_json(url, cache_path):
        """Fetch once, then read from build_cache/ so re-runs are offline and reproducible."""
        path = pathlib.Path(cache_path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(url, timeout=60) as response:
                path.write_bytes(response.read())
        return json.loads(path.read_text())

    def ols_label(curie, ontology):
        """Resolve a term label from EBI OLS4. Returns None if the term is not found."""
        cache_path = CACHE.parent / "labels" / f"{curie.replace(':', '_')}.json"
        url = f"https://www.ebi.ac.uk/ols4/api/terms?obo_id={curie}&ontology={ontology}&size=1"
        for attempt in range(2):  # OLS4 drops the occasional request
            try:
                terms = (
                    fetch_json(url, cache_path).get("_embedded", {}).get("terms", [])
                )
            except urllib.error.URLError:
                continue
            return terms[0]["label"] if terms else None
        return None

    return fetch_json, ols_label


@app.cell
def _(ols_label):
    def ontology_term(raw, ontology):
        """'NCBI:txid9606' or 'obo:FBbi_00000251' -> {ontology_source, term_id, term_label}."""
        if not raw:
            return None
        if raw.startswith("NCBI:txid"):
            curie = f"NCBITaxon:{raw.removeprefix('NCBI:txid')}"
        else:  # obo:FBbi_00000251
            curie = raw.removeprefix("obo:").replace("_", ":", 1)
        source = curie.split(":")[0]
        return {
            "ontology_source": source,
            "term_id": curie,
            "term_label": ols_label(curie, ontology.lower()),
        }

    return (ontology_term,)


@app.cell
def _(CACHE):
    import numpy as np
    import zarr
    from PIL import Image

    def render_thumbnail(zarr_url, uid, size=256, max_pixels=2000 * 2000):
        """PNG of the lowest-resolution level, as the NGFF challenge site renders it in the browser:
        first timepoint, middle Z plane, active OMERO channels in their colours and windows.
        Cached under build_cache/; returns the PNG path, or None if the smallest level is too big."""
        target = CACHE.parent / "thumbnails" / f"{uid}.png"
        if target.exists():
            return target
        group = zarr.open_group(zarr_url, mode="r")
        ome = group.attrs["ome"]
        multiscale = ome["multiscales"][0]
        names = [axis["name"] for axis in multiscale["axes"]]
        level = group[multiscale["datasets"][-1]["path"]]
        shape = dict(zip(names, level.shape))
        if shape["y"] * shape["x"] > max_pixels:
            return None
        index = tuple(0 if n == "t" else shape["z"] // 2 if n == "z" else slice(None) for n in names)
        plane = np.asarray(level[index], dtype=float)
        if "c" not in names:
            plane = plane[None]  # (c, y, x) from here on

        channels = ome.get("omero", {}).get("channels") or [{"color": "FFFFFF"}]
        rgb = np.zeros(plane.shape[1:] + (3,))
        for data, channel in zip(plane, channels):
            if channel.get("active") is False:
                continue
            window = channel.get("window", {})
            low, high = window.get("start"), window.get("end")
            if low is None or high is None or high <= low:
                low, high = np.percentile(data, [0.5, 99.5])  # no usable window: auto-contrast
            scaled = np.clip((data - low) / max(high - low, 1e-9), 0, 1)
            if np.percentile(scaled, 99.5) < 0.1:  # like ome-zarr.js autoBoost: a window too wide to see anything
                low, high = np.percentile(data, [0.5, 99.5])
                scaled = np.clip((data - low) / max(high - low, 1e-9), 0, 1)
            color = np.array([int(channel.get("color", "FFFFFF")[i:i + 2], 16) / 255 for i in (0, 2, 4)])
            rgb += scaled[..., None] * color
        image = Image.fromarray((np.clip(rgb, 0, 1) * 255).astype("uint8"))
        image.thumbnail((size, size))
        target.parent.mkdir(parents=True, exist_ok=True)
        image.save(target)
        return target

    return (render_thumbnail,)


@app.cell
def _(CACHE, LICENSES, SOURCE_CSV, csv, datetime, fetch_json, ontology_term, pystac, re, render_thumbnail):
    HARVESTED = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)

    def build_item(row, extensions):
        zarr_url = row["url"].rstrip("/")
        uid = zarr_url.rsplit("/", 1)[-1].removesuffix(".zarr")
        zarr_meta = fetch_json(f"{zarr_url}/zarr.json", CACHE / uid / "zarr.json")
        crate = fetch_json(
            f"{zarr_url}/ro-crate-metadata.json", CACHE / uid / "ro-crate-metadata.json"
        )

        ome = zarr_meta.get("attributes", {}).get("ome", {})
        axis_names = [a["name"] for a in ome.get("multiscales", [{}])[0].get("axes", [])]
        # the CSV shape is positional: it only means something next to the axis names from zarr.json
        shape = [int(n) for n in row["shape"].split(",")] if row["shape"] else []

        # the crate says organism/method too, but the CSV columns are the challenge's own summary of it
        properties = {
            "title": row["name"],
            "description": row["description"],
            "license": LICENSES.get(row["license"], "other"),
            "bioimage:source": "bia",
            "bioimage:ngff_version": ome.get("version"),
            "bioimage:size_bytes": int(row["written"]) if row["written"] else None,
            **{f"bioimage:size_{name}": size for name, size in zip(axis_names, shape)},
            "bioimage:organism": ontology_term(row["organismId"], "ncbitaxon"),
            "bioimage:imaging_method": ontology_term(row["fbbiId"], "fbbi"),
        }

        item = pystac.Item(
            id=f"bia-{slug(row['name'])}",
            # ponytail: placeholder, not a location; STAC API backends require a geometry
            geometry={"type": "Point", "coordinates": [0.0, 0.0]},
            bbox=[0.0, 0.0, 0.0, 0.0],
            datetime=HARVESTED,
            properties=properties,
            stac_extensions=extensions,
        )
        item.add_asset(
            "data",
            pystac.Asset(
                href=zarr_url,
                media_type="application/vnd.zarr",
                roles=["data"],
                title="OME-Zarr",
            ),
        )
        item.add_asset(
            "zarr-metadata",
            pystac.Asset(
                href=f"{zarr_url}/zarr.json",
                media_type="application/json",
                roles=["metadata"],
                title="OME-Zarr metadata (zarr.json)",
            ),
        )
        item.add_asset(
            "ro-crate",
            pystac.Asset(
                href=f"{zarr_url}/ro-crate-metadata.json",
                media_type="application/ld+json",
                roles=["metadata"],
                title="RO-Crate metadata",
            ),
        )
        if row["origin"]:
            item.add_link(pystac.Link("via", row["origin"], title="Original study"))
        if row["license"] in LICENSES:
            item.add_link(pystac.Link("license", row["license"], title=LICENSES[row["license"]]))
        thumbnail = render_thumbnail(zarr_url, uid)
        if thumbnail:
            item.add_asset("thumbnail", pystac.Asset(
                href="./thumbnail.png", media_type="image/png", roles=["thumbnail"],
                title="Lowest resolution level, middle Z plane",
                extra_fields={"bioimage:rendered_from": str(thumbnail)},  # removed before save
            ))
        item.add_link(pystac.Link(
            "alternate", "./ro-crate-metadata.json", media_type="application/ld+json",
            title="This item as an RO-Crate",
        ))
        return item, crate

    def slug(title, limit=40):
        """'HeLa cells' -> 'hela-cells', cut at a word boundary so ids stay short."""
        words = re.sub(r"[^a-z0-9]+", " ", title.lower()).split()
        out = words[0]
        for word in words[1:]:
            if len(out) + 1 + len(word) > limit:
                break
            out += f"-{word}"
        return out

    def read_rows():
        with open(SOURCE_CSV, newline="") as f:
            return list(csv.DictReader(f))

    return HARVESTED, build_item, read_rows


@app.cell
def _(CACHE, GIDE_TERMS, HARVESTED, LICENSES, crate_json, datetime, fetch_json, json, pathlib, pystac, referenced_crate, urllib):
    GIDE_CRATES = "foundingGIDE/gide-data-deliverable/main/data_deliverable/GIDE_crates"

    def gide_crate(accession):
        """The GIDE study-level RO-Crate for a BIA/EMPIAR accession, or None if GIDE has none."""
        missing = CACHE.parent / "gide" / f"{accession}.missing"
        if missing.exists():
            return None
        url = f"https://raw.githubusercontent.com/{GIDE_CRATES}/{accession}-ro-crate-metadata.json"
        try:
            return fetch_json(url, CACHE.parent / "gide" / f"{accession}.json")
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            missing.parent.mkdir(parents=True, exist_ok=True)
            missing.touch()  # remember the 404 so re-runs stay offline
            return None

    def study_collection(accession, origin, members, crate):
        """One Collection per study: described by its GIDE crate when there is one."""
        root = {}
        if crate:
            graph = {node["@id"]: node for node in crate["@graph"]}
            root = graph[graph["ro-crate-metadata.json"]["about"]["@id"]]
        published = (
            datetime.datetime.fromisoformat(root["datePublished"]).replace(tzinfo=datetime.timezone.utc)
            if root.get("datePublished") else None
        )
        study = pystac.Collection(
            id=accession,
            title=root.get("name") or f"{accession} — {members[0].properties['title']}",
            description=root.get("description") or f"{accession}. No GIDE study crate is available for this study.",
            keywords=root.get("keywords") or None,
            license=LICENSES.get(root.get("license"), members[0].properties["license"]),
            extent=pystac.Extent(
                pystac.SpatialExtent([[0.0, 0.0, 0.0, 0.0]]),  # ponytail: same (0,0) placeholder
                pystac.TemporalExtent([[published or HARVESTED, published or HARVESTED]]),
            ),
        )
        if crate:
            # shipped with the catalog: ship_crate() copies it next to this collection.json
            study.add_asset("ro-crate", pystac.Asset(
                href="./ro-crate-metadata.json",
                media_type="application/ld+json",
                roles=["metadata"],
                title="GIDE study RO-Crate",
            ))
            study.add_link(pystac.Link(
                "via",
                f"https://github.com/{GIDE_CRATES.replace('/main/', '/blob/main/', 1)}/{accession}-ro-crate-metadata.json",
                title="GIDE study crate (source; context compacted)",
            ))
        for url in root.get("thumbnailUrl", [])[:1]:
            study.add_asset("thumbnail", pystac.Asset(href=url, media_type="image/png", roles=["thumbnail"]))
        first = next((m for m in members if "thumbnail" in m.assets), None)
        if "thumbnail" not in study.assets and first:
            study.add_asset("thumbnail", pystac.Asset(
                href=f"./{first.id}/thumbnail.png", media_type="image/png", roles=["thumbnail"],
                title=f"Thumbnail of {first.properties['title']}",
            ))
        study.add_link(pystac.Link("via", origin, title="Study page"))
        study.add_items(members)
        return study

    def ship_crate(study):
        """Write the cached GIDE crate next to the saved study collection.json, with the compact context.

        Returns (bytes as published, bytes as shipped), or None when the study has no crate."""
        if "ro-crate" not in study.assets:
            return None
        cached = CACHE.parent / "gide" / f"{study.id}.json"
        crate = json.loads(cached.read_text())
        # the inline terms GIDE's context lacks (bia:, rdf:seeAlso) must be unused, or dropping them loses data
        graph_text = json.dumps(crate["@graph"])
        dropped = {k for k in (crate["@context"][1:] or [{}])[0] if k not in GIDE_TERMS}
        assert not any(f'"{k}"' in graph_text or f'"{k}:' in graph_text for k in dropped), (study.id, dropped)
        graph = crate["@graph"]
        # shipped in a folder, the crate is attached: its root must be ./ to hold local entities.
        # GIDE's root id (the BioStudies URL) is kept as url; GIDE's own identifier (the accession) stays.
        old_root = next(d["about"]["@id"] for d in graph if d["@id"] == "ro-crate-metadata.json")
        graph = json.loads(json.dumps(graph).replace(json.dumps(old_root), '"./"'))
        root = next(n for n in graph if n["@id"] == "./")
        root.setdefault("identifier", old_root)
        root.setdefault("url", old_root)
        # down to the item crates, as nested crates
        for item in study.get_items():
            root.setdefault("hasPart", []).append({"@id": f"{item.id}/"})
            graph += referenced_crate(f"{item.id}/", item.properties["title"])
        target = pathlib.Path(study.self_href).parent / "ro-crate-metadata.json"
        target.write_text(crate_json(graph))
        return cached.stat().st_size, target.stat().st_size

    return gide_crate, ship_crate, study_collection


@app.cell
def _(json, pathlib, readable_dumps, urllib):
    # RO-Crate tooling requires the RO-Crate context by URL, and rejects GIDE's context URL next to it
    # (GIDE's file imports RO-Crate's again: "recursive context inclusion"). So: the RO-Crate URL, plus
    # only the GIDE term definitions a crate actually uses, taken from GIDE's published context.
    RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.2/context"
    GIDE_CONTEXT_URL = "https://www.gide-project.org/ro-crate/search/1.0/context"
    with urllib.request.urlopen(GIDE_CONTEXT_URL, timeout=60) as _response:
        GIDE_CONTEXT = json.load(_response)["@context"][1]
    GIDE_TERMS = set(GIDE_CONTEXT)

    def used_terms(graph):
        """The GIDE term definitions this graph uses, plus the prefixes those definitions rely on."""
        text = json.dumps(graph)
        used = {k for k in GIDE_CONTEXT if f'"{k}"' in text or f'"{k}:' in text}
        used |= {v["@id"].split(":")[0] for k, v in GIDE_CONTEXT.items()
                 if k in used and isinstance(v, dict) and v["@id"].split(":")[0] in GIDE_CONTEXT}
        return {k: v for k, v in GIDE_CONTEXT.items() if k in used}

    def crate_json(graph):
        # same layout as the STAC JSON: short objects on one line
        terms = used_terms(graph)
        context = [RO_CRATE_CONTEXT, terms] if terms else RO_CRATE_CONTEXT
        return readable_dumps({"@context": context, "@graph": graph}) + "\n"

    def obo_id(curie):
        """'NCBITaxon:9606' -> 'obo:NCBITaxon_9606', the form GIDE crates use."""
        return "obo:" + curie.replace(":", "_", 1)

    def write_item_crate(item):
        """The Item again, as an RO-Crate: one image, its remote assets, and its terms."""
        p = item.properties
        zarr = item.assets["data"].href
        via = {link.rel: link.href for link in item.links if link.rel in ("via", "license")}
        organism, method = p.get("bioimage:organism"), p.get("bioimage:imaging_method")
        root = {
            "@id": "./",
            "@type": "Dataset",
            "name": p["title"],
            "description": p["description"],
            "datePublished": item.datetime.date().isoformat(),
            # a Zarr is a folder: as an RO-Crate Dataset its id ends in /
            "hasPart": [{"@id": f"{zarr}/"}, {"@id": f"{zarr}/zarr.json"}, {"@id": f"{zarr}/ro-crate-metadata.json"}],
            "seeAlso": {"@id": f"./{item.id}.json"},
            **({"thumbnailUrl": [{"@id": "thumbnail.png"}]} if "thumbnail" in item.assets else {}),
        }
        if "license" in via:
            root["license"] = {"@id": via["license"]}
        study = item.get_parent()
        up = []
        if study is not None and "ro-crate" in study.assets:
            # up to the study crate, by relative path. Not a Dataset: a parent is not a data entity of
            # this crate (RO-Crate would then require it in our hasPart). The spec has no parent link.
            root["isPartOf"] = {"@id": "../"}
            up = [
                {"@id": "../", "@type": "CreativeWork", "name": study.title,
                 **({"url": via["via"]} if "via" in via else {}),
                 "subjectOf": {"@id": "../ro-crate-metadata.json"}},
                {"@id": "../ro-crate-metadata.json", "@type": "CreativeWork", "encodingFormat": "application/ld+json"},
            ]
        elif "via" in via:
            root["isPartOf"] = {"@id": via["via"]}
        if organism:
            root["about"] = [{"@id": obo_id(organism["term_id"])}]
        if method:
            root["measurementMethod"] = [{"@id": obo_id(method["term_id"])}]
        graph = [
            {"@id": "ro-crate-metadata.json", "@type": "CreativeWork",
             "conformsTo": {"@id": "https://w3id.org/ro/crate/1.2"}, "about": {"@id": "./"}},
            root,
            {"@id": f"{zarr}/", "@type": "Dataset", "name": "OME-Zarr", "encodingFormat": "application/vnd.zarr",
             **({"contentSize": str(p["bioimage:size_bytes"])} if p.get("bioimage:size_bytes") else {})},
            {"@id": f"{zarr}/zarr.json", "@type": "File", "name": "OME-Zarr metadata",
             "encodingFormat": "application/json"},
            {"@id": f"{zarr}/ro-crate-metadata.json", "@type": "File", "name": "Image RO-Crate (NGFF challenge)",
             "encodingFormat": "application/ld+json"},
        ]
        if "thumbnail" in item.assets:
            root["hasPart"].append({"@id": "thumbnail.png"})
            graph.append({"@id": "thumbnail.png", "@type": "File", "name": "Thumbnail",
                          "encodingFormat": "image/png"})
        if organism:
            graph.append({"@id": obo_id(organism["term_id"]), "@type": "Taxon", "scientificName": organism["term_label"]})
        if method:
            graph.append({"@id": obo_id(method["term_id"]), "@type": "DefinedTerm", "name": method["term_label"]})
        graph += up
        target = pathlib.Path(item.self_href).parent / "ro-crate-metadata.json"
        target.write_text(crate_json(graph))
        return target

    def referenced_crate(folder, name, url=None):
        """RO-Crate 1.2 'Referencing other RO-Crates': the crate as a Dataset that conforms to RO-Crate,
        plus its metadata document, linked with subjectOf. Relative folder ids keep it readable and movable."""
        return [
            {"@id": folder, "@type": "Dataset", "name": name, **({"url": url} if url else {}),
             "conformsTo": {"@id": "https://w3id.org/ro/crate"},
             "subjectOf": {"@id": f"{folder}ro-crate-metadata.json"}},
            {"@id": f"{folder}ro-crate-metadata.json", "@type": "CreativeWork", "encodingFormat": "application/ld+json"},
        ]

    return GIDE_TERMS, crate_json, referenced_crate, write_item_crate


@app.cell
def _(
    BIOIMAGE_EXT,
    HARVESTED,
    SOURCE_CSV_URL,
    Summarizer,
    build_item,
    gide_crate,
    pathlib,
    pystac,
    read_rows,
    ship_crate,
    study_collection,
    write_item_crate,
):
    rows = read_rows()
    items, crates, studies = [], {}, {}
    for _row in rows:
        _item, _crate = build_item(_row, [BIOIMAGE_EXT])
        items.append(_item)
        crates[_item.id] = _crate
        _accession = _row["origin"].rstrip("/").rsplit("/", 1)[-1]  # S-BIAD606, EMPIAR-10310
        studies.setdefault((_accession, _row["origin"]), []).append(_item)
    # ids come from titles, so they must stay unique
    assert len(crates) == len(items), "two titles produced the same item id"

    study_crates = {accession: gide_crate(accession) for accession, _ in studies}
    study_collections = [
        study_collection(accession, origin, members, study_crates[accession])
        for (accession, origin), members in sorted(studies.items())
    ]

    collection = pystac.Collection(
        id="bia",
        title="BIA / EBI — OME 2024 NGFF challenge",
        description=(
            "Images submitted by the BioImage Archive (EMBL-EBI) to the OME 2024 NGFF challenge. "
            "Harvested from the challenge sample list; the OME-Zarr data stays on EBI servers."
        ),
        license="various",
        extent=pystac.Extent(
            # ponytail: same (0,0) placeholder as the items
            pystac.SpatialExtent([[0.0, 0.0, 0.0, 0.0]]),
            pystac.TemporalExtent([[HARVESTED, HARVESTED]]),
        ),
        summaries=Summarizer(
            {
                "license": "v",
                "bioimage:ngff_version": "v",
                "bioimage:size_bytes": "r",
                "bioimage:size_x": "r",
                "bioimage:size_y": "r",
                "bioimage:size_z": "r",
            }
        ).summarize(items),
        extra_fields={
            "bioimage:source": "bia",
            "bioimage:organisms": sorted(
                {i.properties["bioimage:organism"]["term_label"] for i in items if i.properties["bioimage:organism"]}
            ),
            "bioimage:imaging_methods": sorted(
                {i.properties["bioimage:imaging_method"]["term_label"] for i in items if i.properties["bioimage:imaging_method"]}
            ),
            "bioimage:harvested": HARVESTED.isoformat(),
            "bioimage:source_csv": SOURCE_CSV_URL,
        },
    )
    collection.add_children(study_collections)
    collection.add_link(
        pystac.Link("via", SOURCE_CSV_URL, title="Challenge sample list")
    )
    collection.add_link(
        pystac.Link(
            "via", "https://www.ebi.ac.uk/bioimage-archive/", title="BioImage Archive"
        )
    )

    catalog = pystac.Catalog(
        id="biostac-challenge",
        description="STAC pilot over the OME 2024 NGFF challenge data.",
    )
    catalog.add_child(collection)
    thumbnail_sources = {
        _item.id: _item.assets["thumbnail"].extra_fields.pop("bioimage:rendered_from")
        for _item in items if "thumbnail" in _item.assets
    }
    catalog.normalize_hrefs("catalogs/challenge")
    catalog.save(pystac.CatalogType.SELF_CONTAINED)
    crate_sizes = {_study.id: ship_crate(_study) for _study in study_collections}
    for _item in items:
        if _item.id in thumbnail_sources:
            (pathlib.Path(_item.self_href).parent / "thumbnail.png").write_bytes(
                pathlib.Path(thumbnail_sources[_item.id]).read_bytes())
    item_crates = [write_item_crate(_item) for _item in items]
    return catalog, crate_sizes, crates, item_crates, items, rows, study_crates


@app.cell
def _(BIOIMAGE_EXT, JsonSchemaSTACValidator, catalog, json, set_validator):
    # the extension URI is not hosted: hand the local schema to the validator
    validator = JsonSchemaSTACValidator()
    with open("extensions/bioimage/v0.1.0/schema.json") as _f:
        validator.schema_cache[BIOIMAGE_EXT] = json.load(_f)
    set_validator(validator)
    n_valid = catalog.validate_all()
    return (n_valid,)


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
    mo.vstack(
        [
            mo.md(
                f"**{len(rows)}** rows → **{len(items)}** items, {n_valid} objects validated."
            ),
            mo.ui.table(findings, selection=None, pagination=False),
        ]
    )
    return


@app.cell
def _(crate_sizes, item_crates, items, mo, study_crates):
    missing = {
        field: [i.id for i in items if not i.properties.get(field)]
        for field in [
            "bioimage:ngff_version",
            "bioimage:organism",
            "bioimage:imaging_method",
            "description",
        ]
    }
    unlabelled = [
        i.id
        for i in items
        if (i.properties.get("bioimage:organism") or {}).get("term_label") is None
    ]
    mo.md(
        "## Findings\n"
        + "\n".join(f"- missing `{k}`: {v or 'none'}" for k, v in missing.items())
        + f"\n- organism terms OLS4 could not label: {unlabelled or 'none'}"
        + f"\n- studies with a GIDE study crate: {sum(c is not None for c in study_crates.values())} of {len(study_crates)}"
        + f"; without: {sorted(a for a, c in study_crates.items() if c is None) or 'none'}"
        + "\n- study crates, bytes as published → as shipped with the compact context: "
        + ", ".join(f"{k} {a:,} → {b:,}" for k, (a, b) in sorted((k, v) for k, v in crate_sizes.items() if v))
        + f"\n- item crates written: {len(item_crates)}, "
        + f"{min(p.stat().st_size for p in item_crates):,}–{max(p.stat().st_size for p in item_crates):,} bytes each"
    )
    return


if __name__ == "__main__":
    app.run()
