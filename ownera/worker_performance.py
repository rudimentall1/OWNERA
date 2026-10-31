"""Event-derived worker performance and trust evidence."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ownera.event_store import StoredEvent
from ownera.persistent_workforce import PersistentWorkforce


class WorkerPerformanceError(RuntimeError):
    """Workforce history cannot support a trustworthy performance report."""


@dataclass(frozen=True)
class CurrencyCost:
    currency: str
    total: Decimal


@dataclass(frozen=True)
class WorkerPerformance:
    worker_id: str
    enabled: bool
    started_attempts: int
    submitted_attempts: int
    reviewed_attempts: int
    accepted_attempts: int
    rework_attempts: int
    pending_review_attempts: int
    acceptance_rate: float | None
    costs_by_currency: tuple[CurrencyCost, ...]
    trust_band: str


@dataclass(frozen=True)
class WorkforcePerformanceReport:
    aggregate_id: str
    event_count: int
    event_version: int
    event_chain_verified: bool
    workers: tuple[WorkerPerformance, ...]


class WorkerPerformanceService:
    """Build descriptive performance evidence from the verified event stream.

    Metrics are attempt-based, not task-based. A resubmission after rework is a
    new attempt and is attributed to the worker recorded in TaskSubmitted.
    Trust bands are descriptive only and never grant execution permissions.
    """

    def __init__(self, workforce: PersistentWorkforce) -> None:
        self.workforce = workforce

    def build_report(self) -> WorkforcePerformanceReport:
        event_store = self.workforce.repository.event_store
        verified = event_store.verify("workforce", self.workforce.AGGREGATE_ID)
        events = event_store.load("workforce", self.workforce.AGGREGATE_ID)
        if len(events) != self.workforce.event_version:
            raise WorkerPerformanceError("workforce snapshot is stale relative to event history")
        profiles = {worker.worker_id: worker for worker in self.workforce.workers}
        stats: dict[str, dict[str, Any]] = {
            worker_id: {
                "started": 0,
                "submitted": 0,
                "reviewed": 0,
                "accepted": 0,
                "rework": 0,
                "pending": 0,
                "costs": {},
            }
            for worker_id in profiles
        }
        latest_submission: dict[str, tuple[str, str]] = {}
        reviewed_attempts: set[tuple[str, int]] = set()
        attempt_index: dict[str, int] = {}

        for event in events:
            payload = event.payload
            if event.event_type == "TaskStarted":
                worker_id = self._required_string(payload, "worker_id", event)
                if worker_id in stats:
                    stats[worker_id]["started"] += 1
            elif event.event_type == "TaskSubmitted":
                task_id = self._required_string(payload, "task_id", event)
                worker_id = self._required_string(payload, "worker_id", event)
                cost_text = self._required_string(payload, "actual_cost", event)
                currency = self._task_currency(task_id)
                if worker_id not in stats:
                    raise WorkerPerformanceError(
                        f"submission references unregistered worker: {worker_id}"
                    )
                try:
                    cost = Decimal(cost_text)
                except Exception as exc:
                    raise WorkerPerformanceError("invalid cost in submission event") from exc
                if not cost.is_finite() or cost < 0:
                    raise WorkerPerformanceError("submission cost must be finite and non-negative")
                stats[worker_id]["submitted"] += 1
                costs = stats[worker_id]["costs"]
                costs[currency] = costs.get(currency, Decimal("0")) + cost
                attempt_index[task_id] = attempt_index.get(task_id, 0) + 1
                latest_submission[task_id] = (worker_id, str(attempt_index[task_id]))
            elif event.event_type in ("TaskReviewAccepted", "TaskReviewRejected"):
                task_id = self._required_string(payload, "task_id", event)
                self._required_string(payload, "reviewer_id", event)
                accepted = payload.get("accepted")
                if not isinstance(accepted, bool):
                    raise WorkerPerformanceError("review event has invalid accepted flag")
                attempt = latest_submission.get(task_id)
                if attempt is None:
                    raise WorkerPerformanceError(
                        f"review event has no preceding submission for task {task_id}"
                    )
                if (task_id, int(attempt[1])) in reviewed_attempts:
                    raise WorkerPerformanceError(
                        f"multiple review decisions found for one submission: {task_id}"
                    )
                worker_id = attempt[0]
                reviewed_attempts.add((task_id, int(attempt[1])))
                stats[worker_id]["reviewed"] += 1
                stats[worker_id]["accepted" if accepted else "rework"] += 1

        for task_id, (worker_id, attempt_number) in latest_submission.items():
            if (task_id, int(attempt_number)) not in reviewed_attempts:
                stats[worker_id]["pending"] += 1

        reports = []
        for worker_id, profile in sorted(profiles.items()):
            item = stats[worker_id]
            reviewed = item["reviewed"]
            accepted = item["accepted"]
            rate = accepted / reviewed if reviewed else None
            reports.append(
                WorkerPerformance(
                    worker_id=worker_id,
                    enabled=profile.enabled,
                    started_attempts=item["started"],
                    submitted_attempts=item["submitted"],
                    reviewed_attempts=reviewed,
                    accepted_attempts=accepted,
                    rework_attempts=item["rework"],
                    pending_review_attempts=item["pending"],
                    acceptance_rate=rate,
                    costs_by_currency=tuple(
                        CurrencyCost(currency, total)
                        for currency, total in sorted(item["costs"].items())
                    ),
                    trust_band=self._trust_band(reviewed, rate),
                )
            )

        return WorkforcePerformanceReport(
            aggregate_id=self.workforce.AGGREGATE_ID,
            event_count=len(events),
            event_version=self.workforce.event_version,
            event_chain_verified=verified,
            workers=tuple(reports),
        )

    def _task_currency(self, task_id: str) -> str:
        for task in self.workforce.tasks:
            if str(task.task_id) == task_id:
                return task.currency
        raise WorkerPerformanceError(
            f"submission references unknown task currency: {task_id}"
        )

    @staticmethod
    def _required_string(payload: dict[str, Any], key: str, event: StoredEvent) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise WorkerPerformanceError(
                f"{event.event_type} event has invalid {key}"
            )
        return value

    @staticmethod
    def _trust_band(reviewed_attempts: int, acceptance_rate: float | None) -> str:
        if reviewed_attempts < 5:
            return "UNRATED"
        if acceptance_rate is None:
            return "UNRATED"
        if acceptance_rate < 0.70:
            return "REVIEW_REQUIRED"
        if reviewed_attempts >= 20 and acceptance_rate >= 0.90:
            return "CONSISTENT"
        return "LIMITED_EVIDENCE"
