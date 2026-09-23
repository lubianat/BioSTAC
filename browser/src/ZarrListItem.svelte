<script>
  import { filesizeformat } from "./util";
  import { ngffTable } from "./tableStore";
  import Thumbnail from "./Thumbnail.svelte";

  export let rowData;
  export let textFilter;

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
