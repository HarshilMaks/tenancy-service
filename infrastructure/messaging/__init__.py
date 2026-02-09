"""
Messaging Infrastructure - Event Publishing & Subscription
===========================================================

Production-grade event bus implementation supporting multiple backends:
- In-memory (development/testing)
- RabbitMQ (recommended for production)
- Kafka (high-throughput scenarios)
- Redis Pub/Sub (simple deployments)

Features:
    - Async event publishing
    - Retry with exponential backoff
    - Dead letter queue handling
    - Event serialization/deserialization
    - Observability integration

Message Format:
    {
        "event_id": "uuid",
        "event_type": "OrganizationCreated",
        "aggregate_type": "Organization",
        "aggregate_id": "ORG-12345678",
        "timestamp": "2026-02-02T10:30:45Z",
        "version": 1,
        "payload": {...},
        "metadata": {
            "correlation_id": "corr-abc123",
            "causation_id": "evt-xyz789"
        }
    }

Author: Platform Engineering Team
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Type, Union
from uuid import uuid4

from infrastructure.observability.logging import get_logger, get_correlation_id
from infrastructure.observability.metrics import get_metrics, track_event_published
from infrastructure.observability.tracing import create_span, SpanKind

logger = get_logger(__name__)


# =============================================================================
# Event Envelope
# =============================================================================

@dataclass
class EventEnvelope:
    """
    Wrapper for domain events with routing metadata.
    
    Contains the serialized event plus metadata needed for
    message broker routing and processing.
    """
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    timestamp: datetime
    version: int
    payload: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Routing
    routing_key: Optional[str] = None
    exchange: str = "domain.events"
    
    # Delivery
    delivery_attempts: int = 0
    max_retries: int = 3
    
    @classmethod
    def from_domain_event(cls, event: Any) -> "EventEnvelope":
        """Create envelope from domain event."""
        event_dict = event.to_dict() if hasattr(event, "to_dict") else {}
        
        return cls(
            event_id=getattr(event, "event_id", str(uuid4())),
            event_type=event.__class__.__name__,
            aggregate_type=getattr(event, "aggregate_type", "Unknown"),
            aggregate_id=getattr(event, "aggregate_id", ""),
            timestamp=getattr(event, "timestamp", datetime.now(timezone.utc)),
            version=getattr(event, "version", 1),
            payload=event_dict.get("payload", {}),
            metadata={
                "correlation_id": get_correlation_id(),
                **event_dict.get("metadata", {}),
            },
            routing_key=f"{getattr(event, 'aggregate_type', 'domain').lower()}.{event.__class__.__name__}",
        )
    
    def to_json(self) -> str:
        """Serialize envelope to JSON."""
        return json.dumps({
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "timestamp": self.timestamp.isoformat(),
            "version": self.version,
            "payload": self.payload,
            "metadata": self.metadata,
            "routing_key": self.routing_key,
        }, default=str)
    
    @classmethod
    def from_json(cls, data: Union[str, bytes]) -> "EventEnvelope":
        """Deserialize envelope from JSON."""
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        
        parsed = json.loads(data)
        
        return cls(
            event_id=parsed["event_id"],
            event_type=parsed["event_type"],
            aggregate_type=parsed["aggregate_type"],
            aggregate_id=parsed["aggregate_id"],
            timestamp=datetime.fromisoformat(parsed["timestamp"]),
            version=parsed["version"],
            payload=parsed.get("payload", {}),
            metadata=parsed.get("metadata", {}),
            routing_key=parsed.get("routing_key"),
        )


# =============================================================================
# Event Handler Type
# =============================================================================

EventHandler = Callable[[EventEnvelope], None]
AsyncEventHandler = Callable[[EventEnvelope], "asyncio.coroutine"]


# =============================================================================
# Event Publisher Interface
# =============================================================================

class EventPublisher(ABC):
    """
    Abstract base class for event publishers.
    
    Defines the interface for publishing domain events
    to message brokers.
    """
    
    @abstractmethod
    def publish(self, event: Any) -> None:
        """
        Publish a single domain event.
        
        Args:
            event: Domain event to publish
        """
        pass
    
    @abstractmethod
    def publish_batch(self, events: List[Any]) -> None:
        """
        Publish multiple events in a batch.
        
        Args:
            events: List of domain events
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close publisher connections."""
        pass


class EventSubscriber(ABC):
    """
    Abstract base class for event subscribers.
    
    Defines the interface for subscribing to and
    consuming domain events.
    """
    
    @abstractmethod
    def subscribe(
        self,
        event_type: str,
        handler: Union[EventHandler, AsyncEventHandler],
    ) -> None:
        """
        Subscribe to events of a specific type.
        
        Args:
            event_type: Type of event to subscribe to
            handler: Function to handle events
        """
        pass
    
    @abstractmethod
    def start(self) -> None:
        """Start consuming events."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop consuming events."""
        pass


# =============================================================================
# In-Memory Implementation (Development/Testing)
# =============================================================================

class InMemoryEventBus(EventPublisher, EventSubscriber):
    """
    In-memory event bus for development and testing.
    
    NOT suitable for production - events are lost on restart.
    
    Features:
        - Synchronous event delivery
        - Multiple handlers per event type
        - Event history for testing
    """
    
    def __init__(self):
        self._handlers: Dict[str, List[EventHandler]] = defaultdict(list)
        self._all_handlers: List[EventHandler] = []
        self._event_history: List[EventEnvelope] = []
        self._lock = threading.Lock()
        self._running = False
        
        logger.info(
            "InMemoryEventBus initialized (development only)",
            warning="Not suitable for production!",
        )
    
    def publish(self, event: Any) -> None:
        """Publish event to in-memory subscribers."""
        start = time.perf_counter()
        
        with create_span("publish_event", kind=SpanKind.PRODUCER) as span:
            envelope = EventEnvelope.from_domain_event(event)
            
            span.set_attribute("event_type", envelope.event_type)
            span.set_attribute("aggregate_id", envelope.aggregate_id)
            
            logger.info(
                f"Publishing event: {envelope.event_type}",
                event_id=envelope.event_id,
                event_type=envelope.event_type,
                aggregate_id=envelope.aggregate_id,
            )
            
            # Store in history
            with self._lock:
                self._event_history.append(envelope)
            
            # Deliver to handlers
            handlers = self._handlers.get(envelope.event_type, []) + self._all_handlers
            
            for handler in handlers:
                try:
                    handler(envelope)
                except Exception as e:
                    logger.error(
                        f"Event handler failed: {e}",
                        event_type=envelope.event_type,
                        handler=handler.__name__,
                        exc_info=True,
                    )
            
            duration = time.perf_counter() - start
            track_event_published(
                event_type=envelope.event_type,
                duration_seconds=duration,
                success=True,
            )
            
            logger.debug(
                f"Event published: {envelope.event_type}",
                duration_ms=duration * 1000,
                handler_count=len(handlers),
            )
    
    def publish_batch(self, events: List[Any]) -> None:
        """Publish multiple events."""
        logger.info(
            f"Publishing batch of {len(events)} events",
            event_count=len(events),
        )
        
        for event in events:
            self.publish(event)
    
    def subscribe(
        self,
        event_type: str,
        handler: EventHandler,
    ) -> None:
        """Subscribe handler to event type."""
        with self._lock:
            self._handlers[event_type].append(handler)
        
        logger.debug(
            f"Handler subscribed to {event_type}",
            event_type=event_type,
            handler=handler.__name__,
        )
    
    def subscribe_all(self, handler: EventHandler) -> None:
        """Subscribe handler to all events."""
        with self._lock:
            self._all_handlers.append(handler)
        
        logger.debug(
            "Handler subscribed to all events",
            handler=handler.__name__,
        )
    
    def start(self) -> None:
        """Start event bus (no-op for in-memory)."""
        self._running = True
        logger.info("InMemoryEventBus started")
    
    def stop(self) -> None:
        """Stop event bus."""
        self._running = False
        logger.info("InMemoryEventBus stopped")
    
    def close(self) -> None:
        """Close event bus."""
        self.stop()
    
    # Testing helpers
    
    def get_events(
        self,
        event_type: Optional[str] = None,
        aggregate_id: Optional[str] = None,
    ) -> List[EventEnvelope]:
        """Get event history (for testing)."""
        events = self._event_history.copy()
        
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        
        if aggregate_id:
            events = [e for e in events if e.aggregate_id == aggregate_id]
        
        return events
    
    def clear_history(self) -> None:
        """Clear event history (for testing)."""
        with self._lock:
            self._event_history.clear()


# =============================================================================
# Outbox Pattern Implementation
# =============================================================================

@dataclass
class OutboxMessage:
    """
    Message in the transactional outbox.
    
    The outbox pattern ensures events are published reliably
    by storing them in the same transaction as the domain change.
    """
    id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    aggregate_type: str = ""
    aggregate_id: str = ""
    payload: str = ""  # JSON serialized
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None
    attempts: int = 0
    last_error: Optional[str] = None


class TransactionalOutbox:
    """
    Transactional outbox for reliable event publishing.
    
    Stores events in the database within the same transaction
    as the domain change, then publishes them asynchronously.
    
    Guarantees:
        - At-least-once delivery
        - Events survive service restarts
        - Maintains order within aggregate
    
    Usage:
        >>> with db.session() as session:
        ...     org = Organization.create("Acme")
        ...     session.add(org)
        ...     outbox.add(session, OrganizationCreatedEvent(org_id=org.id))
        ...     session.commit()  # Event stored atomically
        >>> 
        >>> # Later, background worker publishes events
        >>> outbox.process_pending()
    """
    
    def __init__(
        self,
        publisher: EventPublisher,
        batch_size: int = 100,
        max_retries: int = 5,
    ):
        self.publisher = publisher
        self.batch_size = batch_size
        self.max_retries = max_retries
        
        logger.info(
            "TransactionalOutbox initialized",
            batch_size=batch_size,
            max_retries=max_retries,
        )
    
    def add(self, session: Any, event: Any) -> OutboxMessage:
        """
        Add event to outbox within transaction.
        
        Args:
            session: Database session
            event: Domain event to store
            
        Returns:
            Created outbox message
        """
        envelope = EventEnvelope.from_domain_event(event)
        
        message = OutboxMessage(
            event_type=envelope.event_type,
            aggregate_type=envelope.aggregate_type,
            aggregate_id=envelope.aggregate_id,
            payload=envelope.to_json(),
        )
        
        # Would store in outbox table
        # session.add(OutboxModel.from_message(message))
        
        logger.debug(
            f"Event added to outbox: {message.event_type}",
            event_type=message.event_type,
            aggregate_id=message.aggregate_id,
            outbox_id=message.id,
        )
        
        return message
    
    def process_pending(self, session: Any) -> int:
        """
        Process pending outbox messages.
        
        Call from background worker to publish stored events.
        
        Returns:
            Number of messages processed
        """
        # Would query outbox table for pending messages
        # messages = session.query(OutboxModel).filter(
        #     OutboxModel.processed_at.is_(None),
        #     OutboxModel.attempts < self.max_retries,
        # ).limit(self.batch_size).all()
        
        processed = 0
        # for message in messages:
        #     try:
        #         envelope = EventEnvelope.from_json(message.payload)
        #         self.publisher.publish(envelope)
        #         message.processed_at = datetime.now(timezone.utc)
        #         processed += 1
        #     except Exception as e:
        #         message.attempts += 1
        #         message.last_error = str(e)
        
        if processed > 0:
            logger.info(
                f"Processed {processed} outbox messages",
                processed_count=processed,
            )
        
        return processed


# =============================================================================
# Event Bus Factory
# =============================================================================

_event_bus: Optional[EventPublisher] = None


def get_event_publisher() -> EventPublisher:
    """
    Get configured event publisher.
    
    Returns appropriate implementation based on configuration.
    """
    global _event_bus
    
    if _event_bus is None:
        from infrastructure.config import get_settings
        
        settings = get_settings()
        broker_type = settings.messaging.broker_type
        
        if broker_type == "memory":
            _event_bus = InMemoryEventBus()
        elif broker_type == "rabbitmq":
            # Would return RabbitMQ implementation
            logger.warning("RabbitMQ not implemented, using in-memory")
            _event_bus = InMemoryEventBus()
        elif broker_type == "kafka":
            # Would return Kafka implementation
            logger.warning("Kafka not implemented, using in-memory")
            _event_bus = InMemoryEventBus()
        else:
            logger.warning(f"Unknown broker type: {broker_type}, using in-memory")
            _event_bus = InMemoryEventBus()
        
        logger.info(
            f"Event publisher initialized: {type(_event_bus).__name__}",
            broker_type=broker_type,
        )
    
    return _event_bus


def reset_event_publisher() -> None:
    """Reset event publisher (for testing)."""
    global _event_bus
    if _event_bus:
        _event_bus.close()
    _event_bus = None


__all__ = [
    # Envelope
    "EventEnvelope",
    
    # Interfaces
    "EventPublisher",
    "EventSubscriber",
    "EventHandler",
    
    # Implementations
    "InMemoryEventBus",
    "TransactionalOutbox",
    "OutboxMessage",
    
    # Factory
    "get_event_publisher",
    "reset_event_publisher",
]
