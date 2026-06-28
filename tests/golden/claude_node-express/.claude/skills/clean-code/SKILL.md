---
name: clean-code
tier: quality
domain: [universal]
description: Universal coding principles applied on every code change — fail-closed error handling, self-documenting code, edge-case awareness, and test coverage for error paths. Stack-agnostic; covers Python, TypeScript/JavaScript, Go, and any other language. Triggers on every commit that touches code files.
globs: "**/*.{py,ts,tsx,js,jsx,go,rs,java,kt,swift,rb}"
context: fork
last_reviewed: "2026-05-13"
allowed-tools:
  - Read
  - Grep
  - Glob
---

This skill enforces universal coding principles on every code change. It is stack-agnostic — same rules hold for Python backends, TypeScript frontends, Go services, and any other language the project uses. Stack-specific layering (Django ORM, FastAPI dependencies, Fiber middleware, React hooks) lives in the matching stack skill that depends on this one.

> **Read the *why*, not just the diff.** Every rule below pairs the wrong shape (`BAD`) with the right one (`GOOD`) **and the reason the right one is right** — and the reason is the point. Internalize it and you apply the principle where no rule is written (the out-of-distribution case that no linter catches); copy the `GOOD` diff alone and you only pass the cases someone already enumerated. These tactics are the concrete expression of the project's [constitution](../../../../docs/governance/constitution.md) values — *smallest-correct-change*, *docs-are-the-contract*, *agent-agnostic* — which carry the WHY one level up. (This is the *Teaching Claude Why* finding applied to ourselves: a principle understood generalizes; a demonstration copied does not.)

> **Strategic parent:** This skill enforces the *tactical* shape of code (naming, structure, error paths). The *strategic* anti-overengineering rule — reuse first, no speculation, diff-minimal, rule-of-three abstraction — lives in [src/core/rules/anti-overengineering.md](../../rules/anti-overengineering.md) and applies to every artifact (docs, hooks, skills, templates, tests, CLI), not just code. Read it before introducing a new abstraction.

## Pre-Code Checklist

Before writing any code, verify you have read the relevant context:

- [ ] Read the engineering doc for the surface being changed (each stack ships its own under `docs/engineering/<stack>-rules.md`, `docs/engineering/frontend-rendering-rules.md`, or the meta-repo's `docs/architecture/meta-project.md`).
- [ ] If touching error handling or API responses: read [api-contract-discipline.md](../../rules/api-contract-discipline.md) and the project's error-envelope doc (`docs/engineering/mcp-error-envelope.md` for `cos_*` MCP tools, `docs/api-contracts/error-format.md` for HTTP services).
- [ ] If touching auth, payments, or file uploads: read `docs/playbooks/security-review.md`.
- [ ] Search the repo for existing patterns before introducing new ones — see the [search](../search/SKILL.md) skill for the grounded-count workflow.
- [ ] Before adding code to a service subtree in a polyglot project, confirm placement against the `docs/engineering/project-anatomy.md` SSOT: same-language reuse lives in `src/shared/<lang>/`, cross-language types in `src/shared/contracts/` — see §7.

## 1. Error Handling: Fail-Closed Default

Every error handling decision defaults to **reject / deny / fail**. Never silently swallow errors.

### Principles

- If verification cannot complete: **reject** (not log-and-allow)
- If permission check fails: **deny access**
- If payment state is unclear: **do not fulfill**
- If external service is down: **fail the request** (not return stale/default data)

### Python — Correct

```python
# GOOD: fail-closed — unknown state rejects
def verify_purchase(user_id: str, product_id: str) -> Purchase:
    try:
        purchase = PurchaseService.get_verified(user_id, product_id)
    except PurchaseNotFoundError:
        raise PermissionDeniedError("Purchase not found")
    except VerificationError:
        logger.error("Purchase verification failed", extra={"user_id": user_id})
        raise ServiceUnavailableError("Unable to verify purchase")

    if purchase.status != PurchaseStatus.COMPLETED:
        raise PermissionDeniedError("Purchase not completed")

    return purchase
```

### Python — Wrong

```python
# BAD: fail-open — unknown state allows access
def verify_purchase(user_id, product_id):
    try:
        purchase = Purchase.objects.get(user_id=user_id, product_id=product_id)
        return purchase
    except Exception:
        # "Just log it" — user gets access anyway
        logger.warning("Could not verify purchase")
        return None  # caller treats None as "skip check"
```

### TypeScript — Correct

```typescript
// GOOD: fail-closed — catch re-throws, never swallows
async function fetchUserProfile(userId: string): Promise<UserProfile> {
  const response = await api.get(`/users/${userId}`);

  if (!response.ok) {
    throw new ApiError("Failed to fetch user profile", response.status);
  }

  return response.data;
}
```

### TypeScript — Wrong

```typescript
// BAD: fail-open — returns fallback on error, caller never knows
async function fetchUserProfile(userId: string) {
  try {
    const response = await api.get(`/users/${userId}`);
    return response.data;
  } catch {
    return { name: "Unknown", email: "" }; // silent fallback
  }
}
```

### Pattern Summary

| Situation | Correct (fail-closed) | Wrong (fail-open) |
|---|---|---|
| Unhandled exception | Re-raise or wrap in typed error | `except Exception: pass` |
| Permission check fails | Return 403 | Log and continue |
| Payment state unknown | Halt fulfillment | Fulfill and reconcile later |
| External service timeout | Return 503 | Return cached/default data |

## 1b. No PII in Logger Calls

Never pass PII (email, full name, IP address, phone) to any `logger.*` call. Use the user's UUID instead. If you need to log an email for debugging, use a masked form (`j***@example.com`). PII-exclusion + secret-redaction discipline is owned by the [security-web](../security-web/SKILL.md) and [observability](../observability/SKILL.md) skills (both co-ship).

```python
# GOOD
logger.error("Payment failed", extra={"user_id": user.id})

# BAD — leaks email
logger.error("Payment failed for %s", user.email)
```

## 1c. Never Manually Build Error Envelopes

Never construct error response dicts by hand (e.g., `return Response({"error_code": ...})`). Raise a typed exception and let the custom exception handler produce the envelope. See `docs/api-contracts/error-format.md`.

```python
# GOOD
raise ProductNotFoundError()

# BAD — bypasses exception handler, duplicates envelope logic
return Response({"error_code": "NOT_FOUND", "message": "Product not found"}, status=404)
```

## 2. No Internal Details in Responses

Never expose implementation details to API consumers.

### Forbidden in API responses

- `str(exc)` from any exception — may contain SQL, paths, or internal state
- Database column names, table names, or query fragments
- Stack traces or file paths
- Internal service names or infrastructure details

### Correct Pattern

```python
# GOOD: generic message to client, details in logs
except IntegrityError as exc:
    logger.error("Duplicate entry on user creation", extra={
        "email_hash": hash_email(data["email"]),
        "error": str(exc),
    })
    raise ConflictError("An account with this email already exists")
```

```typescript
// GOOD: generic error to UI, details in server logs
export async function createUser(data: UserInput) {
  const res = await api.post("/users/", data);

  if (res.status === 409) {
    throw new UserFacingError("An account with this email already exists");
  }

  if (!res.ok) {
    throw new UserFacingError("Something went wrong. Please try again.");
  }

  return res.data;
}
```

### Wrong Pattern

```python
# BAD: leaks DB details
except IntegrityError as exc:
    return Response(
        {"error": str(exc)},  # "duplicate key violates unique constraint users_email_key"
        status=409,
    )
```

## 3. Typed Exceptions

Use domain-specific exception classes. Never raise bare `ValueError` or `Exception`.

### Backend Convention (Python)

Each bounded context defines exceptions in its own `exceptions.py` module — for Django apps that's `apps/<domain>/exceptions.py`, for FastAPI services that's `domain/<name>/exceptions.py`, for the coding-os meta-repo that's `src/core/<subsystem>/exceptions.py`. The shape is the same regardless of framework:

```python
# domain-local exceptions.py
from core.exceptions import AppError  # project's base AppError lives in a single shared module

class ProductNotFoundError(AppError):
    status_code = 404
    default_detail = "Product not found"

class ProductUnavailableError(AppError):
    status_code = 410
    default_detail = "Product is no longer available"
```

### Frontend Convention

Typed errors live in the relevant module or a shared errors file:

```typescript
// lib/errors.ts
export class ApiError extends Error {
  constructor(
    message: string,
    public statusCode: number,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export class UserFacingError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "UserFacingError";
  }
}
```

## 4. Self-Documenting Code

### Naming

Code reads like prose. Names reveal intent without needing comments.

```python
# GOOD
def calculate_discounted_price(base_price: Decimal, discount_pct: Decimal) -> Decimal:
    return base_price * (1 - discount_pct / 100)

# BAD
def calc(p, d):
    return p * (1 - d / 100)
```

```typescript
// GOOD
const isEligibleForRefund = order.status === "delivered" && daysSincePurchase <= 30;

// BAD
const flag = order.s === "d" && diff <= 30;
```

### No Abbreviations / No Cryptic Shortenings

Names spell the concept. Readers should not have to expand acronyms in their head or open another file to learn what `usr`, `prd`, or `mgr` means.

**Rule:** **do not abbreviate.** A name is a contract with every future reader. Keystrokes saved at write-time cost cognitive load on every read.

**Forbidden** (typical examples — extend the spirit):

- `usr` → `user` · `prd` → `product` · `ord` → `order` · `qty` → `quantity` · `amt` → `amount` · `desc` → `description` · `cfg` → `config` · `cnt` → `count` · `idx` → `index` · `len` → `length` · `tmp` → `temporary` (or rename to its actual role) · `val` → `value` · `mgr` → `manager` · `auth` *only* when not paired with `service/token/header` · `resp` → `response` · `req` → `request` · `prev` → `previous` · `curr` → `current` · `arr` → `array` (use the plural noun instead — `items`, `users`).
- Single-letter names outside a tight numeric loop: `let a = ...`, `const x = ...`, `function f(g)`.
- Hungarian-style prefixes: `strName`, `iCount`, `bIsActive`.
- Drop vowels to save chars: `usrCnt`, `prdLst`, `crtdAt`.

**Allowed abbreviations** — well-known initialisms whose expanded form is rarely written even in prose:

| OK | Why |
|---|---|
| `id`, `url`, `uri`, `uuid` | universal protocol/data identifiers |
| `http`, `https`, `tcp`, `udp`, `ip`, `dns`, `tls`, `ssl` | network primitives |
| `api`, `cli`, `gui`, `ui`, `db`, `os`, `io` | system-level surfaces |
| `json`, `yaml`, `csv`, `xml`, `pdf`, `png`, `jpg` | formats |
| `i`, `j`, `k` | numeric loop indices *only* inside a tight `for` body where the role is obvious from context |
| `min`, `max`, `avg`, `sum`, `cnt` *only when paired in math context* | reserved by language stdlibs |
| `id_` / `type_` / `from_` | trailing underscore to dodge Python builtins (preferred over abbreviation) |

When in doubt: write the full word. A name is read 100× for every time it is written.

```python
# GOOD
def find_active_users_by_country(country_code: str) -> list[User]:
    return [user for user in fetch_users() if user.country == country_code and user.is_active]

# BAD — abbreviations leak guesswork into every reader's head
def find_act_usr_by_ctry(c):
    return [u for u in fetch_usrs() if u.ctry == c and u.act]
```

```typescript
// GOOD
const remainingDownloadAttempts = MAX_DOWNLOAD_ATTEMPTS - completedAttempts;

// BAD
const remDlAtt = MAX_DL_ATT - cDlAtt;
```

Exception: when an abbreviation is **part of a domain term** that the team uses verbatim in spec, ticket, or business conversation (e.g. `kyc`, `aml`, `mrr`, `arr`, `roi`, `gdpr`), keep the abbreviation — fighting the domain language costs more than it saves. Document the term once in `docs/engineering/glossary.md` and move on.

### No Magic Numbers / Strings

Any literal that carries business meaning gets a name. `0.05`, `3600`, `1024`, `"prd"`, `"USD"`, `200` (HTTP status), `30` (days), `60_000` (ms timeout) — none of these are obvious to the next reader. The cost is one line; the savings compound across every PR review.

Allowed inline literals (the floor):

- `0`, `1`, `-1`, `2` when used in their natural role (off-by-one, empty check, halving).
- `""`, `[]`, `{}`, `None` / `null` / `undefined` — empty sentinels.
- The string itself in a one-off test assertion (`assert result == "hello"`).
- Math identities: `100` in a percent conversion right next to `discount_pct`.

Everything else: extract.

```python
# GOOD — intent is at the constant, not buried in the expression
MAX_REFUND_WINDOW_DAYS = 30
SESSION_TIMEOUT_SECONDS = 60 * 60        # 1 hour
DEFAULT_PAGE_SIZE = 50

def is_refund_eligible(order: Order) -> bool:
    return order.status == OrderStatus.DELIVERED and order.age_in_days <= MAX_REFUND_WINDOW_DAYS

# BAD — every literal is a "why this number?" land mine
def is_refund_eligible(order):
    return order.status == "delivered" and order.age_in_days <= 30
```

```typescript
// GOOD — units encoded in the name
const RATE_LIMIT_WINDOW_MS = 60_000;
const MAX_RETRIES = 3;
const ALLOWED_FILE_TYPES = new Set(["image/png", "image/jpeg", "image/webp"]);

// BAD — units invisible; status enum reinvented inline
if (Date.now() - lastTry < 60_000 && retryCount < 3) { ... }
if (mime === "image/png" || mime === "image/jpeg") { ... }
```

Co-locate constants:

- File-local constants (no other consumer): top of the file in `SCREAMING_SNAKE_CASE` (Python / Go) or `UPPER_SNAKE` (TS) before the first function.
- Cross-module constants: a single `constants.py` / `constants.ts` in the bounded context — never a global `magic.py` shared by 20 modules.
- Don't promote a 1-off literal to a constant just to follow the rule; if it appears once *and* the meaning is obvious from the surrounding name (`if items.count() == 1: ...`), leave it.

Status codes, MIME types, and protocol verbs belong in an enum or the language's stdlib:

```python
from http import HTTPStatus

return Response(status=HTTPStatus.UNPROCESSABLE_ENTITY)   # not 422
```

### Boolean Parameters: Named Arguments or Enums

A bare boolean at a call site reads as `???`. `transfer_funds(account, 1000, true, false, true)` forces the reader to open the function to learn what each flag means. Forbid positional booleans on public-ish APIs.

**Rule:** if a function takes more than one boolean, **or** even one boolean whose meaning isn't obvious from the function name, switch to one of:

1. **Keyword-only arguments** with descriptive names.
2. **A typed enum** when the flag actually represents a mode with >2 states (`Sync`, `Async`, `DryRun`) — or even just two — so future modes don't require breaking changes.
3. **Two separate functions** when the flag flips the algorithm rather than tweaks a parameter (`copy_file` vs `move_file`).

```python
# GOOD — every flag named at the call site
result = transfer_funds(
    source=account_a,
    destination=account_b,
    amount_cents=100_00,
    *,
    is_internal=True,
    bypass_kyc=False,
)

# Better — modes that may grow get an enum
class TransferMode(Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"
    SANDBOX = "sandbox"

transfer_funds(source=a, destination=b, amount_cents=100_00, mode=TransferMode.INTERNAL)

# BAD — call site reads as line noise
transfer_funds(a, b, 100_00, True, False, True)
```

```typescript
// GOOD
sendNotification({
  user,
  message: "Welcome",
  channel: "email",
  highPriority: false,
  includeMarketingFooter: false,
});

// BAD
sendNotification(user, "Welcome", "email", false, false);
```

Python: enforce keyword-only via `*` in the signature for any flag-like param. TypeScript: take an options object instead of trailing positional booleans. Go: use option-struct pattern (`TransferOptions{Internal: true}`) rather than positional bools.

### Nesting Depth ≤ 2 (Guard-Clause First)

Deeply nested code (`if { if { for { if { ... } } } }`) hides the happy path. Cap nesting at 2 levels inside any function. When you reach 3, refactor — guard-clause the precondition, extract the inner block to a named helper, or return early.

```python
# GOOD — guards out, happy path flat
def process_refund(order_id: str, agent_id: str) -> RefundResult:
    order = get_order_or_raise(order_id)

    if not order.is_refundable:
        raise RefundError("Order is not refundable")

    if not has_permission(agent_id, "refund.execute"):
        raise PermissionDeniedError("Agent cannot execute refunds")

    refund = create_refund(order)
    notify_customer(refund)
    return refund

# BAD — happy path is buried 4 levels deep
def process_refund(order_id, agent_id):
    order = get_order(order_id)
    if order is not None:
        if order.is_refundable:
            if has_permission(agent_id, "refund.execute"):
                refund = create_refund(order)
                if refund:
                    notify_customer(refund)
                    return refund
                else:
                    raise RefundError("Failed to create refund")
            else:
                raise PermissionDeniedError("Agent cannot execute refunds")
        else:
            raise RefundError("Order is not refundable")
    else:
        raise OrderNotFoundError(order_id)
```

The first form is read top-to-bottom in order of decisions. The second form requires the reader to track 4 simultaneous open branches.

When the cap is unavoidable (state machines, parser tables, decision trees built from data), extract that block to a private helper and document the table in a comment — keep the surrounding function flat.

### Comments: Why, Not What

```python
# GOOD: explains business rule
# Stripe requires idempotency keys for all payment creation requests
# to prevent duplicate charges during network retries.
idempotency_key = f"order-{order.id}-{attempt}"

# BAD: restates the code
# Set the idempotency key to order id and attempt
idempotency_key = f"order-{order.id}-{attempt}"
```

### Match the Target Density, Not the Neighbor

The agent runtime tells you to *match the surrounding code's comment density*.
That is a trap when the surrounding code is comment-heavy legacy — matching it
multiplies the noise. Match the density THIS section targets (near-zero,
WHY-only), not the neighbor's. A dense file is tech-debt to thin when you touch
it, never the pattern to extend.

### No Provenance in Comments

A comment explains *why the code is the way it is* in timeless terms. It MUST
NOT record *who/what introduced the change* — no task IDs, no phase/plan
labels, no gate or work-item codes. Version control (`git blame` / `git log`)
already records provenance with perfect fidelity; duplicating it in a comment
just rots — the number is meaningless to the next reader and stale the moment
the work moves on.

```python
# GOOD: timeless reason
# Panel-scoped so two concurrent sessions never overwrite each other's marker.
marker = panel_dir / ".active"

# BAD: provenance noise — strip the TASK-/Phase/gate ref, keep the reason
# TASK-035: panel-scoped so two concurrent sessions never overwrite ...
# Panel-scoped since TASK-035 (Phase G) — ... (E1) closure check
```

Forbidden in any comment: `TASK-123`, `(TASK-123)`, `since/per/as-of TASK-123`,
`Phase 2` / `Phase G` / `(Cortex Phase 2)`, plan-step prefixes like `P5:`, and
gate/work-item codes like `(G9)` / `(E1)` / `(B4)`. If the *reason* is worth a
comment, write the reason; drop the ID. (Domain identifiers that name the thing
the code operates on — e.g. a formula id in `hex(F1)` — are not provenance and
stay.)

### Don't Commit TODOs — File a Task

The project has a task board; use it. A `TODO`/`FIXME` in committed code is
untracked work that rots in place, and a `TODO: TASK-042` is the provenance
anti-pattern above. Prefer `cos task-create` over a code marker. If a marker is
unavoidable mid-development, remove it before you commit — it should never reach
`main`.

```python
# BAD — both forms reach main and rot
# TODO: TASK-042 — add rate limiting
# TODO: add rate limiting later
# FIXME: hack
```

### Function Design

- **Single responsibility** — one function does one thing
- **~20 lines max** — if longer, extract a helper
- **3-4 parameters max** — use a config/options object beyond that
- **Guard clauses first** — handle invalid state at the top, keep the happy path unindented

```python
# GOOD: guard clauses, single responsibility, clear flow
def process_download(user: User, product_id: str) -> DownloadUrl:
    if not user.is_verified:
        raise PermissionDeniedError("Email verification required")

    product = get_product_or_raise(product_id)

    if not product.is_downloadable:
        raise ProductUnavailableError("Product has no downloadable files")

    purchase = get_verified_purchase_or_raise(user.id, product.id)

    return generate_signed_download_url(purchase)
```

## 5. Edge Case Awareness

Before writing any function, ask:

| Question | Example |
|---|---|
| What if the input is `None`/`undefined`? | User passes no product ID |
| What if the input is empty? | Empty string, empty list, `{}` |
| What if the input is at a boundary? | Price of 0, quantity of max int |
| What if the external service is down? | Stripe timeout, S3 unreachable |
| What if there is concurrent access? | Two users buy the last item simultaneously |
| What if the data is stale? | Cached price after a price change |

Address these explicitly — with guard clauses, validation, or documented assumptions.

```python
# GOOD: explicit None/empty handling
def get_product_display_name(product: Product | None) -> str:
    if product is None:
        raise ProductNotFoundError("Product reference is missing")

    if not product.name or not product.name.strip():
        logger.warning("Product has empty name", extra={"product_id": product.id})
        return f"Product #{product.id}"

    return product.name.strip()
```

## 6. Test Error Paths

### Rules

- Every `try/except` block needs a test that triggers the `except` branch
- Every validation rule needs a test with invalid input
- Never write `test_does_not_crash` — assert the correct behavior
- Test the error type, message, and status code

### Python Test Example

```python
class TestVerifyPurchase:
    def test_returns_purchase_when_verified(self, verified_purchase):
        result = verify_purchase(verified_purchase.user_id, verified_purchase.product_id)
        assert result.id == verified_purchase.id
        assert result.status == PurchaseStatus.COMPLETED

    def test_raises_permission_denied_when_not_found(self):
        with pytest.raises(PermissionDeniedError, match="Purchase not found"):
            verify_purchase("nonexistent-user", "nonexistent-product")

    def test_raises_service_unavailable_on_verification_failure(self, mocker):
        mocker.patch(
            "apps.purchases.services.PurchaseService.get_verified",
            side_effect=VerificationError("upstream timeout"),
        )
        with pytest.raises(ServiceUnavailableError, match="Unable to verify"):
            verify_purchase("user-1", "product-1")
```

### TypeScript Test Example

```typescript
describe("fetchUserProfile", () => {
  it("returns profile data on success", async () => {
    mockApi.get.mockResolvedValue({ ok: true, data: mockProfile });

    const result = await fetchUserProfile("user-1");

    expect(result).toEqual(mockProfile);
  });

  it("throws ApiError on non-OK response", async () => {
    mockApi.get.mockResolvedValue({ ok: false, status: 404 });

    await expect(fetchUserProfile("user-1")).rejects.toThrow(ApiError);
    await expect(fetchUserProfile("user-1")).rejects.toMatchObject({
      statusCode: 404,
    });
  });
});
```

## 7. Cross-Service Code Placement — Reuse First

In a polyglot project, *where* code lives is a correctness concern, not just tidiness. The top-level anatomy (SSOT: `docs/engineering/project-anatomy.md`) gives every subtree exactly one owner and one shared layer:

- **Same-language reuse → `src/shared/<lang>/`.** When a second service in the same language needs a helper, type, or client that already exists in one service, promote it to `src/shared/<lang>/` (`go/`, `ts/`, `py/`) instead of copy-pasting. The trigger is the rule-of-three from [anti-overengineering.md](../../rules/anti-overengineering.md) — a real second consumer, not an anticipated one.
- **Cross-language contracts → `src/shared/contracts/` only.** Two services in *different* languages never import each other's code. They share a request or event shape by generating from a versioned artifact in `src/shared/contracts/` (OpenAPI, protobuf, json-schema) — the single cross-language boundary. A Go service and a Python service agree on a payload through the same contract, never by reaching across subtrees.
- **One owner per subtree.** A stack writes only inside its declared `structure.root`; `enforce-scaffold-boundary.sh` blocks a write that crosses into a sibling service. If you feel the urge to edit another service's tree, the code you want belongs in `src/shared/`.

Promotion is reuse-first, not speculation — move code to `src/shared/<lang>/` when the second consumer actually appears. The reuse-first nudge surfaces the suggestion when it detects a symbol duplicated across services; it is advice, never a block.

## Post-Code Checklist

After writing code, verify all eight points before committing:

- [ ] **Fail-closed:** Every error path rejects/denies/fails — no silent swallowing
- [ ] **No leaks:** No `str(exc)`, DB names, or stack traces in API responses
- [ ] **Typed errors:** All raised exceptions use domain-specific classes
- [ ] **Self-documenting:** Names reveal intent; comments explain why, not what; no task/phase/gate provenance in comments — see §4 "No Provenance in Comments"
- [ ] **No abbreviations:** No `usr`/`prd`/`qty`/cryptic shortenings; only the allow-list (`id`, `url`, `http`, loop `i`/`j`) and team-domain terms — see §4 "No Abbreviations"
- [ ] **No magic numbers/strings:** Every business-meaning literal extracted to a named constant or enum — see §4 "No Magic Numbers / Strings"
- [ ] **No bare booleans at call sites:** Keyword-only args, enums, or split functions — never positional `foo(true, false)` — see §4 "Boolean Parameters"
- [ ] **Nesting depth ≤ 2:** Guard-clause out preconditions; extract the inner block when a third level appears — see §4 "Nesting Depth"
- [ ] **No TODOs in committed code:** No `TODO`/`FIXME` and no task/phase/gate IDs in comments — file a task instead — see §4 "Don't Commit TODOs"
- [ ] **Function hygiene:** Functions are ~20 lines, 3-4 params, guard clauses first
- [ ] **Edge cases:** None, empty, boundary, service-down, and concurrency considered
- [ ] **Error path tests:** Every except/catch branch has a corresponding test case
- [ ] **Cross-service placement:** Code reused by a second service is promoted to `src/shared/<lang>/`; cross-language types flow through `src/shared/contracts/` only — see §7 "Cross-Service Code Placement"
