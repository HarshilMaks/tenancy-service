# Security Configuration Guide

## Secrets Management

### ⚠️ CRITICAL: Never Commit Secrets to Git

All sensitive credentials must be managed through environment variables, never hardcoded in version control.

### Environment Files

**`.env`** (Committed to Git)
- ✅ Public configuration only
- ✅ No secrets or credentials
- ✅ Default values for non-sensitive settings
- ✅ Safe to share

**`.env.local`** (NOT Committed - in .gitignore)
- ❌ Never commit this file
- ✅ Local development secrets only
- ✅ Copy from `.env.local.example`
- ✅ Each developer has their own

### Setup for Local Development

1. Copy the template:
```bash
cp .env.local.example .env.local
```

2. Fill in your local secrets:
```bash
# Generate secrets
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Edit .env.local with your values
SECRET_KEY=your_generated_secret_here
JWT_SECRET=your_generated_jwt_secret_here
DATABASE_URL=your_local_database_url
REDIS_URL=your_local_redis_url
```

3. Load environment:
```bash
# The app automatically loads .env.local if it exists
make dev
```

### Production Deployment

For production, set secrets via:

**Option 1: Environment Variables**
```bash
export SECRET_KEY="production_secret_key_here"
export JWT_SECRET="production_jwt_secret_here"
export DATABASE_URL="production_database_url"
export REDIS_URL="production_redis_url"
```

**Option 2: Kubernetes Secrets**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: tenancy-service-secrets
type: Opaque
stringData:
  SECRET_KEY: "production_secret_key"
  JWT_SECRET: "production_jwt_secret"
  DATABASE_URL: "production_database_url"
  REDIS_URL: "production_redis_url"
```

**Option 3: AWS Secrets Manager**
```bash
aws secretsmanager create-secret \
  --name tenancy-service/secrets \
  --secret-string '{
    "SECRET_KEY": "...",
    "JWT_SECRET": "...",
    "DATABASE_URL": "...",
    "REDIS_URL": "..."
  }'
```

## Required Secrets

### SECRET_KEY
- **Purpose**: Encryption key for sensitive data
- **Length**: Minimum 32 characters
- **Generate**: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- **Rotation**: Change periodically in production

### JWT_SECRET
- **Purpose**: JWT token signing
- **Length**: Minimum 32 characters
- **Generate**: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- **Rotation**: Change periodically, invalidates existing tokens

### DATABASE_URL
- **Format**: `postgresql://user:password@host:port/dbname?sslmode=require`
- **Security**: Always use SSL in production
- **Rotation**: Change password periodically

### REDIS_URL
- **Format**: `redis://default:password@host:port`
- **Security**: Use strong passwords
- **Rotation**: Change password periodically

### MESSAGING_RABBITMQ_PASSWORD
- **Purpose**: RabbitMQ authentication
- **Security**: Use strong passwords
- **Rotation**: Change password periodically

## Security Best Practices

### 1. Secret Generation
```bash
# Generate cryptographically secure secrets
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Or use OpenSSL
openssl rand -base64 32
```

### 2. Secret Rotation
- Rotate secrets every 90 days in production
- Update all services simultaneously
- Use blue-green deployment for zero downtime

### 3. Access Control
- Limit who can access production secrets
- Use IAM roles for service-to-service auth
- Audit all secret access

### 4. Monitoring
- Alert on failed authentication attempts
- Monitor secret access patterns
- Log all secret changes

### 5. Backup & Recovery
- Backup secrets securely
- Test recovery procedures
- Keep backups encrypted

## Validation

The application validates secrets on startup:

```python
@field_validator("secret_key", "jwt_secret")
@classmethod
def check_secrets(cls, v: str) -> str:
    """Ensure secrets are set."""
    if not v:
        raise ValueError("Secrets must be set in environment variables")
    if len(v) < 32:
        raise ValueError("Secrets must be at least 32 characters long")
    return v
```

If secrets are missing or invalid, the application will fail to start with a clear error message.

## Troubleshooting

### "Secrets must be set in environment variables"
- Check `.env.local` exists and is loaded
- Verify `SECRET_KEY` and `JWT_SECRET` are set
- Ensure values are at least 32 characters

### "Secrets must be at least 32 characters long"
- Generate new secrets: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
- Update `.env.local` with new values

### "Database connection failed"
- Verify `DATABASE_URL` is correct
- Check database is running and accessible
- Ensure SSL certificates are valid (if using SSL)

## Compliance

This configuration follows:
- ✅ 12-Factor App principles
- ✅ OWASP secret management guidelines
- ✅ PCI DSS requirements
- ✅ GDPR data protection standards

## References

- [12-Factor App - Config](https://12factor.net/config)
- [OWASP - Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [Python Secrets Module](https://docs.python.org/3/library/secrets.html)
