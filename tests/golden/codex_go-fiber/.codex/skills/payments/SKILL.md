---
name: payments
description: Integrate payments and billing correctly — card charges, payment intents, webhooks, idempotent money movement, subscriptions/invoicing, refunds/chargebacks, multi-currency, and reconciliation against a ledger. Use when wiring Stripe/Adyen/Braintree/PayPal, handling a payment webhook, designing a subscription or usage-based billing model, making a charge safe to retry, preventing double-charges, or reconciling provider events against an internal money ledger. Boundary vs api-design and security-web — api-design owns the protocol-neutral HTTP contract shape (idempotency-key mechanics, RFC 9457 errors, pagination) and security-web owns generic OWASP server hardening (authn/z, injection, secrets); this skill owns the money-correctness domain on top of both — never trusting client-sent amounts, PCI scope minimization via tokenization, the webhook-as-source-of-truth state machine, and double-entry reconciliation. Defers durable ledger schema design to db-design.
tier: cross-cutting
domain: [backend, security]
last_reviewed: "2026-06-14"
---

# Payments & Billing — Moving Money Without Losing It

A practical guide to integrating a payment provider such that money is never double-charged, never silently lost, and always reconcilable. Stack-agnostic; recipes target Stripe as the reference provider, with Adyen / Braintree / PayPal noted where the model differs. The governing mindset: **a payment bug is a money bug, and money bugs are visible to finance, regulators, and angry customers.**

## When to Use This Skill

- Wiring a first charge / checkout — payment intents, hosted fields, confirmation flow.
- Handling a provider webhook (`payment_intent.succeeded`, `charge.refunded`, `invoice.paid`).
- Designing a subscription, metered/usage billing, free trial, proration, or dunning flow.
- Making money movement idempotent — a retried request must never charge twice.
- Issuing refunds, handling disputes/chargebacks, partial captures.
- Reconciling provider state against an internal ledger; closing the books.

Skip when: the work is a generic non-money API endpoint (api-design) or generic auth/injection hardening (security-web) with no money movement — those skills own that. This skill is specifically the financial-correctness layer.

## The Five Money-Correctness Invariants

These override convenience every time:

1. **Never trust a client-sent amount.** The price is computed server-side from the cart/plan, never read from the request body. A client that POSTs `{"amount": 1}` for a $1000 order must be charged $1000. This is the single most exploited payments bug.
2. **Every money mutation is idempotent.** A charge/capture/refund call carries an idempotency key derived from the business intent (e.g. `order_id`), so a network retry returns the *original* result instead of moving money again. (api-design owns the generic idempotency-key mechanics; this skill mandates it for money.)
3. **The provider webhook is the source of truth for state, not the API response.** The synchronous create-charge response can be lost (timeout) while the charge still succeeds. Treat the charge as `pending` until the webhook confirms; reconcile on the webhook.
4. **Money is integer minor units, never a float.** Store `amount_cents` (or the currency's minor unit) as an integer. `0.1 + 0.2 != 0.3` in floating point — that rounding error is a regulatory finding.
5. **Every movement is double-entry on an append-only ledger.** A charge debits one account and credits another; the ledger is immutable (corrections are reversing entries, never edits). This is what makes reconciliation and audit possible. (db-design owns the ledger *schema*; this skill owns the *discipline*.)

## PCI Scope — Stay Out of It by Design

Touching raw card numbers (PAN) drags the whole system into PCI-DSS scope (audits, controls, liability). Minimize scope to near-zero:

- **Tokenize at the edge.** The card number goes from the browser/app *directly* to the provider (Stripe Elements, hosted fields, client-side SDK) and comes back as a token. The server stores and uses the token, never the PAN.
- **Never log, store, or transit a raw card number, CVV, or full track data** — not in app logs, not in a debug dump, not "temporarily". CVV may never be stored at all, even encrypted.
- This makes the integration eligible for the lightest PCI self-assessment (SAQ A) instead of the heavyweight ones. Hosted fields are not just convenience; they are the compliance strategy.

## The Webhook State Machine

Charges, refunds, and subscription lifecycle events arrive asynchronously as webhooks. Handle them defensively:

- **Verify the signature** on every webhook before acting — an unsigned/forged webhook is an attacker telling the system a payment succeeded. Use the provider's signing secret; reject on mismatch.
- **Idempotent webhook handlers** — providers retry delivery and send duplicates. Dedup on the event id; processing the same `payment_intent.succeeded` twice must not fulfill the order twice.
- **Webhooks arrive out of order and can race the API response.** Design the handler to be order-independent: reconcile to the *current* provider state, do not assume `created` arrives before `succeeded`.
- **Acknowledge fast, work async.** Return 2xx immediately so the provider stops retrying; do slow fulfillment work off the webhook thread (a queue — see messaging-queues), itself idempotent.
- **A missed webhook must be recoverable.** Poll the provider / run a reconciliation job so a dropped webhook does not strand an order in `pending` forever.

## Subscriptions & Billing Models

- **Let the provider own recurring billing** (Stripe Billing / subscriptions) rather than reimplementing renewal cron, proration math, and dunning — that machinery is a multi-year tar pit.
- **Proration, trials, plan changes** have subtle edge cases (mid-cycle upgrade, downgrade credit, trial-to-paid). Use the provider's proration; verify with the provider's test clock, do not hand-roll the date math.
- **Dunning** (retrying failed recurring charges, grace periods, eventual cancellation) is a churn lever — configure the provider's smart retries; surface payment-failure state to the user before access is revoked.
- **Usage/metered billing**: aggregate usage idempotently (a usage event reported twice must not bill twice — same dedup discipline as everything else).

## Refunds, Disputes, Failures

- **Refunds are also idempotent money movement** — a retried refund must not refund twice. Refund through the provider against the original charge id; record a reversing ledger entry.
- **Chargebacks/disputes** are provider-initiated reversals with evidence deadlines. Capture the dispute webhook, freeze related fulfillment, and surface the deadline to ops — a missed deadline is an automatic loss.
- **Distinguish hard vs soft declines.** Soft decline (insufficient funds, temporary) → safe to retry with backoff. Hard decline (stolen card, do-not-honor) → do not retry; retrying a hard decline can trigger fraud flags.

## Anti-Patterns (reject in review, fix on sight)

- **Trusting a client-supplied price/amount** — server computes the amount, always.
- **No idempotency key on a charge/refund** — a retry double-charges a customer.
- **Treating the synchronous API response as final state** — the webhook is the source of truth.
- **Storing money as a float** — rounding errors become accounting discrepancies.
- **Logging or storing the raw PAN/CVV** — instant PCI scope blowup and breach liability.
- **Unverified webhook signatures** — an attacker can forge "payment succeeded".
- **Non-idempotent webhook handler** — duplicate delivery fulfills the order twice.
- **Editing ledger rows to "fix" a balance** — use reversing entries; the ledger is append-only.
- **Reimplementing subscription renewal/proration by hand** — use the provider's billing engine.
- **Retrying hard declines** — wastes attempts and trips fraud detection.

## Tools per surface (2026 defaults)

| Need | Default | Alternatives |
|---|---|---|
| Card payments + tokenization | Stripe (Elements / Payment Intents) | Adyen, Braintree |
| Subscriptions / invoicing | Stripe Billing | Chargebee, Recurly |
| PayPal / wallet rails | PayPal, Apple Pay / Google Pay via provider | — |
| Marketplace / split payments | Stripe Connect | Adyen for Platforms |
| Internal money ledger | double-entry table in Postgres (db-design) | Ledger DBs (TigerBeetle) |
| Webhook reliability | provider retries + reconciliation job | queue-backed async fulfillment |

## Pairs With

- **api-design** — owns the protocol-neutral idempotency-key mechanics and RFC 9457 error shape; this skill applies them to money and adds the never-trust-the-amount rule.
- **security-web** — owns generic OWASP hardening (authn/z, injection, secrets, webhook transport security); this skill adds PCI scope minimization and the payment-specific threat model on top.
- **db-design** — owns the durable double-entry ledger *schema*; this skill owns the append-only, reconcilable *discipline* that schema must support.
- **messaging-queues** — async, idempotent webhook fulfillment runs through a queue with at-least-once + dedup, exactly as money movement demands.
- **observability** — charge success rate, decline rate, webhook lag, and ledger-vs-provider drift are the billing golden signals; alert on reconciliation mismatch.

## See also

- Stripe docs — Payment Intents, idempotent requests, webhook signature verification, Billing.
- PCI-DSS v4.0 — SAQ A eligibility via tokenization / hosted fields.
- *Patterns of Enterprise Application Architecture* (Fowler) — Money type, double-entry accounting.
- Stripe engineering: "Designing robust and predictable APIs with idempotency."
