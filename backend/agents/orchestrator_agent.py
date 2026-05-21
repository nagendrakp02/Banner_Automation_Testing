
from __future__ import annotations

import traceback
from datetime import datetime

from loguru import logger
from playwright.async_api import async_playwright

from backend.core.config import settings
from backend.core.constants import CheckID, CheckStatus, RunStatus
from backend.services.vision_client import vision_client
from backend.services.broadcaster import broadcaster
from backend.agents.specialist_agents import (
    RenderAgent, VisualAgent, InteractionAgent, PerformanceAgent,
)
from backend.agents.isi_agent import ISIAgent
from backend.db.session import AsyncSessionLocal
from backend.db import models

# Check routing
_ISI_CHECKS = frozenset({
    CheckID.ISI_AUTO_SCROLL,
    CheckID.ISI_WHEEL_SCROLL,
    CheckID.ISI_TEXT_LAYOUT,
})

_NON_ISI_AGENTS: dict[CheckID, type] = {
    CheckID.BANNER_VISIBLE:          RenderAgent,
    CheckID.BORDER_DETECTED:         VisualAgent,
    CheckID.COPY_SELECTION_DISABLED: InteractionAgent,
    CheckID.BANNER_LOAD_TIME:        PerformanceAgent,
}

_PLAN_SYSTEM = (
    "You are QA lead for pharmaceutical digital banner testing. "
    "Given the banner name and the list of checks to run, write 2–3 sentences "
    "summarising your testing strategy. "
    "Highlight any pharma compliance risks specific to these checks. "
    "End with: PLAN READY"
)


class OrchestratorAgent:

    async def run(
        self,
        run_id:      str,
        banner_url:  str,
        banner_name: str,
        check_ids:   list[CheckID],
    ) -> None:
        await broadcaster.emit(
            run_id,
            f"🚀 Starting run: {banner_name}",
            "agent", "orchestrator",
        )

        # ── Mark run as RUNNING ───────────────────────────────────────────────
        async with AsyncSessionLocal() as db:
            run = await db.get(models.TestRun, run_id)
            if not run:
                return
            run.status     = RunStatus.RUNNING
            run.started_at = datetime.utcnow()
            await db.commit()

        # ── Phase 0: Orchestrator plan (text-only LLM) ────────────────────────
        try:
            plan = await vision_client.judge(
                _PLAN_SYSTEM,
                f"Banner: {banner_name}\nURL: {banner_url}\n"
                f"Checks: {[c.value for c in check_ids]}",
                [],   # no screenshots for planning
            )
        except Exception as exc:
            plan = f"[Plan generation failed: {exc}]"
            logger.warning(f"Run {run_id}: plan failed — {exc}")

        await broadcaster.emit(
            run_id, f"📋 Plan: {plan[:300]}", "agent", "orchestrator"
        )
        async with AsyncSessionLocal() as db:
            run = await db.get(models.TestRun, run_id)
            run.orchestrator_reasoning = plan
            await db.commit()

        # ── Phase 1 + 2: Specialist agents ────────────────────────────────────
        results = []
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(
                    headless=settings.playwright_headless,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--ignore-certificate-errors",
                        "--ignore-ssl-errors",
                        "--disable-web-security",
                        "--allow-running-insecure-content",
                        "--disable-features=VizDisplayCompositor",
                    ],
                )
                ctx = await browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    java_script_enabled=True,
                    ignore_https_errors=True,
                    bypass_csp=True,
                )
                page = await ctx.new_page()

                # Navigation with 3-strategy fallback
                await broadcaster.emit(
                    run_id, f"🌐 Navigating to {banner_url}", "info", "orchestrator"
                )
                navigated = False
                for strategy in ("networkidle", "domcontentloaded", "load"):
                    try:
                        await page.goto(
                            banner_url,
                            wait_until=strategy,
                            timeout=settings.playwright_timeout,
                        )
                        navigated = True
                        await broadcaster.emit(
                            run_id,
                            f"✓ Page loaded ({strategy})",
                            "info", "orchestrator",
                        )
                        break
                    except Exception as nav_err:
                        await broadcaster.emit(
                            run_id,
                            f"  ↳ Nav [{strategy}] failed: "
                            f"{str(nav_err)[:80]} — trying next",
                            "warning", "orchestrator",
                        )

                if not navigated:
                    raise RuntimeError(
                        f"All navigation strategies failed for {banner_url}"
                    )

                # Warm-up: allow JS animations / lazy assets to initialise
                await page.wait_for_timeout(2500)
                await broadcaster.emit(
                    run_id, "⏳ Warm-up complete — beginning checks", "info", "orchestrator"
                )

                shot_dir = str(settings.screenshot_dir)

                # Phase 1: Non-ISI checks (sequential)
                non_isi = [c for c in check_ids if c not in _ISI_CHECKS]
                if non_isi:
                    await broadcaster.emit(
                        run_id,
                        f"▶ Phase 1: {len(non_isi)} standard check(s)",
                        "info", "orchestrator",
                    )
                    for cid in non_isi:
                        agent_cls = _NON_ISI_AGENTS.get(cid)
                        if agent_cls:
                            results.append(
                                await agent_cls().run(page, run_id, shot_dir)
                            )

                # Phase 2: ISI suite (sequential within suite)
                isi_requested = [c for c in check_ids if c in _ISI_CHECKS]
                if isi_requested:
                    await broadcaster.emit(
                        run_id,
                        f"▶ Phase 2: ISI suite ({len(isi_requested)} check(s))",
                        "info", "orchestrator",
                    )
                    all_isi = await ISIAgent().run_all(page, run_id, shot_dir)
                    requested_set = set(isi_requested)
                    results.extend(
                        r for r in all_isi if r.check_id in requested_set
                    )

                await browser.close()

        except Exception as exc:
            err = str(exc) or repr(exc) or traceback.format_exc().splitlines()[-1]
            logger.exception(f"Run {run_id} fatal error: {err}")
            await broadcaster.emit(
                run_id, f"💥 Fatal error: {err}", "error", "orchestrator"
            )
            async with AsyncSessionLocal() as db:
                run = await db.get(models.TestRun, run_id)
                run.status       = RunStatus.FAILED
                run.completed_at = datetime.utcnow()
                await db.commit()
            return

        # ── Persist check results ─────────────────────────────────────────────
        passed = sum(1 for r in results if r.status == CheckStatus.PASS)
        failed = sum(1 for r in results if r.status == CheckStatus.FAIL)
        errors = sum(1 for r in results if r.status == CheckStatus.ERROR)

        async with AsyncSessionLocal() as db:
            for r in results:
                # Build confidence annotation for llm_reasoning display
                conf_note = ""
                if r.llm_confidence is not None:
                    conf_note = f"\n\n[Model confidence: {r.llm_confidence}%]"

                db.add(models.CheckResult(
                    run_id          = run_id,
                    check_id        = r.check_id.value,
                    check_name      = r.check_id.value.replace("_", " ").title(),
                    agent_name      = r.agent_name.value,
                    status          = r.status.value,
                    raw_data        = r.raw_data,
                    llm_reasoning   = (r.llm_reasoning or "") + conf_note,
                    llm_verdict     = r.llm_verdict,
                    final_verdict   = r.llm_verdict or r.status.value,
                    screenshot_path = r.screenshot_path,
                    duration_ms     = r.duration_ms,
                    error_message   = r.error_message,
                    executed_at     = r.executed_at,
                ))

            run = await db.get(models.TestRun, run_id)
            run.status        = RunStatus.COMPLETED
            run.completed_at  = datetime.utcnow()
            run.total_checks  = len(results)
            run.passed_checks = passed
            run.failed_checks = failed
            run.error_checks  = errors
            await db.commit()

        summary = (
            f"🏁 Run complete: "
            f"✅ {passed} passed · "
            f"❌ {failed} failed · "
            f"⚠️ {errors} errors"
        )
        await broadcaster.emit(run_id, summary, "result", "orchestrator")
        logger.info(f"Run {run_id}: {summary}")
