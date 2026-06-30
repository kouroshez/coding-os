---
name: wordpress
tier: stack
domain: [backend]
description: Build secure WordPress plugins and themes the WordPress way — hooks (actions/filters), nonces, capability checks, sanitize-on-input/escape-on-output, $wpdb->prepare, proper script enqueuing, and the REST API. Use when writing or reviewing a plugin/theme, hardening WP request handling, hooking into core, registering a block or REST route, or fixing "the plugin is insecure". Targets WordPress 6.x+ on PHP 8.3+. Triggers — "WordPress", "WP plugin", "theme", "add_action", "wpdb", "nonce", "shortcode", "Gutenberg block", "the loop". Pairs with php (the language), security-web (OWASP), sql-authoring (queries behind $wpdb).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# WordPress

WordPress has its own way of doing everything, and fighting it produces brittle, insecure code. Three WP-specific disciplines carry most of the safety: **nonces** (intent), **capability checks** (authorization), and **sanitize-in / escape-out** (data). The PHP language craft is owned by [php](../php/SKILL.md); this is the WordPress layer on top.

> Scan a plugin/theme for the WordPress security footguns:
> `python3 scripts/scan_wp_smells.py wp-content/plugins/myplugin/**/*.php`

## Hooks — the entire extension model

```php
// actions DO something; filters TRANSFORM and must return
add_action('init', 'myplugin_register');
add_filter('the_content', function (string $content): string {
    return $content . '<p>Appended.</p>';   // a filter MUST return the value
});
```

You extend WordPress by hooking, never by editing core. An `add_filter` callback
that forgets to `return` silently blanks the content. Register everything on the
right hook (`init`, `wp_enqueue_scripts`, `rest_api_init`) — running too early
means core isn't loaded yet. Detail → [references/wp-development.md](references/wp-development.md).

## The security trinity (every request handler)

```php
function myplugin_save(): void {
    // 1. NONCE — the request came from your form, not a forged one
    if (!isset($_POST['_wpnonce']) || !wp_verify_nonce($_POST['_wpnonce'], 'myplugin_save')) {
        wp_die('Bad nonce');
    }
    // 2. CAPABILITY — this user is allowed to do this
    if (!current_user_can('edit_posts')) {
        wp_die('Forbidden');
    }
    // 3. SANITIZE input, ESCAPE output
    $title = sanitize_text_field($_POST['title'] ?? '');
    update_post_meta($post_id, 'title', $title);
}
```

All three, every time. A nonce without a capability check stops forgery but not
an under-privileged user; a capability check without a nonce is CSRF-able;
neither without sanitizing is injection. Detail → [references/wp-security.md](references/wp-security.md).

## Database — `$wpdb->prepare`, always

```php
global $wpdb;
// Wrong — SQL injection
$wpdb->query("SELECT * FROM {$wpdb->posts} WHERE post_author = {$_GET['id']}");

// Correct — prepare() binds the placeholders
$rows = $wpdb->get_results(
    $wpdb->prepare("SELECT * FROM {$wpdb->posts} WHERE post_author = %d", $_GET['id'])
);
```

`$wpdb->prepare` with `%d`/`%s`/`%f` placeholders is WordPress's parameterization.
Use `$wpdb->posts` (table prefix-aware), never a hardcoded `wp_posts`. Prefer the
high-level APIs (`WP_Query`, `get_posts`, `update_post_meta`) over raw `$wpdb`
when they fit — they handle escaping and caching.

## Enqueue scripts/styles — never hardcode `<script>`

```php
add_action('wp_enqueue_scripts', function (): void {
    wp_enqueue_script('myplugin', plugins_url('app.js', __FILE__), ['wp-element'], '1.0.0', true);
    wp_localize_script('myplugin', 'MyPlugin', ['nonce' => wp_create_nonce('wp_rest')]);
});
```

`wp_enqueue_script/style` handles dependencies, versioning (cache-busting), and
de-duplication; a raw `<script>` tag in a template breaks all three. Pass data to
JS via `wp_localize_script`, not inline `echo`.

## REST API + blocks

Register routes on `rest_api_init` with a `permission_callback` (returning a
capability check — **never** `__return_true` for anything sensitive). Gutenberg
blocks register via `register_block_type` + `block.json`; server-rendered blocks
escape output the same as any template.

## Anti-patterns (reject on sight)

- A handler with no `wp_verify_nonce` → CSRF.
- A handler with no `current_user_can` → privilege escalation.
- Raw `$_POST`/`$_GET` into `$wpdb->query` or output → injection / XSS.
- `esc_html`/`sanitize_*` skipped → XSS / stored injection.
- Hardcoded `wp_` table prefix instead of `$wpdb->posts`/`$wpdb->prefix`.
- `<script>`/`<link>` in a template instead of `wp_enqueue_*`.
- REST route with `'permission_callback' => '__return_true'` on sensitive data.
- Editing core or a parent theme instead of hooks / a child theme.

## See also

- [references/wp-development.md](references/wp-development.md) — hooks, enqueue, the loop, REST, blocks, plugin/theme structure.
- [references/wp-security.md](references/wp-security.md) — nonces, capabilities, sanitize/escape function map, $wpdb.
- [assets/wp-checklist.md](assets/wp-checklist.md) — the review gate.
- [php](../php/SKILL.md) · [security-web](../security-web/SKILL.md) · [sql-authoring](../sql-authoring/SKILL.md).
