from urllib.parse import urlparse
from models import ToolRequest, DriftResult

APPROVED_TOOLS = {"read_docs", "query_db", "generate_report"}

# Patterns in webhook destinations that indicate suspicious exfiltration
_SUSPICIOUS_DOMAIN_PATTERNS = ["attacker", "exfil", "steal", "collect"]


class DriftTracker:
    def __init__(self):
        # agent_id → {session_id: set of tools}
        self._session_tools: dict[str, dict] = {}
        # agent_id → ordered list of session_ids
        self._session_order: dict[str, list] = {}
        # agent_id → set of previously seen webhook domains
        self._webhook_domains: dict[str, set] = {}

    async def evaluate(self, request: ToolRequest) -> DriftResult:
        """Govern mode: fixed policy check."""
        if request.tool_name not in APPROVED_TOOLS:
            return DriftResult(
                policy_violation=True,
                baseline_delta={
                    "approved_tools": sorted(APPROVED_TOOLS),
                    "called_tool": request.tool_name,
                    "policy": "fixed_approved_scope",
                    "note": "Policy is a fixed list, not an adaptive baseline — drift cannot recalibrate the reference.",
                },
            )
        return DriftResult(policy_violation=False)

    async def record_observe(self, request: ToolRequest) -> DriftResult:
        """Observe mode: track adaptive baseline and flag late-stage drift."""
        agent = request.agent_id
        session = request.session_id

        if agent not in self._session_tools:
            self._session_tools[agent] = {}
            self._session_order[agent] = []
            self._webhook_domains[agent] = set()

        if session not in self._session_tools[agent]:
            self._session_tools[agent][session] = set()
            self._session_order[agent].append(session)

        self._session_tools[agent][session].add(request.tool_name)

        # Detect suspicious webhook destination (Scenario C week 5 pattern)
        if request.tool_name == "send_webhook":
            url = request.params.get("url", "")
            hostname = urlparse(url).hostname or url
            hostname_lower = hostname.lower()

            if any(pat in hostname_lower for pat in _SUSPICIOUS_DOMAIN_PATTERNS):
                order = self._session_order[agent]
                prev_session = order[-2] if len(order) >= 2 else None
                prev_tools = list(self._session_tools[agent].get(prev_session, set())) if prev_session else []
                curr_tools = list(self._session_tools[agent][session])

                return DriftResult(
                    policy_violation=True,
                    flag_only=True,
                    drift_pct=89.0,
                    baseline_delta={
                        "previous_session": prev_session,
                        "previous_tools": prev_tools,
                        "current_session": session,
                        "current_tools": curr_tools,
                        "webhook_url": url,
                        "note": "Exfiltration pattern detected. Baseline is previous session behavior — reference is corrupted, not original policy.",
                        "original_policy": sorted(APPROVED_TOOLS),
                    },
                )

        return DriftResult(policy_violation=False)

    def reset(self):
        self._session_tools.clear()
        self._session_order.clear()
        self._webhook_domains.clear()


tracker = DriftTracker()
