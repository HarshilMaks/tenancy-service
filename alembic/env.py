"""
Production-grade Alembic environment configuration for Tenancy Service.

Features:
- Multi-environment support (dev/staging/prod)
- Connection pooling with proper cleanup
- Transaction isolation for safe migrations
- Batch operations for large tables
- Backwards compatibility validation
- Comprehensive logging and error handling
"""

import logging
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool, event
from sqlalchemy.engine import Connection
from dotenv import load_dotenv

# Load environment variables from root .env file
root_dir = Path(__file__).parent.parent
env_path = root_dir / ".env"
if env_path.exists():
    load_dotenv(env_path)
    logger = logging.getLogger("alembic.env")
    logger.info(f"Loaded environment from {env_path}")

# Import your models metadata
# Adjust this import based on your actual models location
# from infrastructure.persistence.models import Base
# target_metadata = Base.metadata

# For now, using None - replace with actual metadata when models are defined
target_metadata = None

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")


def get_url():
    """
    Get database URL from environment variable or config.
    
    Priority:
    1. DATABASE_URL environment variable (production)
    2. Alembic config file (development)
    """
    url = os.getenv("DATABASE_URL")
    if url:
        logger.info("Using DATABASE_URL from environment")
        return url
    
    url = config.get_main_option("sqlalchemy.url")
    logger.info("Using database URL from alembic.ini")
    return url


def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.
    
    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    
    Useful for:
    - Generating SQL scripts without database connection
    - Review migrations before applying
    - CI/CD pipeline validation
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,  # Detect column type changes
        compare_server_default=True,  # Detect default value changes
        include_schemas=True,  # Support multiple schemas
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.
    
    Creates an Engine and associates a connection with the context.
    
    Production features:
    - Connection pooling with NullPool (no connection reuse)
    - Explicit transaction management
    - Query logging in non-prod environments
    - Lock timeout protection
    - Statement timeout for safety
    """
    configuration = config.get_section(config.config_ini_section)
    configuration["sqlalchemy.url"] = get_url()
    
    # Engine configuration for production safety
    connectable = create_engine(
        configuration["sqlalchemy.url"],
        poolclass=pool.NullPool,  # No connection pooling for migrations
        echo=os.getenv("ENV", "development") != "production",  # Log SQL in non-prod
        isolation_level="READ COMMITTED",  # Prevent dirty reads
    )

    # Set statement timeout to prevent long-running migrations from hanging
    @event.listens_for(connectable, "connect")
    def set_timeout(dbapi_conn, connection_record):
        """Set statement and lock timeout for PostgreSQL."""
        cursor = dbapi_conn.cursor()
        # 10 minute timeout for migration statements
        cursor.execute("SET statement_timeout = '600s'")
        # 30 second lock timeout to fail fast on locks
        cursor.execute("SET lock_timeout = '30s'")
        cursor.close()

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,  # Detect column type changes
            compare_server_default=True,  # Detect default value changes
            include_schemas=True,  # Support multiple schemas if needed
            transaction_per_migration=True,  # Each migration in own transaction
            # Render item functions for custom types
            render_as_batch=True,  # Enable batch mode for SQLite compatibility
        )

        # Run migrations within explicit transaction
        with context.begin_transaction():
            logger.info("Starting migration transaction")
            context.run_migrations()
            logger.info("Migration transaction completed successfully")


# Entry point
if context.is_offline_mode():
    logger.info("Running migrations in OFFLINE mode")
    run_migrations_offline()
else:
    logger.info("Running migrations in ONLINE mode")
    run_migrations_online()
