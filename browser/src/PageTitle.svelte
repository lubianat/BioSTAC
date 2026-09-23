<script>
  import { onMount } from "svelte";
  import YAML from "yaml";

  export let yamlUrl = `${import.meta.env.BASE_URL}config.yaml`;
  export let fallbackTitle = "";
  export let fallbackDescription = "";
  export let center = true;

  let title = "";
  let description = "";

  async function load() {
    try {
      const res = await fetch(yamlUrl, { cache: "no-store" });
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      const y = YAML.parse(await res.text()) || {};
      title = y?.config?.title || "";
      description = y?.config?.description || "";
    } catch (e) {
      console.warn("PageTitle: YAML load failed:", e);
      title = fallbackTitle;
      description = fallbackDescription;
    }
  }

  onMount(load);

  // HMR: re-run load after a hot patch so content reappears
  if (import.meta.hot) {
    import.meta.hot.accept();
    import.meta.hot.on("vite:afterUpdate", load);
  }

  $: displayTitle = title || fallbackTitle;
  $: displayDescription = description || fallbackDescription;
</script>

{#if displayTitle || displayDescription}
  <div class="catalogHeader" class:center>
    {#if displayTitle}<h2 class="catalogTitle">
        {@html displayTitle}
      </h2>{/if}
    {#if displayDescription}<p class="catalogDesc">
        {@html displayDescription}
      </p>{/if}
  </div>
{/if}

<style>
  .catalogHeader {
    max-width: 900px;
    margin: 10px auto 14px auto;
  }
  .catalogHeader.center {
    text-align: center;
  }
  .catalogTitle {
    margin: 0 0 6px 0;
    font-size: 1.35rem;
  }
  .catalogDesc {
    margin: 0;
    opacity: 0.9;
    white-space: pre-line; /* preserve YAML line breaks */
  }
</style>
