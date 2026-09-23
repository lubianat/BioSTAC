<script>
  import { ngffTable } from "./tableStore";
  import { organismStore, imagingModalityStore } from "./ontologyStore";
  import ColumnSort from "./ColumnSort.svelte";
  import ImageList from "./ImageList.svelte";
  import PreviewPopup from "./PreviewPopup.svelte";
  import PageTitle from "./PageTitle.svelte";
  import FilterSelect from "./FilterSelect.svelte";
  import { loadCsv } from "./util";

  import form_select_bg_img from "/selectCaret.svg";
  import zarr_samples from "/samples/zarrs_metadata.csv?url";

  // ────────────────────────────────────────────────────────────────
  // State
  // ────────────────────────────────────────────────────────────────
  let csvUrl = zarr_samples;
  let tableRows = [];
  let totalZarrs = 0;
  let totalBytes = 0;
  let showSourceColumn = false;

  let filters = {
    catalog: "",
    ome_zarr_kind: "",
    dimension: "",
    organism: "",
    modality: "",
    text: "",
  };

  let sortedBy = "";
  let sortAscending = false;

  // ────────────────────────────────────────────────────────────────
  // Data loading & subscription
  // ────────────────────────────────────────────────────────────────
  if (csvUrl) loadCsv(csvUrl, ngffTable);
  tableRows = applyFilters(ngffTable.getRows());

  let allRows = [];

  // Single consolidated subscription
  ngffTable.subscribe((rows) => {
    console.log("ngffTable updated, row count:", rows.length);
    console.log("First few rows:", rows.slice(0, 3));

    allRows = rows; // This ensures allRows is always in sync
    tableRows = applyFilters(rows);
    totalZarrs = rows.length;
    totalBytes = rows.reduce((acc, r) => acc + (parseInt(r.written) || 0), 0);
    showSourceColumn = rows.some((r) => r.source);
  });

  // Add debug to derived options
  $: console.log({ tableRows });

  // ────────────────────────────────────────────────────────────────
  // Filtering
  // ────────────────────────────────────────────────────────────────
  function applyFilters(rows) {
    const { catalog, ome_zarr_kind, dimension, organism, modality, text } =
      filters;
    const txt = text.toLowerCase();
    if (
      catalog == "" &&
      ome_zarr_kind == "" &&
      dimension == "" &&
      organism == "" &&
      modality == "" &&
      text == ""
    ) {
      return rows;
    }

    return rows.filter((r) => {
      if (dimension && String(r.dim_count) !== dimension) return false;
      if (organism && r.organismId !== organism) return false;
      if (modality && r.fbbiId !== modality) return false;
      if (ome_zarr_kind && r.ome_zarr_kind !== ome_zarr_kind) return false;
      if (catalog && r.catalog !== catalog) return false;

      if (
        txt &&
        !(
          r.url?.toLowerCase().includes(txt) ||
          r.description?.toLowerCase().includes(txt) ||
          r.name?.toLowerCase().includes(txt)
        )
      )
        return false;
      return true;
    });
  }

  function setFilter(key, value) {
    filters[key] = value;
    tableRows = applyFilters(ngffTable.getRows());
    console.log({ tableRows });
  }

  function filterText(e) {
    setFilter("text", e.target.value);
  }

  // ────────────────────────────────────────────────────────────────
  // Sorting
  // ────────────────────────────────────────────────────────────────
  function toggleSortAscending() {
    sortAscending = !sortAscending;
    ngffTable.sortTable(sortedBy, sortAscending);
  }

  function handleSort(e) {
    sortedBy = e.target.value;
    ngffTable.sortTable(sortedBy || "index", sortAscending);
  }

  // ────────────────────────────────────────────────────────────────
  // Derived options
  // ────────────────────────────────────────────────────────────────

  $: typeOptions = Array.from(
    new Set(tableRows.map((r) => String(r.ome_zarr_kind)).filter(Boolean)),
  )
    .sort()
    .map((v) => ({ value: String(v), label: `${v}` }));

  $: catalogOptions = Array.from(
    new Set(tableRows.map((r) => String(r.catalog)).filter(Boolean)),
  )
    .sort()
    .map((v) => ({ value: String(v), label: `${v}` }));

  $: dimensionOptions = Array.from(
    new Set(tableRows.map((r) => String(r.dim_count)).filter(Boolean)),
  )
    .sort()
    .map((v) => ({ value: String(v), label: `${v}D` }));

  $: organismOptions = Object.entries($organismStore || {})
    .filter(([id]) => tableRows.some((r) => r.organismId === id))
    .map(([id, name]) => ({ value: id, label: name }));

  $: modalityOptions = Object.entries($imagingModalityStore || {})
    .filter(([id]) => tableRows.some((r) => r.fbbiId === id))
    .map(([id, name]) => ({ value: id, label: name }));

  $: filterOptions = {
    dimension: dimensionOptions,
    organism: organismOptions,
    modality: modalityOptions,
    catalog: catalogOptions,
    ome_zarr_kind: typeOptions,
  };
</script>

<PreviewPopup />

<main style="--form-select-bg-img: url('{form_select_bg_img}')">
  <div class="summary">
    <PageTitle />
    <div class="textInputWrapper">
      <input
        bind:value={filters.text}
        on:input={filterText}
        placeholder="Filter by Name or Description"
        name="textFilter"
      />
      <button
        title="Clear Filter"
        style="visibility:{filters.text ? 'visible' : 'hidden'}"
        on:click={() => setFilter("text", "")}>&times;</button
      >
    </div>
  </div>

  <div class="sidebarContainer">
    <div class="sidebar">
      <div class="filters">
        <div style="white-space: nowrap;">Filter by:</div>

        {#each Object.entries(filterOptions) as [key, options]}
          <FilterSelect
            label={key}
            value={filters[key]}
            {options}
            onChange={(v) => setFilter(key, v)}
          />
        {/each}
        <div class="clear"></div>

        <div>Sort by:</div>
        <div class="selectWrapper">
          <select on:change={handleSort}>
            <option value="">--</option>
            <hr />
            {#each ["x", "y", "z", "c", "t"] as dim}
              <option value="size_{dim}">Size: {dim.toUpperCase()}</option>
            {/each}
            <hr />
            <option value="written">Data Size (bytes)</option>
            <option value="chunk_pixels">Chunk Size (pixels)</option>
            <option value="shard_pixels">Shard Size (pixels)</option>
          </select>
          <div>
            <ColumnSort {sortAscending} toggleAscending={toggleSortAscending} />
          </div>
        </div>
      </div>
    </div>

    <div class="results">
      <h3 style="margin-left: 15px">
        Showing {tableRows.length} out of {totalZarrs} images
      </h3>
      <ImageList {tableRows} textFilter={filters.text} {sortedBy} />
    </div>
  </div>
</main>

<style>
  .sidebarContainer {
    display: flex;
    flex-direction: row;
  }

  .sidebar {
    flex: 250px 0 0;
    padding: 10px;
  }
  .results {
    flex: auto 1 1;
    position: relative;
  }

  input[name="textFilter"] {
    width: 100%;
    flex: auto 1 1;
    border: solid var(--border-color) 1px;
    border-radius: 16px;
    padding: 8px 8px 6px 12px;
    font-size: 1rem;
    background-color: var(--light-background);
    position: relative;
    display: block;
  }
  /* Add a X over the input */
  input[name="textFilter"]::before {
    content: "Where is this going?";
    width: 200px;
    height: 200px;
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    display: block;
  }

  @media (max-width: 800px) {
    .sidebarContainer {
      flex-direction: column;
    }
  }
  select {
    display: block;
    width: 100%;
    padding: 0.3rem 2.25rem 0.3rem 0.75rem;
    font-size: 1rem;
    line-height: 1.5;
    appearance: none;
    background-color: var(--light-background);
    border: 1px solid var(--border-color);
    border-radius: 0.375rem;
    margin: 3px 0;
    float: left;
    background-image: var(--form-select-bg-img);
    background-repeat: no-repeat;
    background-position: right 0.75rem center;
    background-size: 16px 12px;
  }

  .selectWrapper {
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 5px;
  }
  .selectWrapper > select {
    flex: auto 1 1;
  }
  .selectWrapper > div {
    flex: 0 0 20px;
    cursor: pointer;
  }

  .textInputWrapper button {
    background: transparent;
    border: none;
    padding: 2px;
    font-size: 24px;
  }
  .textInputWrapper {
    position: relative;
    max-width: 600px;
    margin: 0 auto 10px auto;
  }
  .textInputWrapper button {
    position: absolute;
    right: 7px;
    top: -1px;
  }

  .filters {
    gap: 10px;
    margin: 5px 0;
  }
  main {
    flex: auto 1 1;
    overflow: scroll;
    width: 100%;
    display: flex;
    flex-direction: column;
    margin: auto;
  }

  .summary {
    z-index: 20;
    padding: 0 10px 10px 10px;
    flex: auto 0 0;
    position: relative;
  }
  .results h3 {
    margin: 10px;
  }
</style>
