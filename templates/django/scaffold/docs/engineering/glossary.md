<!-- domain:ALL | layer:reference | ssot:true | updated:2026-03-13 -->
# Project Glossary

Purpose: Canonical project terminology — use when a term is ambiguous in context.
Read when: A term in architecture, playbooks, or PRD is unclear or ambiguous.
Skip when: Terminology is obvious from context.
Read next: The specific architecture domain or playbook clarifying the term.


> Purpose: Domain language dictionary. Use these terms consistently across all docs.
> Nav: [Docs Index](../00-index.md) | [Code Style](../../CodeStyle.md)

## Business Domain

- **Entitlement** → a user's right to download a purchased product. Created after successful payment. Stored in `downloads.Entitlement` model.
- **Fulfillment** → the process of creating Order, OrderItems, and Entitlements after payment succeeds. Triggered by webhook, executed in `OrderService.fulfill_order()`.
- **Guest checkout** → purchase without an account. Uses email for order association. Guest can later register and link orders via `AccountLinkingService`.
- **Price snapshot** → the `price_at_purchase` field on OrderItem. Preserves the price at time of purchase, independent of future price changes.
- **Digital product** → a downloadable file (template, design, script, tool). No physical shipping.

## Technical Domain

- **BaseModel** → abstract Django model providing `id` (UUID), `created_at`, `updated_at`. All models inherit from it.
- **Bounded context** → a DDD concept. Each Django app (`accounts`, `catalog`, `commerce`, etc.) is a bounded context with its own models and services.
- **PaymentPort** → abstract interface (`apps/payments/ports.py`) defining `create_payment_intent()`, `verify_webhook()`, `refund()`. Adapters implement it for each provider.
- **Service layer** → business logic lives in `apps/*/services/`, never in views or serializers. Services are the only place that orchestrates multi-model operations.
- **Selector (query layer)** → pattern for database queries. Complex queries go in `apps/*/selectors/`, not in views or services directly.

## Infrastructure

- **ISR (Incremental Static Regeneration)** → Next.js feature. Pages are statically generated and revalidated at intervals (30 min for blog, 30 min for products).
- **Celery task** → async background job. Used for: email sending, analytics events, file processing. Never for synchronous request-response.
- **Health check** → `GET /ht/` endpoint. Checks DB, Redis, Celery, S3. Used by Docker, Nginx, and monitoring.

## Payment

- **PaymentIntent** → Stripe object representing a payment attempt. Created by backend, confirmed by frontend via Payment Element.
- **client_secret** → Stripe token passed to frontend to render Payment Element. Never store or log.
- **Idempotency** → webhook handler checks `StripeEvent.stripe_id` before processing. Duplicate webhooks are safely ignored.
- **SAQ-A** → PCI compliance level. Applies when card data never touches our servers (Stripe Payment Element handles it).

## Abbreviations

- DRF → Django REST Framework
- DDD → Domain-Driven Design
- SSOT → Single Source of Truth
- UFS → Universal File Standard (our doc header format)
- REF → Reference shortcode (see `foundation-map.md`)
- PRD → Product Requirements Document
- MVP → Minimum Viable Product (V1 launch scope)
- LCP → Largest Contentful Paint (Core Web Vital)
