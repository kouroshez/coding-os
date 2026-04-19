<!-- domain:DOCS | layer:template | ssot:ref | updated:2026-08-05 -->
# 🚀 Technical Specification Document

### Fill-in template for a new service or system

---

| Field | Value |
|---|---|
| **Project name** | `[project name]` |
| **Document version** | v1.0 |
| **Author** | [team or person] |
| **Created** | [date] |
| **Status** | 🟡 Draft |
| **Last updated** | [date] |

---

## 📋 Table of contents

1. [Executive summary](#-1-executive-summary)
2. [Scale and performance requirements](#-2-scale-and-performance-requirements)
3. [System architecture](#️-3-system-architecture)
4. [Database design](#️-4-database-design)
5. [API design](#-5-api-design)
6. [Security](#-6-security)
7. [DevOps and infrastructure](#-7-devops-and-infrastructure)
8. [Test strategy](#-8-test-strategy)
9. [Planning and timeline](#-9-planning-and-timeline)
10. [Risks](#️-10-risks)
11. [Glossary](#-11-glossary)

---

## 🎯 1. Executive summary

### Objective

> [One paragraph: what does this system do, and which problem does it solve?]

### Current problem

[What need or failure exists today that this system addresses?]

### Proposed solution

[Summary of the technical approach and the reasoning behind it.]

### Stakeholders

| Role | Name | Responsibility |
|---|---|---|
| Product Owner | [name] | Final sign-off on requirements |
| Tech Lead | [name] | Architecture and code review |
| Backend Developer | [name] | API and server-side logic |
| Frontend Developer | [name] | User interface |
| DevOps | [name] | Infrastructure, CI/CD, deployment |
| QA Engineer | [name] | Testing and quality assurance |

---

## ⚡ 2. Scale and performance requirements

> **Why this is the most important section.** Every architectural
> decision downstream — database choice, cache strategy, instance
> sizing — derives from these numbers. Without them, the design is
> guesswork.

### 2.1 Traffic volume

| Metric | Normal | Peak | Notes |
|---|---|---|---|
| Concurrent users | [X] | [X × 3] | Plan for 3× the observed peak |
| Requests per second (RPS) | [X] | [X × 5] | API requests per second |
| Daily active users (DAU) | [X] | — | |
| Monthly active users (MAU) | [X] | — | |
| Monthly growth rate | [X%] | — | Projection |

#### 🧮 How to compute RPS

```
Given 100,000 daily active users at 20 requests each per day:

  100,000 × 20 = 2,000,000 requests per day
  ÷ 86,400 (seconds per day)
  ≈ 23 RPS average

  Peak (factor of 5): ≈ 115 RPS  ← design against this number
```

### 2.2 Performance objectives (SLO)

| Metric | Target (SLO) | Maximum acceptable | Measured by |
|---|---|---|---|
| API response time (P95) | < 200 ms | < 500 ms | Datadog / Prometheus |
| API response time (P99) | < 500 ms | < 1000 ms | Datadog / Prometheus |
| Uptime | 99.9% | 99.5% | Uptime monitoring |
| Error rate | < 0.1% | < 1% | Sentry |
| DB query time (P95) | < 50 ms | < 200 ms | DB slow-query log |

> 💡 **99.9% uptime allows only 8.7 hours of downtime per year.** State
> this explicitly — the number is far less generous than it sounds.

### 2.3 Data volume

| Table / collection | Current size | Monthly growth | Size in 1 year | Strategy |
|---|---|---|---|---|
| users | [X] rows | [X%] | [X] rows | Index on email, phone |
| [primary table] | [X] rows | [X%] | [X] rows | Partition by date |
| [transactions] | [X] rows | [X%] | [X] rows | Archive older than 6 months |
| [logs] | [X] rows | [X%] | [X] rows | Ship to Elasticsearch |

---

## 🏗️ 3. System architecture

### 3.1 Chosen architecture

- [ ] **Monolith** — small team, fastest path to a running system
- [ ] **Modular monolith** — one deployable, logically separated modules *(the default recommendation for most new products)*
- [ ] **Microservices** — large systems with independent teams and independent release cadences

**Rationale:** [why this one, and what was rejected]

### 3.2 Request flow

```
┌─────────┐     ┌─────┐     ┌───────────────┐     ┌───────────────┐
│  Client │────▶│ CDN │────▶│ Load Balancer │────▶│  App Servers  │
└─────────┘     └─────┘     └───────────────┘     └───────┬───────┘
                                                          │
                             ┌────────────────────────────┼───────────────┐
                             │                            │               │
                     ┌───────▼──────┐           ┌─────────▼─────┐  ┌──────▼───┐
                     │ Redis Cache  │           │  PostgreSQL   │  │  Queue   │
                     └──────────────┘           └───────────────┘  └─────┬────┘
                                                                         │
                                                                  ┌──────▼──────┐
                                                                  │   Workers   │
                                                                  └─────────────┘
```

### 3.3 Technology stack

| Layer | Technology | Version | Rationale |
|---|---|---|---|
| Backend framework | [Node.js / Django / Laravel / …] | [v] | [why] |
| Primary database | [PostgreSQL / MySQL / MongoDB] | [v] | [why] |
| Cache | Redis | [v] | Sessions, API cache, queue |
| Message queue | [BullMQ / RabbitMQ / Kafka] | [v] | [why] |
| Search engine | [Elasticsearch / Meilisearch / —] | [v] | [why] |
| Object storage | [S3 / MinIO / —] | — | Files, images, backups |
| CDN | [CloudFront / Cloudflare / —] | — | Static assets |
| Frontend | [React / Vue / Next.js / …] | [v] | [why] |
| Mobile | [React Native / Flutter / —] | [v] | [why] |
| Containers | Docker + Kubernetes | — | Orchestration |

### 3.4 Scaling phases

| Phase | Users | Architecture | Action required |
|---|---|---|---|
| Phase 1 (MVP) | 0 – 10K | Single server + DB | Docker Compose |
| Phase 2 | 10K – 100K | 2 app servers + read replica | Load balancer + replica |
| Phase 3 | 100K – 1M | Kubernetes + sharding | K8s + DB sharding |
| Phase 4 | > 1M | Multi-region + edge | Global distribution |

---

## 🗄️ 4. Database design

### 4.1 Storage choices

| Type | Used for | Technology | Rationale |
|---|---|---|---|
| Relational (SQL) | Core entities, transactions | PostgreSQL | ACID, complex relations |
| Key-value | Cache, sessions | Redis | O(1) access, native TTL |
| Document | [if needed] | MongoDB | Flexible schema |
| Search | Full-text search | Elasticsearch | Ranked and fuzzy queries |

### 4.2 Core tables and indexes

```sql
-- users
CREATE TABLE users (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email       VARCHAR(255) UNIQUE NOT NULL,
  phone       VARCHAR(20),
  status      VARCHAR(20) DEFAULT 'active',
  created_at  TIMESTAMP DEFAULT NOW(),
  updated_at  TIMESTAMP DEFAULT NOW()
);

-- ⚠️ Without these indexes, queries degrade sharply past ~1M rows.
CREATE INDEX idx_users_email          ON users(email);
CREATE INDEX idx_users_phone          ON users(phone);
CREATE INDEX idx_users_status_created ON users(status, created_at DESC);

-- ─────────────────────────────────────────────
-- [primary table]
CREATE TABLE [table_name] (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id),
  status      VARCHAR(20) NOT NULL,
  created_at  TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_[table]_user_id ON [table_name](user_id);
CREATE INDEX idx_[table]_status  ON [table_name](status, created_at DESC);
```

> ⚠️ **Rule of thumb:** every column used in a `WHERE`, `ORDER BY`, or
> `JOIN` needs an index.

### 4.3 Cache strategy

| Data | TTL | Strategy | Invalidation |
|---|---|---|---|
| User profile | 15 minutes | Cache-aside | On update |
| Product listing | 5 minutes | Read-through | On change |
| System settings | 1 hour | Cache-aside | Manual |
| User session | 24 hours | Write-through | On logout |

### 4.4 Database pitfalls

- **N+1 queries:** never issue a query inside a loop — use `JOIN` or eager loading.
- **Pagination:** use cursor-based pagination for large tables; `OFFSET` degrades linearly with depth.
- **Connection pool:** concurrent connections are a finite resource — size the pool deliberately.
- **Soft delete:** prefer a `deleted_at` column over a destructive `DELETE`.

---

## 🔌 5. API design

### 5.1 Standards

- **Base URL:** `https://api.[domain].com/v1`
- **Format:** JSON for both request and response
- **Authentication:** JWT bearer token in the `Authorization` header
- **Versioning:** URL-based — `/v1/`, `/v2/`
- **Rate limiting:** 100 requests per minute per user
- **Pagination:** cursor-based for large collections

### 5.2 Core endpoints

| Method | Endpoint | Description | Auth | Rate limit |
|---|---|---|---|---|
| `POST` | `/auth/register` | Register a user | — | 10/min |
| `POST` | `/auth/login` | Log in, issue JWT | — | 5/min |
| `POST` | `/auth/refresh` | Refresh the access token | JWT | 30/min |
| `POST` | `/auth/logout` | Log out, revoke token | JWT | 30/min |
| `GET` | `/users/me` | Current user profile | JWT | 60/min |
| `PUT` | `/users/me` | Update profile | JWT | 20/min |
| `GET` | `/[resource]` | List with filters and pagination | JWT | 100/min |
| `POST` | `/[resource]` | Create | JWT | 30/min |
| `GET` | `/[resource]/:id` | Fetch one | JWT | 100/min |
| `PUT` | `/[resource]/:id` | Full update | JWT | 30/min |
| `PATCH` | `/[resource]/:id` | Partial update | JWT | 30/min |
| `DELETE` | `/[resource]/:id` | Delete | JWT + admin | 20/min |

### 5.3 Response format

```json
// ✅ Success — single item (200 OK)
{
  "success": true,
  "data": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "name": "..."
  },
  "meta": {
    "timestamp": "2026-01-01T00:00:00Z"
  }
}

// ✅ Success — paginated list (200 OK)
{
  "success": true,
  "data": [],
  "pagination": {
    "cursor": "eyJpZCI6MTAwfQ==",
    "has_more": true,
    "total": 50000
  }
}

// ❌ Error — validation (422)
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The email field is required.",
    "field": "email"
  }
}

// ❌ Error — server (500)
{
  "success": false,
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Internal server error.",
    "request_id": "req_abc123"
  }
}
```

### 5.4 HTTP status codes

| Code | Meaning | When |
|---|---|---|
| `200` | OK | Successful GET, PUT, PATCH |
| `201` | Created | Successful POST that created a resource |
| `204` | No Content | Successful DELETE |
| `400` | Bad Request | Malformed request |
| `401` | Unauthorized | Missing or expired token |
| `403` | Forbidden | Authenticated but not permitted |
| `404` | Not Found | Resource does not exist |
| `422` | Unprocessable | Validation failure |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Server Error | Unhandled internal failure |

---

## 🔐 6. Security

### 6.1 Authentication and authorization

| Concern | Mechanism | Notes |
|---|---|---|
| Authentication | JWT + refresh token | Access 15 min \| refresh 7 days |
| Authorization | RBAC | Roles: `admin`, `user`, `guest` |
| Passwords | bcrypt (cost 12) | Never store plaintext |
| API keys | SHA-256 hash at rest | For B2B service consumers |
| 2FA (optional) | TOTP | For privileged accounts |

### 6.2 OWASP Top 10 checklist

| Vulnerability | Mitigation | Status |
|---|---|---|
| SQL injection | Parameterized queries / ORM | ☐ |
| XSS | Input sanitisation + CSP header | ☐ |
| Broken authentication | JWT + rate limiting on login | ☐ |
| Sensitive data exposure | HTTPS everywhere + encryption at rest | ☐ |
| Broken access control | RBAC validated on every endpoint | ☐ |
| Security misconfiguration | Secure headers, debug disabled in production | ☐ |
| Vulnerable dependencies | `npm audit` / `pip-audit` + Dependabot | ☐ |
| Secrets in source | Vault or env vars + `.gitignore` | ☐ |

### 6.3 Secrets management

```bash
# ❌ Never
DB_PASSWORD="my_password_123"   # hardcoded in source
git add .env                    # committed to version control

# ✅ Correct — local .env, listed in .gitignore
DB_PASSWORD=${DB_PASSWORD}
JWT_SECRET=${JWT_SECRET}
STRIPE_API_KEY=${STRIPE_API_KEY}

# In production use a managed secret store:
# - AWS Secrets Manager
# - HashiCorp Vault
# - Kubernetes Secrets (encrypted at rest)
```

### 6.4 Required security headers

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Content-Security-Policy: default-src 'self'
X-XSS-Protection: 1; mode=block
```

---

## 🚀 7. DevOps and infrastructure

### 7.1 Environments

| Environment | Purpose | URL | Deploy trigger | Database |
|---|---|---|---|---|
| Development | Local development | `localhost` | Docker Compose | Local |
| Staging | Pre-production verification | `staging.domain.com` | Automatic on merge | Anonymised copy |
| Production | Live | `api.domain.com` | Manual approval | Production data |

### 7.2 CI/CD pipeline

```
Git push
  └─▶ CI trigger
        │
        ├─▶ 1. Lint and type check       (~2 min)
        ├─▶ 2. Unit tests                (~5 min)
        ├─▶ 3. Integration tests         (~10 min)
        ├─▶ 4. Dependency / security scan(~3 min)
        ├─▶ 5. Build container image     (~5 min)
        │
        └─▶ Deploy
              ├─▶ branch: main  →  staging     (automatic)
              └─▶ tag: v*.*.*  →  production   (manual approval)
```

### 7.3 Infrastructure

| Component | Service | Production spec | Count |
|---|---|---|---|
| App server | EC2 / Compute | 4 vCPU, 8 GB RAM | 2 + autoscale |
| Database | RDS PostgreSQL | 4 vCPU, 16 GB RAM | 1 primary + 1 replica |
| Cache | ElastiCache Redis | 2 vCPU, 4 GB RAM | 1 + replica |
| Load balancer | ALB / nginx | — | 1 (HA pair) |
| Object storage | S3 | Pay per use | 1 bucket |
| CDN | CloudFront | Pay per use | Global |

### 7.4 Monitoring and alerting

| Signal | Tool | Alert threshold | Response |
|---|---|---|---|
| CPU usage | CloudWatch / Datadog | > 80% | Autoscale + notify |
| Memory usage | CloudWatch | > 85% | Notify and investigate |
| API error rate | Sentry + Datadog | > 1% | Page on-call |
| Response time P99 | Datadog APM | > 1 s | Notify + consider rollback |
| DB connection pool | Prometheus | > 80% | Notify + scale |
| Disk usage | CloudWatch | > 75% | Alert + clean up |
| TLS certificate | Uptime monitor | < 14 days to expiry | Alert |

### 7.5 Backup and disaster recovery

| Data | Backup frequency | Retention | RTO | RPO |
|---|---|---|---|---|
| Database | Every 6 hours + daily | 30 days | < 15 min | < 5 min |
| File storage | Daily incremental | 90 days | < 1 hour | < 24 hours |
| Config / secrets | On change | Indefinite | < 5 min | 0 |

---

## 🧪 8. Test strategy

### 8.1 Test levels

| Level | Tooling | Coverage target | Scope |
|---|---|---|---|
| Unit | Jest / pytest | > 80% | Individual functions and logic |
| Integration | Supertest / pytest | > 60% | API endpoints against a real DB |
| End-to-end | Playwright / Cypress | Critical paths | Complete user journeys |
| Performance | k6 / Locust | Before each release | Load test at [X] concurrent users |
| Security | OWASP ZAP / dependency scan | Each release | Vulnerability scan |

### 8.2 Definition of Done ✅

A feature is ready to deploy when **all** of the following hold:

- [ ] Unit tests written (coverage > 80%)
- [ ] Integration tests written
- [ ] Reviewed by at least one other party
- [ ] Verified in staging
- [ ] API documentation updated
- [ ] Performance checked in staging
- [ ] No secrets or credentials present in source

### 8.3 Example load test

```javascript
// k6 — load test at [X] concurrent users
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  stages: [
    { duration: '2m', target: 100 },   // ramp up
    { duration: '5m', target: 1000 },  // peak load
    { duration: '2m', target: 0 },     // ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<200', 'p(99)<500'],  // SLO from section 2.2
    http_req_failed: ['rate<0.01'],                 // error rate < 1%
  },
};

export default function () {
  const res = http.get('https://staging.domain.com/v1/[endpoint]');
  check(res, { 'status is 200': (r) => r.status === 200 });
}
```

---

## 📅 9. Planning and timeline

### 9.1 Phases

| Phase | Name | Duration | Start | End | Deliverable |
|---|---|---|---|---|---|
| Phase 1 | MVP | [X weeks] | [date] | [date] | Core features live |
| Phase 2 | Stabilisation | [X weeks] | [date] | [date] | Performance and bug fixes |
| Phase 3 | Growth features | [X weeks] | [date] | [date] | Advanced features |
| Phase 4 | Scale | [X weeks] | [date] | [date] | Infrastructure scale-out |

### 9.2 Key milestones

| Milestone | Target date | Success criterion | Status |
|---|---|---|---|
| Database schema frozen | [date] | Tech Lead sign-off | ☐ |
| Auth API complete | [date] | Integration tests pass | ☐ |
| Core APIs complete | [date] | E2E tests pass | ☐ |
| Performance test passed | [date] | P95 < 200 ms under load | ☐ |
| Security audit | [date] | OWASP checklist complete | ☐ |
| Production launch | [date] | Staging stable > 1 week | ☐ |

---

## ⚠️ 10. Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| DB bottleneck under traffic spike | 🟡 Medium | 🔴 High | Connection pooling + read replica ready |
| Third-party API outage | 🔴 High | 🟡 Medium | Circuit breaker + fallback path |
| Security breach | 🟢 Low | 🔴 Critical | OWASP checklist + penetration test |
| Data loss | 🟢 Low | 🔴 Critical | 6-hourly backups + restore drills |
| Key-person dependency | 🟡 Medium | 🔴 High | Documentation + shared ownership |
| Scope creep | 🔴 High | 🟡 Medium | Explicit change-management process |

---

## 📖 11. Glossary

| Term | Definition |
|---|---|
| **RPS** | Requests per second |
| **P95 / P99** | 95th / 99th percentile — 95% or 99% of requests complete within this time |
| **SLA** | Service Level Agreement — contractual uptime commitment to a customer |
| **SLO** | Service Level Objective — the team's internal quality target |
| **RTO** | Recovery Time Objective — maximum acceptable time to restore service |
| **RPO** | Recovery Point Objective — maximum acceptable data loss |
| **RBAC** | Role-Based Access Control |
| **ACID** | Atomicity, Consistency, Isolation, Durability — transaction guarantees |
| **CDN** | Content Delivery Network — edge distribution to reduce latency |
| **CI/CD** | Continuous Integration / Deployment — automated build, test and deploy |
| **N+1 query** | Performance defect: one query per loop iteration instead of a single join |
| **Circuit breaker** | Pattern that stops calls to a failing dependency to prevent cascading failure |
| **Idempotent** | An operation that produces the same result when repeated |
| **Sharding** | Splitting data across database servers for horizontal scale |
| **Eventual consistency** | Replicas converge over time rather than immediately |

---

## 🤖 Using this document with a coding agent

> Provide this section at the start of a session so generated code is
> constrained by the specification rather than by defaults.

```
This is the technical specification for [project name].
All code you write must:

1. Hold under the numbers in section 2 (Scale):
   - [X] concurrent users, [X] RPS at peak
   - P95 response time < 200 ms

2. Create the indexes defined in section 4.2

3. Satisfy the OWASP checklist in section 6.2

4. Use the error format in section 5.3

5. Before each change, state:
   - Why this approach, and what was rejected
   - Which trade-offs it accepts
   - How it behaves at [X] concurrent users
   - Where the first bottleneck will appear
```

---

*Last updated: [date] | Version: v1.0 | Author: [name]*
