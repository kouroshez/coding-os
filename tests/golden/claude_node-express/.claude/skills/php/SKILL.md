---
name: php
tier: stack
domain: [backend]
description: Write modern, secure PHP 8.x — typed properties, enums, readonly, match, constructor promotion, PSR standards, Composer — and avoid the legacy footguns (SQL injection, XSS, unsafe deserialization, eval). Use when writing or reviewing PHP, modernizing a legacy codebase, setting up Composer/autoloading, hardening request handling, or escaping output. Targets PHP 8.3+ and PSR-12. Triggers — "PHP", "Composer", "Laravel", "WordPress plugin", "$_POST", "PDO", "this PHP is insecure", any `*.php`. Pairs with sql-authoring (parameterized queries), security-web (OWASP), wordpress (the CMS layer), api-design (the contract).
globs: ""
paths: []
last_reviewed: "2026-06-04"
versions_ref: versions.json
---

# Modern PHP

PHP earned its insecure reputation from a decade of `mysql_query("...$_GET...")`. Modern PHP (8.3+) is a typed, fast, well-tooled language — the craft is using its type system and PDO, and never trusting `$_GET`/`$_POST`/`$_REQUEST` near a query, a shell, or output.

> Scan PHP for the classic dangerous patterns:
> `python3 scripts/scan_php_smells.py src/**/*.php`

## Use the 8.x type system

```php
// Wrong — untyped, mutable, verbose, no guarantees
class Money {
  public $amount;
  public $currency;
  function __construct($amount, $currency) { $this->amount = $amount; $this->currency = $currency; }
}

// Correct — typed, readonly, promoted constructor params, enum
enum Currency: string { case USD = 'USD'; case EUR = 'EUR'; }

final class Money {
  public function __construct(
    public readonly int $amount,            // promoted + readonly = immutable
    public readonly Currency $currency,
  ) {}
}
```

`declare(strict_types=1);` at the top of every file makes type declarations
enforced, not coerced. Use `readonly` for value objects, `enum` for fixed sets,
`match` (exhaustive, strict `===`) over `switch`, and union/nullable types. Detail
→ [references/modern-php.md](references/modern-php.md).

## Never build SQL from request data

```php
// Wrong — SQL injection, the canonical PHP breach
$id = $_GET['id'];
$db->query("SELECT * FROM users WHERE id = $id");

// Correct — PDO prepared statement; the value never touches the SQL text
$stmt = $pdo->prepare('SELECT * FROM users WHERE id = ?');
$stmt->execute([$_GET['id']]);
```

Use PDO with prepared statements (or an ORM) for **every** query. The legacy
`mysql_*` functions are removed; `mysqli` without bound params is the same hole.
Query craft (parameterization, joins, plans) is owned by
[sql-authoring](../sql-authoring/SKILL.md).

## Escape on output, validate on input

```php
// Wrong — reflected XSS
echo "<p>Hello {$_GET['name']}</p>";

// Correct — escape for the output context
echo '<p>Hello ' . htmlspecialchars($_GET['name'], ENT_QUOTES, 'UTF-8') . '</p>';
```

Validate + sanitize input at the boundary (`filter_input`, a validation library);
escape at output for the **context** (`htmlspecialchars` for HTML, `json_encode`
for JS, parameterized for SQL). Never `echo` raw request data. Server-side
hardening is owned by [security-web](../security-web/SKILL.md).

## Composer + autoloading + tooling

```json
{ "require": { "php": ">=8.3" },
  "autoload": { "psr-4": { "App\\": "src/" } } }
```

PSR-4 autoloading via Composer (`composer dump-autoload`), never manual
`require` chains. Run the toolchain: **PHPStan**/**Psalm** (static analysis at max
level), **PHP-CS-Fixer** (PSR-12 formatting), **PHPUnit** (tests),
**Rector** (automated upgrades). A modern PHP project is statically analyzed —
treat PHPStan level 9 as the target.

## The dangerous-function shortlist (never on user data)

| Function | Risk | Instead |
|---|---|---|
| `eval()` | arbitrary code execution | redesign — almost never needed |
| `extract($_POST)` | variable injection | read keys explicitly |
| `system/exec/shell_exec/passthru` w/ input | command injection | `escapeshellarg`, or avoid the shell |
| `unserialize()` on request data | object-injection RCE | `json_decode` |
| `include`/`require` with a request path | local/remote file inclusion | an allow-list |
| `md5`/`sha1` for passwords | trivially cracked | `password_hash()` (bcrypt/argon2) |

## Anti-patterns (reject on sight)

- Request data concatenated into a query / shell / `include` path.
- `mysql_*` or unbound `mysqli` — use PDO prepared statements.
- `echo`ing raw `$_GET`/`$_POST` without context escaping.
- `==` where `===` is meant (loose comparison: `"0e1" == "0e2"` is true).
- `eval` / `extract($_...)` / `unserialize($_...)` on user data.
- No `declare(strict_types=1)` → types silently coerce.
- `md5`/`sha1` for passwords → `password_hash`.

## See also

- [references/modern-php.md](references/modern-php.md) — 8.x features, PSR, Composer, the toolchain.
- [references/security.md](references/security.md) — injection, XSS, deserialization, sessions, the dangerous functions.
- [assets/php-checklist.md](assets/php-checklist.md) — the review gate.
- [sql-authoring](../sql-authoring/SKILL.md) · [security-web](../security-web/SKILL.md) · [wordpress](../wordpress/SKILL.md).
