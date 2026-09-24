// src/util.js
// Frontend utilities (thumbnails, formatting, ontology lookups).


import YAML from "yaml";

let _config = null;

/** config.yaml, parsed once. It holds the page title and the STAC catalog to read. */
export async function getConfig() {
  if (!_config) {
    _config = fetch(`${import.meta.env.BASE_URL}config.yaml`)
      .then((r) => r.text())
      .then((text) => YAML.parse(text) || {});
  }
  return _config;
}

export async function getJson(url) {
  return await fetch(url).then((r) => r.json());
}

export function filesizeformat(bytes) {
  if (!bytes) return "";
  const round = 2;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(round)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(round)} MB`;
  if (bytes < 1024 ** 4) return `${(bytes / 1024 ** 3).toFixed(round)} GB`;
  if (bytes < 1024 ** 5) return `${(bytes / 1024 ** 4).toFixed(round)} TB`;
  return `${(bytes / 1024 ** 5).toFixed(round)} PB`;
}
