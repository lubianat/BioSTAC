// The only data source: an RO-Crate catalog whose lists are Parquet.
//
// The root crate nests one crate per resource; each resource crate lists study-list.parquet, one row per
// study, naming that study's item-list.parquet. Item lists hold images and plates first and their wells
// after (sorted by bioimage:level), and the study row counts each, so the gallery reads images by row
// range and leaves the wells' row groups unfetched until asked. Those files already hold everything the
// gallery shows — shape, organism, imaging method, size, thumbnail. So nothing here opens a Zarr.

import { writable } from "svelte/store";
import { asyncBufferFromUrl, cachedAsyncBuffer, parquetReadObjects } from "hyparquet";
import { compressors } from "hyparquet-compressors";
import { ngffTable } from "./tableStore";

/** What the catalog says about each of its resources, in the crates' own words. */
export const resourceStore = writable([]);

const AXES = ["t", "c", "z", "y", "x"];

const getJson = (url) => fetch(url).then((r) => r.json());

// Parquet gives integers as BigInt; the table sorts and formats plain numbers.
const num = (value) => (value === null || value === undefined ? undefined : Number(value));

// the fields a well is found by, which its title (the plate's) does not say
const WELL_TERMS = ["idr:gene_symbol", "idr:gene_identifier", "idr:sirna_identifier", "idr:compound_name",
  "idr:control_type", "idr:cell_line"];

function toRow(item, resource, listUrl, listRow) {
  const axes = AXES.filter((axis) => item[`bioimage:size_${axis}`] != null);
  // URLs are absolute, except files shipped with the catalog, which are relative to the list
  const href = (url) => (url ? new URL(url, listUrl).href : undefined);
  const level = item["bioimage:level"];
  const wellTerms = WELL_TERMS.map((key) => item[key]).filter(Boolean).join(" · ");
  return {
    resource,
    url: item.zarr_url,
    name: level === "well" ? `${item.title} · well ${item["idr:well"] ?? item["bioimage:well"]}` : item.title || item.id,
    description: (level === "well" ? wellTerms : item.description) || "",
    license: item.license,
    collection: item.study,
    listRow, // its row in item-list.parquet: the popover reads the full row from there, on click
    level,
    ngff_version: item["bioimage:ngff_version"],
    // the table splits these into size_t, size_c, … and counts the dimensions
    shape: axes.map((axis) => num(item[`bioimage:size_${axis}`])).join(","),
    dimension_names: axes.join(","),
    written: num(item["bioimage:size_bytes"]),
    well_count: num(item["bioimage:wells"]),
    organismId: item["bioimage:ncbitaxon"],
    organismLabel: item["bioimage:organism"]?.term_label,
    fbbiId: item["bioimage:fbbi"],
    modalityLabel: item["bioimage:imaging_method"]?.term_label,
    // the catalog's own PNG, or IDR's renderer where the challenge points at one
    thumbnail: href(item.thumbnail_url),
    // IDR's well annotations, which the Images + wells view filters on
    gene: [item["idr:gene_symbol"], item["idr:gene_identifier"]].filter(Boolean).join(" ") || undefined,
    compound: item["idr:compound_name"] ?? undefined,
    sirna: item["idr:sirna_identifier"] ?? undefined,
    control: item["idr:control_type"] ?? undefined,
    cell_line: item["idr:cell_line"] ?? undefined,
    zarr_metadata: href(item.zarr_metadata_url),
    ro_crate: href(item.crate_href),
  };
}

// a row of study-list.parquet, the table that holds one row per study
function collectionRow(row, resource, listUrl) {
  return {
    resource,
    // the study's page, or its crate where the source has no page
    url: row.study_url ?? new URL(row.crate_href, listUrl).href,
    name: row.title || row.study,
    description: row.description || "",
    license: row.license,
    collection: row.study,
    level: "collection",
    written: num(row.size_bytes),
    item_count: num(row.items),
    has_wells: num(row.wells) > 0,
    authors: row.authors?.join(", "),
    // ponytail: a collection filters by its first taxon and method; every collection today has at most one of each
    organismId: row.organism_terms?.[0],
    organismLabel: row.organisms?.[0],
    fbbiId: row.imaging_method_terms?.[0],
    modalityLabel: row.imaging_methods?.[0],
    thumbnail: row.thumbnail ? new URL(row.thumbnail, listUrl).href : undefined,
    search: [row.authors, row.keywords, row.publication_title].flat().filter(Boolean).join(" "),
  };
}

// every study row of every resource, once the catalog has been crawled
let studies = [];

const readRows = async (url, options) =>
  parquetReadObjects({ file: await asyncBufferFromUrl({ url }), compressors, ...options }); // ranged GETs

/** Read the items of every study: "items" (images and plates) or "wells", each a row range of its list. */
export async function loadTable(kind) {
  await Promise.all(
    studies
      .filter((study) => (kind === "wells" ? study.wells : study.items) > 0)
      .map(async ({ resource, listUrl, items }) => {
        const start = kind === "wells" ? items : 0;
        const rows = await readRows(listUrl, kind === "wells" ? { rowStart: items } : { rowEnd: items });
        ngffTable.addRows(rows.map((row, i) => toRow(row, resource, listUrl, start + i)));
      }),
  );
}

const crateGraph = async (url) => {
  const graph = (await getJson(url))["@graph"];
  const byId = Object.fromEntries(graph.map((node) => [node["@id"], node]));
  return { root: byId["./"], byId };
};
const ids = (value) => (Array.isArray(value) ? value : value ? [value] : []).map((v) => v["@id"]);

/** The crates this crate nests (RO-Crate 1.2 "Referencing other RO-Crates"), as metadata URLs. */
function nestedCrates({ root, byId }, url) {
  return ids(root.hasPart)
    .map((id) => byId[id])
    .filter((node) => node?.conformsTo?.["@id"]?.startsWith("https://w3id.org/ro/crate"))
    .map((node) => new URL(node.subjectOf?.["@id"] ?? `${node["@id"]}ro-crate-metadata.json`, url).href);
}

/** Crawl root crate → resource crates, then read each study-list and the images and plates of every study. */
export async function loadCatalog(rootUrl) {
  const resources = await Promise.all(
    nestedCrates(await crateGraph(rootUrl), rootUrl).map(async (url) => ({ url, crate: await crateGraph(url) })),
  );
  resourceStore.set(
    resources.map(({ crate: { root } }) => ({
      id: root.identifier ?? root.name,
      title: root.name,
      description: root.description,
    })),
  );

  studies = (
    await Promise.all(
      resources.map(async ({ url, crate: { root } }) => {
        const resource = root.identifier ?? root.name;
        const file = ids(root.hasPart).find((id) => id.endsWith("study-list.parquet"));
        if (!file) return [];
        const listUrl = new URL(file, url).href;
        const rows = await readRows(listUrl);
        ngffTable.addRows(rows.map((row) => collectionRow(row, resource, listUrl)));
        return rows.map((row) => ({
          resource,
          study: row.study,
          crateUrl: new URL(row.crate_href, listUrl).href,
          listUrl: new URL(row.item_list_href, listUrl).href,
          items: num(row.items),
          wells: num(row.wells),
        }));
      }),
    )
  ).flat();
  await loadTable("items");
  addSizeRanges();
}

// --- details on demand: nothing below is loaded until someone opens a popover ---

const studyOf = (row) => studies.find((s) => s.resource === row.resource && s.study === row.collection);
const files = new Map(); // list URL -> its file, footer cached after the first read
const crates = new Map(); // crate URL -> its graph

/** The row whose details popover is open, or null. */
export const detailsRow = writable(null);

/** The study crate's URL for a row of any level, collections included. */
export const studyCrateUrl = (row) => studyOf(row)?.crateUrl;

const values = (value) => (Array.isArray(value) ? value : value == null ? [] : [value]);

/** A row's full item-list.parquet row and its study crate, each fetched once. */
export async function loadDetails(row) {
  const study = studyOf(row);
  if (!files.has(study.listUrl)) {
    files.set(study.listUrl, asyncBufferFromUrl({ url: study.listUrl }).then(cachedAsyncBuffer));
  }
  if (!crates.has(study.crateUrl)) crates.set(study.crateUrl, crateGraph(study.crateUrl));
  const [item, { root, byId }] = await Promise.all([
    row.listRow == null
      ? null
      : files.get(study.listUrl).then((file) =>
          parquetReadObjects({ file, compressors, rowStart: row.listRow, rowEnd: row.listRow + 1 })).then((r) => r[0]),
    crates.get(study.crateUrl),
  ]);
  // a reference resolves to its node where the crate has one: authors, taxa, publications
  const nodes = (key) => values(root[key]).map((v) => (v?.["@id"] ? byId[v["@id"]] ?? v : v));
  const named = (key) => nodes(key).map((n) => n?.name ?? n?.scientificName ?? n?.["@id"] ?? n).filter(Boolean);
  return {
    item,
    crateUrl: study.crateUrl,
    crate: {
      name: root.name,
      identifier: root.identifier,
      url: root.url,
      datePublished: root.datePublished,
      license: values(root.license).map((l) => l?.["@id"] ?? l),
      authors: named("author"),
      keywords: values(root.keywords),
      organisms: named("about"),
      methods: named("measurementMethod"),
      publications: [...nodes("citation"), ...nodes("seeAlso")].filter((n) => values(n?.["@type"]).includes("ScholarlyArticle"))
        .map((n) => ({ name: n.name ?? n["@id"], url: n["@id"] })),
      description: root.description,
    },
  };
}

// ponytail: computed here from the loaded images and plates; move into study-list.parquet once settled
/** Give each collection row the smallest and largest size of its images, per axis, for sorting and display. */
function addSizeRanges() {
  const rows = ngffTable.getRows();
  const ranges = {};
  for (const row of rows) {
    if (row.level === "collection") continue;
    const range = (ranges[row.collection] ??= {});
    for (const axis of AXES) {
      const size = row[`size_${axis}`];
      if (size == null || Number.isNaN(size)) continue;
      range[axis] = [Math.min(size, range[axis]?.[0] ?? size), Math.max(size, range[axis]?.[1] ?? size)];
    }
  }
  ngffTable.store.update((table) =>
    table.map((row) => {
      if (row.level !== "collection") return row;
      const range = ranges[row.collection] ?? {};
      // flat too, because sorting reads one field per row
      const flat = Object.entries(range).flatMap(([axis, [min, max]]) => [[`size_min_${axis}`, min], [`size_max_${axis}`, max]]);
      return { ...row, size_range: range, ...Object.fromEntries(flat) };
    }),
  );
}
