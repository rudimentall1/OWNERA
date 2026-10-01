"""Provider-neutral contract for external financial authority.

OWNERA never reconstructs a financial action from a provider response. The
exact FinancialAction digest is the immutable binding between OWNERA intent,
external authorization, and execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .domain import Decision
from .financial_action import FinancialAction


@dataclass(frozen=True)
class AuthorityArtifact:
    """Opaque authorization artifact returned by an external authority."""

    provider: str
    action_digest: str
    decision: Decision
    artifact: dict[str, Any]

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("provider is required")
        if len(self.action_digest) != 64:
            raise ValueError("action_digest must be a SHA-256 hex digest")
        if any(char not in "0123456789abcdef" for char in self.action_digest):
            raise ValueError("action_digest must be lowercase hexadecimal")


class FinancialAuthorityPort(Protocol):
    """Exact financial-action authority boundary.

    Implementations may call Verigate, another policy authority, or a future
    local hardware-backed authority. The execution layer only trusts an
    artifact that is explicitly bound to the exact action digest.
    """

    def authorize(
        self,
        action: FinancialAction,
        *,
        policy_version: str,
    ) -> AuthorityArtifact:
        ...

    def verify(
        self,
        artifact: AuthorityArtifact,
        action: FinancialAction,
    ) -> None:
        """Raise when the artifact is not bound to the exact financial action."""
        ...


def require_allow(artifact: AuthorityArtifact) -> None:
    """Prevent a non-ALLOW authority artifact from reaching execution."""
    if artifact.decision != Decision.ALLOW:
        raise PermissionError("financial authority did not grant execution permission")


def require_action_binding(
    artifact: AuthorityArtifact,
    action: FinancialAction,
) -> None:
    """Fail closed if an authorization was issued for different money."""
    if artifact.action_digest != action.digest():
        raise PermissionError("financial authority is not bound to the exact financial action")
