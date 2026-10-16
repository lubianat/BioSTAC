"""Shared build steps for the challenge catalogs (10_bia_catalog.py, 14_idr_catalog.py, 19_other_catalogs.py).

Each source harvests its own CSV rows; everything else, from fetching zarr.json to writing the
RO-Crate tree and its Parquet lists, is the same and lives here.
"""

import datetime
import hashlib
import json
import pathlib
import re
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request

import duckdb
import numpy as np
import zarr
from PIL import Image

CACHE = pathlib.Path("build_cache")
CHALLENGE = pathlib.Path("catalogs/challenge")
LICENSES = {
    "https://creativecommons.org/licenses/by/4.0/": "CC-BY-4.0",
    "https://creativecommons.org/publicdomain/zero/1.0/": "CC0-1.0",
    "https://creativecommons.org/licenses/by-nc-sa/3.0/": "CC-BY-NC-SA-3.0",
}
RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.2/context"
RO_CRATE_SPEC = "https://w3id.org/ro/crate/1.2"
GIDE_CONTEXT_URL = "https://www.gide-project.org/ro-crate/search/1.0/context"
PARQUET = "application/vnd.apache.parquet"
CRATE = "ro-crate-metadata.json"
LINE_WIDTH = 100


def dumps(value, indent=0):
    """Like json.dumps(indent=2), but any container that fits in LINE_WIDTH stays on one line."""
    flat = json.dumps(value, ensure_ascii=False)
    if not isinstance(value, (dict, list)) or not value or indent + len(flat) <= LINE_WIDTH:
        return flat
    pad = " " * (indent + 2)
    if isinstance(value, dict):
        lines = [f"{pad}{json.dumps(k, ensure_ascii=False)}: {dumps(v, indent + 2)}" for k, v in value.items()]
        return "{\n" + ",\n".join(lines) + "\n" + " " * indent + "}"
    lines = [f"{pad}{dumps(v, indent + 2)}" for v in value]
    return "[\n" + ",\n".join(lines) + "\n" + " " * indent + "]"


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



# --- item rows ------------------------------------------------------------------------------------
# One row per image, plate or well, as a plain dict. Rows become a study's item-list.parquet; the
# BioSTAC item crate says the same thing again, for RO-Crate clients.

LEVELS = ("image", "plate", "well")  # what a row denotes: one image, a whole plate, or one well of a plate


def with_flat_terms(properties):
    """Add the ontology ids as flat columns next to their structs: dictionary-encoded, and Parquet
    readers can filter and skip row groups on them (nested fields are awkward to filter on)."""
    flat = {"bioimage:organism": ("bioimage:ncbitaxon", "NCBITaxon:"),
            "bioimage:imaging_method": ("bioimage:fbbi", "FBbi:")}
    out = {}
    for key, value in properties.items():
        out[key] = value
        # a source may name a term from another ontology (IDR crates use NCIT for some methods):
        # the struct keeps it, the flat column only takes ids of the ontology it is named after
        if key in flat and value and value["term_id"].startswith(flat[key][1]):
            out[flat[key][0]] = value["term_id"]
    return out


def make_item(item_id, zarr_url, properties, harvested, origin=None, license_url=None, level="image"):
    """One row for one OME-Zarr. URLs are absolute, except files BioSTAC ships, which are relative to
    the item-list.parquet (and so to the study folder)."""
    return with_flat_terms({
        "id": item_id,
        "bioimage:level": level,
        **properties,
        "date_published": harvested.date().isoformat(),
        "zarr_url": zarr_url,
        "zarr_metadata_url": f"{zarr_url}/zarr.json",
        "ro_crate_url": f"{zarr_url}/{CRATE}",  # the image's own crate, written by the challenge converter
        "crate_href": f"{item_id}/{CRATE}",  # BioSTAC's crate of this item
        "origin_url": origin,
        "license_url": license_url,
    })


def add_thumbnail(item, rendered=None, remote=None):
    """A rendered PNG ships next to the item crate; a remote one (e.g. IDR's own) is linked."""
    if rendered:
        item["thumbnail_url"] = f"{item['id']}/thumbnail.png"
        item["_rendered"] = str(rendered)  # copied into place by save_resource, never written to the list
    elif remote:
        item["thumbnail_url"] = remote


ROW_GROUP_SIZE = 8192  # small groups: a reader asking for a range of rows (the images, say) fetches little else


def _clean(row):
    return {k: v for k, v in row.items() if v is not None and not k.startswith("_")}


def write_list(rows, path, keep_from=None):
    """Write rows as Parquet, sorted by level then id. Images and plates sort before wells, so they are the
    first rows of the file, and a reader takes them by row range (study-list.parquet counts them). keep_from: an existing list whose rows of the other levels are kept (wells, say)."""
    path = pathlib.Path(path)
    with tempfile.TemporaryDirectory() as scratch:
        source = pathlib.Path(scratch) / "rows.ndjson"
        source.write_text("".join(json.dumps(_clean(r), default=str) + "\n" for r in rows))
        query = f"SELECT * FROM read_json_auto('{source}', sample_size=-1)"
        if keep_from:
            levels = ", ".join(f"'{lv}'" for lv in sorted({r["bioimage:level"] for r in rows}))
            query = (f"""SELECT * FROM read_parquet('{keep_from}') WHERE "bioimage:level" NOT IN ({levels})"""
                     f" UNION ALL BY NAME {query}")
        target = pathlib.Path(scratch) / "list.parquet"  # keep_from may be path itself
        duckdb.sql(f"""COPY ({query} ORDER BY "bioimage:level", id) TO '{target}'
                       (FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_SIZE})""")
        shutil.move(target, path)
    return path


def read_list(path, level=None):
    """Rows of an item list as dicts, optionally of one level."""
    where = f"""WHERE "bioimage:level" = '{level}'""" if level else ""
    result = duckdb.sql(f"SELECT * FROM read_parquet('{path}') {where} ORDER BY id")
    return [dict(zip(result.columns, r)) for r in result.fetchall()]


def crate_root(crate):
    """The descriptor and root entity of an RO-Crate, whatever the descriptor is called."""
    descriptor = next(
        n for n in crate["@graph"]
        if str(n["@id"]).endswith("ro-crate-metadata.json") and "about" in n
        and "ro/crate" in str((n.get("conformsTo") or {}).get("@id", ""))
    )
    root = next(n for n in crate["@graph"] if n["@id"] == descriptor["about"]["@id"])
    return descriptor, root


def crate_published(crate):
    root = crate_root(crate)[1] if crate else {}
    return (
        datetime.datetime.fromisoformat(root["datePublished"]).replace(tzinfo=datetime.timezone.utc)
        if root.get("datePublished") else None
    )



def image_crate_terms(crate):
    """(taxon, FBbi method, license) an image's own crate names, or Nones; the challenge converter wrote
    them on the root or on the biosample / imaging entities, depending on the provider."""
    if not crate:
        return None, None, None
    text = json.dumps(crate)
    taxon = re.search(r"NCBITaxon_\d+|NCBI:txid\d+", text)
    fbbi = re.search(r"FBbi_\d+", text)
    try:
        license_ = crate_root(crate)[1].get("license")
    except StopIteration:  # no RO-Crate descriptor: not every provider wrote one
        license_ = None
    license_ = license_.get("@id") if isinstance(license_, dict) else license_
    return taxon and taxon.group(0), fbbi and fbbi.group(0), license_


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
    terms = used_terms(graph)
    context = [RO_CRATE_CONTEXT, terms] if terms else RO_CRATE_CONTEXT
    return dumps({"@context": context, "@graph": graph}) + "\n"


def descriptor():
    return {"@id": CRATE, "@type": "CreativeWork", "conformsTo": {"@id": RO_CRATE_SPEC}, "about": {"@id": "./"}}


def replace_at_ids(node, old, new):
    """Rewrite matching JSON-LD @id values without touching non-identifier properties such as url."""
    if isinstance(node, list):
        return [replace_at_ids(value, old, new) for value in node]
    if isinstance(node, dict):
        return {
            key: (new if key == "@id" and value == old else replace_at_ids(value, old, new))
            for key, value in node.items()
        }
    return node


def referenced_crate(folder, name, url=None):
    """RO-Crate 1.2 'Referencing other RO-Crates': the crate as a Dataset that conforms to RO-Crate,
    plus its metadata document, linked with subjectOf. Relative folder ids keep it readable and movable."""
    return [
        {"@id": folder, "@type": "Dataset", "name": name, **({"url": url} if url else {}),
         "conformsTo": {"@id": "https://w3id.org/ro/crate"},
         "subjectOf": {"@id": f"{folder}{CRATE}"}},
        {"@id": f"{folder}{CRATE}", "@type": "CreativeWork", "encodingFormat": "application/ld+json"},
    ]


def as_list(value):
    return value if isinstance(value, list) else [] if value is None else [value]


def add_file(graph, path, description):
    """A file shipped in the crate's folder, as a File in the root's hasPart: size and sha256, so a
    reader can tell a stale copy. Replaces the entity if the file was registered before."""
    path = pathlib.Path(path)
    data = path.read_bytes()
    entity = {"@id": path.name, "@type": "File", "name": path.name, "description": description,
              "encodingFormat": PARQUET if path.suffix == ".parquet" else None,
              "contentSize": str(len(data)), "sha256": hashlib.sha256(data).hexdigest()}
    graph[:] = [n for n in graph if n["@id"] != path.name] + [{k: v for k, v in entity.items() if v}]
    root = next(n for n in graph if n["@id"] == "./")
    parts = as_list(root.get("hasPart"))
    if {"@id": path.name} not in parts:
        root["hasPart"] = parts + [{"@id": path.name}]
    return graph


def register_file(folder, path, description):
    """add_file on a crate already on disk (a list rewritten after the crate was)."""
    crate_path = pathlib.Path(folder) / CRATE
    crate = json.loads(crate_path.read_text())
    crate_path.write_text(crate_json(add_file(crate["@graph"], path, description)))


def attached(crate, accession):
    """A published study crate as an attached RO-Crate 1.2: descriptor ro-crate-metadata.json, root ./,
    compact context. The source's own identifier and url are kept."""
    # inline terms the GIDE context lacks must be unused, or dropping them loses data
    graph_text = json.dumps(crate["@graph"])
    inline = next((c for c in as_list(crate["@context"]) if isinstance(c, dict)), {})
    dropped = {k for k in inline if k not in gide_context()}
    assert not any(f'"{k}"' in graph_text or f'"{k}:' in graph_text for k in dropped), (accession, dropped)
    old_descriptor, old_root = (n["@id"] for n in crate_root(crate))
    graph = replace_at_ids(crate["@graph"], old_descriptor, CRATE)
    graph = replace_at_ids(graph, old_root, "./")
    root = next(n for n in graph if n["@id"] == "./")
    root.setdefault("identifier", old_root)  # keeps the source's own identifier when it has one
    root.setdefault("url", old_root)
    return graph


def generated_crate(name, description, items, harvested, url=None):
    """A study crate BioSTAC writes itself, where the source publishes none: its taxa and imaging
    methods are those of its items."""
    taxa = {i["bioimage:organism"]["term_id"]: i["bioimage:organism"] for i in items if i.get("bioimage:organism")}
    methods = {i["bioimage:imaging_method"]["term_id"]: i["bioimage:imaging_method"]
               for i in items if i.get("bioimage:imaging_method")}
    licenses = {i.get("license_url") for i in items} - {None}
    root = {"@id": "./", "@type": "Dataset", "name": name, "description": description,
            "datePublished": harvested.date().isoformat(),
            **({"license": {"@id": licenses.pop()}} if len(licenses) == 1 else {}),
            **({"url": url} if url else {}),
            **({"about": [{"@id": obo_id(t)} for t in taxa]} if taxa else {}),
            **({"measurementMethod": [{"@id": obo_id(m)} for m in methods]} if methods else {})}
    return [descriptor(), root,
            *({"@id": obo_id(t), "@type": "Taxon", "scientificName": v["term_label"] or t} for t, v in taxa.items()),
            *({"@id": obo_id(m), "@type": "DefinedTerm", "name": v["term_label"] or m} for m, v in methods.items())]


def study_graph(study, harvested):
    """The study crate: the source's, attached, or one BioSTAC generates; plus what the gallery reads
    from the root (name, description, license, thumbnail), filled in where the source gives none."""
    items, accession = study["items"], study["id"]
    graph = attached(study["crate"], accession) if study.get("crate") else generated_crate(
        f"{accession} — {items[0]['title']}",
        study.get("description") or f"{accession}. No study crate is available for this study.",
        items, harvested, study.get("page"))
    root = next(n for n in graph if n["@id"] == "./")
    # RO-Crate requires both, and a source crate may give them empty
    root["name"] = root.get("name") or f"{accession} — {items[0]['title']}"
    root["description"] = root.get("description") or f"{accession}. The study crate gives no description."
    root.setdefault("identifier", accession)
    if study.get("page"):
        root.setdefault("url", study["page"])
    if not root.get("license"):
        licenses = {i.get("license_url") for i in items} - {None}
        if len(licenses) == 1:
            root["license"] = {"@id": licenses.pop()}
    first = next((i["thumbnail_url"] for i in items if i.get("thumbnail_url")), None)
    if first and not root.get("thumbnailUrl"):
        root["thumbnailUrl"] = first if first.startswith("http") else {"@id": first}
    if study.get("crate_source"):
        root["isBasedOn"] = {"@id": study["crate_source"]}
    return graph


def write_item_crate(item, folder, study_name, extra_parts=()):
    """The item row again, as an RO-Crate: one image, its remote parts, and its terms.

    extra_parts: more remote Datasets inside the Zarr (e.g. plate wells), as (url, name) pairs."""
    zarr_url = item["zarr_url"]
    organism, method = item.get("bioimage:organism"), item.get("bioimage:imaging_method")
    zarr_node = {"@id": f"{zarr_url}/", "@type": "Dataset", "name": "OME-Zarr",  # a folder: id ends in /
                 "encodingFormat": "application/vnd.zarr",
                 **({"contentSize": str(item["bioimage:size_bytes"])} if item.get("bioimage:size_bytes") else {})}
    if extra_parts:
        zarr_node["hasPart"] = [{"@id": url} for url, _ in extra_parts]
    root = {
        "@id": "./",
        "@type": "Dataset",
        "name": item["title"],
        # RO-Crate requires a description, and the list holds no empty strings
        "description": item.get("description") or f"{item['title']}. The source gives no description.",
        "datePublished": item["date_published"],
        "hasPart": [{"@id": f"{zarr_url}/"}, {"@id": f"{zarr_url}/zarr.json"}],
        # up to the study crate, by relative path. Not a Dataset: a parent is not a data entity of
        # this crate (RO-Crate would then require it in our hasPart). The spec has no parent link.
        "isPartOf": {"@id": "../"},
    }
    graph = [descriptor(), root, zarr_node,
             {"@id": f"{zarr_url}/zarr.json", "@type": "File", "name": "OME-Zarr metadata",
              "encodingFormat": "application/json"}]
    if item.get("ro_crate_url"):
        root["hasPart"].append({"@id": item["ro_crate_url"]})
        graph.append({"@id": item["ro_crate_url"], "@type": "File", "name": "Image RO-Crate (NGFF challenge)",
                      "encodingFormat": "application/ld+json"})
    graph += [{"@id": url, "@type": "Dataset", "name": name} for url, name in extra_parts]
    thumbnail = item.get("thumbnail_url")
    if thumbnail:
        local = not thumbnail.startswith("http")
        root["thumbnailUrl"] = [{"@id": "thumbnail.png" if local else thumbnail}]
        if local:
            root["hasPart"].append({"@id": "thumbnail.png"})
            graph.append({"@id": "thumbnail.png", "@type": "File", "name": "Thumbnail", "encodingFormat": "image/png"})
    if item.get("license_url"):
        root["license"] = {"@id": item["license_url"]}
    if organism:
        root["about"] = [{"@id": obo_id(organism["term_id"])}]
        graph.append({"@id": obo_id(organism["term_id"]), "@type": "Taxon", "scientificName": organism["term_label"]})
    if method:
        root["measurementMethod"] = [{"@id": obo_id(method["term_id"])}]
        graph.append({"@id": obo_id(method["term_id"]), "@type": "DefinedTerm", "name": method["term_label"]})
    graph += [
        {"@id": "../", "@type": "CreativeWork", "name": study_name, "subjectOf": {"@id": f"../{CRATE}"}},
        {"@id": f"../{CRATE}", "@type": "CreativeWork", "encodingFormat": "application/ld+json"},
    ]
    target = folder / CRATE
    target.write_text(crate_json(graph))
    return target


# --- writing the tree ---------------------------------------------------------------------------

# RO-Crate 1.2 requires a license on every root. A catalog crate holds only BioSTAC's own metadata about
# its children (each child keeps its own license), so it is offered as CC0, as BIA and IDR do for metadata.
CATALOG_LICENSE = "https://creativecommons.org/publicdomain/zero/1.0/"


def catalog_graph(name, description, harvested, children, links=(), identifier=None):
    """A crate that organizes others and holds no data of its own: the root, or a resource. children:
    (folder id, name), each a nested crate; links: (href, title) of what it was harvested from."""
    root = {"@id": "./", "@type": "Dataset", "name": name, "description": description,
            "datePublished": harvested.date().isoformat(), "license": {"@id": CATALOG_LICENSE},
            **({"identifier": identifier} if identifier else {}),
            "hasPart": [{"@id": folder} for folder, _ in children]}
    graph = [descriptor(), root, {"@id": CATALOG_LICENSE, "@type": "CreativeWork", "name": "CC0-1.0"}]
    for folder, child_name in children:
        graph += referenced_crate(folder, child_name)
    if links:
        root["isBasedOn"] = [{"@id": href} for href, _ in links]
        graph += [{"@id": href, "@type": "CreativeWork", "name": title} for href, title in links]
    return graph


ROOT_NAME = "BioSTAC — OME 2024 NGFF challenge"
ROOT_DESCRIPTION = ("An RO-Crate catalog over the OME 2024 NGFF challenge data: one nested crate per resource, "
                    "each listing its studies in study-list.parquet, each study its images in item-list.parquet.")


def write_root(harvested, path=CHALLENGE):
    """The root crate, from whichever resources have been built. Deployment rewrites the relative ids."""
    children = [(f"{p.parent.name}/", next(n for n in json.loads(p.read_text())["@graph"] if n["@id"] == "./")["name"])
                for p in sorted(pathlib.Path(path).glob(f"*/{CRATE}"))]
    (pathlib.Path(path) / CRATE).write_text(crate_json(catalog_graph(ROOT_NAME, ROOT_DESCRIPTION, harvested, children)))


def save_resource(resource, title, description, studies, harvested, links=(), path=CHALLENGE):
    """Write one resource's folder: per study its crate, item-list.parquet and item folders; then the
    resource crate, and the root crate again. Other resources are left alone.

    studies: dicts with id, items, and optionally crate (the source's), crate_source (its URL), page
    (the study's web page), description (when there is no crate), extra_parts ({item id: [(url, name)]})."""
    folder = pathlib.Path(path) / resource
    # generated output: clear this resource's folder so renamed or removed items leave nothing stale
    shutil.rmtree(folder, ignore_errors=True)
    for study in studies:
        study_folder = folder / study["id"]
        graph = study_graph(study, harvested)
        name = next(n for n in graph if n["@id"] == "./")["name"]
        for item in study["items"]:
            item["study"] = study["id"]
            item_folder = study_folder / item["id"]
            item_folder.mkdir(parents=True)
            if item.get("_rendered"):
                shutil.copyfile(item["_rendered"], item_folder / "thumbnail.png")
            write_item_crate(item, item_folder, name, (study.get("extra_parts") or {}).get(item["id"], ()))
        write_list(study["items"], study_folder / "item-list.parquet")
        add_file(graph, study_folder / "item-list.parquet", "Items of this study, one row each")
        (study_folder / CRATE).write_text(crate_json(graph))
        study["name"] = name
    (folder / CRATE).write_text(crate_json(catalog_graph(
        title, description, harvested, [(f"{s['id']}/", s["name"]) for s in studies], links, resource)))
    write_root(harvested, path)
    return folder
