<script>
  import omeMainNav from "/ome-main-nav.svg";
  import githubLogo from "/github-mark-white.svg";
  import About from "./About.svelte";

  let about;
</script>

<nav>
  <a
    class="logolink"
    href="https://ome.github.io/ome2024-ngff-challenge/"
    title="The 2024 OME-NGFF challenge, which this is built from"
    target="_blank"><img alt="OME Logo" src={omeMainNav} /></a
  >
  <h2>BioSTAC <span>— 2024 NGFF Challenge</span></h2>
  <div style="flex: 1"></div>

  <button on:click={() => about.show()}>About</button>
  <a
    class="github"
    title="Open in GitHub"
    target="_blank"
    href="https://github.com/lubianat/BioSTAC/"
  >
    <img alt="GitHub Logo" src={githubLogo} />
  </a>
</nav>

<About bind:this={about} />

<style>
  nav {
    top: 0;
    left: 0;
    width: 100%;
    display: flex;
    flex-direction: row;
    margin: 0;
    padding: 5px 15px;
    background-color: #202428;
    z-index: 20;
    align-items: center;
    box-sizing: border-box;
    flex: auto 0 0;
    gap: 5px;
  }

  h2 {
    color: white;
    font-weight: 300;
    margin: 5px 15px;
    font-size: 1.2rem;
  }
  h2 span {
    opacity: 0.7;
  }
  a,
  button {
    color: white;
    text-decoration: none;
    display: block;
    background: transparent;
    border: none;
    font-size: 1rem;
    cursor: pointer;
  }
  .logolink,
  img {
    height: 30px;
  }
  .github img,
  .github {
    height: 20px;
  }
  .github {
    margin: 0 10px;
  }

  @media (max-width: 600px) {
    h2 span {
      display: none;
    }
  }
</style>
