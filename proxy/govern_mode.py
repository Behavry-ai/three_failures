import decision_trace
import dlp as _dlp
import drift_tracker as _dt
import injection_scanner
from models import InjectionResult, DLPResult, DriftResult, ToolDecision, ToolRequest


def _block(request: ToolRequest, checks: list, reason: str) -> ToolDecision:
    trace = decision_trace.seal(request, None, checks, decision="block", reason=reason)
    return ToolDecision(allowed=False, decision="block", reason=reason, trace=trace)


async def handle(request: ToolRequest, forward_fn) -> ToolDecision:
    # 1. Inbound injection scan (request params)
    injection = await injection_scanner.scan(request)
    if injection.found:
        return _block(
            request,
            [injection, DLPResult(threshold_exceeded=False), DriftResult(policy_violation=False)],
            f"injection detected: {injection.pattern}",
        )

    # 2. Cross-session PII fragment check (only for the CRM agent)
    fragment = (
        await _dlp.tracker.check_fragment(request)
        if request.agent_id == "agent-crm"
        else DLPResult(threshold_exceeded=False)
    )
    if fragment.threshold_exceeded:
        return _block(
            request,
            [injection, fragment, DriftResult(policy_violation=False)],
            f"exfil threshold exceeded: {fragment.field_count} PII fields across {fragment.session_count} sessions",
        )

    # 3. Drift / policy check (only for the analyst agent)
    drift = (
        await _dt.tracker.evaluate(request)
        if request.agent_id == "agent-analyst"
        else DriftResult(policy_violation=False)
    )
    if drift.policy_violation and not drift.flag_only:
        return _block(
            request,
            [injection, fragment, drift],
            f"tool not in approved scope: {request.tool_name}",
        )

    # 4. Forward to target
    response = await forward_fn(request)

    # 5. Scan response body for injection patterns
    resp_injection = await injection_scanner.scan_response(request.tool_name, response)

    if resp_injection.found:
        trace = decision_trace.seal(
            request, response, [injection, fragment, drift],
            response_injection=resp_injection,
            decision="flag",
            reason=f"injection in {request.tool_name} response: {resp_injection.pattern}",
        )
        return ToolDecision(
            allowed=True,
            response=response,
            decision="flag",
            reason=f"injection detected in response body: {resp_injection.pattern}",
            trace=trace,
        )

    # 6. PII flag (allowed but flagged)
    if fragment.flag:
        flag_reason = f"PII accumulation pattern: {fragment.field_count} fields, {fragment.session_count} session(s)"
        trace = decision_trace.seal(
            request, response, [injection, fragment, drift],
            decision="flag",
            reason=flag_reason,
        )
        return ToolDecision(allowed=True, response=response, decision="flag", reason=flag_reason, trace=trace)

    trace = decision_trace.seal(request, response, [injection, fragment, drift])
    return ToolDecision(allowed=True, response=response, decision="allow", trace=trace)
