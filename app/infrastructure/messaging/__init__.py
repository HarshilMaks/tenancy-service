"""Messaging Module

Handles event publishing and message queue operations. Implements event-driven
communication between services and event store persistence.

Example:
    >>> from app.infrastructure.messaging import EventPublisher
    >>> publisher = EventPublisher()
    >>> await publisher.publish(tenant_created_event)
"""
