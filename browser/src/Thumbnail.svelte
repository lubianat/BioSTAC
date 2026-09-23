<script>
  // The catalog ships a thumbnail per item, so nothing is rendered from the Zarr here.
  export let src = undefined;
  export let thumbAspectRatio = 1;
  export let cssSize = 120;

  let width = cssSize;
  let height = cssSize;
  if (thumbAspectRatio > 1) height = width / thumbAspectRatio;
  else if (thumbAspectRatio < 1) width = height * thumbAspectRatio;

  let loaded = false;
</script>

<div class="thumbWrapper" style="width:{width}px; height:{height}px;" class:spinner={!loaded}>
  {#if src}
    <img
      {src}
      on:load={() => (loaded = true)}
      on:error={() => (loaded = true)}
      class:hidden={!loaded}
      style="width:{width}px; height:{height}px; object-fit:cover;"
      alt=""
    />
  {/if}
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
