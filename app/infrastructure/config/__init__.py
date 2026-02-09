"""Configuration Module

Handles all application configuration including environment variables, settings,
database configuration, and feature flags.

Example:
    >>> from app.infrastructure.config import get_settings
    >>> settings = get_settings()
    >>> db_url = settings.database_url
"""

from .settings import (
    get_settings,
    clear_settings,
    get_environment,
    is_production,
    is_development,
    is_testing,
    Settings,
    DatabaseSettings,
    RedisSettings,
    ObservabilitySettings,
    MessagingSettings,
    ServiceSettings,
    TenantSettings,
)

__all__ = [
    "get_settings",
    "clear_settings",
    "get_environment",
    "is_production",
    "is_development",
    "is_testing",
    "Settings",
    "DatabaseSettings",
    "RedisSettings",
    "ObservabilitySettings",
    "MessagingSettings",
    "ServiceSettings",
    "TenantSettings",
]
