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
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .gateway import SCENARIOS, authorize, envelope, scoped_facts
from .runner import run_agent
from .sources import SHOPPING_PAGES, SOURCE_PAGES, STORE_SLUGS, extract_sources, render_storefront

WEB = Path(__file__).resolve().parents[2] / "apps" / "web"
app = FastAPI(title="Ghost Shield Gateway")
app.mount("/assets", StaticFiles(directory=WEB), name="assets")
live_slots = asyncio.Semaphore(1)


class SourceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["shopping", "research", "workspace"]
    note: str = Field(default="", max_length=2000)
    pages: dict[str, str] | None = None


class RunInput(SourceInput):
    mode: Literal["fixture", "live"] = "fixture"
    rehearsal: Literal["read_private_note", "send_message"] | None = None


class PolicyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str | None = Field(default=None, max_length=80)
    proposal: object = None


@contextmanager
def database():
    conn = sqlite3.connect(os.getenv("GHOST_DB", "ghost-shield.sqlite3"), timeout=2)
    try:
        with conn:
            conn.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, report TEXT NOT NULL)")
            yield conn
    finally:
        conn.close()


def save_run(report: dict) -> None:
    payload = json.dumps(report, ensure_ascii=False, allow_nan=False)
    payload.encode("utf-8")
    with database() as conn:
        conn.execute("INSERT INTO runs VALUES (?, ?)", (report["id"], payload))


@app.exception_handler(sqlite3.Error)
async def database_failure(request: Request, error: sqlite3.Error):
    return JSONResponse({"detail": "The run store is unavailable. Check the server database."}, status_code=503)


@app.middleware("http")
async def request_limit(request: Request, call_next):
    if request.method == "POST":
        if request.headers.get("transfer-encoding"):
            return JSONResponse({"detail": "Content-Length is required."}, status_code=411)
        length = request.headers.get("content-length", "")
        if not length.isdecimal() or len(length) > 5 or int(length) > 65536:
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


@app.get("/stores/{slug}", response_class=HTMLResponse, include_in_schema=False)
def storefront(slug: str, draft: str | None = None):
    title = STORE_SLUGS.get(slug)
    if title is None:
        raise HTTPException(404, "Store not found.")
    if draft is not None and len(draft) > 3000:
        raise HTTPException(422, "Store draft is too long.")
    return HTMLResponse(
        render_storefront(title, SHOPPING_PAGES[title] if draft is None else draft),
        headers={"Content-Security-Policy": "default-src 'none'; style-src 'self'; script-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
                 "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"},
    )


@app.get("/source-pages/{scenario}")
def source_pages(scenario: str):
    if scenario not in SOURCE_PAGES:
        raise HTTPException(404, "Scenario not found.")
    return SOURCE_PAGES[scenario]


def resolve_sources(body: SourceInput):
    pages = SOURCE_PAGES[body.scenario] if body.pages is None else body.pages
    if any(len(page) > 3000 for page in pages.values()):
        raise HTTPException(422, "Each source page must be at most 3,000 characters.")
    try:
        return pages, extract_sources(body.scenario, pages)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/gateway/evaluate-content")
def evaluate_content(body: SourceInput):
    scenario = SCENARIOS[body.scenario]
    pages, extracted = resolve_sources(body)
    source = envelope(scenario, body.note, pages)
    return {"source": source, "scoped": scoped_facts(source, extracted)}


@app.post("/gateway/authorize-action")
def authorize_action(body: PolicyInput):
    return {**authorize(body.scenario, body.proposal), "executed": False, "side_effect": False}


@app.post("/runs", status_code=201)
async def create_run(body: RunInput, authorization: str = Header(default="")):
    pages, extracted = resolve_sources(body)
    if body.mode == "live":
        token = os.getenv("GHOST_LAB_TOKEN")
        if not os.getenv("GHOST_MODEL_KEY") or not token:
            raise HTTPException(503, "Live models need GHOST_MODEL_KEY and GHOST_LAB_TOKEN.")
        if not secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
            raise HTTPException(401, "A valid lab token is required for live runs.")
        if live_slots.locked():
            raise HTTPException(429, "A live run is already in progress.")
        async with live_slots:
            report = await run_agent(body.scenario, body.note, body.mode, body.rehearsal, pages, extracted)
    else:
        report = await run_agent(body.scenario, body.note, body.mode, body.rehearsal, pages, extracted)

    report.update(id=str(uuid4()), created_at=datetime.now(timezone.utc).isoformat())
    await asyncio.to_thread(save_run, report)
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
    groups = {
        mode: dict(recorded=0, evaluated=0, completed=0, blocked=0, model_denials=0,
                   rehearsal_denials=0, average_duration_ms=None)
        for mode in ("fixture", "live")
    }
    with database() as conn:
        conn.row_factory = sqlite3.Row
        for row in conn.execute("""
            SELECT report ->> '$.mode' AS mode, COUNT(*) AS recorded,
                   COUNT(report ->> '$.task_completed') AS evaluated,
                   COALESCE(SUM(report ->> '$.task_completed'), 0) AS completed,
                   ROUND(AVG(report ->> '$.duration_ms'), 2) AS average_duration_ms
            FROM runs GROUP BY mode
        """):
            values = dict(row)
            groups[values.pop("mode")].update(values)
        for row in conn.execute("""
            SELECT report ->> '$.mode' AS mode, value ->> '$.origin' AS origin, COUNT(*) AS denied
            FROM runs, json_each(runs.report, '$.events')
            WHERE value ->> '$.decision' = 'DENY' GROUP BY mode, origin
        """):
            stats = groups[row["mode"]]
            stats["blocked"] += row["denied"]
            if row["origin"] == "model":
                stats["model_denials"] += row["denied"]
            elif row["origin"] == "manual rehearsal":
                stats["rehearsal_denials"] += row["denied"]
        recent = [json.loads(row[0]) for row in conn.execute("""
            SELECT json_object('id', id, 'scenario', report -> '$.scenario',
                'mode', report -> '$.mode', 'task_completed', report -> '$.task_completed',
                'created_at', report -> '$.created_at')
            FROM runs ORDER BY rowid DESC LIMIT 12
        """)]
    return {"by_mode": groups, "recent": recent}
