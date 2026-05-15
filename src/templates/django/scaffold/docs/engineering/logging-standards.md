<!-- domain:ALL | layer:policy | ssot:true | updated:2026-03-14 -->
# Logging Standards

Purpose: Structured logging format, log levels, and PII exclusion rules for all backend services.
Read when: Adding logging to any backend code or configuring log infrastructure.
Skip when: Frontend-only changes.
Read next: `backend-rules.md` for general backend engineering rules.

> Nav: [Docs Index](../00-index.md) | [Code Style](../../CodeStyle.md)

---

## Format

- **Production**: JSON via `python-json-logger` (already configured in `production.py`)
- **Development**: Standard text format for readability
- **Fields per log entry**: timestamp, level, logger_name, message, request_id (if available), user_id (if authenticated)

---

## Log Levels by Event Type

| Level | When to Use | Examples |
|:------|:------------|:--------|
| DEBUG | Development-only detailed traces | SQL queries, template rendering, cache hits |
| INFO | Normal business operations | User registered, order created, email sent, download completed |
| WARNING | Recoverable issues that need attention | Rate limit hit, soft email bounce, deprecated API usage |
| ERROR | Failed operations that need investigation | Payment failed, webhook processing error, file validation failure |
| CRITICAL | System-level failures | Database connection lost, Redis unreachable, Celery worker crash |

---

## Error Logging Patterns

- Log the full exception context (`exc_info=True`) at ERROR level for unexpected failures.
- Log expected business errors (validation, permission denied) at WARNING level without stack trace.
- **No PII in any `logger.*` call** — never pass `user.email`, full name, phone, or raw IP to any log level. Use `user.id` (UUID) only. For debugging that requires email context, use masked form (`j***@example.com`).
- Include request context (endpoint, method, user UUID) in error logs for traceability.

---

## Security Event Logging

These events MUST be logged at INFO or WARNING level for audit:

- Login success/failure (WARNING for failures)
- Password reset request
- Account creation
- Permission denied (403)
- Rate limit exceeded (429)
- CAPTCHA validation failure
- Download access denied
- Admin actions (create/update/delete)

---

## PII Exclusion Rules (CRITICAL)

**NEVER log:**

- Passwords (raw or hashed)
- Full credit card numbers (Stripe handles payment — we never see them)
- JWT tokens or refresh tokens
- API keys or secrets
- Full email addresses in ERROR/CRITICAL logs (use `j***@example.com` masking)
- IP addresses in logs retained > 90 days (anonymize for compliance)

**OK to log:**

- User IDs (UUIDs)
- Order IDs
- Product IDs
- Event types
- Status codes
- Masked emails in INFO logs (first char + *** + domain)

---

## Django LOGGING Configuration

```python
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "loggers": {
        "apps": {"level": "INFO", "handlers": ["console"], "propagate": False},
        "django.security": {"level": "WARNING", "handlers": ["console"], "propagate": False},
        "celery": {"level": "INFO", "handlers": ["console"], "propagate": False},
    },
    "root": {"level": "WARNING", "handlers": ["console"]},
}
```

---
[Docs Index](../00-index.md)
