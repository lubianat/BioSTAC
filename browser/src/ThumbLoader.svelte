<script>
  import Thumbnail from "./Thumbnail.svelte";

  export let rowData;

  let thumbAspectRatio = 1;
  if (rowData.size_x && rowData.size_y) {
    thumbAspectRatio = rowData.size_x / rowData.size_y;
  }
</script>

<Thumbnail src={rowData.thumbnail} cssSize={512} {thumbAspectRatio} />
