# 🎯 API ENDPOINT SPECIFICATION

**Status:** ✅ Finalized & Document‑Accurate
**Date:** 2026-02-09
**Version:** v1 (document)
**Total Endpoints:** 18
**Categories:** Core, Lifecycle, Settings, Region & Residency, Policy, Usage, Events

---

## 📋 EXECUTIVE SUMMARY

This document is the authoritative API specification for the Tenancy Service — the document-accurate reference teams should use for design, client SDKs, and implementation planning. It defines canonical paths, HTTP methods, request/response shapes (key fields), and implementation intent (Implemented / Partial / Planned). This file represents the desired, finalized API contract; implementation status notes are informational only and do not change the contract.

Key decisions:
- Resource name: `/tenants` (not `/organizations`)
- Lifecycle operations are commands (POST) not PUT
- Versioning: v1 path prefix is the canonical API surface (e.g., `/api/v1/tenants`)

---

## 🗂️ ENDPOINT BREAKDOWN (DOCUMENT-SPEC)

NOTE: For each endpoint we list the canonical contract. Implementation status (Implemented / Partial / Planned) is indicated, but the contract is authoritative.

### 1️⃣ CORE TENANTS
Base Path: `/api/v1/tenants`

POST /api/v1/tenants
- Purpose: Create a tenant
- Request (JSON):
  - name: string (required)
  - edition: string (required) — e.g. free, professional, enterprise
  - region: string (required) — e.g. us-east-1
  - org_type?: string (default: "production")
  - created_by_email?: string
  - billing_email?: string
  - start_trial?: boolean (default: true)
  - trial_days?: integer (default: 14)
- Response (201 Created):
  - id: UUID (internal)
  - org_id: string (external id, e.g. ORG-XXXX)
  - name, status, edition, region, org_type, is_trial, created_at, updated_at
- Errors: 400 on validation
- Contract status: Finalized
- Implementation status: Implemented

GET /api/v1/tenants
- Purpose: List tenants (paginated)
- Query params: skip: int (default 0), limit: int (default 10), status?: string, sort?: string
- Response (200 OK):
  - items: [TenantSummary]
  - total: int
  - skip: int
  - limit: int
- TenantSummary fields: id, org_id, name, status, edition, region, is_trial, created_at
- Contract status: Finalized
- Implementation status: Implemented

GET /api/v1/tenants/{tenant_id}
- Purpose: Retrieve tenant details
- Path param: tenant_id: UUID
- Response (200 OK): Tenant object (see POST response fields)
- Errors: 404 if not found
- Contract status: Finalized
- Implementation status: Implemented

PATCH /api/v1/tenants/{tenant_id}
- Purpose: Partial update of tenant metadata
- Path param: tenant_id: UUID
- Request (JSON):
  - name?: string
  - edition?: string
  - metadata?: object
- Response (200 OK): Updated Tenant object
- Errors: 400 on validation, 404 if not found
- Contract status: Finalized
- Implementation status: Implemented

DELETE /api/v1/tenants/{tenant_id}
- Purpose: Hard delete tenant (admin operation; subject to retention rules)
- Path param: tenant_id: UUID
- Response: 204 No Content (or 200 with {success:true, message:...} — prefer 204)
- Preconditions: tenant must be terminated and retention period elapsed
- Contract status: Finalized
- Implementation status: Planned / partial (see notes)

---

### 2️⃣ TENANT LIFECYCLE (commands)
Base prefix: `/api/v1/tenants/{tenant_id}`

POST /api/v1/tenants/{tenant_id}/activate
- Purpose: Activate a tenant previously created or resumed
- Request: {} (optionally activated_by: string)
- Response (200 OK): { org_id, status: "active", activated_at }
- Contract status: Finalized
- Implementation status: Implemented (command semantics)

POST /api/v1/tenants/{tenant_id}/suspend
- Purpose: Suspend tenant (billing or policy reasons)
- Request (JSON):
  - reason: string (required)
  - suspension_period?: int (days)
  - notify_admins?: boolean (default true)
- Response (200 OK): { org_id, status: "suspended", suspended_at, suspended_reason }
- Contract status: Finalized
- Implementation status: Implemented

POST /api/v1/tenants/{tenant_id}/resume
- Purpose: Resume a suspended tenant
- Request: {} (optionally resumed_by: string)
- Response (200 OK): { org_id, status: "active", resumed_at }
- Contract status: Finalized
- Implementation status: Implemented

POST /api/v1/tenants/{tenant_id}/terminate
- Purpose: Terminate tenant (begin data retention / deletion workflow)
- Request (JSON):
  - reason: string (required)
  - data_retention_days?: int (default 90)
- Response (200 OK): { org_id, status: "terminated", terminated_at, data_retention_until }
- Contract status: Finalized
- Implementation status: Implemented

---

### 3️⃣ TENANT SETTINGS
Base prefix: `/api/v1/tenants/{tenant_id}/settings`

GET /api/v1/tenants/{tenant_id}/settings
- Purpose: Fetch tenant configuration and compliance flags
- Response (200 OK):
  - primary_region: string
  - allowed_regions: [string]
  - compliance_flags: { gdpr: bool, hipaa: bool, ... }
  - data_isolation_mode: string (logical|physical)
  - custom_domain?: string
  - updated_at?: timestamp
- Contract status: Finalized
- Implementation status: Planned (current service stubs this endpoint)

PATCH /api/v1/tenants/{tenant_id}/settings
- Purpose: Update tenant settings
- Request: subset of GET response fields
- Response (200 OK): Updated settings
- Contract status: Finalized
- Implementation status: Planned

---

### 4️⃣ REGION & RESIDENCY
Base prefix: `/api/v1/tenants/{tenant_id}/region`

GET /api/v1/tenants/{tenant_id}/region
- Purpose: Report residency & allowed zones
- Response (200 OK):
  - primary_region: string
  - allowed_regions: [string]
  - data_residency_requirement: string (e.g., US_ONLY)
  - compliance_zones: [string]
- Contract status: Finalized
- Implementation status: Planned / example

POST /api/v1/tenants/{tenant_id}/region/validate
- Purpose: Validate whether a requested region is allowed for this tenant
- Request: { region: string }
- Response: { valid: bool, reason?: string }
- Contract status: Finalized
- Implementation status: Planned

---

### 5️⃣ POLICY ENFORCEMENT
Base prefix: `/api/v1/tenants/{tenant_id}/policy`

POST /api/v1/tenants/{tenant_id}/policy/evaluate
- Purpose: Evaluate whether a tenant/user can perform an action
- Request (JSON):
  - action: string (e.g., "read:data")
  - resource: string (e.g., "dataset:xyz")
  - context?: object (user_id, ip, etc.)
- Response (200 OK):
  - allow: bool
  - reason?: string
  - violations: [string]
- Contract status: Finalized
- Implementation status: Implemented (document contract honored)

---

### 6️⃣ USAGE & METERING
Base prefix: `/api/v1/tenants/{tenant_id}/usage`

GET /api/v1/tenants/{tenant_id}/usage
- Purpose: Retrieve usage metrics for a tenant
- Query params: period (e.g., month|current), start_date, end_date
- Response (200 OK):
  - tenant_id: string
  - period: string
  - metrics: { api_calls: int, storage_gb: float, active_users: int, data_processed_gb: float }
  - limits: { api_calls_limit: int, storage_limit_gb: float, users_limit: int }
  - usage_percentage: { api_calls: float, storage: float, users: float }
- Contract status: Finalized
- Implementation status: Implemented (returns structured metrics)

---

### 7️⃣ EVENTS & AUDIT
Base prefix: `/api/v1/tenants/{tenant_id}/events`

GET /api/v1/tenants/{tenant_id}/events
- Purpose: Query tenant audit events (admin)
- Query params: skip, limit, event_type, sort
- Response (200 OK): paginated list of Event objects:
  - event_id, event_type, timestamp, actor_id?, details?
- Contract status: Finalized
- Implementation status: Implemented (admin-only semantics to be enforced in implementation)

---

## 🔄 MIGRATION PATH (Design-level)

- Old path → New path:
  - `/organizations` → `/tenants`
  - `/organizations/{id}/policy/check` → `/tenants/{id}/policy/evaluate`
- HTTP method corrections:
  - Use POST for lifecycle commands (activate, suspend, resume, terminate) — commands not resource replacements
- Pagination strategy: skip & limit (documented above)
- Error model: use standard JSON API error shape { error: "string", details?: { ... } } across endpoints

---

## 📊 IMPLEMENTATION STATUS (SUMMARY)

| Endpoint | Method | Path | Contract | Implementation Status |
|---|---:|---|---|---|
| Create Tenant | POST | /tenants | Finalized | Implemented
| List Tenants | GET | /tenants | Finalized | Implemented
| Get Tenant | GET | /tenants/{id} | Finalized | Implemented
| Update Tenant | PATCH | /tenants/{id} | Finalized | Implemented
| Delete Tenant | DELETE | /tenants/{id} | Finalized | Planned / Partial
| Activate | POST | /tenants/{id}/activate | Finalized | Implemented
| Suspend | POST | /tenants/{id}/suspend | Finalized | Implemented
| Resume | POST | /tenants/{id}/resume | Finalized | Implemented
| Terminate | POST | /tenants/{id}/terminate | Finalized | Implemented
| Settings (GET/PATCH) | GET/PATCH | /tenants/{id}/settings | Finalized | Planned (501 stubs)
| Region | GET/POST | /tenants/{id}/region* | Finalized | Planned
| Policy Evaluate | POST | /tenants/{id}/policy/evaluate | Finalized | Implemented
| Usage | GET | /tenants/{id}/usage | Finalized | Implemented
| Events | GET | /tenants/{id}/events | Finalized | Implemented
| Health | GET | /health, /health/live, /health/ready | Finalized | Implemented

*Region endpoints may be surfaced under `/api/v1/regions` for organization-level regional settings depending on product rules.

---

## 📝 CHANGELOG (recent updates included in this document)
- 2026-02-09: Document finalized to include all 18 endpoints and reflect the latest service coverage; clarified lifecycle command verbs (POST) and standardized request/response shapes.
- Implemented endpoints noted as such for implementers; settings & region endpoints remain planned and must be implemented to complete the feature set.

---

## ✅ ACCEPTANCE CRITERIA FOR IMPLEMENTATION
- OpenAPI/Swagger specification generated from code must match this contract (paths, methods, schemas) before release.
- End-to-end API tests for critical paths: Create → Activate → Usage & Billing must pass.
- Admin-only endpoints (events) must enforce RBAC.
- Deletion must follow retention policy and be gated by termination + retention expiry.

---

## 📚 NEXT STEPS
1. Confirm this document as the canonical spec (approve or request edits).
2. If approved, generate OpenAPI from this spec and reconcile any diffs with code.
3. Implement remaining planned endpoints (settings & region) and remove 501 stubs.
4. Add API-level tests and update SDKs.

---

Document owner: Platform API team
