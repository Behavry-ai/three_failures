import hashlib
import json
import uuid
from datetime import datetime, timezone
from models import ToolRequest, InjectionResult, DLPResult, DriftResult

_sequence = 0
_prev_hash = "genesis"


def reset_chain():
    global _sequence, _prev_hash
    _sequence = 0
    _prev_hash = "genesis"


def seal(
    request: ToolRequest,
    response: dict | None,
    checks: list,
    response_injection: InjectionResult | None = None,
    decision: str = "allow",
    reason: str | None = None,
) -> dict:
    global _sequence, _prev_hash
    _sequence += 1
    seq = _sequence
    prev = _prev_hash

    injection = next((c for c in checks if isinstance(c, InjectionResult)), None)
    dlp = next((c for c in checks if isinstance(c, DLPResult)), None)
    drift = next((c for c in checks if isinstance(c, DriftResult)), None)

    trace = {
        "trace_id": f"trace_{uuid.uuid4().hex[:8]}",
        "sequence": seq,
        "ts": datetime.now(timezone.utc).isoformat(),
        "prev_hash": prev,
        "request": {
            "tool": request.tool_name,
            "agent_id": request.agent_id,
            "session_id": request.session_id,
            "params": request.params,
        },
        "checks": {
            "injection_scan": {
                "ran": injection is not None,
                "found": injection.found if injection else False,
                "pattern": injection.pattern if injection else None,
                "evidence": injection.evidence if injection else None,
            },
            "response_injection_scan": {
                "ran": response_injection is not None,
                "found": response_injection.found if response_injection else False,
                "pattern": response_injection.pattern if response_injection else None,
                "evidence": response_injection.evidence if response_injection else None,
            },
            "dlp": {
                "ran": dlp is not None,
                "threshold_exceeded": dlp.threshold_exceeded if dlp else False,
                "flag": dlp.flag if dlp else False,
                "field_count": dlp.field_count if dlp else 0,
                "session_count": dlp.session_count if dlp else 0,
                "pii_categories": dlp.pii_categories if dlp else [],
            },
            "drift": {
                "ran": drift is not None,
                "policy_violation": drift.policy_violation if drift else False,
                "flag_only": drift.flag_only if drift else False,
                "drift_pct": drift.drift_pct if drift else 0.0,
                "baseline_delta": drift.baseline_delta if drift else None,
            },
        },
        "decision": decision,
        "reason": reason,
        "response_forwarded": response is not None,
        "attestation": "proxy-generated — independent of agent telemetry",
    }

    chain_hash = hashlib.sha256(
        json.dumps(trace, sort_keys=True).encode()
    ).hexdigest()
    trace["chain_hash"] = chain_hash
    _prev_hash = chain_hash

    return trace
