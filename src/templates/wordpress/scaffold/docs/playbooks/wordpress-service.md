<!-- domain:BACKEND | layer:playbook | ssot:true | updated:{{DATE}} -->
# WordPress Playbook

Purpose: The end-to-end recipe for adding or changing WordPress behavior in {{PROJECT_NAME}}.
Read when: Any task that adds a hook, shortcode, REST route, template, or custom table.
Skip when: Pure infra/devops work — see the deployment docs.
Read next: [WordPress Engineering Rules](../engineering/wordpress-rules.md), [Error Format](../api-contracts/error-format.md)

> Nav: [Master Index](../00-index.md)

## Add behavior (the only sanctioned path)

1. **Decide theme vs plugin** — presentation → theme; behavior/data → plugin
   (portable, survives a theme swap).
2. **Hook in** — `add_action`/`add_filter` with a named callback; never inline
   anonymous logic you cannot test.
3. **Sanitize on input** — `sanitize_text_field`, `absint`, etc. on every
   request value before use.
4. **Verify intent** — nonce-check (`wp_verify_nonce`) every state change and
   capability-check (`current_user_can`) every privileged action.
5. **Escape on output** — `esc_html`, `esc_attr`, `esc_url` at every echo.
6. **Data** — `$wpdb->prepare()` for every query; never interpolate input.
7. **Verify** — `cd src/backend && composer lint`.

## Anti-patterns

- Business logic in the theme — it dies on a theme swap; put it in the plugin.
- Unsanitized `$_GET`/`$_POST` reaching a query — SQL injection.
- A state-changing endpoint without a nonce + capability check — CSRF / privilege escalation.
