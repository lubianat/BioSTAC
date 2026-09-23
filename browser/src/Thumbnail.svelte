<script>
  import { onMount, onDestroy } from "svelte";
  import * as omezarr from "ome-zarr.js";
  import { thumbnailFromConvention } from "./util.js";

  export let source;
  export let thumbAspectRatio = 1;
  export let cssSize = 120;
  export let max_size = 512;

  const BASE = import.meta.env.BASE_URL;

  let imgEl;
  let showSpinner = true;
  // mode: 'none' | 'cached' | 'live'
  let mode = "none";

  // initial css box respecting aspect ratio
  let width = cssSize;
  let height = cssSize;
  if (thumbAspectRatio > 1) height = width / thumbAspectRatio;
  else if (thumbAspectRatio < 1) width = height * thumbAspectRatio;
  let cssWidth = width;
  let cssHeight = height;

  const controller = new AbortController();

  function basenameFromSource(src) {
    try {
      const u = new URL(src, window.location.href);
      const parts = u.pathname.split("/").filter(Boolean);
      return parts[parts.length - 1];
    } catch {
      const parts = src.split("?")[0].split("/");
      return parts[parts.length - 1];
    }
  }

  async function tryCachedFirst() {
    const thumbName = basenameFromSource(source);
    const cachedUrl = `${BASE}thumbs/${thumbName}.jpg`;

    const probe = new Image();
    probe.decoding = "async";
    probe.referrerPolicy = "no-referrer";

    return new Promise((resolve) => {
      probe.onload = () => {
        mode = "cached";
        showSpinner = false;
        if (imgEl) imgEl.src = cachedUrl;
        resolve(true);
      };
      probe.onerror = () => resolve(false);
      probe.src = cachedUrl;
    });
  }

  async function loadWithOmeZarr() {
    try {
      console.log(`Loading thumbnail for ${source} with ome-zarr.js`);
      const dataUrl = await omezarr.renderThumbnail(
        source,
        cssSize,
        true,
        max_size,
      );
      mode = "live";
      if (imgEl) imgEl.src = dataUrl;
      showSpinner = false;
    } catch (err) {
      // Keep spinner indefinitely (your preferred failure mode)
      console.warn("Thumbnail generation failed:", err);
    }
  }

  async function tryConvention() {
    const url = await thumbnailFromConvention(source, max_size);
    if (!url) return false;
    mode = "cached";
    showSpinner = false;
    if (imgEl) imgEl.src = url;
    return true;
  }

  onMount(async () => {
    if (await tryCachedFirst()) return;
    if (await tryConvention()) return;
    await loadWithOmeZarr();
  });

  onDestroy(() => controller.abort());
</script>

<div
  class="thumbWrapper"
  style="width:{cssWidth}px; height:{cssHeight}px;"
  class:spinner={showSpinner}
>
  <img
    bind:this={imgEl}
    class:hidden={mode === "none"}
    style="width:{cssWidth}px; height:{cssHeight}px; object-fit:cover;"
    alt=""
    aria-hidden={mode === "none"}
  />
</div>

<style>
  .hidden {
    display: none;
  }
  .thumbWrapper {
    position: relative;
  }
  img {
    box-shadow: 5px 4px 10px -5px #737373;
  }

  @keyframes spinner {
    to {
      transform: rotate(360deg);
    }
  }
  .spinner::after {
    content: "";
    box-sizing: border-box;
    position: absolute;
    inset: 50% auto auto 50%;
    width: 40px;
    height: 40px;
    margin-left: -20px;
    margin-top: -20px;
    border-radius: 50%;
    border: 5px solid rgba(180, 180, 180, 0.6);
    border-top-color: rgba(0, 0, 0, 0.6);
    animation: spinner 0.6s linear infinite;
  }
</style>
