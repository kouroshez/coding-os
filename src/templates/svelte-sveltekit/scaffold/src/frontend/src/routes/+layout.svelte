<script lang="ts">
  // Root shell for {{PROJECT_NAME}} — nav + a11y landmark; pages render via {@render children()}.
  let { children } = $props();
</script>

<a href="#main" class="skip-link">Skip to content</a>
<header>
  <nav aria-label="Primary">
    <a href="/">{{PROJECT_NAME}}</a>
  </nav>
</header>
<main id="main">
  {@render children()}
</main>

<style>
  .skip-link {
    position: absolute;
    left: -999px;
  }
  .skip-link:focus {
    left: 1rem;
  }
</style>
