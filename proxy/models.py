from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolRequest:
    tool_name: str
    agent_id: str
    session_id: str
    params: dict
    scenario: str | None = None


@dataclass
class InjectionResult:
    found: bool
    pattern: str | None = None
    evidence: dict | None = None


@dataclass
class DLPResult:
    threshold_exceeded: bool
    flag: bool = False
    field_count: int = 0
    session_count: int = 0
    pii_categories: list = field(default_factory=list)


@dataclass
class DriftResult:
    policy_violation: bool
    flag_only: bool = False
    drift_pct: float = 0.0
    baseline_delta: dict | None = None


@dataclass
class ToolDecision:
    allowed: bool
    response: dict | None = None
    decision: str = "allow"  # "allow" | "block" | "flag"
    reason: str | None = None
    trace: dict | None = None
