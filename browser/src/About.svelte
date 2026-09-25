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
      <h2>About BioSTAC</h2>
      <p>
        BioSTAC borrows <a href="https://stacspec.org" target="_blank">STAC</a>,
        the SpatioTemporal Asset Catalog used for satellite imagery, to describe
        bioimages. The OME-Zarrs stay where their resources host them; BioSTAC
        publishes only metadata about them, in four kinds of object:
      </p>
      <dl>
        <dt>Catalog</dt>
        <dd>
          Organizes, holds no data: the root <code>catalog.json</code>, and one
          per resource (<code>idr/</code>, <code>bia/</code>).
        </dd>
        <dt>Collection</dt>
        <dd>
          One study (<code>idr0004/</code>, <code>S-BIAD963/</code>): a Catalog
          plus metadata — license, extent, summaries — and its RO-Crate.
          Collections are never nested.
        </dd>
        <dt>Item</dt>
        <dd>
          One OME-Zarr image or plate, with its organism, imaging method and
          size.
        </dd>
        <dt>Asset</dt>
        <dd>
          The files an Item or Collection points to: the OME-Zarr itself, at IDR
          or BIA, a thumbnail, the RO-Crate, a Parquet table.
        </dd>
      </dl>
      <svg
        viewBox="0 0 480 290"
        role="img"
        aria-label="Root Catalog, then resource Catalog, then study Collection, then Item, then Asset; each study Collection has its Items as a Parquet asset, merged into one Parquet file linked from the resource Catalog"
      >
        <defs>
          <marker id="aboutArrow" viewBox="0 0 10 10" refX="9" refY="5"
            markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
          </marker>
        </defs>
        {#each [["Catalog", "catalog.json"], ["Catalog", "idr/catalog.json"], ["Collection", "idr0004/collection.json"], ["Item", "<image>.json"], ["Asset", "OME-Zarr, at IDR"]] as [kind, file], i}
          <rect x="10" y={10 + i * 58} width="270" height="40" rx="6" />
          <text x="22" y={35 + i * 58}><tspan class="kind">{kind}</tspan> {file}</text>
          {#if i < 4}
            <line x1="145" y1={50 + i * 58} x2="145" y2={66 + i * 58} marker-end="url(#aboutArrow)" />
          {/if}
        {/each}
        <rect x="320" y="68" width="150" height="40" rx="6" class="parquet" />
        <text x="332" y="93">items.parquet</text>
        <line x1="280" y1="88" x2="318" y2="88" class="dashed" marker-end="url(#aboutArrow)" />
        <rect x="320" y="126" width="150" height="40" rx="6" class="parquet" />
        <text x="332" y="151">items.parquet</text>
        <line x1="280" y1="146" x2="318" y2="146" class="dashed" marker-end="url(#aboutArrow)" />
        <line x1="395" y1="126" x2="395" y2="110" marker-end="url(#aboutArrow)" />
        <text x="402" y="122" class="note">merged</text>
        <text x="320" y="190" class="note">one row per Item:</text>
        <text x="320" y="208" class="note">per study, and per</text>
        <text x="320" y="226" class="note">resource in one file</text>
      </svg>
      <p>
        The JSON tree can be walked link by link. The same Items are also
        <a href="https://github.com/stac-utils/stac-geoparquet" target="_blank"
          >stac-geoparquet</a
        >, one row each, which DuckDB or this gallery query in place over HTTP.
        Each study carries its own <code>items.parquet</code> (and, for IDR
        plates, <code>wells.parquet</code>); each resource links those merged into
        one file, so a query across a resource opens one file rather than one
        per study. <code>studies.parquet</code> indexes the study files: filter
        studies there, then read only theirs.
      </p>
    </section>
    <hr />
    <section>
      <h2>About the OME-NGFF Challenge</h2>
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
