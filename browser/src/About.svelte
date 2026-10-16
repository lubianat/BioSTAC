<script>
  import nfdiLogo from "/nfdi_rgb_Wortmarke_Zusatz_quer.png";
  import cziLogo from "/czi-logo-chan-zuckerberg-initiative-logo.png";

  let popover;

  export function show() {
    popover?.showPopover();
  }
</script>

<div bind:this={popover} id="aboutPopover" popover>
  <button class="close" title="Close" on:click={() => popover.hidePopover()}
    >&times;</button
  >
  <div class="content">
    <section>
      <h2>1. The RO-BioSTAC specification</h2>
      <p>
        BioSTAC describes bioimages as nested
        <a href="https://www.researchobject.org/ro-crate/" target="_blank">RO-Crates</a>,
        with Parquet lists for search. The OME-Zarrs stay where their resources host them;
        BioSTAC publishes only metadata about them, at three levels:
      </p>
      <dl>
        <dt>Catalog</dt>
        <dd>
          Organizes, holds no data: the root crate, and one per resource
          (<code>idr/</code>, <code>bia/</code>). A resource crate nests its study crates
          and lists <code>study-list.parquet</code>, one row per study.
        </dd>
        <dt>Study</dt>
        <dd>
          One study (<code>idr0004/</code>, <code>S-BIAD963/</code>): the crate its source
          publishes, or one BioSTAC writes, listing one file, <code>item-list.parquet</code>.
          Studies are never nested.
        </dd>
        <dt>Item</dt>
        <dd>
          One OME-Zarr — an image, a plate, or a plate's well — as a row of that list, with
          its organism, imaging method and size, and absolute URLs to the Zarr and its own crate.
        </dd>
      </dl>
      <svg
        viewBox="0 0 480 200"
        role="img"
        aria-label="Root crate, then resource crate with study-list.parquet, then study crate with item-list.parquet, whose rows point by absolute URL to OME-Zarrs"
      >
        <defs>
          <marker id="aboutArrow" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
          </marker>
        </defs>
        {#each [["Catalog", "ro-crate-metadata.json", "study-list.parquet"], ["Study", "ro-crate-metadata.json", "item-list.parquet"], ["Item", "example.zarr/", "at IDR, BIA, …"]] as [kind, file, list], i}
          <rect x="10" y={10 + i * 66} width="250" height="44" rx="6" />
          <text x="22" y={37 + i * 66}><tspan class="kind">{kind}</tspan> {file}</text>
          <rect x="300" y={10 + i * 66} width="170" height="44" rx="6" class={i < 2 ? "parquet" : ""} />
          <text x="312" y={37 + i * 66}>{list}</text>
          {#if i < 2}
            <line x1="135" y1={54 + i * 66} x2="135" y2={74 + i * 66} marker-end="url(#aboutArrow)" />
            <line x1="385" y1={54 + i * 66} x2="385" y2={74 + i * 66} class="dashed" marker-end="url(#aboutArrow)" />
          {/if}
        {/each}
      </svg>
      <p>
        The crates can be walked link by link with any RO-Crate tool. The lists are what this
        gallery and DuckDB query in place over HTTP: filter studies in
        <code>study-list.parquet</code>, then read only their <code>item-list.parquet</code>.
        Each list holds images and plates first and wells after, so the gallery reads the wells
        of IDR's plates only when you ask for them.
      </p>
    </section>
    <hr />
    <section>
      <h2>2. The demo website</h2>
      <p>
        This gallery is a static site with no server or database of its own. Your browser
        does all the work, fetching the catalog straight from where it is published.
      </p>
      <dl>
        <dt>Front end</dt>
        <dd>
          <a href="https://svelte.dev" target="_blank">Svelte</a>, built with
          <a href="https://vitejs.dev" target="_blank">Vite</a> into plain HTML, JS and CSS.
          A GitHub Actions workflow builds it on every push to <code>main</code> and
          publishes it to GitHub Pages.
        </dd>
        <dt>Catalog hosting</dt>
        <dd>
          The crates and Parquet lists are files in a
          <a href="https://huggingface.co/buckets/tiagolubiana/RO-BioSTAC_demo" target="_blank"
            >Hugging Face bucket</a
          >, uploaded with <code>hf buckets sync</code>. Hugging Face serves them over
          HTTPS with CORS and range requests, so they need no API in front.
          <code>config.yaml</code> names the root crate; point it at another one to show
          another catalog.
        </dd>
        <dt>Reading Parquet</dt>
        <dd>
          <a href="https://github.com/hyparam/hyparquet" target="_blank">hyparquet</a>, a
          pure-JavaScript Parquet reader (with
          <a href="https://github.com/hyparam/hyparquet-compressors" target="_blank"
            >hyparquet-compressors</a
          >) — no DuckDB, no WebAssembly. It reads a file's footer, then fetches only the row
          groups it needs over HTTP range requests, so IDR's wells stay unfetched until you
          ask for them.
        </dd>
        <dt>Search</dt>
        <dd>
          Filtering, sorting and the virtual-scrolled list run in memory over the loaded
          rows. Nothing opens a Zarr to build the list: shape, organism, imaging method, size
          and thumbnail are already columns of the Parquet.
        </dd>
        <dt>Viewing</dt>
        <dd>
          Opening an image hands its OME-Zarr URL to an external viewer, which reads the
          Zarr directly from IDR or the BioImage Archive. The images never pass through
          BioSTAC.
        </dd>
      </dl>
    </section>
    <hr />
    <section>
      <h2>3. The OME-NGFF Challenge</h2>
      <p>
        The <a href="https://github.com/ome/ome2024-ngff-challenge" target="_blank"
          >2024 OME-NGFF challenge</a
        > set out to generate a petabyte of OME-Zarr written to a development
        version of the specification — what became OME-Zarr 0.5, on Zarr v3. The
        aim was to drive implementations forward and to measure what converting
        real data costs, so that others know what to expect.
      </p>
      <p>Each converted dataset had:</p>
      <ul>
        <li>its Zarr v2 arrays rewritten as Zarr v3, optionally sharded;</li>
        <li>
          its <code>.zattrs</code> metadata moved to
          <code>zarr.json["attributes"]["ome"]</code>;
        </li>
        <li>
          a top-level <code>ro-crate-metadata.json</code> naming its specimen and
          imaging modality, and a license.
        </li>
      </ul>
      <p>
        The conversions were done with the challenge's own
        <code>ome2024-ngff-challenge resave</code> tool. Seven sources took part:
        IDR, the BioImage Archive, JAX, WebKnossos, the Crick,
        NFDI4BIOIMAGE and SSBD. The results can be browsed in the
        <a href="https://ome.github.io/ome2024-ngff-challenge/" target="_blank"
          >challenge's gallery</a
        >, which this one is built on.
      </p>
      <p>
        BioSTAC catalogs two of those sources so far, IDR and the BioImage
        Archive, and serves the catalog from Hugging Face buckets. It shows the
        STAC specification repurposed for bioimaging, and how STAC could support
        federated search across resources.
      </p>
      <p class="thanks">
        Coordination of the challenge was supported by the
        <a href="https://www.nfdi.de/" target="_blank"
          >German National Research Data Initiative (NFDI)</a
        >
        and the
        <a href="https://chanzuckerberg.com/" target="_blank"
          >Chan Zuckerberg Initiative</a
        >.
      </p>
      <div class="logos">
        <img src={nfdiLogo} alt="NFDI" />
        <img src={cziLogo} alt="Chan Zuckerberg Initiative" />
      </div>
    </section>
  </div>
</div>

<style>
  #aboutPopover {
    position: fixed;
    inset: 50% auto auto 50%;
    transform: translate(-50%, -50%);
    width: min(640px, 92vw);
    max-height: 80vh;
    overflow: auto;
    border: solid var(--border-color) 1px;
    border-radius: 8px;
    box-shadow: 5px 4px 20px -5px #737373;
    padding: 0;
  }
  #aboutPopover::backdrop {
    background-color: rgba(0, 0, 0, 0.4);
  }
  .content {
    padding: 20px 24px 24px 24px;
  }
  h2 {
    margin: 0 0 12px 0;
  }
  p {
    line-height: 1.5;
  }
  .thanks {
    font-size: 0.9rem;
    opacity: 0.85;
  }
  .close {
    position: absolute;
    right: 8px;
    top: 8px;
    font-size: 1.8rem;
    line-height: 1;
    padding: 0 8px;
    background: transparent;
    border: none;
    cursor: pointer;
  }
  .logos {
    display: flex;
    align-items: center;
    gap: 20px;
  }
  .logos img {
    height: 34px;
  }
  hr {
    border: none;
    border-top: solid var(--border-color) 1px;
    margin: 24px 0;
  }
  ul {
    line-height: 1.5;
    padding-left: 20px;
  }
  dt {
    font-weight: 600;
  }
  dd {
    margin: 0 0 8px 16px;
  }
  svg {
    display: block;
    width: 100%;
    max-width: 480px;
    margin: 16px auto;
    font-size: 13px;
  }
  svg rect {
    fill: none;
    stroke: currentColor;
    stroke-opacity: 0.5;
  }
  svg rect.parquet {
    stroke-dasharray: 4 3;
  }
  svg line {
    stroke: currentColor;
  }
  svg line.dashed {
    stroke-dasharray: 4 3;
  }
  svg text {
    fill: currentColor;
    font-family: monospace;
  }
  svg .kind {
    font-family: inherit;
    font-weight: 600;
  }
  svg .note {
    font-family: inherit;
    font-style: italic;
    opacity: 0.7;
  }
</style>
