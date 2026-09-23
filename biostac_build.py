"""Shared build steps for the challenge catalogs (10_bia_catalog.py, 14_idr_catalog.py).

Each source harvests its own CSV rows; everything else, from fetching zarr.json to writing the
STAC + RO-Crate tree, is the same and lives here.
"""

import datetime
import json
import pathlib
import re
import shutil
import urllib.error
import urllib.parse
import urllib.request

import duckdb
import numpy as np
import pystac
import rustac
import zarr
from PIL import Image
from pystac.summaries import Summarizer
from pystac.validation import JsonSchemaSTACValidator, set_validator

from readable_stac_io import ReadableStacIO
from readable_stac_io import dumps as readable_dumps

pystac.StacIO.set_default(ReadableStacIO)  # short objects on one line, for human readers

CACHE = pathlib.Path("build_cache")
BIOIMAGE_EXT = "https://example.org/stac/bioimage/v0.1.0/schema.json"
LICENSES = {
    "https://creativecommons.org/licenses/by/4.0/": "CC-BY-4.0",
    "https://creativecommons.org/publicdomain/zero/1.0/": "CC0-1.0",
    "https://creativecommons.org/licenses/by-nc-sa/3.0/": "CC-BY-NC-SA-3.0",
}
PLACEHOLDER_BBOX = [0.0, 0.0, 0.0, 0.0]  # ponytail: not a location; STAC API backends require a geometry
RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.2/context"
GIDE_CONTEXT_URL = "https://www.gide-project.org/ro-crate/search/1.0/context"


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def web_url(url):
    """Percent-encode spaces and the like, so the URL is a valid href/IRI; already-encoded parts stay."""
    return urllib.parse.quote(url, safe=":/%?=&()#,+")


def fetch_json(url, cache_path):
    """Fetch once, then read from build_cache/ so re-runs are offline and reproducible."""
    path = pathlib.Path(cache_path)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(web_url(url), timeout=60) as response:
            path.write_bytes(response.read())
    return json.loads(path.read_text())


def fetch_bytes(url):
    """Raw bytes of a URL, for files that are not JSON (an annotation CSV, say)."""
    with urllib.request.urlopen(web_url(url), timeout=180) as response:
        return response.read()


def fetch_json_or_none(url, cache_path):
    """Like fetch_json, but a 404 is remembered and returns None."""
    missing = pathlib.Path(str(cache_path) + ".missing")
    if missing.exists():
        return None
    try:
        return fetch_json(url, cache_path)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        missing.parent.mkdir(parents=True, exist_ok=True)
        missing.touch()  # remember the 404 so re-runs stay offline
        return None


def slug(text, limit=40):
    """'HeLa cells' -> 'hela-cells', cut at a word boundary so ids stay short."""
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    out = words[0]
    for word in words[1:]:
        if len(out) + 1 + len(word) > limit:
            break
        out += f"-{word}"
    return out


# --- ontology terms ---------------------------------------------------------------------------

def ols_label(curie, ontology):
    """Resolve a term label from EBI OLS4. Returns None if the term is not found."""
    cache_path = CACHE / "labels" / f"{curie.replace(':', '_')}.json"
    url = f"https://www.ebi.ac.uk/ols4/api/terms?obo_id={curie}&ontology={ontology}&size=1"
    for attempt in range(2):  # OLS4 drops the occasional request
        try:
            terms = fetch_json(url, cache_path).get("_embedded", {}).get("terms", [])
        except urllib.error.URLError:
            continue
        return terms[0]["label"] if terms else None
    return None


def to_curie(raw):
    """'NCBI:txid9606', 'obo:FBbi_00000251' or 'http://purl.obolibrary.org/obo/NCBITaxon_9606' -> CURIE."""
    raw = raw.strip()
    if raw.startswith("NCBI:txid"):
        return f"NCBITaxon:{raw.removeprefix('NCBI:txid')}"
    raw = raw.removeprefix("http://purl.obolibrary.org/obo/").removeprefix("obo:")
    return raw.replace("_", ":", 1)


def ontology_term(raw, ontology):
    """Any taxon/FBbi spelling -> {ontology_source, term_id, term_label}."""
    if not raw:
        return None
    curie = to_curie(raw)
    return {"ontology_source": curie.split(":")[0], "term_id": curie, "term_label": ols_label(curie, ontology)}


def obo_id(curie):
    """'NCBITaxon:9606' -> 'obo:NCBITaxon_9606', the form GIDE crates use."""
    return "obo:" + curie.replace(":", "_", 1)


# --- OME-Zarr ---------------------------------------------------------------------------------

def image_group(zarr_url, cache_dir):
    """Where the pixels of an OME-Zarr are, per layout: (layout, group url, its zarr.json, root zarr.json).

    plate -> first well, first field;  bioformats2raw -> 0/;  image -> the root itself."""
    root = fetch_json(f"{zarr_url}/zarr.json", cache_dir / "zarr.json")
    ome = root.get("attributes", {}).get("ome", {})
    if "plate" in ome:
        well = ome["plate"]["wells"][0]["path"]
        well_meta = fetch_json(f"{zarr_url}/{well}/zarr.json", cache_dir / "well.json")
        field = well_meta["attributes"]["ome"]["well"]["images"][0]["path"]
        url = f"{zarr_url}/{well}/{field}"
        return "plate", url, fetch_json(f"{url}/zarr.json", cache_dir / "field.json"), root
    if "bioformats2raw.layout" in ome and "multiscales" not in ome:
        url = f"{zarr_url}/0"
        return "bioformats2raw", url, fetch_json(f"{url}/zarr.json", cache_dir / "image.json"), root
    return "image", zarr_url, root, root


def axis_names(group_meta):
    return [a["name"] for a in group_meta["attributes"]["ome"]["multiscales"][0]["axes"]]


def render_thumbnail(group_url, cache_key, size=256, max_pixels=2000 * 2000):
    """PNG of the lowest-resolution level, as the NGFF challenge site renders it in the browser:
    first timepoint, middle Z plane, active OMERO channels in their colours and windows.
    Cached under build_cache/thumbnails/; returns the PNG path, or None if the smallest level is too big."""
    target = CACHE / "thumbnails" / f"{cache_key}.png"
    if target.exists():
        return target
    group = zarr.open_group(web_url(group_url), mode="r")
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


# --- STAC ---------------------------------------------------------------------------------------

LEVELS = ("image", "plate", "well")  # what a row denotes: one image, a whole plate, or one well of a plate


def with_flat_terms(properties):
    """Add the ontology ids as flat columns next to their structs: dictionary-encoded, and the
    Parquet readers can filter and skip row groups on them (nested fields are awkward, and
    rustac's CQL2 misses them entirely)."""
    flat = {"bioimage:organism": "bioimage:ncbitaxon", "bioimage:imaging_method": "bioimage:fbbi"}
    out = {}
    for key, value in properties.items():
        out[key] = value
        if key in flat and value:
            out[flat[key]] = value["term_id"]
    return out


def make_item(item_id, zarr_url, properties, harvested, origin=None, license_url=None, level="image"):
    """A STAC Item for one OME-Zarr, with its data, zarr.json and image-crate assets."""
    properties = with_flat_terms({"bioimage:level": level, **properties})
    item = pystac.Item(
        id=item_id,
        geometry={"type": "Point", "coordinates": [0.0, 0.0]},
        bbox=PLACEHOLDER_BBOX,
        datetime=harvested,
        properties=properties,
        stac_extensions=[BIOIMAGE_EXT],
    )
    item.add_asset("data", pystac.Asset(
        href=zarr_url, media_type="application/vnd.zarr", roles=["data"], title="OME-Zarr"))
    item.add_asset("zarr-metadata", pystac.Asset(
        href=f"{zarr_url}/zarr.json", media_type="application/json", roles=["metadata"],
        title="OME-Zarr metadata (zarr.json)"))
    item.add_asset("ro-crate", pystac.Asset(
        href=f"{zarr_url}/ro-crate-metadata.json", media_type="application/ld+json", roles=["metadata"],
        title="RO-Crate metadata"))
    if origin:
        item.add_link(pystac.Link("via", origin, title="Original study"))
    if license_url in LICENSES:
        item.add_link(pystac.Link("license", license_url, title=LICENSES[license_url]))
    return item


def add_thumbnail(item, rendered=None, remote=None):
    """A rendered PNG ships next to the Item; a remote one (e.g. IDR's own) is linked."""
    if rendered:
        item.add_asset("thumbnail", pystac.Asset(
            href="./thumbnail.png", media_type="image/png", roles=["thumbnail"],
            title="Lowest resolution level, middle Z plane",
            extra_fields={"bioimage:rendered_from": str(rendered)},  # removed before save
        ))
    elif remote:
        item.add_asset("thumbnail", pystac.Asset(
            href=remote, media_type="image/jpeg", roles=["thumbnail"], title="Thumbnail from the source"))


def add_crate_link(item):
    item.add_link(pystac.Link(
        "alternate", "./ro-crate-metadata.json", media_type="application/ld+json",
        title="This item as an RO-Crate",
    ))


def crate_root(crate):
    """The descriptor and root entity of an RO-Crate, whatever the descriptor is called."""
    descriptor = next(
        n for n in crate["@graph"]
        if str(n["@id"]).endswith("ro-crate-metadata.json") and "about" in n
        and "ro/crate" in str((n.get("conformsTo") or {}).get("@id", ""))
    )
    root = next(n for n in crate["@graph"] if n["@id"] == descriptor["about"]["@id"])
    return descriptor, root


def study_collection(accession, members, crate, harvested, study_page, crate_source=None,
                     crate_title="Study RO-Crate", fallback_description=None):
    """crate_source: (href, title) of where the study crate was published, linked as via."""
    """One Collection per study: described by its study crate when there is one."""
    root = crate_root(crate)[1] if crate else {}
    published = (
        datetime.datetime.fromisoformat(root["datePublished"]).replace(tzinfo=datetime.timezone.utc)
        if root.get("datePublished") else None
    )
    license_ = root.get("license")
    license_ = license_.get("@id") if isinstance(license_, dict) else license_
    study = pystac.Collection(
        id=accession,
        title=root.get("name") or f"{accession} — {members[0].properties['title']}",
        description=root.get("description") or fallback_description
        or f"{accession}. No study crate is available for this study.",
        keywords=root.get("keywords") or None,
        license=LICENSES.get(license_, members[0].properties["license"]),
        extent=pystac.Extent(
            pystac.SpatialExtent([PLACEHOLDER_BBOX]),
            pystac.TemporalExtent([[published or harvested, published or harvested]]),
        ),
    )
    if crate:
        # shipped with the catalog: ship_crate() writes it next to this collection.json
        study.add_asset("ro-crate", pystac.Asset(
            href="./ro-crate-metadata.json", media_type="application/ld+json", roles=["metadata"],
            title=crate_title,
        ))
        if crate_source:
            study.add_link(pystac.Link("via", crate_source[0], title=crate_source[1]))
    thumbnails = root.get("thumbnailUrl", [])
    for url in (thumbnails if isinstance(thumbnails, list) else [thumbnails])[:1]:
        url = url.get("@id") if isinstance(url, dict) else url
        kind = "image/png" if url.lower().endswith(".png") else "image/jpeg" if "render_thumbnail" in url else None
        study.add_asset("thumbnail", pystac.Asset(href=url, media_type=kind, roles=["thumbnail"]))
    first = next((m for m in members if "thumbnail" in m.assets), None)
    if "thumbnail" not in study.assets and first:
        href = first.assets["thumbnail"].href
        study.add_asset("thumbnail", pystac.Asset(
            href=f"./{first.id}/thumbnail.png" if href == "./thumbnail.png" else href,
            media_type=first.assets["thumbnail"].media_type, roles=["thumbnail"],
            title=f"Thumbnail of {first.properties['title']}",
        ))
    if study_page:
        study.add_link(pystac.Link("via", study_page, title="Study page"))
    study.add_items(members)
    return study


def resource_collection(source, title, description, studies, items, harvested, links=(), extra_fields=None):
    collection = pystac.Collection(
        id=source,
        title=title,
        description=description,
        license="various",
        extent=pystac.Extent(
            pystac.SpatialExtent([PLACEHOLDER_BBOX]),
            pystac.TemporalExtent([[harvested, harvested]]),
        ),
        summaries=Summarizer({
            "license": "v", "bioimage:ngff_version": "v", "bioimage:size_bytes": "r",
            "bioimage:size_x": "r", "bioimage:size_y": "r", "bioimage:size_z": "r",
        }).summarize(items),
        extra_fields={
            "bioimage:source": source,
            "bioimage:organisms": sorted({
                i.properties["bioimage:organism"]["term_label"] or i.properties["bioimage:organism"]["term_id"]
                for i in items if i.properties.get("bioimage:organism")}),
            "bioimage:imaging_methods": sorted({
                i.properties["bioimage:imaging_method"]["term_label"] or i.properties["bioimage:imaging_method"]["term_id"]
                for i in items if i.properties.get("bioimage:imaging_method")}),
            "bioimage:harvested": harvested.isoformat(),
            **(extra_fields or {}),
        },
    )
    collection.add_children(studies)
    for href, link_title in links:
        collection.add_link(pystac.Link("via", href, title=link_title))
    return collection


def validate(catalog):
    """validate_all() with the bioimage extension schema, which is not hosted, handed in locally."""
    validator = JsonSchemaSTACValidator()
    with open("extensions/bioimage/v0.1.0/schema.json") as f:
        validator.schema_cache[BIOIMAGE_EXT] = json.load(f)
    set_validator(validator)
    return catalog.validate_all()


# --- RO-Crate ------------------------------------------------------------------------------------
# RO-Crate tooling requires the RO-Crate context by URL, and rejects GIDE's context URL next to it
# (GIDE's file imports RO-Crate's again: "recursive context inclusion"). So: the RO-Crate URL, plus
# only the GIDE term definitions a crate actually uses, taken from GIDE's published context.

_gide_context = None


def gide_context():
    global _gide_context
    if _gide_context is None:
        _gide_context = fetch_json(GIDE_CONTEXT_URL, CACHE / "gide-search-context.json")["@context"][1]
    return _gide_context


def used_terms(graph):
    """The GIDE term definitions this graph uses, plus the prefixes those definitions rely on."""
    context, text = gide_context(), json.dumps(graph)
    used = {k for k in context if f'"{k}"' in text or f'"{k}:' in text}
    used |= {v["@id"].split(":")[0] for k, v in context.items()
             if k in used and isinstance(v, dict) and v["@id"].split(":")[0] in context}
    return {k: v for k, v in context.items() if k in used}


def crate_json(graph):
    # same layout as the STAC JSON: short objects on one line
    terms = used_terms(graph)
    context = [RO_CRATE_CONTEXT, terms] if terms else RO_CRATE_CONTEXT
    return readable_dumps({"@context": context, "@graph": graph}) + "\n"


def referenced_crate(folder, name, url=None):
    """RO-Crate 1.2 'Referencing other RO-Crates': the crate as a Dataset that conforms to RO-Crate,
    plus its metadata document, linked with subjectOf. Relative folder ids keep it readable and movable."""
    return [
        {"@id": folder, "@type": "Dataset", "name": name, **({"url": url} if url else {}),
         "conformsTo": {"@id": "https://w3id.org/ro/crate"},
         "subjectOf": {"@id": f"{folder}ro-crate-metadata.json"}},
        {"@id": f"{folder}ro-crate-metadata.json", "@type": "CreativeWork", "encodingFormat": "application/ld+json"},
    ]


def ship_crate(study, crate, cached_path):
    """Write a study crate next to the saved study collection.json, as an attached RO-Crate 1.2:
    compact context, descriptor named ro-crate-metadata.json, root ./, and nested item crates.

    Returns (bytes as published, bytes as shipped)."""
    # inline terms the GIDE context lacks must be unused, or dropping them loses data
    graph_text = json.dumps(crate["@graph"])
    inline = next((c for c in (crate["@context"] if isinstance(crate["@context"], list) else []) if isinstance(c, dict)), {})
    dropped = {k for k in inline if k not in gide_context()}
    assert not any(f'"{k}"' in graph_text or f'"{k}:' in graph_text for k in dropped), (study.id, dropped)

    descriptor, root = crate_root(crate)
    old_descriptor, old_root = descriptor["@id"], root["@id"]
    # RO-Crate 1.2: the descriptor MUST be ro-crate-metadata.json; the root of an attached crate is ./
    text = json.dumps(crate["@graph"])
    text = text.replace(json.dumps(old_descriptor), '"ro-crate-metadata.json"')
    text = text.replace(json.dumps(old_root), '"./"')
    graph = json.loads(text)
    root = next(n for n in graph if n["@id"] == "./")
    root.setdefault("identifier", old_root)  # keeps the source's own identifier when it has one
    root.setdefault("url", old_root)
    for item in study.get_items():
        root.setdefault("hasPart", []).append({"@id": f"{item.id}/"})
        graph += referenced_crate(f"{item.id}/", item.properties["title"])
    target = pathlib.Path(study.self_href).parent / "ro-crate-metadata.json"
    target.write_text(crate_json(graph))
    return pathlib.Path(cached_path).stat().st_size, target.stat().st_size


def write_item_crate(item, extra_parts=()):
    """The Item again, as an RO-Crate: one image, its remote assets, and its terms.

    extra_parts: more remote Datasets inside the Zarr (e.g. plate wells), as (url, name) pairs."""
    p = item.properties
    zarr_url = item.assets["data"].href
    via = {link.rel: link.href for link in item.links if link.rel in ("via", "license")}
    organism, method = p.get("bioimage:organism"), p.get("bioimage:imaging_method")
    zarr_node = {"@id": f"{zarr_url}/", "@type": "Dataset", "name": "OME-Zarr",  # a folder: id ends in /
                 "encodingFormat": "application/vnd.zarr",
                 **({"contentSize": str(p["bioimage:size_bytes"])} if p.get("bioimage:size_bytes") else {})}
    if extra_parts:
        zarr_node["hasPart"] = [{"@id": url} for url, _ in extra_parts]
    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": p["title"],
        # RO-Crate requires a description; STAC forbids an empty one, so the Item may have none
        "description": p.get("description") or f"{p['title']}. The source gives no description.",
        "datePublished": item.datetime.date().isoformat(),
        "hasPart": [{"@id": f"{zarr_url}/"}, {"@id": f"{zarr_url}/zarr.json"},
                    {"@id": f"{zarr_url}/ro-crate-metadata.json"}],
        "seeAlso": {"@id": f"./{item.id}.json"},
    }
    thumbnail = item.assets.get("thumbnail")
    if thumbnail:
        local = thumbnail.href == "./thumbnail.png"
        root["thumbnailUrl"] = [{"@id": "thumbnail.png" if local else thumbnail.href}]
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
        zarr_node,
        {"@id": f"{zarr_url}/zarr.json", "@type": "File", "name": "OME-Zarr metadata",
         "encodingFormat": "application/json"},
        {"@id": f"{zarr_url}/ro-crate-metadata.json", "@type": "File", "name": "Image RO-Crate (NGFF challenge)",
         "encodingFormat": "application/ld+json"},
    ]
    graph += [{"@id": url, "@type": "Dataset", "name": name} for url, name in extra_parts]
    if thumbnail and thumbnail.href == "./thumbnail.png":
        root["hasPart"].append({"@id": "thumbnail.png"})
        graph.append({"@id": "thumbnail.png", "@type": "File", "name": "Thumbnail", "encodingFormat": "image/png"})
    if organism:
        graph.append({"@id": obo_id(organism["term_id"]), "@type": "Taxon", "scientificName": organism["term_label"]})
    if method:
        graph.append({"@id": obo_id(method["term_id"]), "@type": "DefinedTerm", "name": method["term_label"]})
    graph += up
    target = pathlib.Path(item.self_href).parent / "ro-crate-metadata.json"
    target.write_text(crate_json(graph))
    return target


# --- writing the tree ---------------------------------------------------------------------------

ROW_GROUP_SIZE = 50_000


def merge_geoparquet(source, path, sort_by=("collection", "id"), row_group_size=ROW_GROUP_SIZE):
    """Rewrite stac-geoparquet (one file, or a glob of parts) laid out for search: sorted by the columns
    people filter on, with statistics on every column. rustac leaves statistics off the string columns,
    and without them a reader cannot skip row groups at all."""
    path = pathlib.Path(path)
    stac = duckdb.sql(f"""SELECT decode(value) FROM parquet_kv_metadata('{source}')
                          WHERE decode(key) = 'stac-geoparquet' LIMIT 1""").fetchone()[0]
    order = ", ".join(f'"{column}"' for column in sort_by)
    # DuckDB writes the 'geo' key itself; passing ours too would duplicate it
    duckdb.sql(f"""COPY (SELECT * FROM read_parquet('{source}', union_by_name := true) ORDER BY {order})
                   TO '{path}' (FORMAT parquet, COMPRESSION zstd,
                                ROW_GROUP_SIZE {row_group_size}, KV_METADATA {{'stac-geoparquet': {stac!r}}})""")
    return path


async def write_geoparquet(items, path, sort_by=("collection", "id"), row_group_size=ROW_GROUP_SIZE):
    """rustac writes the file, because it gets the STAC metadata right, then merge_geoparquet lays it out."""
    path = pathlib.Path(path)
    raw = path.with_name(path.stem + ".raw.parquet")  # rustac picks the format from the extension
    await rustac.write(str(raw), items)
    merge_geoparquet(raw, path, sort_by, row_group_size)
    raw.unlink()
    return path


ROOT_CATALOG = pathlib.Path("catalogs/challenge/catalog.json")


def save_resource(resource, items, studies, study_crates, extra_parts=None, root_path=ROOT_CATALOG):
    """Save one resource's subtree under the shared root catalog, leaving the other resources alone.
    Then ship study crates, copy rendered thumbnails, and write item crates.

    study_crates: {accession: (crate, cached path)}; extra_parts: {item id: [(url, name), ...]}."""
    rendered = {
        item.id: item.assets["thumbnail"].extra_fields.pop("bioimage:rendered_from")
        for item in items
        if "thumbnail" in item.assets and "bioimage:rendered_from" in item.assets["thumbnail"].extra_fields
    }
    root_path = pathlib.Path(root_path)
    if root_path.exists():
        root = pystac.Catalog.from_file(str(root_path))
        root.remove_child(resource.id)  # replaces this resource; the others stay as they are
    else:
        root = pystac.Catalog(id="biostac-challenge", description="STAC pilot over the OME 2024 NGFF challenge data.")
    root.set_self_href(str(root_path))
    root.add_child(resource)
    # generated output: clear this resource's folder so renamed or removed items leave nothing stale
    shutil.rmtree(root_path.parent / resource.id, ignore_errors=True)
    resource.normalize_hrefs(str(root_path.parent / resource.id))
    resource.save(pystac.CatalogType.SELF_CONTAINED)
    root.save_object(include_self_link=False)
    crate_sizes = {
        study.id: ship_crate(study, *study_crates[study.id])
        for study in studies if study_crates.get(study.id)
    }
    for item in items:
        if item.id in rendered:
            (pathlib.Path(item.self_href).parent / "thumbnail.png").write_bytes(
                pathlib.Path(rendered[item.id]).read_bytes())
    item_crates = [write_item_crate(item, (extra_parts or {}).get(item.id, ())) for item in items]
    return crate_sizes, item_crates
