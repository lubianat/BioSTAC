<script>
  import Main from "./Main.svelte";
  import Nav from "./Nav.svelte";
</script>

<div class="app">
  <Nav />
  <Main />
</div>

<style>
  .app {
    margin: 0;
    padding: 0;
    inset: 0;
    display: flex;
    flex-direction: column;
  }
</style>
