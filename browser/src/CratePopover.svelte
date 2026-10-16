<script>
  // The full row of an item, read from its item-list.parquet, and the study crate it belongs to.
  // Both are fetched when the popover opens, not before.
  import { detailsRow, loadDetails } from "./crateStore";

  let popover;
  let details;

  const EXPLORER = "https://arunaengine.github.io/ro-crate-explorer/?crateUrl=";
  const isUrl = (value) => typeof value === "string" && /^https?:/.test(value);
  const show = (value) =>
    value?.term_id ? `${value.term_label ?? ""} (${value.term_id})`
    : Array.isArray(value) ? value.join(", ")
    : typeof value === "bigint" ? Number(value).toLocaleString()
    : value instanceof Date ? value.toISOString().slice(0, 10)
    : String(value);

  detailsRow.subscribe((row) => {
    if (!row || !popover) return;
    details = loadDetails(row);
    popover.showPopover();
  });
</script>

<div bind:this={popover} id="cratePopover" popover on:toggle={(e) => e.newState === "closed" && detailsRow.set(null)}>
  <button class="close" title="Close" on:click={() => popover.hidePopover()}>&times;</button>
  {#if details}
    {#await details}
      <p>Loading…</p>
    {:then { item, crate, crateUrl }}
      <section>
        <h3>Study: {crate.name}</h3>
        <p>
          <a href={crateUrl} target="_blank" rel="noreferrer">ro-crate-metadata.json</a> ·
          <a href={EXPLORER + encodeURIComponent(crateUrl)} target="_blank" rel="noreferrer">open in RO-Crate Explorer</a>
          {#if isUrl(crate.url)} · <a href={crate.url} target="_blank" rel="noreferrer">study page</a>{/if}
        </p>
        <table>
          {#each [["Identifier", crate.identifier], ["Published", crate.datePublished], ["License", crate.license],
                  ["Authors", crate.authors], ["Organisms", crate.organisms], ["Imaging methods", crate.methods],
                  ["Keywords", crate.keywords]] as [label, value]}
            {#if value?.length}<tr><td>{label}</td><td>{show(value)}</td></tr>{/if}
          {/each}
          {#each crate.publications as publication}
            <tr><td>Publication</td><td>{#if isUrl(publication.url)}<a href={publication.url} target="_blank" rel="noreferrer">{publication.name}</a>{:else}{publication.name}{/if}</td></tr>
          {/each}
        </table>
        {#if crate.description}<p class="description">{crate.description}</p>{/if}
      </section>
      {#if item}
        <section>
          <h3>Item: {item.title ?? item.id}</h3>
          <table>
            {#each Object.entries(item).filter(([, v]) => v != null) as [key, value]}
              <tr><td>{key}</td><td>{#if isUrl(value)}<a href={value} target="_blank" rel="noreferrer">{value}</a>{:else}{show(value)}{/if}</td></tr>
            {/each}
          </table>
        </section>
      {/if}
    {:catch error}
      <p>Could not load the details: {error.message}</p>
    {/await}
  {/if}
</div>

<style>
  #cratePopover {
    width: min(900px, 95vw);
    max-height: 85vh;
    overflow: auto;
    padding: 10px 20px;
    box-shadow: 5px 4px 10px -5px #737373;
  }
  .close {
    position: sticky;
    float: right;
    top: 0;
    font-size: 2rem;
    padding: 2px 9px;
  }
  table {
    border-collapse: collapse;
    font-size: 0.9rem;
  }
  td {
    padding: 2px 8px;
    vertical-align: top;
    overflow-wrap: anywhere;
  }
  td:first-child {
    white-space: nowrap;
    color: #555;
  }
  .description {
    white-space: pre-line;
  }
</style>
