<script>
  import { ngffTable } from "./tableStore";
  import { organismStore, imagingModalityStore } from "./ontologyStore";
  import ColumnSort from "./ColumnSort.svelte";
  import ImageList from "./ImageList.svelte";
  import PreviewPopup from "./PreviewPopup.svelte";
  import PageTitle from "./PageTitle.svelte";
  import FilterSelect from "./FilterSelect.svelte";
  import SourceChips from "./SourceChips.svelte";
  import { loadStac, loadTable } from "./stacStore";
  import { getConfig } from "./util";

  import form_select_bg_img from "/selectCaret.svg";

  // ────────────────────────────────────────────────────────────────
  // State
  // ────────────────────────────────────────────────────────────────
  let tableRows = [];
  let totalZarrs = 0;
  let totalBytes = 0;
  let showSourceColumn = false;

  let filters = {
    resource: "",
    collection: "",
    dimension: "",
    organism: "",
    modality: "",
    text: "",
  };

  // what the list shows, as the bioimage:levels it includes; for HCS a well is the image unit
  const VIEWS = {
    collection: { label: "Collections", levels: ["collection"] },
    image: { label: "Images", levels: ["image"] },
    plate: { label: "Plates", levels: ["plate"] },
    wells: { label: "Images + wells", levels: ["image", "well"] },
  };
  let view = "image";
  let wells = "loading"; // 139k rows: fetched in the background once the rest is shown

  function setView(v) {
    view = v;
    tableRows = applyFilters(ngffTable.getRows());
  }

  function openCollection(row) {
    filters.collection = row.collection;
    setView(row.has_wells ? "plate" : "image");
  }

  let sortedBy = "";
  let sortAscending = false;

  // ────────────────────────────────────────────────────────────────
  // Data loading & subscription
  // ────────────────────────────────────────────────────────────────
  getConfig()
    .then((cfg) => loadStac(cfg.stac))
    .then(() => loadTable("wells"))
    .then(() => (wells = "loaded"));
  tableRows = applyFilters(ngffTable.getRows());

  let allRows = [];
  let viewRows = []; // every row of the current view, before the filters

  // Single consolidated subscription
  ngffTable.subscribe((rows) => {
    allRows = rows; // This ensures allRows is always in sync
    tableRows = applyFilters(rows);
    totalBytes = rows.reduce((acc, r) => acc + (parseInt(r.written) || 0), 0);
    showSourceColumn = rows.some((r) => r.source);
  });

  // ────────────────────────────────────────────────────────────────
  // Filtering
  // ────────────────────────────────────────────────────────────────
  function applyFilters(rows) {
    const { resource, collection, dimension, organism, modality, text } =
      filters;
    const txt = text.toLowerCase();
    const levels = VIEWS[view].levels;
    rows = rows.filter((r) => levels.includes(r.level));
    if (rows.length !== viewRows.length || rows[0] !== viewRows[0]) viewRows = rows; // options follow only the view
    totalZarrs = rows.length;

    return rows.filter((r) => {
      if (dimension && String(r.dim_count) !== dimension) return false;
      if (organism && r.organismId !== organism) return false;
      if (modality && r.fbbiId !== modality) return false;
      if (resource && r.resource !== resource) return false;
      if (collection && r.collection !== collection) return false;

      if (txt && !r.haystack.includes(txt)) return false;
      return true;
    });
  }

  function setFilter(key, value) {
    filters[key] = value;
    tableRows = applyFilters(ngffTable.getRows());
  }

  // over 139k wells a keystroke per filter pass is too many: wait for a pause
  let textTimer;
  function filterText(e) {
    clearTimeout(textTimer);
    textTimer = setTimeout(() => setFilter("text", e.target.value), 200);
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
  // Derived options, from the whole view, so they don't churn with each filter
  // ────────────────────────────────────────────────────────────────
  const distinct = (rows, key) => new Set(rows.map((r) => r[key]).filter((v) => v != null && v !== ""));

  $: collectionOptions = Array.from(distinct(viewRows, "collection"))
    .sort()
    .map((v) => ({ value: String(v), label: `${v}` }));

  $: dimensionOptions = Array.from(distinct(viewRows, "dim_count"))
    .sort()
    .map((v) => ({ value: String(v), label: `${v}D` }));

  $: organismIds = distinct(viewRows, "organismId");
  $: fbbiIds = distinct(viewRows, "fbbiId");
  $: organismOptions = Object.entries($organismStore || {})
    .filter(([id]) => organismIds.has(id))
    .map(([id, name]) => ({ value: id, label: name }));

  $: modalityOptions = Object.entries($imagingModalityStore || {})
    .filter(([id]) => fbbiIds.has(id))
    .map(([id, name]) => ({ value: id, label: name }));

  $: filterOptions = {
    dimension: dimensionOptions,
    organism: organismOptions,
    modality: modalityOptions,
    collection: collectionOptions,
  };
</script>

<PreviewPopup />

<main style="--form-select-bg-img: url('{form_select_bg_img}')">
  <div class="summary">
    <PageTitle />
    <div class="views">
      {#each Object.entries(VIEWS) as [key, { label }]}
        <button class:active={view === key} on:click={() => setView(key)}>{label}</button>
      {/each}
    </div>
    <SourceChips value={filters.resource} onChange={(v) => setFilter("resource", v)} />
    <div class="textInputWrapper">
      <input
        bind:value={filters.text}
        on:input={filterText}
        placeholder="Type to filter"
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
            <option value="well_count">Wells</option>
          </select>
          <div>
            <ColumnSort {sortAscending} toggleAscending={toggleSortAscending} />
          </div>
        </div>
      </div>
    </div>

    <div class="results">
      <h3 style="margin-left: 15px">
        Showing {tableRows.length} out of {totalZarrs} {VIEWS[view].label.toLowerCase()}
        {#if view === "wells" && wells === "loading"}(loading wells…){/if}
      </h3>
      <ImageList {tableRows} textFilter={filters.text} onOpenCollection={openCollection} />
    </div>
  </div>
</main>

<style>
  .views {
    display: flex;
    justify-content: center;
    gap: 4px;
    margin-bottom: 10px;
  }
  .views button {
    padding: 4px 14px;
    border: 1px solid var(--border-color);
    border-radius: 16px;
    background: var(--light-background);
    cursor: pointer;
  }
  .views button.active {
    background: var(--border-color);
    font-weight: bold;
  }
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
