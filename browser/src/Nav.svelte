<script>
  import githubLogo from "/github-mark-white.svg";
  let base = import.meta.env.BASE_URL;

  console.log("Nav base", base);
</script>

<!-- base element used to define relative links -->
<base href={base} />

<nav>
  <!-- <a class="logolink" href={base}><img alt="OME Logo" src={omeMainNav} /></a>
  <a href={base}><h2>Zowser — an OME-Zarr browser</h2></a> -->
  <div style="flex: 1"></div>

  <a href="about/"> About </a>
  <a
    class="github"
    title="Open in GitHub"
    target="_blank"
    href="https://github.com/lubianat/zowser/"
  >
    <img alt="GitHub Logo" src={githubLogo} />
  </a>
</nav>

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

  a {
    color: white;
    text-decoration: none;
    display: block;
  }

  img {
    height: 30px;
  }
</style>
