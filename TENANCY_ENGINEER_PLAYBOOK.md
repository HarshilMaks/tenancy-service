# Tenancy Service — Engineering Playbook

> This is not a tutorial. This is the 90% — the decisions, concepts, and industry patterns you must own to call yourself the engineer of this system. The code is the remaining 10%. Read this, research each section, make your decisions, then build.

---

## Table of Contents

1. [What Is a Tenancy Service?](#1-what-is-a-tenancy-service)
2. [Architecture Decisions You Must Make](#2-architecture-decisions-you-must-make)
3. [Phase 1: Core Safety](#3-phase-1-core-safety)
4. [Phase 2: Scale & Fairness](#4-phase-2-scale--fairness)
5. [Phase 3: Operations](#5-phase-3-operations)
6. [Phase 4: Integration & Ecosystem](#6-phase-4-integration--ecosystem)
7. [Industry Patterns Reference](#7-industry-patterns-reference)
8. [Learning Roadmap](#8-learning-roadmap)
9. [Your Decisions Log](#9-your-decisions-log)

---

## 1. What Is a Tenancy Service?

### Why it exists
Every SaaS platform needs to isolate customer data. Salesforce has Organizations. Stripe has Accounts. GitHub has Organizations. Each is a **tenant** — a boundary that separates one customer's data from another's.

### The hard problem
Multi-tenancy is trivial to build badly and hard to build well. The challenge is not "can I create an org" — it's:

- Can a user in Org A ever see Org B's data? (isolation)
- Can one noisy tenant degrade the experience for others? (fairness)
- Can I recover a tenant that was accidentally deleted? (safety)
- Can I bill a tenant based on their usage? (metering)
- Can I add a new feature flag for one tenant without deploying? (flexibility)

### Your job
You are not building a CRUD API. You are building a **boundary system** — the thing that keeps tenants safe, fair, and manageable at scale.

### Study these
- Salesforce Multi-Tenant Architecture (search: "salesforce multitenant architecture")
- Stripe's approach to tenant isolation
- GitHub's Organization model
- Postgres Row-Level Security docs
- AWS S3 tenant isolation model (resource-based policies)

---

## 2. Architecture Decisions You Must Make

These are YOUR decisions. I cannot make them. Research each, pick one, and be ready to defend it.

### 2.1 Isolation Model

**The question:** How do you prevent Tenant A from accessing Tenant B's data?

| Approach | How it works | Used by | Trade-off |
|---|---|---|---|
| **Database-per-tenant** | Separate DB per customer | Salesforce (early days) | Strongest isolation, hardest to operate, expensive |
| **Schema-per-tenant** | Same DB, separate schemas | Citus, some enterprise | Good isolation, migration pain scales with tenant count |
| **Row-Level Security (RLS)** | Same tables, `tenant_id` policy on every row | Postgres-native, modern SaaS | Best operational cost, must ensure every query respects policy |
| **Application-level filtering** | WHERE tenant_id = ? in every query | Most startups | Leakiest — one missing WHERE clause = data leak |

**Your research:**
- Read: Postgres RLS documentation (`CREATE POLICY`, `ALTER TABLE … ENABLE ROW LEVEL SECURITY`)
- Read: How does RLS interact with connection pooling? (PgBouncer, transaction mode)
- Read: How does `app.current_user_id` session variable work in Postgres for RLS?
- **Decision:** Which model? Write down why.

**Senior engineer insight:** Application-level filtering is the most common cause of multi-tenant data leaks in production. RLS is a defense-in-depth layer — even if a developer forgets a WHERE clause, the database enforces isolation. Use RLS + application filtering together, not one or the other.

### 2.2 Tenant Context Propagation

**The question:** How does every part of your system know which tenant is making the request?

The flow is: HTTP request → middleware extracts tenant_id → propagates to every downstream call (DB queries, event publishing, billing checks).

**Patterns:**
- **Context variable** (Python `contextvars`) — async-safe, per-request
- **Thread-local** — not async-safe
- **Explicit parameter** — every function takes `tenant_id` — most correct, most verbose

**Your research:**
- Read: Python `contextvars` module
- Read: FastAPI middleware + `request.state`
- **Decision:** How will tenant_id flow from HTTP request to SQL query? Draw the data flow.

### 2.3 ID Strategy

**The question:** What format are your tenant IDs?

| Option | Example | Used by |
|---|---|---|
| UUID v4 | `a1b2c3d4-...` | Generic, fine |
| ULID | `01ARZ3NDEKTSV4RRFFQ69G5FAV` | Sortable, timestamp-encoded |
| NanoID | `V1StGXR8_Z5jdHi6B-myT` | URL-safe, compact |
| Prefixed | `org_a1b2c3d4` | Stripe, GitHub — human-scannable |

**Your decision:** What prefix? What length? Why?

### 2.4 Event Sourcing vs Audit Log

**The question:** When something happens to a tenant (created, suspended, billing changed), do you store just the latest state or every event?

- **Audit log:** Store events alongside current state. Simple. Events are read-only records.
- **Event sourcing:** Events ARE the source of truth. Current state is rebuilt by replaying events. Complex. Powerful for debugging and time-travel.

**Your research:**
- Read: Event sourcing vs event logging
- Read: When is event sourcing overengineering? (short answer: most of the time)
- **Decision:** Audit log or event sourcing? Under what conditions would you change to the other?

### 2.5 Idempotency Strategy

**The question:** If a client sends the same "create tenant" request twice, what happens?

**Study this:** Stripe's idempotency — `Idempotency-Key` header, stored for 24 hours, same key + same payload = same response. Different payload = error.

**Your research:**
- Read: Stripe idempotency docs
- Read: How does idempotency interact with retry logic?
- **Decision:** TTL on idempotency keys? What happens if same key, different payload?

### 2.6 Soft Delete & Retention

**The question:** When someone "deletes" a tenant, does the data disappear forever?

**Your research:**
- Read: GDPR right to erasure vs business retention requirements
- Read: Soft delete patterns (`deleted_at`, `deleted = TRUE`)
- **Decision:** Retention period? What happens to billing during retention? Can support restore?

---

## 3. Phase 1: Core Safety

Build in this order. Do NOT skip to Phase 2 until Phase 1 is tested and proven.

### 3.1 RLS Implementation

**What you must learn:**
- How to create a `tenant_id` column on every tenant-scoped table
- How to write a `CREATE POLICY` that uses `current_setting('app.tenant_id')`
- How to set the tenant context at the start of each request
- How RLS interacts with: foreign keys, indexes, `SELECT … FOR UPDATE`, aggregations

**The decision you must make:**
- What session variable name? (`app.tenant_id`, `tenancy.current_tenant`)
- How do you handle admin queries that need to see all tenants?
- Do you enable RLS on reference tables (e.g., `plan_tiers`) that are not tenant-specific?

**Test cases to write yourself:**
- Tenant A queries → only sees Tenant A's rows
- Tenant A tries to access Tenant B's specific ID → gets 404 or 403
- Admin bypasses RLS → sees all tenants
- Unauthenticated request → RLS denies (or defaults to no rows)
- Concurrent requests from different tenants → isolation holds

### 3.2 Idempotency

**What you must learn:**
- Where to store idempotency keys (Redis, DB table, in-memory?)
- What is the TTL? (Stripe uses 24h)
- What happens when same key arrives with: same payload, different payload, expired key?
- How does idempotency interact with RLS?

**The decision you must make:**
- Storage backend for idempotency keys
- TTL duration
- Error response when key is reused with different payload (`409 Conflict`)
- Do idempotency keys expire or are they kept forever?

**Test cases:**
- POST /organizations with Idempotency-Key → creates, returns 201
- Same key again → returns same 201, does NOT create duplicate
- Same key, different body → returns 409
- Expired key → creates new resource

### 3.3 Soft Delete

**What you must learn:**
- Soft delete patterns: `deleted_at` column vs `deleted` boolean
- How does soft delete interact with unique constraints? (e.g., unique org name)
- How does soft delete interact with RLS?
- How does soft delete interact with foreign key constraints?

**The decision you must make:**
- `deleted_at` (timestamp) or `deleted` + `deleted_at`?
- Can a soft-deleted tenant be restored? To what state?
- Can a soft-deleted tenant's name be reused by a new tenant?
- Purge: how long before hard delete? Cron job or scheduled task?

**Test cases:**
- Delete tenant → marked as deleted, not actually removed
- Query tenant by ID after delete → returns 404 (or 410 Gone?)
- List tenants → does not include deleted
- Restore deleted tenant → works, state restored
- Purge expired tenants → actually deletes from DB

### 3.4 Data Model Alignment

**The current code has commented-out fields that DON'T exist in the DB:**
- `is_trial`, `trial_ends_at`, `trial_converted_at`
- `billing_info` (JSONB)
- `regional_settings` (JSONB)
- `activated_at`
- `terminated_at`
- `current_users`, `current_storage_bytes`, `current_api_calls_today`

**Your decision:** Which of these do you actually need? Add them to the model + migration, or delete them from the code. Dead code is technical debt.

---

## 4. Phase 2: Scale & Fairness

### 4.1 Per-Tenant Rate Limiting

**What you must learn:**
- Token bucket vs sliding window vs fixed window algorithms
- How to key rate limits by tenant_id and endpoint
- What limits make sense (100 req/min per tenant? 1000?)

**The decision you must make:**
- Algorithm: token bucket, sliding window, or fixed window?
- Storage: Redis (correct) vs in-memory (wrong for multi-instance)
- Limits by endpoint? (GET /tenants can be more permissive than POST)
- What happens when limit exceeded? (429 + Retry-After header)

### 4.2 Feature Flag Enforcement

**What you must learn:**
- The Edition enum exists (`free`, `essentials`, `professional`, `enterprise`, `unlimited`)
- What features does each edition get?
- How do you check "can this tenant perform this action?" in a use case?
- How do you avoid checking features in 50 places with if/else?

**The decision you must make:**
- Centralized feature registry (dict of {feature_name: set_of_editions})
- How to add a new feature flag without code change? (database-backed flags?)
- What happens when a free tenant tries a pro feature? (403 with upgrade prompt)

### 4.3 Webhook Delivery

**What you must learn:**
- Outbound webhook pattern: when domain event happens → notify external systems
- Retry with exponential backoff
- Delivery receipts (what if the receiver is down?)
- Signature verification (HMAC)

**The decision you must make:**
- Webhook retry policy: max attempts? backoff schedule?
- What events trigger webhooks? (tenant.created, tenant.suspended, tenant.deleted)
- Where does the webhook URL come from? (tenant config, env var, admin UI?)

---

## 5. Phase 3: Operations

### 5.1 Admin API

**What you must learn:**
- Internal admin endpoints need different auth (API key, not user JWT)
- Impersonation: support team can act as a tenant
- Force state transitions: what if a tenant's status is stuck?

**The decision you must make:**
- How does admin auth differ from user auth?
- What admin operations exist? (list all tenants, force state change, view any tenant)
- Audit logging for admin actions (who did what, when)

### 5.2 Circuit Breakers

**What you must learn:**
- Circuit breaker pattern: closed (normal) → open (failing) → half-open (testing)
- Why? If billing is down, the tenancy service should degrade gracefully, not fall over
- What dependencies need circuit breakers? (DB, Redis, billing service, messaging)

**The decision you must make:**
- What is the fallback behavior for each dependency?
  - DB down → service is down (no fallback)
  - Redis down → rate limiting disabled, idempotency disabled, but CRUD still works
  - Billing service down → tenant creation still works (default to free tier)
  - Messaging down → events logged but not published

### 5.3 SLIs & Health Dashboard

**What you must learn:**
- SLI: Service Level Indicator (p99 latency, error rate, request rate)
- How to expose metrics (Prometheus endpoint at `/metrics`)
- What metrics matter for a tenancy service?

**The decision you must make:**
- What metrics do you track?
  - Request latency (p50, p95, p99)
  - Error rate by endpoint
  - Active tenant count
  - Event publication rate
- Alert thresholds: what latency triggers a page?

---

## 6. Phase 4: Integration & Ecosystem

### 6.1 Billing Integration

**What you must learn:**
- Usage metering: count API calls, storage, users per tenant
- Tier enforcement: if tenant exceeds free tier limits, block or downgrade?
- Dunning: what happens when payment fails?

**The decision you must make:**
- Do metering in the tenancy service or in a separate billing service?
- When to check limits: on every request? periodically?
- Grace period after payment failure before suspension

### 6.2 Migration Safety

**What you must learn:**
- Zero-downtime migrations: expand-migrate-contract pattern
- Backward-compatible schema changes
- How to roll back a migration

**The decision you must make:**
- Migration strategy for each change:
  - Adding a column → safe (expand)
  - Removing a column → two-phase (stop writing → stop reading → drop)
  - Renaming a column → not safe, add new + migrate data + drop old
- Pre-deployment migration checklist (what to check before running)

### 6.3 Observability in Depth

**What you must learn:**
- Structured logging with correlation IDs across services
- Distributed tracing (OpenTelemetry)
- What to log: every state transition, every error, every admin action
- What NOT to log: PII, credentials, full request bodies

**The decision you must make:**
- Log format: JSON (correct for prod), colored text (dev)
- What fields are redacted in logs? (PII masker config)
- Do you emit custom business metrics? (TenantCreated count, Suspension count)

---

## 7. Industry Patterns Reference

### How Salesforce Does Tenancy
- **Metadata-driven:** Each org has its own metadata (custom objects, fields, workflows)
- **Row-level security:** Sharing rules, roles, and manual sharing
- **Governor limits:** Per-org limits on API calls, storage, query rows
- **Org ID pattern:** Prefixed (e.g., `00DXXXXXXXXXXXX`)

### How Stripe Does Tenancy
- **Account ID pattern:** Prefixed (`acct_xxxxxxxxxxxx`)
- **Idempotency:** `Idempotency-Key` header, 24h TTL
- **Event-driven:** Webhook delivery for every meaningful event
- **API versioning:** Per-account API version pinning

### How GitHub Does Tenancy
- **Organization as tenant:** Org owns repos, teams, users
- **Role-based access:** Owner, member, outside collaborator
- **Audit log:** Stream of all org-level events
- **Feature flags:** Per-org beta features

### Common patterns across all three
1. **Prefixed IDs** — human-recognizable resource type
2. **Event streams** — every notable action generates an event
3. **Per-tenant limits** — fairness through isolation
4. **Admin bypass** — internal tools can act as any tenant
5. **Soft delete** — recovery window before permanent destruction

---

## 8. Learning Roadmap

This is the order to study things. Each item links to what you need to understand before writing code.

### Week 1: Fundamentals
- [ ] FastAPI dependency injection (how `Depends()` works)
- [ ] SQLAlchemy ORM + Core (session management, query building)
- [ ] Alembic migrations (autogenerate, manual revisions)
- [ ] Postgres enums, indexes, JSONB, UUIDs
- [ ] How `contextvars` work in Python (async request context)

### Week 2: Tenant Isolation
- [ ] Postgres Row-Level Security (`CREATE POLICY`, `ALTER TABLE … ENABLE ROW LEVEL SECURITY`)
- [ ] How RLS interacts with connection pooling (PgBouncer)
- [ ] `SET LOCAL` vs `SET SESSION` for tenant context
- [ ] Writing RLS policies that work with foreign keys

### Week 3: Data Safety
- [ ] Idempotency patterns (Stripe approach)
- [ ] Soft delete patterns (deleted_at, unique constraints with deletion)
- [ ] Optimistic locking (version field, concurrent updates)
- [ ] Event sourcing vs event logging

### Week 4: API Design
- [ ] RESTful tenant management (resources, endpoints, status codes)
- [ ] JWT structure and verification (claims, expiry, signing)
- [ ] Pagination strategies (cursor vs offset, why cursor scales)
- [ ] Rate limiting algorithms (token bucket, sliding window, leaky bucket)

### Week 5: Operations
- [ ] Docker + docker-compose for local development
- [ ] Health check patterns (liveness, readiness, startup)
- [ ] Prometheus metrics exposition format
- [ ] Structured logging (JSON, correlation IDs, PII masking)

### Week 6: Integration
- [ ] Webhook delivery patterns (retry, backoff, signature)
- [ ] Circuit breaker pattern
- [ ] Feature flags (database-backed, gradual rollout)
- [ ] Billing metering patterns

---

## 9. Your Decisions Log

Before every phase, write down your decisions here. This becomes your **architecture decision record (ADR)** — the thing senior engineers maintain.

### Phase 1 Decisions

| Decision | Your Choice | Rationale |
|---|---|---|
| Isolation model | | |
| Tenant ID format | | |
| Event sourcing or audit log | | |
| Idempotency key TTL | | |
| Soft delete retention period | | |
| Can deleted tenant name be reused? | | |

### Phase 2 Decisions

| Decision | Your Choice | Rationale |
|---|---|---|
| Rate limit algorithm | | |
| Rate limit storage (Redis?) | | |
| Feature flag storage (code vs DB?) | | |
| Webhook retry schedule | | |
| Webhook HMAC secret (per-tenant or global?) | | |

### Phase 3 Decisions

| Decision | Your Choice | Rationale |
|---|---|---|
| Admin auth mechanism | | |
| Circuit breaker fallback per dependency | | |
| SLI metrics to track | | |
| Alert thresholds | | |

---

## Final Mantra

> **"Will this leak data?"** — every decision starts here.

> **"Will this survive without me?"** — the test of production readiness.

> **"Did I write a test that proves it?"** — the difference between belief and knowledge.

Build slow. Test hard. Document your decisions. The repo is proof of work; the decisions log is proof of engineering.
