// src/util.js
// Frontend utilities (logos, CSV, formatting, and wrappers).
// Imports the math/color rendering functions from util_core.js.

import Papa from "papaparse";

export const SAMPLES_HOME =
  "https://raw.githubusercontent.com/ome/ome2024-ngff-challenge/main/samples/ngff_samples.csv";



export async function loadMultiscales(url, signal) {
  let zarrData;
  try {
    const res = await fetch(`${url}/zarr.json`, { signal });
    if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}/zarr.json`);
    zarrData = await res.json();
  } catch (err) {
    console.warn(`[ngffLoader] ${url}/zarr.json not found or invalid`, err.message);
    return [undefined, url];
  }

  const attrs = zarrData?.attributes?.ome;
  if (!attrs) return [undefined, url];

  // Plain image
  if (attrs.multiscales) return [attrs, url];

  // Plate-style (multi-well)
  if (attrs.plate) {
    const well = attrs.plate.wells[0];
    const imgPath = `${url}/${well.path}/0`;
    const [msData, msUrl] = await loadMultiscales(imgPath, signal);
    return [msData, msUrl, attrs.plate];
  }

  // Bioformats2raw layout
  if (attrs["bioformats2raw.layout"]) {
    const bf2rawUrl = `${url}/0`;
    return await loadMultiscales(bf2rawUrl, signal);
  }

  return [undefined, url];
}

import YAML from "yaml";

const DEFAULT_YAML_URL = `${import.meta.env.BASE_URL}config.yaml`;
let _viewConfigPromise = null;

// Lazy-load and cache the YAML config the first time it's needed
export async function getViewConfig() {
  if (_viewConfigPromise) return _viewConfigPromise;

  _viewConfigPromise = (async () => {
    try {
      const txt = await fetch(DEFAULT_YAML_URL).then((r) => r.text());
      const cfg = YAML.parse(txt) || {};
      const whitelist = new Set((cfg.samples || []).map((u) => (u || "").trim()));
      const overrides = new Map();

      for (const item of cfg.extended_samples || []) {
        if (item && item.url) {
          const { url, ...rest } = item;
          overrides.set((url || "").trim(), rest);
        }
      }

      console.log("Overrides:", { overrides });
      // allow both samples + extended
      const allowed = new Set([...whitelist, ...overrides.keys()]);
      const predicate = (row) => allowed.has((row.url || "").trim());

      return { predicate, overrides, cfg };
    } catch (err) {
      console.warn("No YAML view config found, showing all rows.", err);
      // fallback: no filtering, no overrides
      return { predicate: () => true, overrides: new Map(), };
    }
  })();

  return _viewConfigPromise;
}


// ──────────────────────────────────────────────
// FRONTEND-ONLY HELPERS
// ──────────────────────────────────────────────


export function loadCsv(csvUrl, ngffTable, parentRow = {}) {
  Papa.parse(csvUrl, {
    header: false,
    download: true,
    skipEmptyLines: "greedy",
    complete: async (results) => {
      let colNames = ["url"];
      let firstRow = results.data[0];
      if (firstRow.length > 1) {
        colNames = firstRow;
        results.data.shift();
      }
      const dataRows = results.data.map((row) => {
        const rowObj = { ...parentRow };
        for (let i = 0; i < colNames.length; i++) {
          rowObj[colNames[i]] = row[i];
        }
        return rowObj;
      });

      let zarrUrlRows


      // ───── apply whitelist + overrides from YAML (optional) ─────
      const { predicate, overrides, cfg } = await getViewConfig();


      zarrUrlRows = dataRows
        .filter(predicate)
        .map((row) => {
          const patch = overrides.get((row.url || "").trim());
          const updatedRow = patch ? Object.assign(row, patch) : row;
          // Set default catalog if not defined
          if (!updatedRow.catalog) {
            updatedRow.catalog = "none"; // or whatever default you want
          }
          return updatedRow;
        });

      const unique = {};
      zarrUrlRows.forEach((row) => {
        if (!unique[row.url]) unique[row.url] = row;
      });
      zarrUrlRows = Object.values(unique);

      console.log({ cfg });
      const catalogs = cfg.catalogs;

      Object.values(catalogs).forEach((c) => {
        zarrUrlRows.forEach((row) => {
          if (row.catalog === c.name) {
            row.catalog_url = c.url;
          }
        });
      });

      const plate_count = zarrUrlRows.reduce(
        (acc, r) => (r.wells ? acc + 1 : acc),
        0
      );
      const bytes = zarrUrlRows.reduce(
        (acc, r) => acc + parseInt(r.written || 0),
        0
      );
      let image_count = zarrUrlRows.length;
      if (plate_count > 0) {
        image_count = zarrUrlRows.reduce(
          (acc, r) => acc + parseInt(r.images || 1),
          0
        );
      }

      ngffTable.addRows(zarrUrlRows);

    },
  });
}

export async function getJson(url) {
  return await fetch(url).then((r) => r.json());
}

// Thumbnails convention v1 (zarr-conventions). Returns a URL for the best
// thumbnail (largest edge <= maxEdge, preferring JPEG) or null if the group
// doesn't declare/carry the convention.
// ponytail: convention detected by name/uuid/url substring per spec; only one is required.
export async function thumbnailFromConvention(source, maxEdge = 512, signal) {
  let attrs;
  try {
    const z = await getJson(`${source}/zarr.json`);
    attrs = z?.attributes ?? z;
  } catch {
    return null;
  }
  const conventions = attrs?.zarr_conventions ?? [];
  const hasConvention = conventions.some(
    (c) =>
      c.uuid === "49326c01-1180-4743-b15f-f7157038a6ab" ||
      c.name === "thumbnails" ||
      c.schema_url?.includes("/thumbnails/") ||
      c.spec_url?.includes("/thumbnails/"),
  );
  const thumbnails = attrs?.thumbnails;
  if (!hasConvention || !thumbnails?.length) return null;

  const fits = thumbnails.filter((t) => Math.max(t.width, t.height) <= maxEdge);
  const pool = fits.length ? fits : thumbnails;
  const best = pool.sort((a, b) => {
    const aEdge = Math.max(a.width, a.height);
    const bEdge = Math.max(b.width, b.height);
    // Prefer larger when it fits under maxEdge, else smallest available.
    if (aEdge !== bEdge) return fits.length ? bEdge - aEdge : aEdge - bEdge;
    // Tie-break: JPEG over PNG.
    return (
      Number(b.media_type === "image/jpeg") -
      Number(a.media_type === "image/jpeg")
    );
  })[0];

  if (!best) return null;
  return best.path ? `${source}/${best.path}` : best.url || null;
}

export function getRandomInt(max) {
  return Math.floor(Math.random() * max);
}

export async function lookupOrganism(taxonId) {
  const id = taxonId.replace("NCBI:txid", "");
  const res = await getJson(
    `https://rest.ensembl.org/taxonomy/id/${id}?content-type=application/json`
  );
  return res.name || taxonId;
}

export async function lookupImagingModality(fbbiId) {
  const fbbi_id = fbbiId.replace("obo:", "");
  const res = await getJson(
    `https://www.ebi.ac.uk/ols4/api/ontologies/fbbi/terms/http%253A%252F%252Fpurl.obolibrary.org%252Fobo%252F${fbbi_id}`
  );
  return res.label;
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

export function range(start, end) {
  return Array.from({ length: end - start }, (_, i) => i + start);
}
