<!-- domain:INFRA | layer:reference | ssot:true | updated:2026-03-29 -->
# Secrets Rotation Runbook

Purpose: Step-by-step procedures for rotating all production secrets with zero downtime.
Read when: A secret has been exposed, a rotation schedule triggers, or onboarding a new team member to ops procedures.
Skip when: No secrets need rotation and no exposure has occurred.
Read next: `../architecture/04a-auth-security.md` for auth architecture details.

> Nav: [Docs Index](../00-index.md) | [Backend Rules](./backend-rules.md)

---

## Django SECRET_KEY

**Automated rotation available.** Django 4.1+ supports `SECRET_KEY_FALLBACKS` for zero-downtime key rotation.

### Automated (recommended)

```bash
make rotate-secret-key
# or with custom .env path:
bash infrastructure/scripts/rotate-secrets.sh --env-file src/backend/.env
```

The script:
1. Generates a new 50-character random key
2. Moves the current key to `DJANGO_SECRET_KEY_FALLBACKS`
3. Sets the new key as `DJANGO_SECRET_KEY`
4. Creates a timestamped backup of `.env`

### Post-rotation

1. Deploy the application (existing sessions remain valid via fallback)
2. After 7+ days with no session errors: remove the old key from `DJANGO_SECRET_KEY_FALLBACKS`
3. Monitor Django logs for `Signature verification failed` warnings

### Manual (if script unavailable)

1. Generate: `python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
2. Set `DJANGO_SECRET_KEY=<new_key>` in `.env`
3. Set `DJANGO_SECRET_KEY_FALLBACKS=<old_key>` in `.env` (comma-separated if multiple)
4. Deploy
5. After 7 days, remove old key from `DJANGO_SECRET_KEY_FALLBACKS`

---

## Stripe API Keys

Stripe keys support a 24-hour grace period where both old and new keys work.

### Steps

1. Go to Stripe Dashboard -> Developers -> API keys
2. Click "Roll key" on the secret key (`sk_live_...`)
3. Stripe provides the new key immediately; old key works for 24 hours
4. Validate the new key:
   ```bash
   make rotate-secret WHICH=stripe
   ```
5. Update `STRIPE_LIVE_SECRET_KEY` (or `STRIPE_TEST_SECRET_KEY`) in `.env`
6. Deploy within 24 hours
7. Verify webhook signatures still work (webhook signing secret is separate)

### Webhook signing secret

1. Go to Stripe Dashboard -> Developers -> Webhooks -> your endpoint
2. Click "Reveal" on signing secret, then "Roll secret"
3. Update `STRIPE_WEBHOOK_SECRET` in `.env`
4. Deploy immediately (no grace period for webhook secrets)

---

## Postmark API Token

Postmark invalidates the old token immediately on regeneration. Schedule maintenance window.

### Steps

1. Go to Postmark -> Servers -> your server -> API Tokens
2. Click "Regenerate" (old token invalidated instantly)
3. Update `POSTMARK_SERVER_TOKEN` in `.env`
4. Deploy immediately
5. Verify email delivery by checking Postmark activity log

### Risk mitigation

- Schedule during low-traffic hours
- Have the new token ready to paste before regenerating
- Deploy within 2-3 minutes of regeneration

---

## Sentry DSN

Sentry DSN rotation is rarely needed. The DSN contains only the project ID and public key (no secret material). Rotate only if the DSN was accidentally exposed in client-side code alongside private data.

### Steps

1. Go to Sentry -> Settings -> Projects -> your project -> Client Keys
2. Click "Generate new key" (creates a new DSN; old remains active)
3. Update `SENTRY_DSN` in `.env`
4. Deploy
5. After confirming new DSN works: disable the old key in Sentry

---

## PostHog API Key

PostHog project API keys are public by design (used in client-side analytics). Rotation is only needed if the project itself needs to change.

### Steps

1. Go to PostHog -> Settings -> Project -> API Key
2. Regenerate the project API key
3. Update `NEXT_PUBLIC_POSTHOG_KEY` in frontend `.env`
4. Rebuild and deploy the frontend
5. Old events may still arrive on the old key until all clients refresh

---

## Cloudflare Turnstile

### Steps

1. Go to Cloudflare Dashboard -> Turnstile -> your site
2. Click "Rotate secret key" (both keys valid for 24 hours)
3. Update `TURNSTILE_SECRET_KEY` in backend `.env`
4. Deploy backend within 24 hours
5. Site key (`NEXT_PUBLIC_TURNSTILE_SITE_KEY`) does not change during rotation

---

## Rotation Schedule

Recommended rotation cadence:

- **Django SECRET_KEY**: every 90 days or on suspected exposure
- **Stripe keys**: every 90 days or on suspected exposure
- **Postmark token**: only on suspected exposure (no grace period makes routine rotation risky)
- **Sentry DSN**: only on suspected exposure
- **PostHog key**: only if project change needed
- **Turnstile secret**: every 90 days or on suspected exposure
