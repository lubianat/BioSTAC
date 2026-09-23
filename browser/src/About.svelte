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
    <h2>About BioSTAC</h2>
    <p>
      BioSTAC is an experimental <a href="https://stacspec.org" target="_blank"
        >STAC</a
      >
      catalog of the submissions to the
      <a href="https://ome.github.io/ome2024-ngff-challenge/" target="_blank"
        >2024 OME-NGFF challenge</a
      >: one Collection per contributing resource, one Item per OME-Zarr
      image/plate. Everything below comes from HuggingFace; the catalog's
      Parquet files and the pre-rendered thumbnails linked by them.
    </p>
    <p>
      OME-Zarrs stay where their resources put them. BioSTAC re-publishes
      metadata in Parquet and JSON, served from Hugging Face buckets. It is a
      demonstration of the STAC specification hijacked for bioimaging, and of
      the potential of STAC to enable federated search across multiple
      resources.
    </p>
    <p class="thanks">
      Coordination of the challenge this derives from was supported by the
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
</style>
