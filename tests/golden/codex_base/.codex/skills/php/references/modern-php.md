<!-- domain:BACKEND | layer:reference | ssot:true | updated:2026-06-04 -->
# Modern PHP — 8.x Features, PSR, Tooling

> P: The PHP 8.x language features and toolchain that make PHP a typed, safe, maintainable language.
> R: Writing new PHP or modernizing legacy code.
> S: Security footguns — see [security.md](security.md).
> N: [SKILL.md](../SKILL.md), [php-checklist.md](../assets/php-checklist.md)

> Nav: [Skill](../SKILL.md)

## Always start strict

```php
<?php
declare(strict_types=1);   // first line of EVERY file — enforces types, no coercion
```

Without it, `function f(int $x)` happily accepts `"5"` (coerced). With it, that's
a `TypeError` — bugs surface at the boundary, not three layers deep.

## The features that change how you write

| Feature | Replaces | Example |
|---|---|---|
| constructor promotion | boilerplate assignments | `public function __construct(public readonly int $id) {}` |
| `readonly` | manual immutability | `public readonly string $name;` |
| `enum` | class constants / magic strings | `enum Status: string { case Active = 'active'; }` |
| `match` | `switch` (no fallthrough, strict `===`, returns) | `$x = match($s) { 'a' => 1, default => 0 };` |
| named args | positional-arg guessing | `new Money(amount: 100, currency: Currency::USD)` |
| nullsafe `?->` | nested null checks | `$user?->address?->city` |
| first-class callable | `Closure::fromCallable` | `$fn = strlen(...);` |
| union/intersection types | `mixed` | `function f(int\|string $x): User&Loggable` |

`match` is strict (`===`) and exhaustive (throws on no match) — prefer it to
`switch` for value mapping. Enums make illegal states unrepresentable, like a
discriminated union.

## Composer & autoloading

```json
{
  "require": { "php": ">=8.3" },
  "require-dev": { "phpstan/phpstan": "^2", "friendsofphp/php-cs-fixer": "^3" },
  "autoload": { "psr-4": { "App\\": "src/" } }
}
```

PSR-4 maps a namespace prefix to a directory; `composer dump-autoload -o`
generates an optimized classmap for production. Never hand-write `require`
chains. Commit `composer.lock`; CI runs `composer install` (lockfile-exact), not
`update`.

## The toolchain (a modern project runs all of these in CI)

| Tool | Job | Target |
|---|---|---|
| PHPStan / Psalm | static analysis | level 9 / errorLevel 1 |
| PHP-CS-Fixer | formatting | PSR-12 |
| PHPUnit / Pest | tests | the [testing-strategy](../../testing-strategy/SKILL.md) pyramid |
| Rector | automated refactors / version upgrades | run on upgrade |

PSR standards worth knowing: PSR-4 (autoloading), PSR-12 (style), PSR-7
(HTTP messages), PSR-15 (middleware), PSR-3 (logging). Frameworks (Laravel,
Symfony) build on these — learn the PSR, not just the framework helper.
