

"""api/routes.py — BannerMind v8 Enterprise API Routes"""
import uuid
from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter, Depends, HTTPException, BackgroundTasks,
    WebSocket, WebSocketDisconnect,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from loguru import logger

from backend.db.session import get_db
from backend.db import models
from backend.core.constants import CheckID, RunStatus, CHECK_LABELS, CHECK_AGENT_MAP
from backend.agents.orchestrator_agent import OrchestratorAgent
from backend.services.broadcaster import broadcaster
from backend.services.vision_client import vision_client

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class BannerCreate(BaseModel):
    url_id:     str
    name:       str
    url:        str
    client:     Optional[str] = None
    dimensions: Optional[str] = None


class BannerOut(BaseModel):
    id: str; url_id: str; name: str; url: str
    client: Optional[str]; dimensions: Optional[str]
    is_active: bool; created_at: datetime
    class Config: from_attributes = True


class RunCreate(BaseModel):
    banner_id:    str
    check_ids:    list[str]
    triggered_by: str = "manual"


class CheckResultOut(BaseModel):
    id: str; check_id: str; check_name: str; agent_name: str; status: str
    raw_data:       Optional[dict]
    llm_reasoning:  Optional[str]
    llm_verdict:    Optional[str]
    final_verdict:  Optional[str]
    screenshot_path: Optional[str]
    duration_ms:    Optional[float]
    error_message:  Optional[str]
    executed_at:    Optional[datetime]
    class Config: from_attributes = True


class RunOut(BaseModel):
    id: str; banner_id: str; status: str; triggered_by: str
    total_checks: int; passed_checks: int; failed_checks: int; error_checks: int
    started_at:             Optional[datetime]
    completed_at:           Optional[datetime]
    orchestrator_reasoning: Optional[str]
    created_at:             datetime
    check_results:          list[CheckResultOut] = []
    class Config: from_attributes = True


# ── Routers ───────────────────────────────────────────────────────────────────
banners_router = APIRouter(prefix="/banners", tags=["banners"])
runs_router    = APIRouter(prefix="/runs",    tags=["runs"])
ws_router      = APIRouter(tags=["websocket"])
misc_router    = APIRouter(tags=["misc"])


# ── Banners ───────────────────────────────────────────────────────────────────

@banners_router.get("/", response_model=list[BannerOut])
async def list_banners(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.Banner).order_by(models.Banner.created_at.desc())
    )
    return result.scalars().all()


@banners_router.post("/", response_model=BannerOut, status_code=201)
async def create_banner(payload: BannerCreate, db: AsyncSession = Depends(get_db)):
    ex = await db.execute(
        select(models.Banner).where(models.Banner.url_id == payload.url_id)
    )
    if ex.scalar_one_or_none():
        raise HTTPException(409, f"url_id '{payload.url_id}' already exists")
    b = models.Banner(**payload.model_dump())
    db.add(b)
    await db.commit()
    await db.refresh(b)
    return b


@banners_router.patch("/{bid}", response_model=BannerOut)
async def update_banner(bid: str, payload: dict, db: AsyncSession = Depends(get_db)):
    b = await db.get(models.Banner, bid)
    if not b:
        raise HTTPException(404, "Banner not found")
    for k, v in payload.items():
        if hasattr(b, k):
            setattr(b, k, v)
    await db.commit()
    await db.refresh(b)
    return b


@banners_router.delete("/{bid}", status_code=204)
async def delete_banner(bid: str, db: AsyncSession = Depends(get_db)):
    b = await db.get(models.Banner, bid)
    if not b:
        raise HTTPException(404, "Banner not found")
    await db.delete(b)
    await db.commit()


# ── Runs ──────────────────────────────────────────────────────────────────────

async def _fire_run(run_id: str, url: str, name: str, checks: list[CheckID]):
    await OrchestratorAgent().run(run_id, url, name, checks)


@runs_router.post("/", response_model=RunOut, status_code=202)
async def create_run(
    payload: RunCreate,
    bg:      BackgroundTasks,
    db:      AsyncSession = Depends(get_db),
):
    banner = await db.get(models.Banner, payload.banner_id)
    if not banner:
        raise HTTPException(404, "Banner not found")

    valid = {c.value for c in CheckID}
    bad   = [c for c in payload.check_ids if c not in valid]
    if bad:
        raise HTTPException(422, f"Invalid check IDs: {bad}")

    checks = [CheckID(c) for c in payload.check_ids]
    run    = models.TestRun(
        id           = str(uuid.uuid4()),
        banner_id    = banner.id,
        status       = RunStatus.PENDING,
        triggered_by = payload.triggered_by,
        total_checks = len(checks),
        created_at   = datetime.utcnow(),
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    bg.add_task(_fire_run, run.id, banner.url, banner.name, checks)

    return RunOut(
        id=run.id, banner_id=run.banner_id, status=run.status,
        triggered_by=run.triggered_by, total_checks=run.total_checks,
        passed_checks=0, failed_checks=0, error_checks=0,
        started_at=None, completed_at=None, orchestrator_reasoning=None,
        created_at=run.created_at, check_results=[],
    )


@runs_router.get("/", response_model=list[RunOut])
async def list_runs(
    banner_id: Optional[str] = None,
    limit:     int            = 50,
    db:        AsyncSession   = Depends(get_db),
):
    q = (
        select(models.TestRun)
        .options(selectinload(models.TestRun.check_results))
        .order_by(models.TestRun.created_at.desc())
        .limit(limit)
    )
    if banner_id:
        q = q.where(models.TestRun.banner_id == banner_id)
    return (await db.execute(q)).scalars().all()


@runs_router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(models.TestRun)
        .options(selectinload(models.TestRun.check_results))
        .where(models.TestRun.id == run_id)
    )
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(404, "Run not found")
    return r


@runs_router.delete("/{run_id}", status_code=204)
async def delete_run(run_id: str, db: AsyncSession = Depends(get_db)):
    r = await db.get(models.TestRun, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    await db.delete(r)
    await db.commit()


# ── WebSocket live log ────────────────────────────────────────────────────────

@ws_router.websocket("/ws/runs/{run_id}")
async def run_ws(ws: WebSocket, run_id: str):
    await ws.accept()
    logger.info(f"WS connected: run {run_id}")

    async def send(payload: str):
        await ws.send_text(payload)

    broadcaster.subscribe(run_id, send)
    try:
        while True:
            await ws.receive_text()   # keep alive; client sends nothing
    except WebSocketDisconnect:
        logger.info(f"WS disconnected: run {run_id}")
    finally:
        broadcaster.unsubscribe(run_id, send)


# ── Health + metadata ─────────────────────────────────────────────────────────

@misc_router.get("/health")
async def health():
    model_info = await vision_client.get_model_info()
    return {
        "status":          "ok",
        "version":         "8.0.0",
        "vision_backend":  "ollama",
        "ollama_running":  model_info["ollama_running"],
        "active_model":    model_info["active_model"],
        "model_pulled":    model_info["model_pulled"],
        "vision_models":   model_info["vision_models"],
        "ollama_url":      model_info["ollama_url"],
        "setup_hint": (
            None if model_info["model_pulled"]
            else (
                f"Model not pulled. Run: "
                f"ollama pull {model_info.get('active_model','llava:13b')}"
            )
        ),
    }


@misc_router.get("/checks")
async def list_checks():
    return [
        {
            "id":    c.value,
            "name":  CHECK_LABELS[c],
            "agent": CHECK_AGENT_MAP[c].value,
        }
        for c in CheckID
    ]