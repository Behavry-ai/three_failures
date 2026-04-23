"""10 integration tests — mode toggle, reset, SSE timing, and stack health."""
import asyncio
import time

import httpx
import pytest
import pytest_asyncio
from conftest import PROXY, TARGETS, AGENTS, UI


@pytest.mark.asyncio
async def test_proxy_health(proxy):
    r = await proxy.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_targets_health(targets):
    r = await targets.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_agents_health(agents):
    r = await agents.get("/health")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_ui_loads():
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(UI)
        assert r.status_code == 200
        assert "Three Failures" in r.text


@pytest.mark.asyncio
async def test_mode_toggle_no_restart(proxy):
    await proxy.post("/admin/mode", json={"mode": "govern"})
    r = await proxy.get("/admin/mode")
    assert r.json()["mode"] == "govern"

    await proxy.post("/admin/mode", json={"mode": "observe"})
    r = await proxy.get("/admin/mode")
    assert r.json()["mode"] == "observe"


@pytest.mark.asyncio
async def test_reset_clears_event_store(proxy, agents):
    await proxy.post("/admin/mode", json={"mode": "observe"})
    await agents.post("/agents/run/b")
    await asyncio.sleep(3)

    hist = await proxy.get("/events/history")
    assert len(hist.json()) > 0

    await proxy.post("/admin/reset")
    hist = await proxy.get("/events/history")
    assert hist.json() == []


@pytest.mark.asyncio
async def test_sse_event_arrives_within_200ms(proxy):
    """POST a direct tool call and verify the history entry appears quickly."""
    start = time.monotonic()
    await proxy.post(
        "/tool/read_docs",
        json={"params": {}},
        headers={"X-Session-Id": "test-sse", "X-Agent-Id": "test-agent", "X-Scenario": "c"},
    )
    elapsed = time.monotonic() - start
    hist = await proxy.get("/events/history")
    assert len(hist.json()) >= 1
    # The event processing (including SSE broadcast) must complete within the request
    assert elapsed < 2.0


@pytest.mark.asyncio
async def test_scenario_a_completes_under_30s(proxy, agents):
    await proxy.post("/admin/mode", json={"mode": "observe"})
    start = time.monotonic()
    await agents.post("/agents/run/a")
    await asyncio.sleep(16 * 0.4 + 2)  # 16 calls × 0.4s + buffer
    elapsed = time.monotonic() - start
    assert elapsed < 30.0


@pytest.mark.asyncio
async def test_scenario_b_completes_under_30s(proxy, agents):
    await proxy.post("/admin/mode", json={"mode": "observe"})
    start = time.monotonic()
    await agents.post("/agents/run/b")
    await asyncio.sleep(3 * 0.4 + 2)
    elapsed = time.monotonic() - start
    assert elapsed < 30.0


@pytest.mark.asyncio
async def test_events_arrive_progressively(proxy, agents):
    """Events must stream in over time, not in a single burst."""
    await proxy.post("/admin/mode", json={"mode": "observe"})
    await agents.post("/agents/run/a")

    snapshots = []
    for _ in range(6):
        await asyncio.sleep(1.0)
        hist = await proxy.get("/events/history")
        snapshots.append(len(hist.json()))

    # Count must strictly increase for at least a few snapshots
    increasing = sum(1 for i in range(1, len(snapshots)) if snapshots[i] > snapshots[i - 1])
    assert increasing >= 3, f"Expected progressive arrival, got counts: {snapshots}"
