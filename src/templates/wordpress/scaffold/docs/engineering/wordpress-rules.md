<!-- domain:BACKEND | layer:rules | ssot:true | updated:{{DATE}} -->
# WordPress Engineering Rules

Purpose: Non-negotiable conventions for the {{PROJECT_NAME}} WordPress backend.
Read when: Editing anything under `src/backend/`.
Skip when: Frontend/mobile work.
Read next: [WordPress Playbook](../playbooks/wordpress-service.md)

> Nav: [Master Index](../00-index.md)

## Hard rules

1. **Theme vs plugin** — behavior and data live in the plugin; the theme is
   presentation only.
2. **Sanitize on input, escape on output** — always, at every boundary. A raw
   superglobal reaching a query or an echo is a build-blocking finding.
3. **Nonce + capability** — every state change verifies a nonce; every
   privileged action checks `current_user_can`.
4. **Prepared queries** — `$wpdb->prepare()` for every query with input; never
   string-interpolate.
5. **No direct file access** — guard PHP files with `if (!defined('ABSPATH')) exit;`.
6. **Namespaced hooks/options** — prefix everything with the project slug to
   avoid collisions with other plugins.

## Testing bar

REST routes ≥ happy + permission-denied path; security-sensitive callbacks
tested for nonce/capability rejection.
