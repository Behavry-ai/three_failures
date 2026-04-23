import asyncio
import time

import httpx
import pytest
import pytest_asyncio

PROXY   = "http://localhost:8100"
TARGETS = "http://localhost:8101"
AGENTS  = "http://localhost:8102"
UI      = "http://localhost:3100"

SCENARIO_A_CALLS = 16   # 4 sessions × 4 PII tools
SCENARIO_B_CALLS = 3
SCENARIO_C_CALLS = 12   # 3+2+3+2+2


def _wait_for(url: str, timeout: int = 30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            httpx.get(url, timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    pytest.skip(f"Service not available: {url}")


@pytest.fixture(scope="session", autouse=True)
def services_up():
    for url in [f"{PROXY}/health", f"{TARGETS}/health", f"{AGENTS}/health"]:
        _wait_for(url)


@pytest_asyncio.fixture
async def proxy():
    async with httpx.AsyncClient(base_url=PROXY, timeout=60.0) as client:
        yield client


@pytest_asyncio.fixture
async def agents():
    async with httpx.AsyncClient(base_url=AGENTS, timeout=60.0) as client:
        yield client


@pytest_asyncio.fixture
async def targets():
    async with httpx.AsyncClient(base_url=TARGETS, timeout=10.0) as client:
        yield client


@pytest_asyncio.fixture(autouse=True)
async def reset_state(proxy):
    await proxy.post("/admin/reset")
    yield
    await proxy.post("/admin/reset")


@pytest_asyncio.fixture
async def observe_mode(proxy):
    await proxy.post("/admin/mode", json={"mode": "observe"})
    yield


@pytest_asyncio.fixture
async def govern_mode(proxy):
    await proxy.post("/admin/mode", json={"mode": "govern"})
    yield


async def run_and_wait(agents_client: httpx.AsyncClient, proxy_client: httpx.AsyncClient, scenario: str, expected_calls: int, timeout: int = 30):
    """Trigger a scenario and poll until all expected events land in the history."""
    await agents_client.post(f"/agents/run/{scenario}")
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        hist = await proxy_client.get("/events/history")
        events = hist.json()
        if len(events) >= expected_calls:
            return events
        await asyncio.sleep(0.3)
    hist = await proxy_client.get("/events/history")
    return hist.json()
