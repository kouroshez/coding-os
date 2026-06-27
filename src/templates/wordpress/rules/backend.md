---
globs: ["src/backend/**/*.php"]
alwaysApply: false
---

# WordPress Backend Rules (auto-loaded on src/backend/**/*.php)

When editing any PHP file under `src/backend/` in a WordPress project, follow these standards:

- **Theme vs plugin** — behavior and data live in the plugin; the theme is presentation only. Business logic in a theme is a review finding.
- **Sanitize on input, escape on output** — always, at every boundary. A raw `$_POST`/`$_GET` value never reaches the DB or the page unescaped.
- **Nonce + capability** — every state change verifies a nonce and a `current_user_can()` capability; no privileged action trusts the request alone.
- **Prepared queries** — `$wpdb->prepare()` for every query with input; never interpolate a variable into SQL.
- **No direct file access** — guard every PHP file with `if (!defined('ABSPATH')) exit;`.
- **Namespaced hooks/options** — prefix hooks, options, and globals with the project slug so two plugins never collide.

Canonical policy: `docs/engineering/wordpress-rules.md`
Playbook: `docs/playbooks/wordpress-service.md`
Primary skill: `wordpress`
