"""
Database Module - SQLAlchemy Connection Management
===================================================

Production-grade database connectivity with:
- Connection pooling
- Automatic reconnection
- Transaction management
- Health monitoring
- Query instrumentation

Design Principles:
    - Session-per-request pattern
    - Connection pool management
    - Graceful degradation
    - Observable queries

Author: Platform Engineering Team
"""

from __future__ import annotations

import contextlib
import time
from typing import Any, Callable, Generator, Optional

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool

from infrastructure.config import get_database_settings, DatabaseSettings
from infrastructure.observability.logging import get_logger, LogContext
from infrastructure.observability.metrics import get_metrics, track_database_operation
from infrastructure.observability.tracing import create_span, SpanKind

logger = get_logger(__name__)


# =============================================================================
# Database Manager
# =============================================================================

class DatabaseManager:
    """
    Manages database connections and sessions.
    
    Features:
        - Connection pooling with configurable limits
        - Automatic reconnection on failure
        - Query timing and logging
        - Health checking
        - Transaction helpers
    
    Usage:
        >>> db = DatabaseManager()
        >>> with db.session() as session:
        ...     result = session.query(Organization).all()
    """
    
    def __init__(
        self,
        settings: Optional[DatabaseSettings] = None,
    ):
        self._settings = settings or get_database_settings()
        self._engine: Optional[Engine] = None
        self._session_factory: Optional[sessionmaker] = None
        self._initialized = False
        
        logger.info(
            "Database manager created",
            host=self._settings.host,
            port=self._settings.port,
            database=self._settings.name,
            pool_size=self._settings.pool_size,
        )
    
    @property
    def engine(self) -> Engine:
        """Get or create database engine."""
        if self._engine is None:
            self._initialize()
        return self._engine
    
    @property
    def session_factory(self) -> sessionmaker:
        """Get or create session factory."""
        if self._session_factory is None:
            self._initialize()
        return self._session_factory
    
    def _initialize(self) -> None:
        """Initialize database connection."""
        if self._initialized:
            return
        
        with LogContext() as ctx:
            logger.info(
                "Initializing database connection",
                database_url=self._settings.url_masked,
            )
            
            start = time.perf_counter()
            
            try:
                # Prepare connect args - exclude statement_timeout for Neon pooled connections
                connect_args = {}
                if not ("neon.tech" in self._settings.url and "pooler" in self._settings.url):
                    # Only add statement_timeout for non-Neon or non-pooled connections
                    connect_args["options"] = f"-c statement_timeout={self._settings.statement_timeout_ms}"
                
                # Create engine with connection pooling
                self._engine = create_engine(
                    self._settings.url,
                    poolclass=QueuePool,
                    pool_size=self._settings.pool_size,
                    max_overflow=self._settings.max_overflow,
                    pool_timeout=self._settings.pool_timeout,
                    pool_recycle=self._settings.pool_recycle,
                    pool_pre_ping=True,  # Verify connections before use
                    echo=self._settings.echo,
                    connect_args=connect_args,
                )
                
                # Register event listeners for instrumentation
                self._register_events()
                
                # Create session factory
                self._session_factory = sessionmaker(
                    bind=self._engine,
                    autocommit=False,
                    autoflush=False,
                    expire_on_commit=False,
                )
                
                # Test connection
                with self._engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                
                duration_ms = (time.perf_counter() - start) * 1000
                self._initialized = True
                
                logger.info(
                    "Database connection established",
                    duration_ms=duration_ms,
                    pool_size=self._settings.pool_size,
                )
                
            except Exception as e:
                logger.error(
                    "Failed to initialize database connection",
                    error=str(e),
                    database_url=self._settings.url_masked,
                    exc_info=True,
                )
                raise
    
    def _register_events(self) -> None:
        """Register SQLAlchemy event listeners for instrumentation."""
        
        @event.listens_for(self._engine, "before_cursor_execute")
        def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """Log query start."""
            conn.info.setdefault("query_start_time", []).append(time.perf_counter())
        
        @event.listens_for(self._engine, "after_cursor_execute")
        def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
            """Log query completion with timing."""
            start_times = conn.info.get("query_start_time", [])
            if start_times:
                start = start_times.pop()
                duration = (time.perf_counter() - start) * 1000
                
                # Extract operation type
                operation = statement.split()[0].upper() if statement else "UNKNOWN"
                
                # Log slow queries
                if duration > 1000:  # > 1 second
                    logger.warning(
                        "Slow query detected",
                        duration_ms=duration,
                        operation=operation,
                        statement_preview=statement[:200] if statement else None,
                    )
                else:
                    logger.debug(
                        "Query executed",
                        duration_ms=duration,
                        operation=operation,
                    )
                
                # Track metrics
                track_database_operation(
                    operation=operation.lower(),
                    table="unknown",  # Would need parsing to extract
                    duration_seconds=duration / 1000,
                    success=True,
                )
        
        @event.listens_for(self._engine, "handle_error")
        def handle_error(exception_context):
            """Log database errors."""
            logger.error(
                "Database error",
                error=str(exception_context.original_exception),
                statement=exception_context.statement[:200] if exception_context.statement else None,
                exc_info=True,
            )
    
    @contextlib.contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Create a database session context manager.
        
        Automatically handles commit/rollback on exit.
        
        Usage:
            >>> with db.session() as session:
            ...     session.query(Organization).all()
        """
        session = self.session_factory()
        
        try:
            # Temporarily disable tracing to fix context token issue
            # TODO: Fix tracing context management
            yield session
            session.commit()
                
        except Exception as e:
            logger.error(
                "Session error, rolling back",
                error=str(e),
                exc_info=True,
            )
            session.rollback()
            raise
            
        finally:
            session.close()
    
    def get_session(self) -> Session:
        """
        Get a new session (caller responsible for closing).
        
        Prefer using session() context manager when possible.
        """
        return self.session_factory()
    
    def health_check(self) -> dict:
        """
        Check database connectivity.
        
        Returns:
            Health check result dict
        """
        start = time.perf_counter()
        
        try:
            with self._engine.connect() as conn:
                result = conn.execute(text("SELECT 1"))
                result.close()
            
            duration_ms = (time.perf_counter() - start) * 1000
            
            # Get pool stats
            pool_status = {
                "pool_size": self._engine.pool.size(),
                "checked_in": self._engine.pool.checkedin(),
                "checked_out": self._engine.pool.checkedout(),
                "overflow": self._engine.pool.overflow(),
            }
            
            return {
                "status": "healthy",
                "latency_ms": duration_ms,
                "pool": pool_status,
            }
            
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            
            logger.error(
                "Database health check failed",
                error=str(e),
                exc_info=True,
            )
            
            return {
                "status": "unhealthy",
                "latency_ms": duration_ms,
                "error": str(e),
            }
    
    def dispose(self) -> None:
        """Dispose of the database engine and connections."""
        if self._engine:
            logger.info("Disposing database engine")
            self._engine.dispose()
            self._engine = None
            self._session_factory = None
            self._initialized = False
    
    def close(self) -> None:
        """Alias for dispose() for compatibility."""
        self.dispose()


# =============================================================================
# Global Instance
# =============================================================================

_db_manager: Optional[DatabaseManager] = None


def get_db_manager() -> DatabaseManager:
    """Get global database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager()
    return _db_manager


def get_db_session() -> Generator[Session, None, None]:
    """
    Dependency for FastAPI to get database session.
    
    Usage:
        >>> @app.get("/organizations")
        ... def list_orgs(session: Session = Depends(get_db_session)):
        ...     return session.query(Organization).all()
    """
    with get_db_manager().session() as session:
        yield session


def create_all_tables(engine: Optional[Engine] = None) -> None:
    """
    Create all database tables.
    
    Should only be used in development/testing.
    Use Alembic migrations for production.
    """
    from infrastructure.persistence.tenant_repository import Base
    
    engine = engine or get_db_manager().engine
    
    logger.warning(
        "Creating all database tables (use migrations in production!)",
    )
    
    Base.metadata.create_all(bind=engine)
    
    logger.info("Database tables created")


def drop_all_tables(engine: Optional[Engine] = None) -> None:
    """
    Drop all database tables.
    
    DANGER: Destroys all data. Only for testing.
    """
    from infrastructure.persistence.tenant_repository import Base
    
    engine = engine or get_db_manager().engine
    
    logger.warning("DROPPING ALL DATABASE TABLES!")
    
    Base.metadata.drop_all(bind=engine)
    
    logger.info("Database tables dropped")


__all__ = [
    "DatabaseManager",
    "get_db_manager",
    "get_db_session",
    "create_all_tables",
    "drop_all_tables",
]
