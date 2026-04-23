"""15 tests for govern mode — pre-execution policy enforcement."""
import json
import pytest
import pytest_asyncio
from conftest import run_and_wait


@pytest.mark.asyncio
async def test_scenario_a_block_before_call_8(govern_mode, proxy, agents):
    import asyncio; await asyncio.sleep(0)
    events = await run_and_wait(agents, proxy, "a", 7, timeout=30)
    sc_a = [e for e in events if e["scenario"] == "a"]
    blocks = [e for e in sc_a if e["decision"] == "block"]
    assert len(blocks) >= 1, "Expected at least one block in Scenario A"
    # The first block must occur at or before event index 7 (call 7)
    first_block_idx = next(i for i, e in enumerate(sc_a) if e["decision"] == "block")
    assert first_block_idx < 8, f"First block at index {first_block_idx}, expected < 8"


@pytest.mark.asyncio
async def test_scenario_a_flag_at_call_4(govern_mode, proxy, agents):
    import asyncio; await asyncio.sleep(0)
    events = await run_and_wait(agents, proxy, "a", 4, timeout=30)
    sc_a = [e for e in events if e["scenario"] == "a"]
    assert len(sc_a) >= 4
    # Call 4 (index 3) should be a flag
    assert sc_a[3]["decision"] == "flag", f"Expected flag at call 4, got {sc_a[3]['decision']}"


@pytest.mark.asyncio
async def test_scenario_a_decision_trace_sealed(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", 7, timeout=30)
    sc_a = [e for e in events if e["scenario"] == "a"]
    blocks = [e for e in sc_a if e["decision"] == "block"]
    assert len(blocks) >= 1
    trace = blocks[0].get("trace")
    assert trace is not None, "Block event must have a decision trace"


@pytest.mark.asyncio
async def test_scenario_a_trace_contains_session_count(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", 7, timeout=30)
    sc_a = [e for e in events if e["scenario"] == "a"]
    blocks = [e for e in sc_a if e["decision"] == "block"]
    trace = blocks[0]["trace"]
    dlp = trace["checks"]["dlp"]
    assert dlp["session_count"] >= 1


@pytest.mark.asyncio
async def test_scenario_a_trace_contains_field_count(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", 7, timeout=30)
    sc_a = [e for e in events if e["scenario"] == "a"]
    blocks = [e for e in sc_a if e["decision"] == "block"]
    trace = blocks[0]["trace"]
    dlp = trace["checks"]["dlp"]
    assert dlp["field_count"] >= 7


@pytest.mark.asyncio
async def test_scenario_a_trace_contains_pii_categories(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "a", 7, timeout=30)
    sc_a = [e for e in events if e["scenario"] == "a"]
    blocks = [e for e in sc_a if e["decision"] == "block"]
    trace = blocks[0]["trace"]
    dlp = trace["checks"]["dlp"]
    assert len(dlp["pii_categories"]) >= 1


@pytest.mark.asyncio
async def test_scenario_b_injection_detected_in_response(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "b", 2, timeout=30)
    sc_b = [e for e in events if e["scenario"] == "b"]
    web_fetch_events = [e for e in sc_b if e["tool"] == "web_fetch"]
    assert len(web_fetch_events) == 1
    assert web_fetch_events[0]["decision"] == "flag", \
        f"web_fetch should be flagged for response injection, got {web_fetch_events[0]['decision']}"


@pytest.mark.asyncio
async def test_scenario_b_write_file_never_forwarded(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "b", 3, timeout=30)
    sc_b = [e for e in events if e["scenario"] == "b"]
    write_events = [e for e in sc_b if e["tool"] == "write_file"]
    assert len(write_events) == 1
    assert write_events[0]["decision"] == "block", \
        f"write_file to /etc/crontab must be blocked, got {write_events[0]['decision']}"


@pytest.mark.asyncio
async def test_scenario_b_write_file_decision_trace(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "b", 3, timeout=30)
    sc_b = [e for e in events if e["scenario"] == "b"]
    write_events = [e for e in sc_b if e["tool"] == "write_file"]
    trace = write_events[0].get("trace")
    assert trace is not None


@pytest.mark.asyncio
async def test_scenario_b_trace_contains_injection_payload(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "b", 3, timeout=30)
    sc_b = [e for e in events if e["scenario"] == "b"]
    write_events = [e for e in sc_b if e["tool"] == "write_file"]
    trace = write_events[0]["trace"]
    inj = trace["checks"]["injection_scan"]
    assert inj["found"] is True
    assert inj["evidence"] is not None


@pytest.mark.asyncio
async def test_scenario_c_query_external_blocked_week_2(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "c", 4, timeout=35)
    sc_c = [e for e in events if e["scenario"] == "c"]
    week2 = [e for e in sc_c if e["session_id"] == "sess_c2"]
    ext_api = [e for e in week2 if e["tool"] == "query_external_api"]
    assert len(ext_api) == 1
    assert ext_api[0]["decision"] == "block", \
        f"query_external_api must be blocked in week 2, got {ext_api[0]['decision']}"


@pytest.mark.asyncio
async def test_scenario_c_week_1_all_allow(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "c", 3, timeout=35)
    sc_c = [e for e in events if e["scenario"] == "c"]
    week1 = [e for e in sc_c if e["session_id"] == "sess_c1"]
    assert all(e["decision"] == "allow" for e in week1), \
        f"Week 1 must be all allow, got {[(e['tool'], e['decision']) for e in week1]}"


@pytest.mark.asyncio
async def test_scenario_c_subsequent_weeks_not_normalized(govern_mode, proxy, agents):
    """Later weeks must keep getting blocked — the policy never adapts."""
    import asyncio; await asyncio.sleep(0)
    events = await run_and_wait(agents, proxy, "c", 4, timeout=35)
    await asyncio.sleep(6)
    hist = await proxy.get("/events/history")
    sc_c = [e for e in hist.json() if e["scenario"] == "c"]
    week3 = [e for e in sc_c if e["session_id"] == "sess_c3"]
    non_approved = [e for e in week3 if e["tool"] not in ("read_docs", "query_db", "generate_report")]
    assert all(e["decision"] == "block" for e in non_approved), \
        f"All non-approved tools in week 3 must still be blocked: {[(e['tool'], e['decision']) for e in non_approved]}"


@pytest.mark.asyncio
async def test_scenario_c_trace_shows_fixed_policy(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "c", 4, timeout=35)
    sc_c = [e for e in events if e["scenario"] == "c"]
    blocks = [e for e in sc_c if e["decision"] == "block"]
    assert len(blocks) >= 1
    trace = blocks[0]["trace"]
    drift = trace["checks"]["drift"]
    assert drift["policy_violation"] is True
    bd = drift["baseline_delta"]
    assert bd is not None
    assert "approved_tools" in bd


@pytest.mark.asyncio
async def test_govern_mode_field_set_correctly(govern_mode, proxy, agents):
    events = await run_and_wait(agents, proxy, "b", 3, timeout=30)
    sc_b = [e for e in events if e["scenario"] == "b"]
    assert all(e["mode"] == "govern" for e in sc_b)
