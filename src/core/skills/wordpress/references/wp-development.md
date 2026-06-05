<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# WordPress Development — Hooks, Enqueue, Loop, REST, Blocks

> P: Build plugins/themes the WordPress way so code survives core updates.
> R: Writing a plugin/theme, registering a route/block, or rendering content.
> S: Security specifics — see [wp-security.md](wp-security.md).
> N: [SKILL.md](../SKILL.md), [wp-checklist.md](../assets/wp-checklist.md)

> Nav: [Skill](../SKILL.md)

## Actions vs filters

| | Action | Filter |
|---|---|---|
| purpose | DO something (side effect) | TRANSFORM a value |
| returns | nothing | the (modified) value — ALWAYS |
| example | `add_action('init', $fn)` | `add_filter('the_title', $fn)` |

A filter callback that doesn't `return` blanks the value it was given — the most
common WordPress bug. Hook priority (3rd arg) orders callbacks; accepted-args
(4th) controls how many params core passes.

## Plugin/theme structure

```
my-plugin/
├── my-plugin.php        # header comment + bootstrap (hooks only, no logic dump)
├── includes/            # classes, autoloaded
├── assets/              # js/css (enqueued, never inline)
└── languages/           # i18n .pot/.po
```

Use a child theme to customize a theme (never edit the parent — updates wipe it).
Namespacing or a unique prefix on every function/option/meta key avoids
collisions with other plugins.

## The loop + WP_Query

```php
$q = new WP_Query(['post_type' => 'book', 'posts_per_page' => 10]);
while ($q->have_posts()) { $q->the_post(); the_title('<h2>', '</h2>'); }
wp_reset_postdata();   // ALWAYS reset after a custom query
```

Prefer `WP_Query`/`get_posts` over raw `$wpdb` — they cache and escape. Always
`wp_reset_postdata()` after a secondary loop or the global `$post` stays wrong.

## Enqueue (the only way to load assets)

```php
add_action('wp_enqueue_scripts', function (): void {
  wp_enqueue_style('mp', plugins_url('app.css', __FILE__), [], '1.0.0');
  wp_enqueue_script('mp', plugins_url('app.js', __FILE__), [], '1.0.0', true);  // true = footer
});
```

`wp_enqueue_*` dedupes, versions (cache-bust), and resolves dependencies. Pass
PHP→JS data with `wp_localize_script` / `wp_add_inline_script`, never `echo` into
a `<script>`.

## REST API + blocks

```php
add_action('rest_api_init', function (): void {
  register_rest_route('myplugin/v1', '/items', [
    'methods'  => 'GET',
    'callback' => 'myplugin_items',
    'permission_callback' => fn() => current_user_can('read'),   // never __return_true on sensitive data
  ]);
});
```

Blocks register with `register_block_type(__DIR__ . '/build')` reading
`block.json` (the SSOT for a block's metadata). Server-rendered blocks escape
output exactly like a template.
