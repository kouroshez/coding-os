<!-- domain:BACKEND | layer:asset | ssot:false | updated:2026-06-04 -->
# PHP Review Checklist

Run before merging PHP.

## Language
- [ ] `declare(strict_types=1);` at the top of every file.
- [ ] Types on every parameter, property, and return (no implicit `mixed`).
- [ ] `readonly` value objects, `enum` for fixed sets, `match` over `switch`.
- [ ] `===` not `==` (no loose comparison surprises).

## Security
- [ ] Every query is a PDO prepared statement (`ERRMODE_EXCEPTION`, `EMULATE_PREPARES=false`).
- [ ] Output escaped for its context (`htmlspecialchars`/`json_encode`) or via an auto-escaping template.
- [ ] No request data in `system/exec/include/require/unserialize/eval`.
- [ ] Passwords via `password_hash`/`password_verify` — never `md5`/`sha1`.
- [ ] Sessions: httponly + secure + samesite cookies; `session_regenerate_id` on privilege change.
- [ ] CSRF token on state-changing forms.
- [ ] `python3 scripts/scan_php_smells.py <files>` → `clean`.

## Tooling
- [ ] Composer PSR-4 autoload; `composer.lock` committed; CI uses `composer install`.
- [ ] PHPStan/Psalm at max level — clean.
- [ ] PHP-CS-Fixer (PSR-12) — formatted.
- [ ] PHPUnit/Pest tests for the change.
- [ ] `make skills-check-versions` — PHP version pin current.
