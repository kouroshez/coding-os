<!-- domain:DOCS | layer:policy | ssot:true | updated:{{DATE}} -->
# GDPR / Privacy Compliance

Purpose: Define data handling, consent, and retention rules for personal data in the project.
Read when: Adding any feature that collects, stores, processes, or shares user-identifiable data.
Skip when: Working on infrastructure or internal-only features with no PII.
Read next: Engineering rules for logging (PII redaction) and security architecture.

> Nav: [Docs Index](../00-index.md)

## Personal Data Inventory

<!-- List every type of personal data the project collects. Example:

- Email address (auth, marketing, transactional)
- Name (account profile, billing)
- IP address (audit log, rate limiting, fraud detection)
- Payment info (handled by provider, never stored locally)
-->

(empty — populate when first PII is collected)

## Lawful Basis

For each data type above, specify lawful basis (consent / contract / legitimate interest / legal obligation).

## Retention Rules

- Define maximum retention period per data type
- Define automated deletion policy
- Define user-initiated deletion (right to erasure) flow

## Consent Management

- How is consent obtained? (signup checkbox, cookie banner, etc.)
- How is consent recorded? (timestamp, version of terms agreed to)
- How is consent withdrawn?

## Data Subject Rights

Provide a path for users to:

- Access their data (export)
- Rectify their data (edit)
- Erase their data (account deletion)
- Object to processing
- Port their data (machine-readable export)

## Data Processor Inventory

<!-- List every third-party that receives user data. Example:

- Payment provider (Stripe, PayPal): payment data
- Email provider (Postmark, SendGrid): email + name
- Analytics (PostHog, Plausible): IP, session, user agent
- Hosting (AWS, Cloudflare R2): all stored data
-->

(empty — populate as integrations are added)

## Breach Response

- Detection: monitoring + alerting
- Containment: rotate credentials, isolate affected systems
- Notification: notify regulator within 72 hours, notify affected users without undue delay
- Documentation: log incident in `governance/archive/`
