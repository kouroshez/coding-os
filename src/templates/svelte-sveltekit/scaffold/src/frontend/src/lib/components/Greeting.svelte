<script lang="ts">
  // Reusable presentational component for {{PROJECT_NAME}} — props in, markup out.
  let { name }: { name: string } = $props();
</script>

<p>Hello, {name}.</p>
