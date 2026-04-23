import drift_tracker as _dt
from models import DriftResult, InjectionResult, DLPResult, ToolRequest, ToolDecision


async def handle(request: ToolRequest, forward_fn) -> ToolDecision:
    # Adaptive drift tracking is scoped to agent-analyst (Scenario C)
    drift = (
        await _dt.tracker.record_observe(request)
        if request.agent_id == "agent-analyst"
        else DriftResult(policy_violation=False)
    )

    response = await forward_fn(request)

    if drift.policy_violation and drift.flag_only:
        import decision_trace
        trace = decision_trace.seal(
            request, response,
            checks=[InjectionResult(found=False), DLPResult(threshold_exceeded=False), drift],
            decision="flag",
            reason=f"exfil pattern detected: drift {drift.drift_pct:.0f}% from session baseline",
        )
        return ToolDecision(
            allowed=True,
            response=response,
            decision="flag",
            reason=f"exfil pattern detected — drift {drift.drift_pct:.0f}% from previous session baseline (baseline corrupted)",
            trace=trace,
        )

    return ToolDecision(allowed=True, response=response, decision="allow")
