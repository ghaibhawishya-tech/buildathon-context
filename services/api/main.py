"""HTTP interface for the lab and external gateway consumers."""
import asyncio
import json
import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .gateway import SCENARIOS, authorize, envelope, scoped_facts
from .runner import run_agent

WEB = Path(__file__).resolve().parents[2] / "apps" / "web"
app = FastAPI(title="Ghost Shield Gateway")
app.mount("/assets", StaticFiles(directory=WEB), name="assets")
live_slots = asyncio.Semaphore(1)


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["shopping", "research", "workspace"]
    note: str = Field(default="", max_length=2000)


class RunInput(SourceInput):
    mode: Literal["fixture", "live"] = "fixture"
    rehearsal: Literal["read_private_note", "send_message"] | None = None


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str | None = Field(default=None, max_length=80)
    proposal: object = None


@contextmanager
def database():
    conn = sqlite3.connect(os.getenv("GHOST_DB", "ghost-shield.sqlite3"))
    try:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, report TEXT NOT NULL)")
            yield conn
    finally:
        conn.close()


@app.middleware("http")
async def request_limit(request: Request, call_next):
    if request.method == "POST":
        if request.headers.get("transfer-encoding"):
            return JSONResponse({"detail": "Content-Length is required."}, status_code=411)
        length = request.headers.get("content-length", "")
        if not length.isdecimal() or len(length) > 5 or int(length) > 16384:
            return JSONResponse({"detail": "Request body exceeds the allowed size."}, status_code=413)
    return await call_next(request)


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB / "index.html", headers={
        "Content-Security-Policy": "default-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
    })


@app.get("/health")
def health():
    return {"status": "ok", "live_configured": bool(os.getenv("GHOST_MODEL_KEY") and os.getenv("GHOST_LAB_TOKEN"))}


@app.get("/scenarios")
def scenarios():
    return {key: {"title": item.title, "task": item.task, "resource": item.resource}
            for key, item in SCENARIOS.items()}


@app.post("/gateway/evaluate-content")
def evaluate_content(body: SourceInput):
    scenario = SCENARIOS[body.scenario]
    source = envelope(scenario, body.note)
    return {"source": source, "scoped": scoped_facts(scenario, source)}


@app.post("/gateway/authorize-action")
def authorize_action(body: PolicyInput):
    return {**authorize(body.scenario, body.proposal), "executed": False, "side_effect": False}


@app.post("/runs", status_code=201)
async def create_run(body: RunInput, authorization: str = Header(default="")):
    if body.mode == "live":
        token = os.getenv("GHOST_LAB_TOKEN")
        if not os.getenv("GHOST_MODEL_KEY") or not token:
            raise HTTPException(503, "Live models need GHOST_MODEL_KEY and GHOST_LAB_TOKEN.")
        if not secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401, "A valid lab token is required for live runs.")
        if live_slots.locked():
            raise HTTPException(429, "A live run is already in progress.")
        async with live_slots:
            try:
                report = await asyncio.wait_for(run_agent(body.scenario, body.note, body.mode, body.rehearsal), timeout=45)
            except TimeoutError:
                raise HTTPException(504, "The model exceeded the run deadline.") from None
    else:
        report = await run_agent(body.scenario, body.note, body.mode, body.rehearsal)

    report.update(id=str(uuid4()), created_at=datetime.now(timezone.utc).isoformat())
    with database() as conn:
        conn.execute("INSERT INTO runs VALUES (?, ?)", (report["id"], json.dumps(report)))
    return report


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    with database() as conn:
        row = conn.execute("SELECT report FROM runs WHERE id = ?", (run_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Run not found.")
    return json.loads(row[0])


@app.get("/runs/{run_id}/events")
def get_events(run_id: str):
    return get_run(run_id)["events"]


@app.get("/metrics")
def metrics():
    with database() as conn:
        records = [json.loads(row[0]) for row in conn.execute("SELECT report FROM runs ORDER BY rowid DESC")]
    groups = {}
    for mode in ("fixture", "live"):
        runs = [run for run in records if run["mode"] == mode]
        groups[mode] = {
            "recorded": len(runs),
            "evaluated": sum(run["task_completed"] is not None for run in runs),
            "completed": sum(run["task_completed"] is True for run in runs),
            "blocked": sum(event["decision"] == "DENY" for run in runs for event in run["events"]),
            "average_duration_ms": round(sum(run["duration_ms"] for run in runs) / len(runs), 2) if runs else None,
        }
    recent = [{key: run[key] for key in ("id", "scenario", "mode", "task_completed", "created_at")}
              for run in records[:12]]
    return {"by_mode": groups, "recent": recent}
