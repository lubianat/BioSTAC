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

  // a dropdown filter matches a row field exactly; a typed one (IDR annotations, too many values
  // for a dropdown) matches any part of it
  const SELECT_FIELDS = {
    dimension: "dim_count", organism: "organismId", modality: "fbbiId", collection: "collection",
    license: "license", control: "control", cell_line: "cell_line",
  };
  const TYPED_FIELDS = { gene: "gene", compound: "compound", sirna: "sirna" };
  const SIZES = ["x", "y", "z", "c", "t"].map((d) => ({ value: `size_${d}`, label: `Size: ${d.toUpperCase()}` }));
  const BYTES = { value: "written", label: "Data size" };

  let filters = { resource: "", text: "" };
  let viewRows = []; // every row of the current view, before the filters (declared before applyFilters first runs)
  let facetCounts = {}; // dropdown -> value -> rows, under every other filter

  // what the list shows, as the bioimage:levels it includes; for HCS a well is the image unit
  const VIEWS = {
    collection: {
      label: "Collections", levels: ["collection"],
      selects: ["organism", "modality", "license"],
      // a collection holds many sizes: sort by the smallest or largest of its images
      sorts: [
        ...["y", "x", "z", "c", "t"].flatMap((d) => [
          { value: `size_max_${d}`, label: `Max ${d.toUpperCase()}` },
          { value: `size_min_${d}`, label: `Min ${d.toUpperCase()}` },
        ]),
        BYTES,
        { value: "item_count", label: "Items" },
      ],
    },
    image: {
      label: "Images", levels: ["image"],
      selects: ["dimension", "organism", "modality", "collection"],
      sorts: [...SIZES, BYTES],
    },
    plate: {
      label: "Plates", levels: ["plate"],
      selects: ["organism", "modality", "collection"],
      sorts: [{ value: "well_count", label: "Wells" }, BYTES],
    },
    wells: {
      label: "Images + wells", levels: ["image", "well"],
      selects: ["dimension", "organism", "modality", "collection", "control", "cell_line"],
      typed: ["gene", "compound", "sirna"],
      sorts: [...SIZES, BYTES],
    },
  };
  let view = "image";
  let wells = "loading"; // 139k rows: fetched in the background once the rest is shown

  function setView(v) {
    view = v;
    // a filter the new view does not show would still apply, invisibly: drop it
    const shown = [...VIEWS[v].selects, ...(VIEWS[v].typed ?? []), "resource", "text", "collection"];
    for (const key of Object.keys(filters)) if (!shown.includes(key)) delete filters[key];
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
    const txt = filters.text.toLowerCase();
    const selects = Object.entries(filters).filter(([k, v]) => v && SELECT_FIELDS[k]);
    const typed = Object.entries(filters).filter(([k, v]) => v && TYPED_FIELDS[k]).map(([k, v]) => [k, v.toLowerCase()]);
    const levels = VIEWS[view].levels;
    rows = rows.filter((r) => levels.includes(r.level));
    if (rows.length !== viewRows.length || rows[0] !== viewRows[0]) viewRows = rows; // options follow only the view
    totalZarrs = rows.length;

    // Crossfiltering in one pass: a dropdown's options are the values left by every *other* filter,
    // so a row failing only that dropdown's own selection still counts toward it (and you can switch
    // within it). Text, resource and typed fields are not dropdowns: failing them drops the row.
    const facets = VIEWS[view].selects;
    const counts = Object.fromEntries(facets.map((f) => [f, new Map()]));
    const tally = (f, r) => {
      const v = r[SELECT_FIELDS[f]];
      if (v != null && v !== "") counts[f].set(String(v), (counts[f].get(String(v)) ?? 0) + 1);
    };
    const results = [];
    for (const r of rows) {
      if (filters.resource && r.resource !== filters.resource) continue;
      if (typed.some(([k, v]) => !r[TYPED_FIELDS[k]]?.toLowerCase().includes(v))) continue;
      if (txt && !r.haystack.includes(txt)) continue;
      let failed = null;
      let fails = 0;
      for (const [k, v] of selects) if (String(r[SELECT_FIELDS[k]]) !== v && ++fails === 1) failed = k;
      if (fails === 0) {
        results.push(r);
        for (const f of facets) tally(f, r);
      } else if (fails === 1 && counts[failed]) tally(failed, r);
    }
    facetCounts = counts;
    return results;
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
  // Derived options: dropdowns from the facet counts, typed fields from the whole view
  // ────────────────────────────────────────────────────────────────
  const distinct = (rows, key) => new Set(rows.map((r) => r[key]).filter((v) => v != null && v !== ""));

  // what the catalog calls an ontology id, else the value itself
  $: names = { organism: $organismStore || {}, modality: $imagingModalityStore || {} };
  const label = (names, key, value) => (key === "dimension" ? `${value}D` : (names[key]?.[value] ?? value));
  $: filterOptions = Object.fromEntries(
    VIEWS[view].selects.map((key) => [
      key,
      Array.from(facetCounts[key] ?? [])
        .map(([value, n]) => ({ value, label: `${label(names, key, value)} (${n.toLocaleString()})` }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    ]),
  );
  $: typedOptions = Object.fromEntries(
    (VIEWS[view].typed ?? []).map((key) => [key, Array.from(distinct(viewRows, TYPED_FIELDS[key])).sort()]),
  );
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
            label={key.replace("_", " ")}
            value={filters[key] ?? ""}
            {options}
            onChange={(v) => setFilter(key, v)}
          />
        {/each}
        {#each Object.entries(typedOptions) as [key, options]}
          <input
            class="typed"
            list="{key}-options"
            placeholder={key === "sirna" ? "siRNA" : key}
            value={filters[key] ?? ""}
            on:change={(e) => setFilter(key, e.target.value)}
          />
          <datalist id="{key}-options">
            {#each options as option}<option value={option}></option>{/each}
          </datalist>
        {/each}
        <div class="clear"></div>

        <div>Sort by:</div>
        <div class="selectWrapper">
          <select on:change={handleSort}>
            <option value="">--</option>
            <hr />
            {#each VIEWS[view].sorts as sort}
              <option value={sort.value}>{sort.label}</option>
            {/each}
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
  input.typed {
    display: block;
    width: 100%;
    box-sizing: border-box;
    padding: 0.3rem 0.75rem;
    font-size: 1rem;
    margin: 3px 0;
    background-color: var(--light-background);
    border: 1px solid var(--border-color);
    border-radius: 0.375rem;
  }
  .sidebarContainer {
    display: flex;
    flex-direction: row;
  }

  .sidebar {
    flex: 0 0 250px;
    min-width: 0;
    box-sizing: border-box;
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
