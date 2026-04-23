"""15 tests for observe mode — logs everything, enforces nothing."""
import pytest
import pytest_asyncio
from conftest import SCENARIO_A_CALLS, SCENARIO_B_CALLS, run_and_wait


@pytest.mark.asyncio
async def test_scenario_a_all_calls_complete(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", SCENARIO_A_CALLS)
    sc_a = [e for e in events if e["scenario"] == "a"]
    assert len(sc_a) == SCENARIO_A_CALLS


@pytest.mark.asyncio
async def test_scenario_a_all_allow(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", SCENARIO_A_CALLS)
    sc_a = [e for e in events if e["scenario"] == "a"]
    decisions = {e["decision"] for e in sc_a}
    assert decisions == {"allow"}, f"Expected only allow, got {decisions}"


@pytest.mark.asyncio
async def test_scenario_a_zero_blocks(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", SCENARIO_A_CALLS)
    sc_a = [e for e in events if e["scenario"] == "a"]
    blocks = [e for e in sc_a if e["decision"] == "block"]
    assert len(blocks) == 0


@pytest.mark.asyncio
async def test_scenario_a_zero_flags(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", SCENARIO_A_CALLS)
    sc_a = [e for e in events if e["scenario"] == "a"]
    flags = [e for e in sc_a if e["decision"] == "flag"]
    assert len(flags) == 0


@pytest.mark.asyncio
async def test_scenario_a_four_sessions(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", SCENARIO_A_CALLS)
    sc_a = [e for e in events if e["scenario"] == "a"]
    sessions = {e["session_id"] for e in sc_a}
    assert sessions == {"sess_a1", "sess_a2", "sess_a3", "sess_a4"}


@pytest.mark.asyncio
async def test_scenario_a_four_customers_profiled(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", SCENARIO_A_CALLS)
    sc_a = [e for e in events if e["scenario"] == "a"]
    tools_used = {e["tool"] for e in sc_a}
    assert "read_customer_record" in tools_used
    assert "get_transaction_history" in tools_used


@pytest.mark.asyncio
async def test_scenario_b_all_three_calls_allowed(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "b", SCENARIO_B_CALLS)
    sc_b = [e for e in events if e["scenario"] == "b"]
    assert len(sc_b) == SCENARIO_B_CALLS
    assert all(e["decision"] == "allow" for e in sc_b)


@pytest.mark.asyncio
async def test_scenario_b_write_to_crontab_allowed(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "b", SCENARIO_B_CALLS)
    sc_b = [e for e in events if e["scenario"] == "b"]
    write_events = [e for e in sc_b if e["tool"] == "write_file"]
    assert len(write_events) == 1
    assert write_events[0]["decision"] == "allow"


@pytest.mark.asyncio
async def test_scenario_b_zero_blocks(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "b", SCENARIO_B_CALLS)
    sc_b = [e for e in events if e["scenario"] == "b"]
    assert all(e["decision"] != "block" for e in sc_b)


@pytest.mark.asyncio
async def test_scenario_b_log_accurate_log_useless(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "b", SCENARIO_B_CALLS)
    sc_b = [e for e in events if e["scenario"] == "b"]
    tools = [e["tool"] for e in sc_b]
    assert tools == ["read_file", "web_fetch", "write_file"]


@pytest.mark.asyncio
async def test_scenario_c_weeks_1_4_all_allow(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "c", 4, timeout=35)
    import asyncio; await asyncio.sleep(10)  # wait for all weeks
    hist = await proxy.get("/events/history")
    sc_c = [e for e in hist.json() if e["scenario"] == "c"]
    early = [e for e in sc_c if e["session_id"] in ("sess_c1", "sess_c2", "sess_c3", "sess_c4")]
    assert all(e["decision"] == "allow" for e in early), \
        f"Expected all allow in weeks 1-4, got: {[(e['tool'], e['decision']) for e in early]}"


@pytest.mark.asyncio
async def test_scenario_c_week_5_flagged(observe_mode, proxy, agents):
    import asyncio
    await agents.post("/agents/run/c")
    await asyncio.sleep(12)
    hist = await proxy.get("/events/history")
    sc_c = [e for e in hist.json() if e["scenario"] == "c"]
    week5 = [e for e in sc_c if e["session_id"] == "sess_c5"]
    flags = [e for e in week5 if e["decision"] == "flag"]
    assert len(flags) >= 1, f"Expected at least one flag in week 5, got decisions: {[e['decision'] for e in week5]}"


@pytest.mark.asyncio
async def test_scenario_c_week_5_not_blocked(observe_mode, proxy, agents):
    import asyncio
    await agents.post("/agents/run/c")
    await asyncio.sleep(12)
    hist = await proxy.get("/events/history")
    sc_c = [e for e in hist.json() if e["scenario"] == "c"]
    week5 = [e for e in sc_c if e["session_id"] == "sess_c5"]
    blocks = [e for e in week5 if e["decision"] == "block"]
    assert len(blocks) == 0, "Observe mode must not block — only flag"


@pytest.mark.asyncio
async def test_scenario_a_mode_field(observe_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", SCENARIO_A_CALLS)
    sc_a = [e for e in events if e["scenario"] == "a"]
    assert all(e["mode"] == "observe" for e in sc_a)


@pytest.mark.asyncio
async def test_observe_mode_no_trace(observe_mode, proxy, agents):
    """Observe mode should not produce decision traces (no enforcement)."""
    events = await run_and_wait(agents, proxy, "b", SCENARIO_B_CALLS)
    sc_b = [e for e in events if e["scenario"] == "b"]
    # In observe mode, traces are not attached to non-flag events
    non_flag_traces = [e for e in sc_b if e["decision"] == "allow" and e.get("trace")]
    assert len(non_flag_traces) == 0
