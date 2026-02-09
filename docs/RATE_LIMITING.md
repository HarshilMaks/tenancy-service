# Rate Limiting Guide

## Overview

Rate limiting protects your API from DoS (Denial of Service) attacks by limiting requests per IP address.

## Configuration

### Environment Variables

```bash
# Enable/disable rate limiting
SERVICE_RATE_LIMIT_ENABLED=true

# Max requests per window
SERVICE_RATE_LIMIT_REQUESTS=100

# Time window in seconds
SERVICE_RATE_LIMIT_WINDOW=60
```

### Default Settings

- **Enabled**: `true`
- **Requests per window**: `100`
- **Window duration**: `60` seconds
- **Result**: 100 requests per minute per IP

## How It Works

1. **Track requests** by client IP address
2. **Count requests** in current time window
3. **Check limit** - if exceeded, return 429 (Too Many Requests)
4. **Add headers** - inform client of rate limit status

## Response Headers

When rate limited:

```
HTTP/1.1 429 Too Many Requests
Retry-After: 60
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1707464399
```

When not limited:

```
HTTP/1.1 200 OK
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1707464399
```

## Configuration Examples

### Development (Permissive)
```bash
SERVICE_RATE_LIMIT_ENABLED=true
SERVICE_RATE_LIMIT_REQUESTS=1000
SERVICE_RATE_LIMIT_WINDOW=60
```

### Production (Strict)
```bash
SERVICE_RATE_LIMIT_ENABLED=true
SERVICE_RATE_LIMIT_REQUESTS=100
SERVICE_RATE_LIMIT_WINDOW=60
```

### High-Traffic (Balanced)
```bash
SERVICE_RATE_LIMIT_ENABLED=true
SERVICE_RATE_LIMIT_REQUESTS=500
SERVICE_RATE_LIMIT_WINDOW=60
```

### Disabled (Not Recommended)
```bash
SERVICE_RATE_LIMIT_ENABLED=false
```

## Exemptions

These endpoints are **NOT** rate limited:
- `/health` - Health checks
- `/health/live` - Kubernetes liveness probe
- `/health/ready` - Kubernetes readiness probe

## Testing

### Test Rate Limiting

```bash
# Make 101 requests quickly
for i in {1..101}; do
  curl -s http://localhost:8000/api/v1/tenants \
    -H "Content-Type: application/json" \
    -d '{"name": "Test"}' \
    -w "Status: %{http_code}\n"
done

# First 100 should return 200/201
# 101st should return 429
```

### Check Rate Limit Headers

```bash
curl -i http://localhost:8000/api/v1/tenants

# Look for:
# X-RateLimit-Limit: 100
# X-RateLimit-Remaining: 99
# X-RateLimit-Reset: 1707464399
```

## Client Handling

### Retry Logic

```python
import time
import requests

def call_api_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url)
        
        if response.status_code == 429:
            # Rate limited - wait and retry
            retry_after = int(response.headers.get("Retry-After", 60))
            print(f"Rate limited. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            continue
        
        return response
    
    raise Exception("Max retries exceeded")
```

### Check Remaining Requests

```python
response = requests.get(url)
remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
limit = int(response.headers.get("X-RateLimit-Limit", 0))

print(f"Requests remaining: {remaining}/{limit}")

if remaining < 10:
    print("Warning: Approaching rate limit")
```

## Monitoring

### Log Rate Limit Violations

```bash
# Search logs for rate limit exceeded
grep "Rate limit exceeded" logs/tenancy-service.log

# Output:
# {
#   "level": "WARNING",
#   "message": "Rate limit exceeded",
#   "client_ip": "192.168.1.100",
#   "requests": 100,
#   "limit": 100,
#   "path": "/api/v1/tenants"
# }
```

### Metrics

Track rate limit violations:

```bash
# Prometheus metric
rate_limit_violations_total{endpoint="/api/v1/tenants"}
```

## Security Considerations

### IP Spoofing

Rate limiting uses client IP from request. Behind a proxy, ensure:

```python
# In main.py
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["trusted-proxy-ip"]
)
```

### Distributed Attacks

Single-machine rate limiting won't stop distributed attacks. For production:

1. **Use Redis** for distributed rate limiting
2. **Use API Gateway** (AWS API Gateway, Kong, etc.)
3. **Use WAF** (Web Application Firewall)

### Legitimate Traffic

Adjust limits based on:
- Expected request volume
- API complexity
- User base size
- Business requirements

## Troubleshooting

### "Rate limit exceeded" for legitimate traffic

**Solution**: Increase limits

```bash
SERVICE_RATE_LIMIT_REQUESTS=500
SERVICE_RATE_LIMIT_WINDOW=60
```

### Rate limiting not working

**Check**:
1. `SERVICE_RATE_LIMIT_ENABLED=true`
2. Middleware is registered in `app/main.py`
3. Check logs for rate limit violations

### Different limits per endpoint

**Solution**: Use API Gateway or WAF for per-endpoint limits

## Production Checklist

- [ ] Rate limiting enabled
- [ ] Limits set appropriately for traffic
- [ ] Health checks exempted
- [ ] Monitoring configured
- [ ] Client retry logic implemented
- [ ] Logs monitored for violations
- [ ] Tested with load testing tool

## References

- [RFC 6585 - HTTP 429](https://tools.ietf.org/html/rfc6585)
- [OWASP - DoS Protection](https://owasp.org/www-community/attacks/Denial_of_Service)
- [FastAPI - Middleware](https://fastapi.tiangolo.com/tutorial/middleware/)
