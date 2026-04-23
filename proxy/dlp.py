from models import ToolRequest, DLPResult

PII_TOOLS = {
    "read_customer_record",
    "query_account_balance",
    "fetch_contact_info",
    "get_transaction_history",
}

FLAG_THRESHOLD = 4   # flag after 4 PII calls (end of first session)
BLOCK_THRESHOLD = 7  # block after 7 PII calls cross-session


class DLPTracker:
    def __init__(self):
        self._state: dict[str, dict] = {}

    async def check_fragment(self, request: ToolRequest) -> DLPResult:
        if request.tool_name not in PII_TOOLS:
            return DLPResult(threshold_exceeded=False)

        agent = request.agent_id
        if agent not in self._state:
            self._state[agent] = {"field_count": 0, "sessions": set(), "pii_categories": []}

        s = self._state[agent]
        s["field_count"] += 1
        s["sessions"].add(request.session_id)
        s["pii_categories"].append(request.tool_name)

        field_count = s["field_count"]
        session_count = len(s["sessions"])
        categories = list(set(s["pii_categories"]))

        if field_count >= BLOCK_THRESHOLD:
            return DLPResult(
                threshold_exceeded=True,
                field_count=field_count,
                session_count=session_count,
                pii_categories=categories,
            )
        if field_count >= FLAG_THRESHOLD:
            return DLPResult(
                threshold_exceeded=False,
                flag=True,
                field_count=field_count,
                session_count=session_count,
                pii_categories=categories,
            )
        return DLPResult(threshold_exceeded=False, field_count=field_count, session_count=session_count)

    def reset(self):
        self._state.clear()


tracker = DLPTracker()
