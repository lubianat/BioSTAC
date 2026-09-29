<script>
  import { filesizeformat } from "./util";
  import { ngffTable } from "./tableStore";
  import Thumbnail from "./Thumbnail.svelte";

  export let rowData;
  export let textFilter;
  export let onOpenCollection = () => {};

  import OpenWith from "./OpenWithViewers/index.svelte";

  // Hardcoding datatype and version.
  // TODO: Should be inferred from the file as in the ngff-validator
  let ome_zarr_data_type = "image";
  let ome_zarr_version = "0.5";

  let thumbAspectRatio = 1;
  if (rowData.size_x && rowData.size_y) {
    thumbAspectRatio = rowData.size_x / rowData.size_y;
  }

  function handleThumbClick() {
    console.log("Clicked on thumbnail");
    ngffTable.setSelectedRow(rowData);
  }

</script>

<div class="zarr-list-item">
  <div class="thumbWrapper" on:click={handleThumbClick}>
    <Thumbnail src={rowData.thumbnail} {thumbAspectRatio} />
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
    <div class="description" class:hideOnSmall={!textFilter} title={rowData.description}>
      {@html rowData.description.replaceAll(
        textFilter,
        `<mark>${textFilter}</mark>`,
      )}
    </div>

    {#if rowData.level === "collection"}
      <div>
        <a href={rowData.url} target="_blank" rel="noreferrer">{rowData.collection}</a> ·
        {rowData.item_count} items · {rowData.license}
        <button on:click={() => onOpenCollection(rowData)}>Show {rowData.has_wells ? "plates" : "images"}</button>
      </div>
      {#if rowData.authors}<div>{rowData.authors}</div>{/if}
      {#if rowData.size_range && Object.keys(rowData.size_range).length}
        <div>
          {#each Object.entries(rowData.size_range) as [axis, [min, max]]}
            {axis.toUpperCase()}: {min === max ? min : `${min}–${max}`} &nbsp;
          {/each}
        </div>
      {/if}
      <div>Data size: {filesizeformat(rowData.written)}</div>
    {:else}
    <OpenWith
      source={rowData.level === "well" ? rowData.url.replace(/\/[^/]+\/[^/]+$/, "") : rowData.url}
      dtype={ome_zarr_data_type}
      version={ome_zarr_version}
    />
    <div>
      {rowData.level}{#if rowData.well_count}, {rowData.well_count} wells{/if} ·
      {rowData.collection} · OME-NGFF {rowData.ngff_version}
    </div>
    <div>
      Array dimensions:
      {#each ["t", "c", "z", "y", "x"] as dim}
        {#if rowData[`size_${dim}`] !== undefined}
          {dim.toUpperCase()}:{rowData[`size_${dim}`]} &nbsp;
        {/if}
      {/each}
    </div>
    <div>Data size: {filesizeformat(rowData.written)}</div>
    {/if}
  </div>
</div>

<style>
  .description {
    display: -webkit-box;
    -webkit-line-clamp: 3;
    line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
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
