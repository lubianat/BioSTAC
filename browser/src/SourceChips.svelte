<script>
  // One chip per resource the catalog publishes, named by the catalog itself: the
  // Collection id on the chip, its title and description in the tooltip.
  // Picking one filters the list; picking it again clears the filter.
  import { resourceStore } from "./stacStore";

  export let value = "";
  export let onChange;
</script>

{#if $resourceStore.length > 1}
  <div class="chips">
    {#each $resourceStore as resource}
      <button
        class="chip"
        class:selected={value === resource.id}
        title="{resource.title}&#10;{resource.description}"
        on:click={() => onChange(value === resource.id ? "" : resource.id)}
      >
        {resource.id.toUpperCase()}
        {#if value === resource.id}<span class="clear">&times;</span>{/if}
      </button>
    {/each}
  </div>
{/if}

<style>
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    margin: 0 auto 10px auto;
  }
  .chip {
    border: solid var(--border-color) 1px;
    border-radius: 16px;
    background-color: var(--light-background);
    padding: 5px 14px;
    font-size: 0.95rem;
    cursor: pointer;
    color: inherit;
  }
  .chip.selected {
    border-color: #555;
    box-shadow: inset 0 0 0 1px #555;
    font-weight: 600;
  }
  .clear {
    margin-left: 6px;
    opacity: 0.6;
  }
</style>
