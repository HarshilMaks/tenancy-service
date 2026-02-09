# Logging & PII Masking Guide

## Overview

All logging in the tenancy service includes automatic PII masking for compliance with GDPR, SOC2, and HIPAA.

## What Gets Masked

### Automatic Masking
- ✅ Email addresses → `***EMAIL***`
- ✅ Phone numbers → `***PHONE***`
- ✅ Social security numbers → `***SSN***`
- ✅ Credit card numbers → `***CC***`
- ✅ API keys → `***API_KEY***`
- ✅ Bearer tokens → `Bearer ***TOKEN***`

### Sensitive Fields
These fields are always masked in structured logs:
- `password`, `secret`, `token`, `api_key`
- `auth`, `authorization`, `credential`
- `credit_card`, `card_number`, `cvv`
- `ssn`, `social_security`
- `access_token`, `refresh_token`, `private_key`

## Logging Best Practices

### ✅ DO: Use extra dict for sensitive data

```python
import logging

logger = logging.getLogger(__name__)

# Good - org_id is masked automatically
logger.info("Organization created", extra={"org_id": org_id})

# Good - user_id is masked automatically
logger.warning("User not found", extra={"user_id": user_id})
```

### ❌ DON'T: Include sensitive data in message

```python
# Bad - exposes org_id in message
logger.info(f"Organization {org_id} created")

# Bad - exposes email in message
logger.info(f"User {email} logged in")

# Bad - exposes password in message
logger.info(f"Password reset for {password}")
```

### ✅ DO: Use generic error messages

```python
# Good - generic message, org_id in extra
logger.warning("Organization not found", extra={"org_id": org_id})

# Good - generic message, user_id in extra
logger.error("User authentication failed", extra={"user_id": user_id})
```

### ❌ DON'T: Expose details in error messages

```python
# Bad - exposes org_id
raise HTTPException(detail=f"Organization {org_id} not found")

# Bad - exposes email
raise HTTPException(detail=f"Email {email} already exists")
```

## Logging in Endpoints

### Pattern

```python
import logging
from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)

@router.post("/organizations")
async def create_organization(request: CreateOrgRequest):
    """Create organization."""
    try:
        # Log action with org_id in extra
        logger.info("Creating organization", extra={"org_id": request.org_id})
        
        # Do work...
        org = create_org(request)
        
        # Log success
        logger.info("Organization created successfully", extra={"org_id": org.org_id})
        
        return org
        
    except Exception as e:
        # Log error with org_id in extra, not in message
        logger.error("Failed to create organization", extra={"org_id": request.org_id})
        
        # Return generic error message
        raise HTTPException(
            status_code=500,
            detail="Failed to create organization"
        )
```

## Log Levels

| Level | When to Use | Example |
|-------|------------|---------|
| DEBUG | Detailed debugging info | Variable values, function entry/exit |
| INFO | Normal operation events | Organization created, user logged in |
| WARNING | Unusual but handled | Org not found, invalid input |
| ERROR | Failures requiring attention | Database error, API call failed |
| CRITICAL | System-wide failures | Database down, service unavailable |

## Log Format

All logs are JSON formatted for log aggregation:

```json
{
  "timestamp": "2026-02-09T06:23:37.123Z",
  "level": "INFO",
  "logger": "tenancy_service.api.organizations",
  "message": "Organization created successfully",
  "correlation_id": "req-abc123def456",
  "org_id": "ORG-12345678",
  "duration_ms": 45.2
}
```

## Correlation IDs

Every request gets a correlation ID for tracing:

```python
# Automatically set by middleware
correlation_id = request.headers.get("x-correlation-id")

# Included in all logs
logger.info("Processing request", extra={"correlation_id": correlation_id})

# Returned in response headers
response.headers["x-correlation-id"] = correlation_id
```

## Audit Logging

For compliance, audit important actions:

```python
from infrastructure.observability.logging import AuditLogger

audit = AuditLogger("tenancy_service")

# Log modification
audit.log_modification(
    actor_id="user-123",
    resource_type="organization",
    resource_id="ORG-12345678",
    action="create",
    changes={"name": "Acme Corp", "edition": "professional"}
)

# Log access
audit.log_access(
    actor_id="user-123",
    resource_type="organization",
    resource_id="ORG-12345678",
    action="view"
)
```

## Monitoring Logs

### Check for PII Leaks

```bash
# Search for exposed emails
grep -r "@" logs/ | grep -v "***EMAIL***"

# Search for exposed passwords
grep -r "password" logs/ | grep -v "***"

# Search for exposed tokens
grep -r "Bearer" logs/ | grep -v "***TOKEN***"
```

### View Logs

```bash
# Development (human readable)
tail -f logs/tenancy-service.log | jq .

# Production (JSON)
tail -f logs/tenancy-service.log
```

## Configuration

### Environment Variables

```bash
# Log level
OBSERVABILITY_LOG_LEVEL=INFO

# Log format (json or text)
OBSERVABILITY_LOG_FORMAT=json

# Enable PII masking
OBSERVABILITY_PII_MASKING_ENABLED=true

# Mask emails
OBSERVABILITY_MASK_EMAILS=true

# Mask IP addresses
OBSERVABILITY_MASK_IPS=false
```

## Compliance

This logging configuration complies with:
- ✅ GDPR - No personal data in logs
- ✅ SOC2 - Audit trail for all actions
- ✅ HIPAA - Sensitive data masked
- ✅ PCI DSS - No payment card data in logs

## Troubleshooting

### "Sensitive data in logs"

Check that you're using `extra` dict:

```python
# ❌ Bad
logger.info(f"User {email} created")

# ✅ Good
logger.info("User created", extra={"user_id": user_id})
```

### "Correlation ID not in logs"

Ensure middleware is configured:

```python
# In app/main.py
@app.middleware("http")
async def add_correlation_id(request: Request, call_next):
    correlation_id = request.headers.get("x-correlation-id") or generate_id()
    request.state.correlation_id = correlation_id
    # ... rest of middleware
```

### "Logs not being masked"

Verify PII masking is enabled:

```bash
OBSERVABILITY_PII_MASKING_ENABLED=true
```

## References

- [GDPR Logging Requirements](https://gdpr-info.eu/)
- [SOC2 Audit Logging](https://www.aicpa.org/soc2)
- [HIPAA Logging](https://www.hhs.gov/hipaa/)
- [Python Logging](https://docs.python.org/3/library/logging.html)
