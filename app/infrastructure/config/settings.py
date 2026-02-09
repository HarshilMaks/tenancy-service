"""
Configuration Module - 12-Factor App Configuration
===================================================

Centralized configuration management following 12-factor app principles.
All configuration is loaded from environment variables.

Features:
    - Type-safe configuration with Pydantic
    - Environment-specific defaults
    - Secret masking in logs
    - Validation on startup
    - Singleton pattern

Configuration Sources (in priority order):
    1. Environment variables
    2. .env file (development only)
    3. Default values

Author: Platform Engineering Team
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# Environment Detection
# =============================================================================

def get_environment() -> str:
    """Detect current environment."""
    return os.environ.get("ENVIRONMENT", "development").lower()


def is_production() -> bool:
    """Check if running in production."""
    return get_environment() == "production"


def is_development() -> bool:
    """Check if running in development."""
    return get_environment() == "development"


def is_testing() -> bool:
    """Check if running in test mode."""
    return get_environment() == "testing" or os.environ.get("TESTING", "").lower() == "true"


# =============================================================================
# Database Settings
# =============================================================================

class DatabaseSettings(BaseSettings):
    """Database connection configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="DATABASE_",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Primary connection URL (takes precedence if set)
    url_override: Optional[str] = Field(default=None, alias="DATABASE_URL", description="Complete database URL (overrides individual settings)")
    
    # Individual connection parameters (fallback when URL not provided)
    host: str = Field(default="localhost", description="Database host")
    port: int = Field(default=5432, description="Database port")
    name: str = Field(default="tenancy_service", description="Database name")
    user: str = Field(default="postgres", description="Database user")
    password: str = Field(default=None, description="Database password - MUST be set in .env or DATABASE_PASSWORD")
    
    # Connection pool
    pool_size: int = Field(default=10, description="Connection pool size")
    max_overflow: int = Field(default=20, description="Max pool overflow")
    pool_timeout: int = Field(default=30, description="Pool timeout seconds")
    pool_recycle: int = Field(default=1800, description="Connection recycle seconds")
    
    # SSL
    ssl_mode: str = Field(default="prefer", description="SSL mode")
    ssl_cert_path: Optional[str] = Field(default=None, description="SSL cert path")
    
    # Query settings
    echo: bool = Field(default=False, description="Echo SQL queries")
    statement_timeout_ms: int = Field(default=30000, description="Statement timeout")
    
    @property
    def url(self) -> str:
        """Build SQLAlchemy database URL - uses DATABASE_URL if provided, otherwise builds from components."""
        if self.url_override:
            return self.url_override
        return (
            f"postgresql://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )
    
    @property
    def async_url(self) -> str:
        """Build async SQLAlchemy database URL."""
        if self.url_override:
            # Convert postgresql:// to postgresql+asyncpg://
            return self.url_override.replace("postgresql://", "postgresql+asyncpg://", 1)
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )
    
    @property
    def url_masked(self) -> str:
        """URL with password masked for logging."""
        if self.url_override:
            # Mask password in URL
            import re
            return re.sub(r'://([^:]+):([^@]+)@', r'://\1:***@', self.url_override)
        return (
            f"postgresql://{self.user}:***"
            f"@{self.host}:{self.port}/{self.name}"
        )


# =============================================================================
# Redis Settings
# =============================================================================

class RedisSettings(BaseSettings):
    """Redis connection configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        case_sensitive=False,
    )
    
    host: str = Field(default="localhost", description="Redis host")
    port: int = Field(default=6379, description="Redis port")
    password: Optional[str] = Field(default=None, description="Redis password")
    db: int = Field(default=0, description="Redis database number")
    ssl: bool = Field(default=False, description="Enable SSL")
    
    # Connection pool
    max_connections: int = Field(default=50, description="Max connections")
    socket_timeout: float = Field(default=5.0, description="Socket timeout")
    
    @property
    def url(self) -> str:
        """Build Redis URL."""
        auth = f":{self.password}@" if self.password else ""
        scheme = "rediss" if self.ssl else "redis"
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.db}"
    
    @property
    def url_masked(self) -> str:
        """URL with password masked for logging."""
        auth = ":***@" if self.password else ""
        scheme = "rediss" if self.ssl else "redis"
        return f"{scheme}://{auth}{self.host}:{self.port}/{self.db}"


# =============================================================================
# Observability Settings
# =============================================================================

class ObservabilitySettings(BaseSettings):
    """Logging, metrics, and tracing configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="OBSERVABILITY_",
        case_sensitive=False,
    )
    
    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_format: str = Field(default="json", description="Log format (json/text)")
    log_pii_masking: bool = Field(default=True, description="Mask PII in logs")
    
    # Metrics
    metrics_enabled: bool = Field(default=True, description="Enable metrics")
    metrics_port: int = Field(default=9090, description="Metrics server port")
    
    # Tracing
    tracing_enabled: bool = Field(default=True, description="Enable tracing")
    tracing_sample_rate: float = Field(default=1.0, description="Trace sample rate")
    tracing_endpoint: Optional[str] = Field(default=None, description="OTLP endpoint")
    
    # Health checks
    health_check_interval: int = Field(default=30, description="Health check interval")


# =============================================================================
# Messaging Settings
# =============================================================================

class MessagingSettings(BaseSettings):
    """Message broker configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="MESSAGING_",
        case_sensitive=False,
    )
    
    # Broker type
    broker_type: str = Field(default="memory", description="Broker type (memory/rabbitmq/kafka)")
    
    # RabbitMQ
    rabbitmq_host: str = Field(default="localhost", description="RabbitMQ host")
    rabbitmq_port: int = Field(default=5672, description="RabbitMQ port")
    rabbitmq_user: str = Field(default="guest", description="RabbitMQ user")
    rabbitmq_password: str = Field(default=None, description="RabbitMQ password - MUST be set in .env or MESSAGING_RABBITMQ_PASSWORD")
    rabbitmq_vhost: str = Field(default="/", description="RabbitMQ vhost")
    
    # Kafka
    kafka_bootstrap_servers: str = Field(default="localhost:9092", description="Kafka servers")
    kafka_group_id: str = Field(default="tenancy-service", description="Kafka consumer group")
    
    @property
    def rabbitmq_url(self) -> str:
        """Build RabbitMQ URL."""
        return (
            f"amqp://{self.rabbitmq_user}:{self.rabbitmq_password}"
            f"@{self.rabbitmq_host}:{self.rabbitmq_port}/{self.rabbitmq_vhost}"
        )


# =============================================================================
# Service Settings
# =============================================================================

class ServiceSettings(BaseSettings):
    """Service-specific configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="SERVICE_",
        case_sensitive=False,
    )
    
    name: str = Field(default="tenancy_service", description="Service name")
    version: str = Field(default="1.0.0", description="Service version")
    environment: str = Field(default="development", description="Environment")
    debug: bool = Field(default=False, description="Debug mode")
    
    # API
    api_host: str = Field(default="0.0.0.0", description="API host")
    api_port: int = Field(default=8000, description="API port")
    api_prefix: str = Field(default="/api/v1", description="API prefix")
    
    # Workers
    workers: int = Field(default=4, description="Worker count")
    
    # CORS
    cors_origins: str = Field(default="*", description="CORS origins (comma-separated)")
    cors_allow_headers: str = Field(
        default="Content-Type,Authorization,X-Correlation-ID,X-Request-ID",
        description="CORS allowed headers (comma-separated)"
    )
    cors_allow_methods: str = Field(
        default="GET,POST,PUT,DELETE,OPTIONS",
        description="CORS allowed methods (comma-separated)"
    )
    cors_allow_credentials: bool = Field(default=True, description="Allow credentials in CORS")
    cors_max_age: int = Field(default=600, description="CORS max age in seconds")
    
    # Security
    allowed_hosts: str = Field(default="*", description="Allowed hosts (comma-separated)")
    
    # Rate limiting
    rate_limit_enabled: bool = Field(default=True, description="Enable rate limiting")
    rate_limit_requests: int = Field(default=100, description="Requests per window")
    rate_limit_window: int = Field(default=60, description="Rate limit window (seconds)")
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins into list."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def cors_allow_headers_list(self) -> List[str]:
        """Parse CORS allowed headers into list."""
        return [header.strip() for header in self.cors_allow_headers.split(",")]
    
    @property
    def cors_allow_methods_list(self) -> List[str]:
        """Parse CORS allowed methods into list."""
        return [method.strip() for method in self.cors_allow_methods.split(",")]
    
    @property
    def allowed_hosts_list(self) -> List[str]:
        """Parse allowed hosts into list."""
        if self.allowed_hosts == "*":
            return ["*"]
        return [host.strip() for host in self.allowed_hosts.split(",")]


# =============================================================================
# Tenant Settings
# =============================================================================

class TenantSettings(BaseSettings):
    """Tenant/organization specific configuration."""
    
    model_config = SettingsConfigDict(
        env_prefix="TENANT_",
        case_sensitive=False,
    )
    
    # Trial settings
    default_trial_days: int = Field(default=14, description="Default trial duration")
    trial_extension_days: int = Field(default=7, description="Trial extension days")
    max_trial_extensions: int = Field(default=2, description="Max trial extensions")
    
    # Retention
    data_retention_days: int = Field(default=90, description="Data retention after termination")
    hard_delete_after_days: int = Field(default=90, description="Hard delete after termination")
    
    # Limits
    max_name_length: int = Field(default=255, description="Max organization name length")
    max_users_free: int = Field(default=5, description="Max users for free tier")
    max_sandboxes: int = Field(default=10, description="Max sandbox orgs per production")


# =============================================================================
# Main Settings
# =============================================================================

class Settings(BaseSettings):
    """
    Main application settings.
    
    Aggregates all configuration sections.
    
    Usage:
        >>> settings = get_settings()
        >>> print(settings.database.url_masked)
        >>> print(settings.service.name)
    """
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Sub-configurations
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    messaging: MessagingSettings = Field(default_factory=MessagingSettings)
    service: ServiceSettings = Field(default_factory=ServiceSettings)
    tenant: TenantSettings = Field(default_factory=TenantSettings)
    
    # Security - MUST be set in environment variables
    secret_key: str = Field(
        default=None,
        description="Secret key for encryption - MUST be set in .env or SECRET_KEY"
    )
    jwt_secret: str = Field(
        default=None,
        description="JWT signing secret - MUST be set in .env or JWT_SECRET"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiration_minutes: int = Field(default=30, description="JWT expiration")
    
    @field_validator("secret_key", "jwt_secret")
    @classmethod
    def check_secrets(cls, v: str) -> str:
        """Ensure secrets are set."""
        if not v:
            raise ValueError("Secrets must be set in environment variables (.env or SECRET_KEY/JWT_SECRET)")
        if len(v) < 32:
            raise ValueError("Secrets must be at least 32 characters long")
        return v
    
    def to_safe_dict(self) -> Dict[str, Any]:
        """Export settings with secrets masked."""
        return {
            "service": {
                "name": self.service.name,
                "version": self.service.version,
                "environment": self.service.environment,
                "debug": self.service.debug,
            },
            "database": {
                "host": self.database.host,
                "port": self.database.port,
                "name": self.database.name,
                "pool_size": self.database.pool_size,
            },
            "redis": {
                "host": self.redis.host,
                "port": self.redis.port,
                "db": self.redis.db,
            },
            "observability": {
                "log_level": self.observability.log_level,
                "metrics_enabled": self.observability.metrics_enabled,
                "tracing_enabled": self.observability.tracing_enabled,
            },
        }


# =============================================================================
# Settings Factory
# =============================================================================

@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Settings are loaded once and cached for performance.
    Call clear_settings() to reload.
    
    Returns:
        Settings instance
    """
    # Load .env file explicitly to ensure DATABASE_URL is available
    from dotenv import load_dotenv
    load_dotenv()
    
    return Settings()


def clear_settings() -> None:
    """Clear cached settings (for testing)."""
    get_settings.cache_clear()


# =============================================================================
# Convenience Accessors
# =============================================================================

def get_database_settings() -> DatabaseSettings:
    """Get database settings."""
    return get_settings().database


def get_redis_settings() -> RedisSettings:
    """Get Redis settings."""
    return get_settings().redis


def get_observability_settings() -> ObservabilitySettings:
    """Get observability settings."""
    return get_settings().observability


def get_service_settings() -> ServiceSettings:
    """Get service settings."""
    return get_settings().service


def get_tenant_settings() -> TenantSettings:
    """Get tenant settings."""
    return get_settings().tenant


__all__ = [
    # Environment
    "get_environment",
    "is_production",
    "is_development",
    "is_testing",
    
    # Settings classes
    "Settings",
    "DatabaseSettings",
    "RedisSettings",
    "ObservabilitySettings",
    "MessagingSettings",
    "ServiceSettings",
    "TenantSettings",
    
    # Factory
    "get_settings",
    "clear_settings",
    
    # Convenience
    "get_database_settings",
    "get_redis_settings",
    "get_observability_settings",
    "get_service_settings",
    "get_tenant_settings",
]
