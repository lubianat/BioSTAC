from __future__ import annotations

import argparse
import csv
import json
import logging
from pathlib import Path

import math


import requests
import yaml
import re


# ────────────────────────────────────────────────────────────────────────────────
# Logging configuration
# ────────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("load_zarr_stats")

# ────────────────────────────────────────────────────────────────────────────────
# Path configuration
# ────────────────────────────────────────────────────────────────────────────────
HERE = Path(__file__).parent


# ────────────────────────────────────────────────────────────────────────────────
# Utility functions
# ────────────────────────────────────────────────────────────────────────────────


def detect_ome_zarr_kind(root_zarr_json: dict) -> str:
    """
    Classify the root of an OME-Zarr store into one of:
      image_with_multiscales, image_no_multiscales, label,
      bioformats2raw, plate, well
    """
    attrs = root_zarr_json.get("attributes", {}) or {}
    ome = attrs.get("ome", {}) or {}

    # Highest-priority structural kinds
    if ome.get("plate"):
        return "plate"
    if ome.get("well"):
        return "well"
    if ome.get("bioformats2raw.layout"):
        return "bioformats2raw"

    # Image vs label
    if ome.get("multiscales"):
        return "image_with_multiscales"

    # Label-only roots:
    #  - NGFF "image-label" on array roots
    #  - Root 'labels' listing without multiscales
    if "image-label" in attrs:
        return "label"
    if attrs.get("labels") and not ome.get("multiscales"):
        return "label"

    # If the root is an array and we didn't see multiscales, treat as image without multiscales
    if root_zarr_json.get("node_type") == "array":
        return "image_no_multiscales"

    # Fallback
    return "image_no_multiscales"


def load_json(url: str):
    try:
        log.debug(f"Fetching JSON: {url}")
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as e:
        log.warning(f"Failed to load JSON from {url}: {e}")
        return {}


def format_bytes_human_readable(num_bytes):
    unit = None
    for u in ["B", "KB", "MB", "GB", "TB"]:
        unit = u
        if num_bytes < 1024.0:
            break
        num_bytes /= 1024.0
    return f"{num_bytes:.2f} {unit}"


def list_to_str(my_list):
    if not my_list:
        return ""
    return ",".join(str(item) for item in my_list)


# ────────────────────────────────────────────────────────────────────────────────
# Zarr metadata utilities
# ────────────────────────────────────────────────────────────────────────────────
def get_chunk_and_shard_shapes(zarray):
    """Returns dict with 'shape', 'chunks' and 'shards' keys (if shards are present)"""
    if "chunks" in zarray:
        return {"chunks": zarray["chunks"], "shape": zarray["shape"]}

    chunk_shape = (
        zarray.get("chunk_grid", {}).get("configuration", {}).get("chunk_shape")
    )
    sharding_codecs = [
        codec
        for codec in zarray.get("codecs", [])
        if codec.get("name") == "sharding_indexed"
    ]
    if len(sharding_codecs) > 0:
        sub_chunks = (
            sharding_codecs[0].get("configuration", {}).get("chunk_shape")
            if sharding_codecs
            else None
        )
        if sub_chunks:
            return {
                "chunks": sub_chunks,
                "shards": chunk_shape,
                "shape": zarray["shape"],
            }
    return {"chunks": chunk_shape, "shape": zarray["shape"]}


# Based on https://github.com/ome/ome-ngff-validator/blob/dfa175df9a20d9c2aaf576762472272fe393a3e8/src/JsonValidator/MultiscaleArrays/ZarrArray/index.svelte#L33
def get_array_values(zarr_url, multiscales):
    # we want chunks, shards, shape from first resolution level...
    # but we want total 'written' bytes for all resolutions...
    dict_data = {}

    # Hardcode to use only the first multiscales
    # See https://ngff.openmicroscopy.org/rfc/6/index.html
    for ds in multiscales[0]["datasets"]:

        array_url = zarr_url + "/" + ds["path"]
        array_json = load_json(array_url + "/zarr.json")

        if len(dict_data) == 0:
            dict_data = get_chunk_and_shard_shapes(array_json)
            dict_data["written"] = 0

        # Get dtype (v3: 'data_type', not supporting v2: 'dtype')
        array_data_type = array_json["data_type"]
        array_shape = array_json["shape"]
        if "int" in array_data_type or "float" in array_data_type:
            m = re.search(r"(\d+)", array_data_type)
            if m:
                bytes_per_pixel = int(m.group(1)) // 8
            else:
                # fallback for e.g. 'u1', 'i2', 'f4', etc.
                for n in [1, 2, 4, 8]:
                    if str(n) in array_data_type:
                        bytes_per_pixel = n
                        break

        pixels = math.prod(array_shape)
        total_bytes = bytes_per_pixel * pixels

        dict_data["written"] = dict_data["written"] + total_bytes
        dict_data["dimension_names"] = array_json.get("dimension_names", "")

    return dict_data


def load_rocrate(zarr_url):
    rocrate_json = load_json(zarr_url + "/ro-crate-metadata.json")

    if len(rocrate_json) == 0:
        log.debug(f"Ro-Crate metadata not found.")

        return {
            "license": "",
            "name": "",
            "description": "",
            "organismId": "",
            "fbbiId": "",
        }

    rc_graph = rocrate_json.get("@graph", {})
    license = name = description = organismId = fbbiId = None

    for item in rc_graph:
        if item.get("license"):
            license = item["license"]
        if item.get("name"):
            name = item["name"]
        if item.get("description"):
            description = item["description"]
        if item.get("@type") == "biosample":
            organismId = item.get("organism_classification", {}).get("@id")
        if item.get("@type") == "image_acquisition":
            fbbiId = item.get("fbbi_id", {}).get("@id")

    rocrate_data = {
        "license": license,
        "name": name,
        "description": description,
        "organismId": organismId,
        "fbbiId": fbbiId,
    }

    log.debug(f"Loaded Ro-Crate metadata: {rocrate_data}")

    return rocrate_data


def load_series(zarr_url):
    """Return a list of series identifiers."""
    series_url = zarr_url + "/OME/METADATA.ome.xml"
    rsp = requests.get(series_url)
    if (rsp.status_code // 100) != 2:
        series_json = load_json(zarr_url + "/OME/zarr.json")
        return series_json.get("attributes", {}).get("ome", {}).get("series", [])
    return ["0"]


# ────────────────────────────────────────────────────────────────────────────────
# Main Zarr loader
# ────────────────────────────────────────────────────────────────────────────────
def load_zarr(zarr_url, average_count=5):
    log.info(f"Loading Zarr: {zarr_url}")

    # Assuming v0.5
    response = load_json(zarr_url + "/zarr.json")

    if not response:
        log.error(f"No zarr.json found at {zarr_url}")
        return {}

    ome_zarr_kind = detect_ome_zarr_kind(response)

    ome_json = response.get("attributes", {}).get("ome", {})
    multiscales = ome_json.get("multiscales")
    plate = ome_json.get("plate")
    bf2raw = ome_json.get("bioformats2raw.layout")

    stats = None

    stats = {"written": 0}
    if multiscales:
        stats = get_array_values(zarr_url, multiscales)

    elif plate is not None:
        log.debug("→ Using plate data")
        written_values = []

        # Estimating data size from a sample
        for well in plate["wells"][:average_count]:
            field_path = f"{well['path']}/0"
            plate_img_url = f"{zarr_url}/{field_path}/zarr.json"
            plate_img_json = load_json(plate_img_url)
            plate_ome_json = plate_img_json.get("attributes", {}).get("ome", {})
            plate_img = plate_ome_json.get("multiscales")
            if plate_img:
                img_stats = get_array_values(zarr_url + "/" + field_path, plate_img)
                if img_stats.get("written", 0) > 0:
                    written_values.append(img_stats["written"])
                    stats = img_stats
            else:
                log.warning(f"Missing multiscales in plate image {field_path}")

        avg_written = sum(written_values) / len(written_values) if written_values else 0
        image_count = len(plate["wells"]) * plate.get("field_count", 1)
        stats = stats or {}
        stats["written"] = avg_written * image_count
        log.debug(f"Computed average written={avg_written}, total images={image_count}")

    elif bf2raw:
        log.debug("→ Using bioformats2raw layout")
        series = load_series(zarr_url)
        if series:
            bf_img_json = load_json(zarr_url + f"/{series[0]}/zarr.json")
            bf_img_ms = (
                bf_img_json.get("attributes", {}).get("ome", {}).get("multiscales")
            )
            if bf_img_ms:
                stats = get_array_values(zarr_url + f"/{series[0]}", bf_img_ms)
            else:
                log.warning("Missing multiscales in first series image")
        else:
            log.warning("No series found in bioformats2raw layout")

    else:
        log.warning("No recognized OME structure found in zarr.json")

    rocrate_data = load_rocrate(zarr_url)
    if len(rocrate_data) > 0:
        stats.update({"rocrate_found": True})
    else:
        stats.update({"rocrate_found": False})
    stats.update(rocrate_data)

    stats["ome_zarr_kind"] = ome_zarr_kind

    log.debug(
        f"Detected structure: multiscales={bool(multiscales)}, "
        f"plate={bool(plate)}, bf2raw={bool(bf2raw)}"
    )

    if stats is None:
        log.error("Could not determine stats for this Zarr")
        stats = {}

    stats.update(rocrate_data)
    log.debug(f"Final stats keys: {list(stats.keys())}")
    return stats


# ────────────────────────────────────────────────────────────────────────────────
# Input parser
# ────────────────────────────────────────────────────────────────────────────────
def extract_zarr_urls(input_path: str) -> list[str]:
    with Path(input_path).open() as f:
        data = yaml.safe_load(f)

    urls = []
    if "samples" not in data and "extended_samples" not in data:
        log.error("Config does not contain 'samples' or 'extende_samples' keys.")

    if "samples" in data:
        sample_val = data["samples"]
        if isinstance(sample_val, str):
            urls.append(sample_val)
        elif isinstance(sample_val, list):
            for item in sample_val:
                if isinstance(item, str):
                    urls.append(item)

    if "extended_samples" in data:
        extra_extended_info = data["extended_samples"]
        for item in extra_extended_info:
            urls.append(item["url"])

    return urls


# ────────────────────────────────────────────────────────────────────────────────
# Main entry point
# ────────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Hydrate NGFF Zarr stats to CSV.")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing metadata file.",
    )
    args = parser.parse_args()

    if args.verbose >= 2:
        log.setLevel(logging.DEBUG)
    elif args.verbose == 1:
        log.setLevel(logging.INFO)
    else:
        log.setLevel(logging.WARNING)

    input_path = HERE / "config.yaml"
    output_csv = HERE / "public" / "samples" / "zarrs_metadata.csv"

    column_names = [
        "url",
        "ome_zarr_kind",
        "written",
        "written_human_readable",
        "shape",
        "shards",
        "chunks",
        "dimension_names",
        "license",
        "name",
        "description",
        "organismId",
        "fbbiId",
    ]

    unique_urls = set(extract_zarr_urls(input_path))
    log.info(f"Found {len(unique_urls)} unique Zarr URLs")

    if args.overwrite:
        # Recreate the file: write header and all entries
        with output_csv.open("w", newline="") as csvfile:
            writer = csv.writer(csvfile, delimiter=",", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(column_names)

            for url in unique_urls:
                log.info(f"Processing {url}")
                stats = load_zarr(url)

                row = [
                    url,
                    stats.get("ome_zarr_kind", ""),
                    stats.get("written", 0),
                    format_bytes_human_readable(stats.get("written", 0)),
                    list_to_str(stats.get("shape", "")),
                    list_to_str(stats.get("shards", "")),
                    list_to_str(stats.get("chunks", "")),
                    list_to_str(stats.get("dimension_names", "")),
                    stats.get("license", ""),
                    stats.get("name", ""),
                    stats.get("description", ""),
                    stats.get("organismId", ""),
                    stats.get("fbbiId", ""),
                ]

                writer.writerow(row)
    else:
        # Append new entries only, skipping URLs already present
        existing_urls = set()
        if output_csv.exists():
            with output_csv.open("r", newline="") as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    existing_urls.add(row.get("url", ""))

        with output_csv.open("a", newline="") as csvfile:
            writer = csv.writer(csvfile, delimiter=",", quoting=csv.QUOTE_MINIMAL)
            # Write header if creating a new file
            if not output_csv.exists() or output_csv.stat().st_size == 0:
                writer.writerow(column_names)

            for url in unique_urls:
                if url in existing_urls:
                    log.info(f"Skipping {url} (already in CSV)")
                    continue

                log.info(f"Processing {url}")
                stats = load_zarr(url)

                row = [
                    url,
                    stats.get("ome_zarr_kind", ""),
                    stats.get("written", 0),
                    format_bytes_human_readable(stats.get("written", 0)),
                    list_to_str(stats.get("shape", "")),
                    list_to_str(stats.get("shards", "")),
                    list_to_str(stats.get("chunks", "")),
                    list_to_str(stats.get("dimension_names", "")),
                    stats.get("license", ""),
                    stats.get("name", ""),
                    stats.get("description", ""),
                    stats.get("organismId", ""),
                    stats.get("fbbiId", ""),
                ]

                writer.writerow(row)

    log.info(f"✅ Done. Results written to {output_csv}")


# ────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
