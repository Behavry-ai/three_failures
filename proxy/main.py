import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

import decision_trace as _dtrace
import dlp as _dlp
import drift_tracker as _dt
import govern_mode
import observe_mode
from db import clear_events, get_all_events, init_db, insert_event
from models import ToolDecision, ToolRequest

TARGETS_URL = os.getenv("TARGETS_URL", "http://lab-targets:8001")

_current_mode = os.getenv("LAB_MODE", "observe")
_subscribers: list[asyncio.Queue] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(title="Three Failures Lab Proxy", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _forward(request: ToolRequest) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{TARGETS_URL}/tools/{request.tool_name}",
                json=request.params,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"error": str(exc), "tool": request.tool_name}


async def _broadcast(event: dict):
    dead = []
    for q in _subscribers:
        try:
            await q.put(event)
        except Exception:
            dead.append(q)
    for q in dead:
        _subscribers.remove(q)


async def _record_and_broadcast(request: ToolRequest, decision: ToolDecision, mode: str):
    event = {
        "id": f"evt_{uuid.uuid4().hex[:8]}",
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "scenario": request.scenario,
        "agent_id": request.agent_id,
        "session_id": request.session_id,
        "tool": request.tool_name,
        "params": request.params,
        "decision": decision.decision,
        "reason": decision.reason,
        "trace": decision.trace,
    }
    await insert_event({
        **event,
        "params": json.dumps(event["params"]),
        "trace": json.dumps(event["trace"]) if event["trace"] else None,
    })
    await _broadcast(event)
    return event


@app.post("/tool/{tool_name}")
async def tool_call(
    tool_name: str,
    body: dict,
    x_session_id: str = Header(default="unknown"),
    x_agent_id: str = Header(default="unknown"),
    x_scenario: str | None = Header(default=None),
    x_mode: str | None = Header(default=None),  # per-request override for dual-mode runs
):
    global _current_mode
    mode = x_mode if x_mode in ("observe", "govern") else _current_mode
    params = body.get("params", body)
    request = ToolRequest(
        tool_name=tool_name,
        agent_id=x_agent_id,
        session_id=x_session_id,
        params=params,
        scenario=x_scenario,
    )

    if mode == "govern":
        decision = await govern_mode.handle(request, _forward)
    else:
        decision = await observe_mode.handle(request, _forward)

    await _record_and_broadcast(request, decision, mode)

    if not decision.allowed:
        return {
            "blocked": True,
            "decision": decision.decision,
            "reason": decision.reason,
            "trace": decision.trace,
        }

    return {
        "blocked": False,
        "decision": decision.decision,
        "reason": decision.reason,
        "response": decision.response,
        "trace": decision.trace,
    }


@app.get("/events")
async def events():
    async def _stream():
        q: asyncio.Queue = asyncio.Queue()
        _subscribers.append(q)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=20.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        except GeneratorExit:
            pass
        finally:
            try:
                _subscribers.remove(q)
            except ValueError:
                pass

    return StreamingResponse(_stream(), media_type="text/event-stream")


@app.post("/admin/mode")
async def set_mode(body: dict):
    global _current_mode
    mode = body.get("mode", "observe")
    if mode not in ("observe", "govern"):
        raise HTTPException(400, "mode must be 'observe' or 'govern'")
    _current_mode = mode
    _dlp.tracker.reset()
    _dt.tracker.reset()
    await clear_events()
    await _broadcast({"type": "mode_changed", "mode": mode})
    return {"mode": _current_mode}


@app.post("/admin/reset")
async def reset():
    _dlp.tracker.reset()
    _dt.tracker.reset()
    _dtrace.reset_chain()
    await clear_events()
    await _broadcast({"type": "reset"})
    return {"status": "ok"}


@app.get("/admin/mode")
async def get_mode():
    return {"mode": _current_mode}


@app.get("/events/history")
async def history():
    return await get_all_events()


@app.post("/admin/complete")
async def scenario_complete(body: dict):
    await _broadcast({"type": "scenario_complete", "scenario": body.get("scenario")})
    return {"status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok", "mode": _current_mode}
