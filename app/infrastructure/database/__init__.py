"""Database Module

Manages database connection, session creation, and database initialization.
Provides database session management for dependency injection.

Example:
    >>> from app.infrastructure.database import get_db
    >>> async def endpoint(db = Depends(get_db)):
    >>>     # Use database session
"""
