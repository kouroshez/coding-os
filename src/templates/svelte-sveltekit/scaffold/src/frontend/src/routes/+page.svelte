<script lang="ts">
  import type { PageData } from "./$types";

  // {{PROJECT_NAME}} landing page — presentational; data comes from +page.ts load.
  let { data }: { data: PageData } = $props();
</script>

<h1>{data.title}</h1>
<p>Scaffolded by coding-os — see docs/playbooks/svelte-sveltekit-app.md to add routes.</p>
