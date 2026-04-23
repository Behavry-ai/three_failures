import asyncio
import os

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import scenario_a
import scenario_b
import scenario_c

PROXY_URL = os.getenv("PROXY_URL", "http://lab-proxy:8000")

app = FastAPI(title="Three Failures Lab Agents")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_SCENARIOS = {"a": scenario_a.run, "b": scenario_b.run, "c": scenario_c.run}


async def _reset_proxy():
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(f"{PROXY_URL}/admin/reset")
        except Exception:
            pass


async def _notify_complete(scenario: str):
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(f"{PROXY_URL}/admin/complete", json={"scenario": scenario})
        except Exception:
            pass


async def _run_dual(fn, scenario: str):
    await asyncio.gather(fn("observe"), fn("govern"))
    await _notify_complete(scenario)


@app.post("/agents/run/{scenario}")
async def run_scenario(scenario: str):
    fn = _SCENARIOS.get(scenario.lower())
    if fn is None:
        raise HTTPException(400, f"Unknown scenario '{scenario}'. Use a, b, or c.")
    await _reset_proxy()
    asyncio.create_task(_run_dual(fn, scenario.lower()))
    return {"status": "started", "scenario": scenario.lower()}


@app.get("/health")
async def health():
    return {"status": "ok"}
