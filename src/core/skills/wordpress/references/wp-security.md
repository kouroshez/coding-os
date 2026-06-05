<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# WordPress Security — Nonces, Capabilities, Sanitize/Escape, $wpdb

> P: The WordPress-specific defensive functions and exactly when each applies.
> R: Handling any request, output, or database access in a plugin/theme.
> S: General OWASP / PHP-language security — [security-web](../../security-web/SKILL.md) + [php](../../php/SKILL.md).
> N: [SKILL.md](../SKILL.md), [wp-development.md](wp-development.md)

> Nav: [Skill](../SKILL.md)

## Nonces — prove intent (anti-CSRF)

```php
// in the form
wp_nonce_field('myplugin_save', '_wpnonce');
// in the handler
check_admin_referer('myplugin_save');     // dies on failure (admin forms)
// AJAX
check_ajax_referer('myplugin_ajax', 'nonce');
```

A nonce ties a request to a user + action + short time window — it stops a forged
cross-site request. It is **not** authorization (see capabilities) and not a
replacement for sanitizing.

## Capabilities — prove authorization

```php
if (!current_user_can('manage_options')) { wp_die('Forbidden'); }
```

Check the **capability** (`edit_posts`, `manage_options`, `delete_users`), never
the role name — capabilities are the stable API. For a specific object:
`current_user_can('edit_post', $post_id)`.

## Sanitize on input, escape on output

| Input → sanitize | Output → escape |
|---|---|
| `sanitize_text_field($s)` | `esc_html($s)` (HTML body) |
| `sanitize_email($e)` | `esc_attr($s)` (HTML attribute) |
| `absint($n)` | `esc_url($u)` (href/src) |
| `sanitize_key($k)` | `esc_js($s)` (inline JS) |
| `wp_kses_post($html)` (allow safe HTML) | `wp_kses($html, $allowed)` |

Sanitize when you store; escape when you render, for the **context**. `wp_kses`
is for "allow some HTML" (a comment body); `esc_html` is for "allow none". Never
trust data even from the database — escape on output regardless of source.

## $wpdb — prepare everything

```php
$wpdb->get_results(
  $wpdb->prepare("SELECT * FROM {$wpdb->prefix}orders WHERE status = %s AND total > %d",
                 $status, $min)
);
```

`%s` (string), `%d` (int), `%f` (float). The table name uses `$wpdb->prefix` /
`$wpdb->posts` (multisite + custom-prefix safe). Prefer `WP_Query`,
`get_post_meta`, `get_option` over raw SQL — they escape and cache for free.

## Options & meta

`update_option`/`get_option` and `update_post_meta`/`get_post_meta` store data —
sanitize before storing, escape on output. Register settings with a
`sanitize_callback` so the Settings API enforces it. Never store secrets in an
autoloaded option (loads on every request).
