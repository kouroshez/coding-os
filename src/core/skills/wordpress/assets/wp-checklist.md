<!-- domain:BACKEND | layer:asset | ssot:false | updated:2026-06-04 -->
# WordPress Plugin/Theme Review Checklist

Run before shipping a plugin or theme.

## The security trinity (every request handler)
- [ ] Nonce verified (`wp_verify_nonce`/`check_admin_referer`/`check_ajax_referer`).
- [ ] Capability checked (`current_user_can('<cap>')`) — not a role name.
- [ ] Input sanitized (`sanitize_text_field`/`absint`/`wp_kses_post`).
- [ ] Output escaped for context (`esc_html`/`esc_attr`/`esc_url`).

## Database
- [ ] Every `$wpdb` query uses `->prepare()` with `%d`/`%s`/`%f`.
- [ ] Table names via `$wpdb->prefix`/`$wpdb->posts` — never hardcoded `wp_`.
- [ ] High-level APIs (`WP_Query`, `get_post_meta`) preferred over raw SQL.

## WordPress way
- [ ] Extends via hooks; no core / parent-theme edits (child theme used).
- [ ] Filters always `return`; callbacks on the correct hook.
- [ ] Assets via `wp_enqueue_*` (versioned), data via `wp_localize_script`.
- [ ] `wp_reset_postdata()` after every secondary loop.
- [ ] REST routes have a real `permission_callback` (never `__return_true` on sensitive data).
- [ ] Unique prefix/namespace on functions, options, meta keys.

## Verify
- [ ] `python3 scripts/scan_wp_smells.py <plugin php files>` → `clean`.
- [ ] PHPCS with the WordPress-Extra ruleset — clean.
- [ ] `make skills-check-versions` — WordPress/PHP pins current.
