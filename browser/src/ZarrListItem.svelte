<script>
  import { onMount } from "svelte";
  import { filesizeformat } from "./util";
  import { loadMultiscales, ngffTable } from "./tableStore";
  import Thumbnail from "./Thumbnail.svelte";
  import { onDestroy } from "svelte";

  export let rowData;
  export let textFilter;
  export let sortedBy = undefined;

  import OpenWith from "./OpenWithViewers/index.svelte";

  // Hardcoding datatype and version.
  // TODO: Should be inferred from the file as in the ngff-validator
  let ome_zarr_data_type = "image";
  let ome_zarr_version = "0.5";

  let imgAttrs;
  let imgUrl;
  let plateAttrs;

  let thumbDatasetIndex;
  let thumbAspectRatio = 1;
  const controller = new AbortController();
  // If we have shape info
  if (rowData.size_x && rowData.size_y) {
    let longestSide = Math.max(rowData.size_x, rowData.size_y);
    // We want max target size of e.g. 256 pixels
    thumbDatasetIndex = 0;
    while (longestSide > 256) {
      thumbDatasetIndex += 1;
      longestSide = longestSide / 2;
    }
    thumbAspectRatio = rowData.size_x / rowData.size_y;
  }

  function csvUrl(rowData) {
    let currentUrl = window.location.origin + window.location.pathname;
    return currentUrl + "?csv=" + rowData.csv;
  }

  function handleThumbClick() {
    console.log("Clicked on thumbnail");
    ngffTable.setSelectedRow(rowData);
  }

  function formatUrlToName(url) {
    if (textFilter && url.toLowerCase().includes(textFilter.toLowerCase())) {
      const MAX_LENGTH = 50;

      // find first occurrence of textFilter in url and highlight it
      let urlLc = url.toLowerCase();
      let filterLc = textFilter.toLowerCase();
      let startMatch = urlLc.indexOf(filterLc);

      // let endMatch = start + filterLc.length;
      let start = Math.max(0, Math.min(startMatch, url.length - MAX_LENGTH));

      let result = url.substring(start, startMatch);
      result += "<mark>";
      result += url.substring(startMatch, startMatch + filterLc.length);
      result += "</mark>";
      result += url.substring(startMatch + filterLc.length);
      return result;
    }
    return url.split("/").pop();
  }

  onMount(async () => {
    let zarrUrl = rowData.url;
    // If we know the path to first series, add it
    if (rowData.series0 !== undefined) {
      zarrUrl += "/" + rowData.series0;
    }
    let img = await loadMultiscales(zarrUrl, controller.signal);
    imgAttrs = img[0];
    imgUrl = img[1];
    plateAttrs = img[2]; // optional
  });

  onDestroy(() => {
    // Doesn't seem to abort fetching of chunks
    controller.abort();
  });
</script>

<div class="zarr-list-item">
  <div class="thumbWrapper" on:click={handleThumbClick}>
    {#if imgAttrs}
      <Thumbnail
        source={imgUrl}
        attrs={imgAttrs}
        max_size={2000}
        {thumbDatasetIndex}
        {thumbAspectRatio}
      />
    {/if}
  </div>
  <div>
    <div class="nameRow">
      <div title={rowData.name}>
        <strong>
          {@html rowData.name.replaceAll(
            textFilter,
            `<mark>${textFilter}</mark>`,
          )}</strong
        >
      </div>
    </div>
    <div class:hideOnSmall={!textFilter}>
      {@html rowData.description.replaceAll(
        textFilter,
        `<mark>${textFilter}</mark>`,
      )}
    </div>

    <OpenWith
      source={rowData.url}
      dtype={ome_zarr_data_type}
      version={ome_zarr_version}
    />
    <div>
      Content mode: {rowData.ome_zarr_kind}
    </div>
    <div>
      Array dimensions:
      {#each ["t", "c", "z", "y", "x"] as dim}
        {#if rowData[`size_${dim}`] !== undefined}
          {dim.toUpperCase()}:{rowData[`size_${dim}`]} &nbsp;
        {/if}
      {/each}
    </div>
    {#if sortedBy == "chunk_pixels"}
      <div>Chunk shape: {rowData.chunks}</div>
    {:else if sortedBy == "shard_pixels"}
      <div>Shard shape: {rowData.shards}</div>
    {:else}
      <div>Data size: {filesizeformat(rowData.written)}</div>
    {/if}
  </div>
</div>

<style>
  .thumbWrapper {
    width: 120px;
    height: 120px;
    cursor: pointer;
  }
  .zarr-list-item {
    padding: 10px;
    display: flex;
    flex-direction: row;
    align-items: start;
    gap: 10px;
    background-color: var(--background-color);
  }
  @media (max-width: 800px) {
    /* On small screen, hide name & description */
    .hideOnSmall {
      display: none;
    }
  }

  :root {
    --icon-size: 20px;
  }
</style>
