// The only data source: a STAC catalog whose Collections publish stac-geoparquet.
//
// The root catalog links its resources, and each resource Catalog links its Parquet tables by
// `bioimage:table`: "items" (images and plates, merged from its collections' own files), "studies" (one row per collection) and
// "wells". Those files already hold everything the gallery shows — shape, organism, imaging method,
// size, thumbnail. So nothing here opens a Zarr.

import { writable } from "svelte/store";
import { asyncBufferFromUrl, parquetReadObjects } from "hyparquet";
import { compressors } from "hyparquet-compressors";
import { ngffTable } from "./tableStore";

/** What the catalog says about each of its resources, in the catalog's own words. */
export const resourceStore = writable([]);

const AXES = ["t", "c", "z", "y", "x"];

const getJson = (url) => fetch(url).then((r) => r.json());

// Parquet gives integers as BigInt; the table sorts and formats plain numbers.
const num = (value) => (value === null || value === undefined ? undefined : Number(value));

// the fields a well is found by, which its title (the plate's) does not say
const WELL_TERMS = ["idr:gene_symbol", "idr:gene_identifier", "idr:sirna_identifier", "idr:compound_name",
  "idr:control_type", "idr:cell_line"];

function toRow(item, resource, resourceUrl) {
  const axes = AXES.filter((axis) => item[`bioimage:size_${axis}`] != null);
  // an asset href is either absolute or relative to its item, which lives in its own folder
  const itemBase = new URL(
    `${item.collection}/${item.id}/`,
    resourceUrl.replace(/[^/]*$/, ""),
  ).href;
  const href = (asset) => (asset ? new URL(asset.href, itemBase).href : undefined);
  const level = item["bioimage:level"];
  const wellTerms = WELL_TERMS.map((key) => item[key]).filter(Boolean).join(" · ");
  return {
    resource,
    url: item.assets.data.href,
    name: level === "well" ? `${item.title} · well ${item["idr:well"] ?? item["bioimage:well"]}` : item.title || item.id,
    description: (level === "well" ? wellTerms : item.description) || "",
    license: item.license,
    collection: item.collection,
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
    thumbnail: href(item.assets.thumbnail),
    // IDR's well annotations, which the Images + wells view filters on
    gene: [item["idr:gene_symbol"], item["idr:gene_identifier"]].filter(Boolean).join(" ") || undefined,
    compound: item["idr:compound_name"] ?? undefined,
    sirna: item["idr:sirna_identifier"] ?? undefined,
    control: item["idr:control_type"] ?? undefined,
    cell_line: item["idr:cell_line"] ?? undefined,
    zarr_metadata: href(item.assets["zarr-metadata"]),
    ro_crate: href(item.assets["ro-crate"]),
  };
}

// a row of studies.parquet, the table that holds one row per collection
function collectionRow(row, resource) {
  return {
    resource,
    url: row.study_url,
    name: row.title || row.study,
    description: row.description || "",
    license: row.license,
    collection: row.study,
    level: "collection",
    written: num(row.size_bytes),
    item_count: num(row.items),
    has_wells: Boolean(row.wells_href),
    authors: row.authors?.join(", "),
    // ponytail: a collection filters by its first taxon and method; every collection today has at most one of each
    organismId: row.organism_terms?.[0],
    organismLabel: row.organisms?.[0],
    fbbiId: row.imaging_method_terms?.[0],
    modalityLabel: row.imaging_methods?.[0],
    thumbnail: row.thumbnail,
    search: [row.authors, row.keywords, row.publication_title].flat().filter(Boolean).join(" "),
  };
}

// every table link of every resource, once the catalog has been crawled
let tableLinks = [];

/** Read one kind of table ("items", "studies", "wells") from every resource that publishes it. */
export async function loadTable(kind) {
  for (const { url, resource, resourceUrl } of tableLinks.filter((link) => link.kind === kind)) {
    const file = await asyncBufferFromUrl({ url }); // ranged GETs, not a full download
    const rows = await parquetReadObjects({ file, compressors });
    ngffTable.addRows(
      rows.map((row) => (kind === "studies" ? collectionRow(row, resource) : toRow(row, resource, resourceUrl))),
    );
  }
}

/** Crawl the catalog, then load images, plates and collections; wells wait for loadTable("wells"). */
export async function loadStac(rootUrl) {
  const root = await getJson(rootUrl);
  const children = root.links
    .filter((link) => link.rel === "child")
    .map((link) => new URL(link.href, rootUrl).href);

  // the resource Catalogs first: they are small, and they say what this catalog offers
  const collections = await Promise.all(
    children.map(async (url) => ({ url, collection: await getJson(url) })),
  );
  resourceStore.set(
    collections.map(({ collection }) => ({
      id: collection.id,
      title: collection.title || collection.id,
      description: collection.description,
    })),
  );

  tableLinks = collections.flatMap(({ url: resourceUrl, collection }) => {
    // a Catalog has no assets: the Parquet is a link, picked by its bioimage:table
    // (a resource published before that was a Collection with an "items" asset)
    const links = collection.links.filter((link) => link["bioimage:table"]);
    if (!links.length && collection.assets?.items) links.push({ ...collection.assets.items, "bioimage:table": "items" });
    return links.map((link) => ({
      kind: link["bioimage:table"],
      url: new URL(link.href, resourceUrl).href,
      resource: collection.id,
      resourceUrl,
    }));
  });
  await Promise.all([loadTable("items"), loadTable("studies")]);
  addSizeRanges();
}

// ponytail: computed here from the loaded images and plates; move into studies.parquet once settled
/** Give each collection row the smallest and largest size of its images, per axis. */
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
    table.map((row) => (row.level === "collection" ? { ...row, size_range: ranges[row.collection] ?? {} } : row)),
  );
}
