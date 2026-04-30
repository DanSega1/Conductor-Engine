"""Runtime policy implementations."""

from __future__ import annotations

from typing import Any

import httpx

from engine.interfaces.policy import OPAInput, PolicyContext, PolicyDecision, PolicyDecisionType
from engine.interfaces.task import RiskLevel, TaskRecord

_RISK_ORDER: dict[RiskLevel, int] = {
    RiskLevel.LOW: 0,
    RiskLevel.MEDIUM: 1,
    RiskLevel.HIGH: 2,
    RiskLevel.CRITICAL: 3,
}


class NullPolicyEngine:
    """Default policy engine that allows every task."""

    def evaluate(self, task: TaskRecord, context: PolicyContext) -> PolicyDecision:
        return PolicyDecision(decision=PolicyDecisionType.ALLOW)

    def health_check(self) -> list[str]:
        return []


class RiskLevelPolicyEngine:
    """Rule-based policy engine that enforces a maximum capability risk level.

    Denies tasks whose capability risk level exceeds *deny_above*.
    Requires-approval tasks whose capability risk level equals *require_approval_at*
    (when set).

    Works without an OPA server — suitable for local or development deployments.
    Production deployments can swap this for OPAPolicyEngine without changing the
    supervisor contract.
    """

    def __init__(
        self,
        *,
        deny_above: RiskLevel = RiskLevel.CRITICAL,
        require_approval_at: RiskLevel | None = None,
        allowed_capabilities: frozenset[str] | None = None,
    ) -> None:
        """Initialise the risk-level policy engine.

        Args:
            deny_above: Deny any capability with a risk level strictly above this.
                        Defaults to CRITICAL (deny nothing by default).
            require_approval_at: Require approval for capabilities at exactly this
                                 risk level (evaluated before the deny check).
            allowed_capabilities: When set, only these capability names are permitted
                                  regardless of risk level. All others are denied.
        """
        self.deny_above = deny_above
        self.require_approval_at = require_approval_at
        self.allowed_capabilities = allowed_capabilities

    def evaluate(self, task: TaskRecord, context: PolicyContext) -> PolicyDecision:
        capability = context.capability

        if self.allowed_capabilities is not None and capability.name not in self.allowed_capabilities:
            return PolicyDecision(
                decision=PolicyDecisionType.DENY,
                reason=f"Capability '{capability.name}' is not in the allowed set",
                metadata={"capability": capability.name, "policy": "allowlist"},
            )

        cap_risk = RiskLevel(capability.risk_level)
        cap_order = _RISK_ORDER[cap_risk]

        if self.require_approval_at is not None and cap_risk == self.require_approval_at:
            return PolicyDecision(
                decision=PolicyDecisionType.REQUIRE_APPROVAL,
                reason=f"Capability '{capability.name}' requires approval at risk level '{cap_risk}'",
                metadata={"risk_level": cap_risk, "policy": "risk_threshold"},
            )

        if cap_order > _RISK_ORDER[self.deny_above]:
            return PolicyDecision(
                decision=PolicyDecisionType.DENY,
                reason=(
                    f"Capability '{capability.name}' risk level '{cap_risk}' exceeds"
                    f" permitted maximum '{self.deny_above}'"
                ),
                metadata={"risk_level": cap_risk, "deny_above": self.deny_above, "policy": "risk_threshold"},
            )

        return PolicyDecision(decision=PolicyDecisionType.ALLOW)

    def health_check(self) -> list[str]:
        return []


class OPAPolicyEngine:
    """Policy engine that evaluates tasks against an OPA REST API.

    Sends a standard OPA input bundle to the configured policy path and maps
    the result back to a PolicyDecision.

    Expected OPA response shape (result of POST /v1/data/{policy_path}):
        {"result": {"allow": bool, "require_approval": bool, "reason": str}}

    When *fail_open* is True, HTTP or connectivity errors allow the task
    through (fail-open/permissive). When False (default), errors deny the task
    (fail-closed/secure).
    """

    def __init__(
        self,
        url: str,
        policy_path: str = "conductor/authz",
        *,
        timeout_seconds: float = 5.0,
        fail_open: bool = False,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        """Initialise the OPA policy engine.

        Args:
            url: Base URL of the OPA server (e.g. "http://localhost:8181").
            policy_path: OPA policy path to query (appended to /v1/data/).
            timeout_seconds: HTTP request timeout.
            fail_open: If True, connectivity errors produce ALLOW decisions.
                       If False (default), connectivity errors produce DENY.
            extra_headers: Additional HTTP headers (e.g. for auth tokens).
        """
        self.url = url.rstrip("/")
        self.policy_path = policy_path.strip("/")
        self.timeout_seconds = timeout_seconds
        self.fail_open = fail_open
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if extra_headers:
            self._headers.update(extra_headers)

    def _query_url(self) -> str:
        return f"{self.url}/v1/data/{self.policy_path}"

    def _build_payload(self, task: TaskRecord, context: PolicyContext) -> dict[str, Any]:
        return {"input": OPAInput.from_context(task, context).model_dump()}

    def _map_response(self, data: dict[str, Any]) -> PolicyDecision:
        result = data.get("result") or {}
        reason: str | None = result.get("reason")

        if result.get("require_approval"):
            return PolicyDecision(
                decision=PolicyDecisionType.REQUIRE_APPROVAL,
                reason=reason,
                metadata={"opa_result": result},
            )
        if result.get("allow", False):
            return PolicyDecision(
                decision=PolicyDecisionType.ALLOW,
                reason=reason,
                metadata={"opa_result": result},
            )
        return PolicyDecision(
            decision=PolicyDecisionType.DENY,
            reason=reason or "OPA policy denied the request",
            metadata={"opa_result": result},
        )

    def evaluate(self, task: TaskRecord, context: PolicyContext) -> PolicyDecision:
        try:
            response = httpx.post(
                self._query_url(),
                json=self._build_payload(task, context),
                headers=self._headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return self._map_response(response.json())
        except Exception as exc:
            if self.fail_open:
                return PolicyDecision(
                    decision=PolicyDecisionType.ALLOW,
                    reason=f"OPA unreachable (fail-open): {exc}",
                    metadata={"opa_error": str(exc), "fail_open": True},
                )
            return PolicyDecision(
                decision=PolicyDecisionType.DENY,
                reason=f"OPA unreachable (fail-closed): {exc}",
                metadata={"opa_error": str(exc), "fail_open": False},
            )

    def health_check(self) -> list[str]:
        issues: list[str] = []
        try:
            response = httpx.get(f"{self.url}/health", timeout=self.timeout_seconds)
            if response.status_code != 200:
                issues.append(f"opa: health endpoint returned {response.status_code}")
        except Exception as exc:
            issues.append(f"opa: cannot reach server at {self.url!r}: {exc}")
        return issues
