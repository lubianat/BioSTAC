// The only data source: a STAC catalog whose Collections publish stac-geoparquet.
//
// The root catalog links its resources, each resource advertises an "items" Parquet
// asset, and that file already holds everything the gallery shows — shape, organism,
// imaging method, size, thumbnail. So nothing here opens a Zarr.

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

function toRow(item, resource, collectionUrl) {
  const axes = AXES.filter((axis) => item[`bioimage:size_${axis}`] != null);
  const base = collectionUrl.replace(/collection\.json$/, "");
  return {
    resource,
    url: item.assets.data.href,
    name: item.title || item.id,
    description: item.description || "",
    license: item.license,
    collection: item.collection,
    level: item["bioimage:level"],
    ngff_version: item["bioimage:ngff_version"],
    // the table splits these into size_t, size_c, … and counts the dimensions
    shape: axes.map((axis) => num(item[`bioimage:size_${axis}`])).join(","),
    dimension_names: axes.join(","),
    written: num(item["bioimage:size_bytes"]),
    well_count: num(item["bioimage:wells"]),
    organismId: item["bioimage:ncbitaxon"],
    fbbiId: item["bioimage:fbbi"],
    // each item is a folder in the bucket, named by its id, holding its thumbnail
    thumbnail: item.assets.thumbnail
      ? new URL(`${item.collection}/${item.id}/${item.assets.thumbnail.href}`, base).href
      : undefined,
    zarr_metadata: item.assets["zarr-metadata"]?.href,
    ro_crate: item.assets["ro-crate"]?.href,
  };
}

/** Crawl the catalog and load every Collection's items.parquet into the table. */
export async function loadStac(rootUrl) {
  const root = await getJson(rootUrl);
  const children = root.links
    .filter((link) => link.rel === "child")
    .map((link) => new URL(link.href, rootUrl).href);

  for (const collectionUrl of children) {
    const collection = await getJson(collectionUrl);
    const items = collection.assets?.items;
    if (!items) {
      console.warn(`${collection.id} publishes no items.parquet`);
      continue;
    }
    const url = new URL(items.href, collectionUrl).href;
    const file = await asyncBufferFromUrl({ url }); // ranged GETs, not a full download
    const rows = await parquetReadObjects({ file, compressors });
    ngffTable.addRows(rows.map((row) => toRow(row, collection.id, collectionUrl)));
    resourceStore.update((known) => [
      ...known,
      { id: collection.id, title: collection.title || collection.id, description: collection.description },
    ]);
  }
}
