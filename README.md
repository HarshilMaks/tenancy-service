## Tenancy Service

A Multi-Tenant Organization Management Service built with FastAPI and Clean Architecture principles. This service provides comprehensive tenant lifecycle management with enterprise-level observability, monitoring, and compliance features.

## Overview

The Tenancy Service manages organization lifecycle operations including creation, suspension, policy enforcement, and billing management. It implements Domain-Driven Design patterns with extensive logging, metrics collection, and distributed tracing for production environments.

### Key Features

- **Multi-tenant Organization Management**: Complete CRUD operations for tenant organizations
- **Edition-based Feature Gating**: Granular control over features per subscription tier
- **Production Observability**: Comprehensive logging, metrics, and distributed tracing
- **Clean Architecture**: Domain-driven design with clear separation of concerns
- **Type Safety**: Full type hints with Pydantic validation
- **Event-Driven Architecture**: Asynchronous event publishing for decoupled operations
- **Health Monitoring**: Kubernetes-ready health checks and dependency monitoring
- **Compliance Ready**: PII masking, audit logging, and GDPR compliance features

## Architecture

### 8-Layer Clean Architecture

```
FRONTEND (Browser)
    ↓
LAYER 1: ENTRY POINT (app/main.py)
    - FastAPI server startup
    - Middleware configuration
    - Route registration
    ↓
LAYER 2: API ROUTES (app/api/*/routes.py)
    - HTTP endpoints (GET, POST, PUT, DELETE)
    - Input validation (Pydantic schemas)
    - Response formatting
    ↓
LAYER 3: USE CASES (app/business/use_cases/*.py)
    - Business logic orchestration
    - Repository calls
    - Event publishing
    ↓
LAYER 4: DOMAIN LAYER (app/business/domain/*)
    - Business entities (Tenant)
    - Business rules (invariants)
    - State machine (lifecycle)
    ↓
LAYER 5: STATE MACHINE (lifecycle.py)
    - Valid state transitions
    - Lifecycle management
    - State rules enforcement
    ↓
LAYER 6: REPOSITORY (tenant_repository.py)
    - Database operations
    - Save/load data
    - Query methods
    ↓
LAYER 7: DATABASE (domain_models.py)
    - SQLAlchemy models
    - Table definitions
    - Constraints & indexes
    ↓
PostgreSQL Database
    - tenants table (15 columns)
    - tenant_events table (8 columns)
    - alembic_version table (1 column)
    ↓
LAYER 8: EVENTS (tenant_events.py)
    - Domain events
    - Event publishing
    - Event storage
    ↓
OTHER SYSTEMS
    - Billing system
    - Email service
    - Analytics
    - Notifications
```

### Architecture Principles

1. **Separation of Concerns** - Each layer has ONE responsibility
2. **Testability** - Can test each layer independently
3. **Maintainability** - Business rules in one place
4. **Scalability** - Can replace layers without changing others
5. **Reusability** - Same use case from HTTP, CLI, message queue

### Request Flow Example

```
POST /api/v1/tenants { "name": "Acme", "edition": "professional" }
    ↓
API validates input (Pydantic schema)
    ↓
Use case: CreateTenantUseCase.execute()
    - Validates inputs
    - Checks uniqueness
    - Creates domain object
    ↓
Domain: Tenant entity
    - Enforces invariants
    - Validates business rules
    ↓
State Machine: OrganizationLifecycle
    - Validates state transitions
    - Ensures PROVISIONING → TRIAL is valid
    ↓
Repository: TenantRepository.save()
    - Converts domain object to database model
    - Executes INSERT SQL
    ↓
Database: PostgreSQL
    - Stores in tenants table
    - Returns saved record
    ↓
Events: TenantCreatedEvent
    - Published to event bus
    - Stored in tenant_events table
    - Other systems listen and react
    ↓
Response: HTTP 201 Created
{
  "id": "uuid-123",
  "external_id": "ORG-E4900E20",
  "name": "Acme",
  "edition": "professional",
  "status": "PROVISIONING"
}
```

### Layer Details

**LAYER 1: ENTRY POINT (app/main.py)**
- Creates FastAPI application
- Configures middleware (CORS, tracing, metrics, correlation ID)
- Registers all API routes
- Handles startup/shutdown lifecycle
- Impact: Without this → No API, no way to call service

**LAYER 2: API ROUTES (app/api/*/routes.py)**
- Defines HTTP endpoints (GET, POST, PUT, DELETE)
- Validates input using Pydantic schemas
- Calls use cases with validated data
- Formats and returns responses
- Impact: Without this → No way to interact with service

**LAYER 3: USE CASES (app/business/use_cases/*.py)**
- Implements business logic orchestration
- Validates business rules
- Calls repositories to save data
- Publishes domain events
- Impact: Without this → Business logic scattered everywhere

**LAYER 4: DOMAIN LAYER (app/business/domain/*)**
- Defines business entities (Tenant)
- Enforces business rules (invariants)
- Manages state transitions
- Validates domain constraints
- Impact: Without this → Business rules scattered, easy to break

**LAYER 5: STATE MACHINE (lifecycle.py)**
- Defines valid state transitions
- Manages organization lifecycle
- Enforces state machine rules
- Prevents invalid transitions
- Impact: Without this → Invalid states possible

**LAYER 6: REPOSITORY (tenant_repository.py)**
- Saves/loads data from database
- Abstracts database details
- Provides query methods
- Converts between domain and database models
- Impact: Without this → Database code scattered in use cases

**LAYER 7: DATABASE (domain_models.py)**
- Defines SQLAlchemy models
- Maps to database tables
- Enforces database constraints
- Manages relationships
- Impact: Without this → No persistent storage

**LAYER 8: EVENTS (tenant_events.py)**
- Defines domain events
- Publishes events when things happen
- Other systems listen and react
- Enables loose coupling
- Impact: Without this → Systems tightly coupled

## System Flow

```mermaid
sequenceDiagram
    participant C as Client
    participant API as API Layer
    participant APP as Application Layer
    participant DOM as Domain Layer
    participant INFRA as Infrastructure Layer
    participant DB as Database
    participant EVENTS as Event Bus
    
    C->>API: POST /organizations
    API->>API: Validate Request
    API->>APP: Execute Use Case
    
    APP->>DOM: Validate Business Rules
    DOM->>APP: Return Validation Result
    
    APP->>DOM: Create Organization
    DOM->>APP: Return Domain Object
    
    APP->>INFRA: Save via Repository
    INFRA->>DB: Persist Data
    DB->>INFRA: Confirm Save
    INFRA->>APP: Return Saved Object
    
    APP->>INFRA: Publish Events
    INFRA->>EVENTS: Send Domain Events
    EVENTS->>INFRA: Acknowledge
    
    APP->>API: Return Response
    API->>C: HTTP 201 Created
    
    Note over API,EVENTS: All operations include logging, metrics, and tracing
```

## Project Structure

The service follows Clean Architecture principles with clear layer separation:

- **app/**: FastAPI application entry point and REST API endpoints
- **services/**: Use cases and business orchestration logic (formerly application/)
- **domain/**: Core business logic, entities, and domain rules
- **infrastructure/**: External adapters for persistence, events, and observability
- **events/**: Domain event definitions and handlers
- **tests/**: Comprehensive test suite with unit and integration tests

## Getting Started

### Prerequisites

- Python 3.12+ ✅
- PostgreSQL 14+ ✅ (Currently: Neon PostgreSQL 17.7)
- uv package manager ✅

**✅ Current Environment:**
- Python 3.12 with virtual environment active
- Neon PostgreSQL cloud database connected
- All dependencies installed and working
- Database schema migrated and ready

### Installation

Clone the repository and install dependencies:

```bash
git clone <repository-url>
cd tenancy_service
make install
```

### Local Development Setup

1. **Create `.env.local` with your local secrets:**

```bash
# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/tenancy_service

# Redis
REDIS_URL=redis://localhost:6379

# Security (generate with: python -c "import secrets; print(secrets.token_urlsafe(32))")
SECRET_KEY=your_secret_key_minimum_32_characters_long_here
JWT_SECRET=your_jwt_secret_minimum_32_characters_long_here

# RabbitMQ (if using)
MESSAGING_RABBITMQ_PASSWORD=your_rabbitmq_password
```

2. **Start development server:**

```bash
make dev
```

The app automatically loads `.env.local` (not committed to git).

### Configuration

The service uses environment variables for configuration:

**Development (`.env` - committed to git)**
- Public configuration only
- No secrets or credentials

**Local Development (`.env.local` - NOT committed)**
- Your local secrets
- Copy template from above
- Never commit this file

#### Database Configuration

The service supports both DATABASE_URL (recommended) and individual database settings:

**Option 1: DATABASE_URL (Recommended for cloud databases)**
```bash
# .env.local
DATABASE_URL=postgresql://user:pass@host:port/dbname?sslmode=require
```

**Option 2: Individual settings**
```bash
# .env.local
DATABASE_HOST=localhost
DATABASE_PORT=5432
DATABASE_NAME=tenancy_service
DATABASE_USER=postgres
DATABASE_PASSWORD=your_password
```

**✅ Current Setup: Neon PostgreSQL**
- ✅ Cloud-hosted PostgreSQL with CONNECTION pooling
- ✅ DATABASE_URL configuration active
- ✅ SSL enabled with proper certificates
- ✅ Optimized for Neon-specific connection handling

Key configuration sections:
- Database connection (DATABASE_URL or individual settings)
- Observability endpoints (metrics, tracing, logging)
- Security configuration (CORS, API keys)
- Feature flags and environment settings

### Database Setup

**🎯 Database Status: ✅ READY**

The database is fully configured and running:

```bash
# Check current migration status
alembic current

# Apply any pending migrations
alembic upgrade head

# For fresh setup (if needed)
make db-setup
```

**Current Schema:**
- ✅ Tables: `tenants`, `tenant_events`, `alembic_version`
- ✅ Enum types: `tenant_status`, `plan_tier`
- ✅ Indexes: 13 performance indexes
- ✅ Functions & Triggers: Auto-timestamps and sequences
- ✅ Constraints: Business rule validation at DB level

### Development Server

Start the development server with hot reload:

```bash
make dev
```

The API will be available at http://localhost:8000 with automatic documentation at /docs.

## Current Status

**🚀 FULLY OPERATIONAL TENANCY SERVICE**

This service is production-ready and fully functional:

| Feature | Status | Description |
|---------|--------|-------------|
| 🌐 **API Layer** | ✅ **READY** | FastAPI with validation, docs, health checks |
| 🧠 **Domain Logic** | ✅ **COMPLETE** | Salesforce-style organization management |
| 🗄️ **Database** | ✅ **RUNNING** | Neon PostgreSQL with full schema |
| 🔄 **Migrations** | ✅ **APPLIED** | Alembic v001_initial successfully |
| ⚡ **Performance** | ✅ **OPTIMIZED** | Connection pooling, indexes, triggers |
| 📊 **Observability** | ✅ **CONFIGURED** | Logging, metrics, tracing ready |
| 🛡️ **Security** | ✅ **ENABLED** | SSL, PII masking, audit trails |

**Test the running system:**
```bash
# Start development server
make dev

# Test health endpoint
curl http://localhost:8000/health

# View API documentation
open http://localhost:8000/docs

# Create test organization
curl -X POST http://localhost:8000/organizations \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Corp", "edition": "professional", "region": "us-east-1"}'
```

## Development Workflow

### Available Commands

The project includes a comprehensive Makefile with development commands:

- **make install**: Install all dependencies
- **make dev**: Start development server
- **make test**: Run test suite
- **make lint**: Run code quality checks
- **make db-setup**: Initialize database
- **make db-migrate**: Run database migrations
- **make clean**: Clean build artifacts

### Code Quality

The project enforces high code quality standards:

- **Type Checking**: mypy for static type analysis
- **Code Formatting**: black and isort for consistent formatting
- **Linting**: flake8 for code quality checks
- **Testing**: pytest with coverage reporting

### Testing

Run the comprehensive test suite:

```bash
make test
```

Tests include:
- Unit tests for domain logic
- Integration tests for repository operations
- API endpoint testing
- Performance and load testing

## Production Deployment

### Health Checks

The service includes comprehensive health monitoring:

- **/health/live**: Kubernetes liveness probe
- **/health/ready**: Kubernetes readiness probe  
- **/health/startup**: Kubernetes startup probe
- **/health/dependencies**: Dependency health status

### Observability

Built-in production observability features:

- **Structured Logging**: JSON format with correlation IDs and PII masking
- **Metrics Collection**: Prometheus-compatible metrics for requests, business KPIs, and system health
- **Distributed Tracing**: OpenTelemetry spans for request flow visualization
- **Health Monitoring**: Dependency checks and system health aggregation

### Security

Production security features:

- **PII Masking**: Automatic masking of sensitive data in logs
- **Audit Logging**: Comprehensive audit trail for compliance
- **Request Validation**: Pydantic-based input validation
- **CORS Configuration**: Configurable cross-origin request handling

## API Documentation

### Core Endpoints

- **POST /organizations**: Create new organization
- **GET /organizations/{id}**: Retrieve organization details
- **PUT /organizations/{id}/suspend**: Suspend organization
- **PUT /organizations/{id}/activate**: Activate organization
- **POST /organizations/{id}/policies**: Enforce organization policies

### Authentication

The service integrates with external authentication systems and supports:

- Bearer token authentication
- Request correlation tracking
- Audit logging for security events

## Contributing

### Development Standards

- Follow Clean Architecture principles
- Implement comprehensive test coverage
- Use type hints throughout
- Include detailed logging and error handling
- Follow domain-driven design patterns

### Code Review Process

1. Create feature branch from main
2. Implement changes with tests
3. Run quality checks locally
4. Submit pull request with description
5. Address review feedback
6. Merge after approval

## License

This project is licensed under the MIT License. See LICENSE file for details.

## Support

For questions, issues, or contributions:

- Create GitHub issues for bug reports
- Submit pull requests for enhancements
- Review documentation in /docs directory
- Check health endpoints for system status
