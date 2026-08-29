"""Append-only audit event primitives for OWNERA."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


@dataclass(frozen=True)
class AuditEvent:
    event_type: str
    actor: str
    correlation_id: UUID
    payload_hash: str
    policy_version: str | None = None
    id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AuditLog:
    """In-memory append-only log for the sandbox/foundation layer."""

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        if self._events and event.timestamp < self._events[-1].timestamp:
            raise ValueError("audit events must be append-ordered")
        self._events.append(event)

    def all(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)
