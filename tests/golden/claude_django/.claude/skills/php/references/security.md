<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# PHP Security — Injection, XSS, Deserialization, Sessions

> P: The PHP-specific exploit classes and the exact defensive idiom for each.
> R: Handling any request data, output, file path, or session in PHP.
> S: General server-side OWASP — that's [security-web](../../security-web/SKILL.md) (SSOT).
> N: [SKILL.md](../SKILL.md), [modern-php.md](modern-php.md)

> Nav: [Skill](../SKILL.md)

The OWASP rules are owned by [security-web](../../security-web/SKILL.md); this is
the PHP-syntax application of them.

## SQL injection → PDO prepared statements

```php
$stmt = $pdo->prepare('SELECT * FROM users WHERE email = :email');
$stmt->execute(['email' => $email]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);
```

Set `PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION` and
`PDO::ATTR_EMULATE_PREPARES => false` so prepares are real (server-side), not
string-built emulations.

## XSS → escape for the output context

| Context | Escape |
|---|---|
| HTML body | `htmlspecialchars($s, ENT_QUOTES, 'UTF-8')` |
| HTML attribute | `htmlspecialchars` (with quotes) |
| JavaScript | `json_encode($s, JSON_HEX_TAG \| JSON_HEX_AMP)` |
| URL | `rawurlencode($s)` |

A template engine (Twig, Blade) auto-escapes by default — prefer it to manual
`echo`. Set a strict `Content-Security-Policy` header as defense-in-depth.

## Command injection → avoid the shell, or escape

```php
// if you MUST shell out, escape each argument
$out = shell_exec('convert ' . escapeshellarg($input) . ' out.png');
```

Better: use a library/extension instead of shelling out. Never pass request data
to `system`/`exec`/`shell_exec`/`passthru`/`popen` unescaped.

## Object injection → never unserialize request data

`unserialize($_POST['x'])` lets an attacker instantiate arbitrary classes and
trigger magic methods (`__wakeup`, `__destruct`) → RCE. Use `json_decode` for
request data. If you must `unserialize`, pass `['allowed_classes' => false]`.

## File inclusion → allow-list paths

```php
// Wrong — ?page=../../etc/passwd
include $_GET['page'] . '.php';

// Correct — map to a fixed allow-list
$pages = ['home' => 'home.php', 'about' => 'about.php'];
include $pages[$_GET['page']] ?? '404.php';
```

## Passwords & sessions

- `password_hash($pw, PASSWORD_DEFAULT)` to store, `password_verify` to check —
  never `md5`/`sha1`. `password_needs_rehash` on login to upgrade the cost.
- Session cookies: `session.cookie_httponly=1`, `cookie_secure=1`,
  `cookie_samesite=Lax`; `session_regenerate_id(true)` on privilege change to
  stop fixation.
- CSRF: a per-session token in every state-changing form, verified server-side.
