
from __future__ import annotations

import asyncio
import os
import re
import time
from datetime import datetime

from loguru import logger

from backend.agents.base_agent import AgentResult, QA_PERSONA
from backend.core.constants import AgentName, CheckID, CheckStatus
from backend.services.vision_client import vision_client, OllamaError
from backend.services import screenshot as ss
from backend.services.broadcaster import broadcaster


# ─────────────────────────────────────────────────────────────────────────────
# Pharma signal detection — runs in every accessible frame
# ─────────────────────────────────────────────────────────────────────────────
_PHARMA_SIGNAL_JS = """() => {
    const text = (document.body || document.documentElement).innerText || '';
    const html  = (document.body || document.documentElement).innerHTML || '';
    const lower = text.toLowerCase();
    const SIGNALS = [
        'important safety information',
        'prescribing information',
        'indication',
        'contraindication',
        'warnings and precautions',
        'adverse reaction',
        'full prescribing',
        'medication guide',
        'see full',
        'isi',
    ];
    const found = SIGNALS.filter(s => lower.includes(s));
    // Also look for drug-name patterns: registered trademark next to caps word
    const hasDrugName = /[A-Z]{4,}[®™]/.test(text) || /[®™]\s*[A-Z]{3,}/.test(text);
    return {
        pharmaSignals:    found,
        hasDrugName:      hasDrugName,
        textLength:       text.length,
        isPharmaBanner:   found.length > 0 || hasDrugName,
        sampleText:       text.substring(0, 300),
    };
}"""

# ─────────────────────────────────────────────────────────────────────────────
# ISI element scanner — handles GWD clip-box pattern + native scrollers
# ─────────────────────────────────────────────────────────────────────────────
_ISI_FIND_JS = """() => {
    const ISI_ID_KW  = ['isi','important-safety','important_safety','isi-area','isi-panel','isi-container','prescribing','safety-info','pfi'];
    const ISI_CLS_KW = ['isi','safety','prescribing','important-safety'];

    function matchesKeyword(el, kwList) {
        const id  = (el.id  || '').toLowerCase();
        const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
        return kwList.some(kw => id.includes(kw) || cls.includes(kw));
    }

    function getEffectiveScrollable(el) {
        // Check if el itself is a native scroller
        const s  = window.getComputedStyle(el);
        const ov = s.overflowY;
        if ((ov === 'scroll' || ov === 'auto') && el.scrollHeight > el.clientHeight + 5) {
            return { isNative: true, scrollPx: el.scrollHeight - el.clientHeight, childSel: null };
        }
        // GWD pattern: container clips (overflow:hidden) but child is tall
        // Look for a direct child with large height
        const children = Array.from(el.children);
        for (const ch of children) {
            const cr = ch.getBoundingClientRect();
            const cs = window.getComputedStyle(ch);
            if (cr.height > el.getBoundingClientRect().height + 20) {
                // Child is taller than container — this is the scroller child
                let childSel = null;
                if (ch.id)       childSel = '#' + ch.id;
                else if (typeof ch.className === 'string' && ch.className.trim()) {
                    childSel = '.' + ch.className.trim().split(/\s+/)[0];
                }
                return { isNative: false, scrollPx: Math.round(cr.height - el.getBoundingClientRect().height), childSel };
            }
        }
        return { isNative: false, scrollPx: 0, childSel: null };
    }

    const candidates = [];
    const all = Array.from(document.querySelectorAll('div, section, aside, article'));

    for (const el of all) {
        if (!matchesKeyword(el, ISI_ID_KW.concat(ISI_CLS_KW))) continue;
        const r = el.getBoundingClientRect();
        if (r.width < 10) continue;
        // Accept ANY height — even a small clip box
        const scroll = getEffectiveScrollable(el);
        const textLen = (el.textContent || '').trim().length;

        let score = 0;
        const id  = (el.id  || '').toLowerCase();
        const cls = (typeof el.className === 'string' ? el.className : '').toLowerCase();
        ISI_ID_KW.forEach(kw  => { if (id.includes(kw))  score += 4; });
        ISI_CLS_KW.forEach(kw => { if (cls.includes(kw)) score += 2; });
        if (scroll.scrollPx > 100) score += 5;
        if (scroll.scrollPx > 0)   score += 2;
        if (scroll.isNative)       score += 3;
        if (textLen > 200)         score += 3;
        if (textLen > 50)          score += 1;
        if (r.height > 50)         score += 1;

        // Build selector
        let sel = el.tagName.toLowerCase();
        if (el.id) sel = '#' + el.id;
        else if (typeof el.className === 'string' && el.className.trim()) {
            sel = '.' + el.className.trim().split(/\s+/)[0];
        }

        candidates.push({
            sel, score,
            scrollHeight:     el.scrollHeight,
            clientHeight:     Math.round(r.height),
            width:            Math.round(r.width),
            overflowY:        window.getComputedStyle(el).overflowY,
            isNativeScroll:   scroll.isNative,
            hasCustomScroll:  !scroll.isNative && scroll.scrollPx > 0,
            customChildSel:   scroll.childSel,
            needsScroll:      scroll.scrollPx > 5,
            scrollablePixels: Math.max(0, scroll.scrollPx),
            textLength:       textLen,
        });
    }

    if (!candidates.length) return { found: false };

    candidates.sort((a, b) => b.score - a.score || b.scrollablePixels - a.scrollablePixels);
    const best = candidates[0];
    return {
        found:            true,
        selector:         best.sel,
        score:            best.score,
        scrollHeight:     best.scrollHeight,
        clientHeight:     best.clientHeight,
        width:            best.width,
        overflowY:        best.overflowY,
        isNativeScroll:   best.isNativeScroll,
        hasCustomScroll:  best.hasCustomScroll,
        customChildSel:   best.customChildSel,
        needsScroll:      best.needsScroll,
        scrollablePixels: best.scrollablePixels,
        textLength:       best.textLength,
        topCandidates:    candidates.slice(0, 3).map(c => ({
            sel: c.sel, score: c.score,
            h: c.clientHeight, scrollPx: c.scrollablePixels, text: c.textLength,
        })),
    };
}"""


def _read_pos_js(isi: dict) -> str:
    """JS IIFE to read ISI scroll/transform position."""
    sel   = isi["selector"].replace("'", "\\'")
    child = (isi.get("customChildSel") or ".__none__").replace("'", "\\'")
    return (
        f"(function(){{"
        f"  var c=document.querySelector('{sel}');"
        f"  if(!c) return 0;"
        f"  if(c.scrollTop>1) return c.scrollTop;"
        # Child transform (GSAP/CSS animation)
        f"  var ch=c.querySelector('{child}');"
        f"  if(ch){{"
        f"    var ts=window.getComputedStyle(ch).transform;"
        f"    if(ts&&ts!=='none'){{"
        f"      try{{var m=new DOMMatrix(ts);if(Math.abs(m.m42)>1)return -m.m42;}}catch(e){{}}"
        f"    }}"
        f"    var top=parseFloat(ch.style.top||'0');"
        f"    if(!isNaN(top)&&Math.abs(top)>1) return -top;"
        f"    var mt=parseFloat(ch.style.marginTop||'0');"
        f"    if(!isNaN(mt)&&Math.abs(mt)>1) return -mt;"
        f"  }}"
        # Container transform
        f"  var ct=window.getComputedStyle(c).transform;"
        f"  if(ct&&ct!=='none'){{"
        f"    try{{var mc=new DOMMatrix(ct);if(Math.abs(mc.m42)>1)return -mc.m42;}}catch(e){{}}"
        f"  }}"
        f"  return c.scrollTop;"
        f"}})()"
    )


async def _collect_banner_evidence(page) -> dict:
    """
    Scans ALL Playwright frames for:
      1. Pharma signals (drug names, ISI text)
      2. ISI element (with GWD clip-box awareness)
    Returns a unified evidence dict.
    """
    pharma_info = {
        "isPharmaBanner": False,
        "pharmaSignals": [],
        "hasDrugName": False,
        "sampleText": "",
        "foundInFrame": None,
    }
    isi_info  = {"found": False}
    isi_frame = None

    frames_ok  = 0
    frames_err = 0

    for frame in page.frames:
        try:
            # Pharma signals
            sig = await frame.evaluate(_PHARMA_SIGNAL_JS)
            if sig.get("isPharmaBanner") and not pharma_info["isPharmaBanner"]:
                pharma_info = {**sig, "foundInFrame": frame.url}
            frames_ok += 1
        except Exception as exc:
            frames_err += 1
            logger.debug(f"Pharma scan frame {frame.url[:50]}: {exc}")

        try:
            # ISI element
            isi = await frame.evaluate(_ISI_FIND_JS)
            if isi.get("found"):
                cur_score = isi.get("score", 0)
                if not isi_info.get("found") or cur_score > isi_info.get("score", 0):
                    isi_info  = isi
                    isi_frame = frame
        except Exception as exc:
            logger.debug(f"ISI scan frame {frame.url[:50]}: {exc}")

    return {
        "pharma":      pharma_info,
        "isi":         isi_info,
        "isiFrame":    isi_frame,
        "framesOk":    frames_ok,
        "framesErr":   frames_err,
        "totalFrames": len(page.frames),
    }


# ─────────────────────────────────────────────────────────────────────────────
# ISI Agent
# ─────────────────────────────────────────────────────────────────────────────
class ISIAgent:
    agent_name = AgentName.ISI

    async def run_all(self, page, run_id: str, screenshot_dir: str) -> list[AgentResult]:
        os.makedirs(screenshot_dir, exist_ok=True)
        checks = [
            (CheckID.ISI_AUTO_SCROLL,  self._auto_scroll),
            (CheckID.ISI_WHEEL_SCROLL, self._wheel_scroll),
            (CheckID.ISI_TEXT_LAYOUT,  self._text_layout),
        ]
        results = []
        for idx, (check_id, fn) in enumerate(checks):
            # Reload before every check to reset animation state
            if idx > 0:
                await self._log(run_id, f"  ↺ Reloading page before {check_id.value}", "info")
                try:
                    await page.reload(wait_until="networkidle", timeout=30_000)
                except Exception:
                    try:
                        await page.reload(wait_until="domcontentloaded", timeout=30_000)
                    except Exception as e:
                        await self._log(run_id, f"  ⚠ Reload failed: {e}", "warning")
                await asyncio.sleep(2.5)

            results.append(await self._run_check(check_id, fn, page, run_id, screenshot_dir))
        return results

    # ── Run harness ────────────────────────────────────────────────────────
    async def _run_check(self, check_id, fn, page, run_id, screenshot_dir) -> AgentResult:
        start = time.perf_counter()
        await self._log(run_id, f"▶ ISI: {check_id.value}", "agent")
        try:
            dom_ev, sys_p, user_p, shots = await fn(page, run_id, screenshot_dir, check_id)
            primary = shots[0] if shots else None
            await self._log(run_id, f"  → Ollama ({len(shots)} shot(s), {len(user_p)} chars)", "info")

            reasoning  = await vision_client.judge(sys_p, user_p, shots)
            await self._log(run_id, f"  ← {reasoning[:140]}", "agent")
            verdict    = self._extract(reasoning)
            confidence = vision_client.extract_confidence(reasoning)

            # ── Post-verdict correction ───────────────────────────────────
            # If LLM says "not_applicable" but the banner IS a pharma banner
            # with no ISI found, that is a compliance FAIL — not N/A.
            if verdict == "not_applicable":
                pharma = dom_ev.get("pharma", {})
                isi_found = dom_ev.get("isiFound", True)
                if pharma.get("isPharmaBanner") and not isi_found:
                    await self._log(
                        run_id,
                        f"  ⚠ Overriding not_applicable→fail: "
                        f"pharma banner but no ISI found (pharmaSignals={pharma.get('pharmaSignals')})",
                        "warning",
                    )
                    verdict = "fail"

            status = CheckStatus.PASS if verdict in ("pass", "not_applicable") else CheckStatus.FAIL

            dur      = (time.perf_counter() - start) * 1000
            icon     = "✓" if status == CheckStatus.PASS else "✗"
            conf_str = f" conf={confidence}%" if confidence is not None else ""
            await self._log(run_id, f"{icon} ISI {check_id.value}: {status.value.upper()} ({dur:.0f}ms{conf_str})", "result")

            return AgentResult(
                check_id=check_id, agent_name=AgentName.ISI,
                status=status, raw_data=dom_ev,
                llm_reasoning=reasoning, llm_verdict=verdict,
                llm_confidence=confidence, screenshot_path=primary, duration_ms=dur,
            )
        except OllamaError as exc:
            dur = (time.perf_counter() - start) * 1000
            msg = str(exc)
            await self._log(run_id, f"  ⚠ Ollama: {msg[:120]}", "error")
            return AgentResult(check_id=check_id, agent_name=AgentName.ISI,
                               status=CheckStatus.ERROR, raw_data={},
                               error_message=msg, llm_reasoning=f"Vision model unavailable: {msg}",
                               duration_ms=dur)
        except Exception as exc:
            dur = (time.perf_counter() - start) * 1000
            err = str(exc) or repr(exc)
            logger.exception(f"ISI {check_id}: {err}")
            await self._log(run_id, f"  ✗ ERROR: {err}", "error")
            return AgentResult(check_id=check_id, agent_name=AgentName.ISI,
                               status=CheckStatus.ERROR, raw_data={}, error_message=err, duration_ms=dur)

    # ── CHECK-5: ISI Auto-Scroll ────────────────────────────────────────────
    async def _auto_scroll(self, page, run_id, screenshot_dir, check_id):
        # Reload for fresh animation state on auto-scroll check
        await self._log(run_id, "  ↺ Reloading for fresh animation state", "info")
        try:
            await page.reload(wait_until="networkidle", timeout=30_000)
            await asyncio.sleep(2.5)
        except Exception:
            await asyncio.sleep(1.0)

        ev = await _collect_banner_evidence(page)
        isi         = ev["isi"]
        isi_frame   = ev.get("isiFrame") or page.main_frame
        pharma      = ev["pharma"]
        path_t0     = f"{screenshot_dir}/{run_id}_{check_id.value}_t0.png"
        path_tmax   = f"{screenshot_dir}/{run_id}_{check_id.value}_tmax.png"

        await self._log(
            run_id,
            f"  Pharma={pharma['isPharmaBanner']} signals={pharma['pharmaSignals']} "
            f"drugName={pharma['hasDrugName']} | "
            f"ISI found={isi.get('found')} sel={isi.get('selector')} "
            f"score={isi.get('score')} scrollPx={isi.get('scrollablePixels',0)} "
            f"frames={ev['framesOk']}/{ev['totalFrames']}",
            "info",
        )

        # ── Case: no ISI found ────────────────────────────────────────────
        if not isi["found"]:
            # Take a full-page screenshot so LLM can see the actual banner
            shot = await ss.capture(page, path_t0)
            shots = [shot] if shot else []

            pharma_context = self._pharma_context_str(pharma, ev)
            sys_p = (
                f"{QA_PERSONA}\n\n"
                "═══ CHECK: ISI Auto-Scroll (CHECK-5) ═══\n\n"
                f"{pharma_context}\n\n"
                "No ISI DOM element was detected by the automated scanner.\n\n"
                "YOUR TASK:\n"
                "Look at the screenshot carefully.\n\n"
                "STEP 1 — Determine banner type:\n"
                "  Look for: drug name (usually in large text with ® or ™), "
                "drug indication, 'Ask about', 'Learn more' CTA buttons.\n"
                "  Non-branded banners: generic awareness ads, disease education "
                "without drug names, conference banners without drug branding.\n\n"
                "STEP 2 — Apply rule:\n"
                "  • Branded pharma ad (drug name visible) AND no ISI found → VERDICT: fail\n"
                "    (FDA requires ISI on all branded digital ads)\n"
                "  • Clearly non-branded awareness ad → VERDICT: not_applicable\n\n"
                "Describe what drug/brand names or safety text you see in the screenshot."
            )
            text = (
                f"ISI element: NOT FOUND (scanned {ev['framesOk']} frames, "
                f"{ev['framesErr']} inaccessible)\n\n"
                f"Pharma signal detection:\n"
                f"  isPharmaBanner={pharma['isPharmaBanner']}\n"
                f"  signals found: {pharma['pharmaSignals']}\n"
                f"  hasDrugName={pharma['hasDrugName']}\n"
                f"  sample text: \"{pharma['sampleText'][:200]}\"\n\n"
                f"Look at the screenshot and determine if this is a branded pharma ad. "
                f"If YES → VERDICT: fail (ISI missing). If NO → VERDICT: not_applicable."
            )
            return {"isiFound": False, "pharma": pharma, "framesScanned": ev['framesOk']}, sys_p, text, shots

        # ── Case: ISI found — take snapshots ─────────────────────────────
        sel    = isi["selector"]
        pos_js = _read_pos_js(isi)

        await self._log(
            run_id,
            f"  ISI: sel={sel} h={isi['clientHeight']}px "
            f"scrollPx={isi['scrollablePixels']} native={isi['isNativeScroll']} "
            f"custom={isi['hasCustomScroll']}",
            "info",
        )

        shot_t0   = await ss.capture_isi_highlighted(page, sel, path_t0)
        snapshots = []

        for t in [0, 4, 8, 12, 16]:
            if t > 0:
                await asyncio.sleep(4)
            try:
                pos = float(await isi_frame.evaluate(f"() => {pos_js}"))
            except Exception:
                pos = 0.0
            snapshots.append({"t": t, "pos": round(pos, 1)})
            await self._log(run_id, f"  ⏱ T={t}s pos={pos:.1f}px", "info")

        shot_tmax = await ss.capture_isi_highlighted(page, sel, path_tmax)

        positions      = [s["pos"] for s in snapshots]
        total_movement = round(max(positions) - positions[0], 1)
        any_movement   = any(abs(snapshots[i+1]["pos"] - snapshots[i]["pos"]) > 1.0
                             for i in range(len(snapshots) - 1))

        # Pre-compute verdict to guide LLM clearly
        needs_scroll = isi["needsScroll"]
        has_movement = any_movement
        has_custom   = isi["hasCustomScroll"]
        is_native    = isi["isNativeScroll"]

        if not needs_scroll:
            pre_verdict = "pass"
            pre_reason  = f"needsScroll=false — ISI content ({isi['scrollHeight']}px) fits in container ({isi['clientHeight']}px). No auto-scroll required."
        elif has_movement:
            pre_verdict = "pass"
            pre_reason  = f"anyMovement=true — ISI scrolled {total_movement}px over 16s. Auto-scroll is working."
        elif has_custom:
            pre_verdict = "visual"
            pre_reason  = "hasCustomScroll=true, no DOM position change detected — must compare screenshots for CSS-transform-based scrolling."
        elif is_native:
            pre_verdict = "fail"
            pre_reason  = (
                f"needsScroll=true ({isi['scrollablePixels']}px overflow), "
                f"isNativeScroll=true, anyMovement=false — "
                f"ISI has overflow content but did NOT auto-scroll during 16s."
            )
        else:
            pre_verdict = "fail"
            pre_reason  = (
                f"needsScroll=true ({isi['scrollablePixels']}px overflow), "
                f"no scroll mechanism found, anyMovement=false."
            )

        if pre_verdict == "visual":
            verdict_instruction = (
                "hasCustomScroll=true: scroller uses CSS transforms (GSAP/GWD) — DOM position reads 0.\n"
                "COMPARE Image 1 (T=0s) vs Image 2 (T=max) carefully:\n"
                "  • Different ISI text visible between images → auto-scroll working → VERDICT: pass\n"
                "  • Images identical → ISI did NOT scroll → VERDICT: fail"
            )
        else:
            verdict_instruction = (
                f"PRE-COMPUTED VERDICT: {pre_verdict.upper()}\n"
                f"REASON: {pre_reason}\n\n"
                f"Confirm by examining the screenshots, then output VERDICT: {pre_verdict}."
            )

        dom_ev = {
            "isiFound": True, "selector": sel, "score": isi.get("score"),
            "scrollHeight": isi["scrollHeight"], "clientHeight": isi["clientHeight"],
            "needsScroll": isi["needsScroll"], "scrollablePixels": isi["scrollablePixels"],
            "isNativeScroll": isi["isNativeScroll"], "hasCustomScroll": isi["hasCustomScroll"],
            "snapshots": snapshots, "totalMovement": total_movement, "anyMovement": any_movement,
            "pharma": pharma,
        }

        sys_p = (
            f"{QA_PERSONA}\n\n"
            "═══ CHECK: ISI Auto-Scroll (CHECK-5) ═══\n\n"
            "You see TWO screenshots of the ISI section (blue outline):\n"
            "  Image 1: ISI at T=0s\n"
            "  Image 2: ISI at the moment of maximum scroll movement (T=16s)\n\n"
            "FDA rule: the ISI MUST either fit fully in the visible area "
            "OR auto-scroll to reveal all content during the banner loop.\n\n"
            "══ DECISION ══\n\n"
            f"{verdict_instruction}\n\n"
            "State which condition applied. Describe what you see in both images."
        )
        snap_lines = "\n".join(f"  T={s['t']}s → {s['pos']}px" for s in snapshots)
        text = (
            f"ISI selector={sel}, score={isi.get('score')}\n"
            f"needsScroll={isi['needsScroll']}, scrollablePixels={isi['scrollablePixels']}px\n"
            f"isNativeScroll={isi['isNativeScroll']}, hasCustomScroll={isi['hasCustomScroll']}\n\n"
            f"Position readings over 16s:\n{snap_lines}\n"
            f"totalMovement={total_movement}px, anyMovement={any_movement}\n\n"
            f"Pre-computed verdict: {pre_verdict.upper()} — {pre_reason}\n\n"
            f"Confirm with screenshot evidence, then give VERDICT."
        )
        shots = [s for s in [shot_t0, shot_tmax] if s]
        return dom_ev, sys_p, text, shots

    # ── CHECK-7: ISI Wheel Scroll ───────────────────────────────────────────
    async def _wheel_scroll(self, page, run_id, screenshot_dir, check_id):
        ev          = await _collect_banner_evidence(page)
        isi         = ev["isi"]
        isi_frame   = ev.get("isiFrame") or page.main_frame
        pharma      = ev["pharma"]
        path_before = f"{screenshot_dir}/{run_id}_{check_id.value}_before.png"

        await self._log(
            run_id,
            f"  Pharma={pharma['isPharmaBanner']} | "
            f"ISI found={isi.get('found')} sel={isi.get('selector')} "
            f"scrollPx={isi.get('scrollablePixels',0)}",
            "info",
        )

        if not isi["found"]:
            shot = await ss.capture(page, path_before)
            shots = [shot] if shot else []
            pharma_context = self._pharma_context_str(pharma, ev)
            sys_p = (
                f"{QA_PERSONA}\n\n"
                "═══ CHECK: ISI Wheel Scroll (CHECK-7) ═══\n\n"
                f"{pharma_context}\n\n"
                "No ISI DOM element was detected.\n\n"
                "Look at the screenshot:\n"
                "  • Branded ad (drug name visible) AND no ISI → VERDICT: fail\n"
                "  • Non-branded awareness ad → VERDICT: not_applicable\n\n"
                "Describe what you see."
            )
            text = (
                f"isiFound=false, frames={ev['framesOk']}/{ev['totalFrames']}\n"
                f"pharmaSignals={pharma['pharmaSignals']}, hasDrugName={pharma['hasDrugName']}\n"
                f"sampleText: \"{pharma['sampleText'][:200]}\""
            )
            return {"isiFound": False, "pharma": pharma}, sys_p, text, shots

        sel    = isi["selector"]
        sel_e  = sel.replace("'", "\\'")
        pos_js = _read_pos_js(isi)

        # Reset ISI scroll to top before the wheel test.
        # If auto-scroll ran before this check, the ISI may already be at
        # scrollBottom (e.g. positionBefore=899) — a wheel event there would
        # correctly produce deltaISI=0 even though wheel scroll works fine.
        # Resetting ensures we measure from a known baseline.
        try:
            await isi_frame.evaluate(f"""() => {{
                const el = document.querySelector('{sel_e}');
                if (el) el.scrollTop = 0;
            }}""")
            await asyncio.sleep(0.3)
        except Exception:
            pass

        shot_before = await ss.capture_isi_highlighted(page, sel, path_before)
        pos_before  = 0.0
        win_before  = 0.0
        try:
            pos_before = float(await isi_frame.evaluate(f"() => {pos_js}"))
            win_before = float(await page.evaluate("() => window.scrollY"))
        except Exception:
            pass

        # Fire wheel event at ISI centre
        # IMPORTANT: If ISI is inside an iframe, page.evaluate() finds the element
        # in the main frame only. We need the iframe's position relative to the
        # viewport to calculate the correct mouse coordinates.
        wheel_fired = False
        try:
            # First try: find element directly via page (works if ISI is in main frame)
            rect = await page.evaluate(f"""() => {{
                const el = document.querySelector('{sel_e}');
                if (!el) return null;
                const r = el.getBoundingClientRect();
                return {{ cx: r.left + r.width/2, cy: r.top + r.height/2, found: true }};
            }}""")

            # If not found in main frame, find the hosting iframe and calculate offset
            if not rect or not rect.get("found"):
                rect = await page.evaluate(f"""() => {{
                    const iframes = Array.from(document.querySelectorAll('iframe'));
                    for (const iframe of iframes) {{
                        try {{
                            const iDoc = iframe.contentDocument || iframe.contentWindow.document;
                            const el = iDoc.querySelector('{sel_e}');
                            if (!el) continue;
                            const iframeRect = iframe.getBoundingClientRect();
                            const elRect = el.getBoundingClientRect();
                            return {{
                                cx: iframeRect.left + elRect.left + elRect.width / 2,
                                cy: iframeRect.top  + elRect.top  + elRect.height / 2,
                                found: true, viaIframe: true
                            }};
                        }} catch(e) {{}}
                    }}
                    return null;
                }}""")

            if rect and rect.get("found"):
                cx = max(1, min(rect["cx"], 1279))
                cy = max(1, min(rect["cy"], 799))
                await page.mouse.move(cx, cy)
                # Fire wheel multiple times to ensure it registers
                await page.mouse.wheel(0, 200)
                await asyncio.sleep(0.3)
                await page.mouse.wheel(0, 200)
                wheel_fired = True
                await self._log(
                    run_id,
                    f"  🖱 Wheel +400px fired at ({cx:.0f},{cy:.0f})"
                    + (" [via iframe offset]" if rect.get("viaIframe") else ""),
                    "info"
                )
        except Exception as e:
            await self._log(run_id, f"  ⚠ Wheel fire error: {e}", "warning")

        if not wheel_fired:
            # Fallback: fire at viewport centre
            await page.mouse.move(640, 400)
            await page.mouse.wheel(0, 400)
            await self._log(run_id, "  🖱 Wheel +400px fired at viewport centre (fallback)", "info")

        await asyncio.sleep(2.5)

        path_after = f"{screenshot_dir}/{run_id}_{check_id.value}_after.png"
        shot_after = await ss.capture_isi_highlighted(page, sel, path_after)
        pos_after  = 0.0
        win_after  = 0.0
        try:
            pos_after = float(await isi_frame.evaluate(f"() => {pos_js}"))
            win_after = float(await page.evaluate("() => window.scrollY"))
        except Exception:
            pass

        delta_isi = round(pos_after - pos_before, 1)
        delta_win = round(win_after - win_before, 1)
        leak      = delta_win > 5

        dom_ev = {
            "isiFound": True, "selector": sel, "score": isi.get("score"),
            "scrollHeight": isi["scrollHeight"], "clientHeight": isi["clientHeight"],
            "isScrollable": isi["needsScroll"], "scrollablePixels": isi["scrollablePixels"],
            "isNativeScroll": isi["isNativeScroll"], "hasCustomScroll": isi["hasCustomScroll"],
            "positionBefore": round(pos_before, 1), "positionAfter": round(pos_after, 1),
            "deltaISI": delta_isi, "deltaWindow": delta_win, "scrollLeaked": leak,
            "pharma": pharma,
        }

        # Pre-compute the decision so the LLM just confirms it visually
        is_scrollable = isi["needsScroll"]
        if not is_scrollable:
            pre_verdict = "pass"
            pre_reason  = f"isScrollable=false — ISI content ({isi['scrollHeight']}px) fits in container ({isi['clientHeight']}px). No wheel response needed."
        elif leak:
            pre_verdict = "fail"
            pre_reason  = f"Scroll leaked to page (deltaWindow={delta_win:.1f}px > 5px) — ISI does not contain wheel events."
        elif delta_isi > 5:
            pre_verdict = "pass"
            pre_reason  = f"ISI moved {delta_isi:.1f}px in response to wheel — wheel scroll is working."
        elif isi.get("hasCustomScroll"):
            pre_verdict = "visual"  # requires screenshot comparison
            pre_reason  = "hasCustomScroll=true and deltaISI≤5 — must compare screenshots visually."
        else:
            pre_verdict = "fail"
            pre_reason  = (
                f"isScrollable=true ({isi['scrollablePixels']}px overflow), "
                f"isNativeScroll={isi['isNativeScroll']}, hasCustomScroll=false. "
                f"Scroll position reset to 0 before test. "
                f"After wheel +400px: position {pos_before:.0f}px → {pos_after:.0f}px (delta={delta_isi:+.1f}px). "
                f"ISI did not respond to wheel scroll — broken."
            )

        if pre_verdict == "visual":
            verdict_instruction = (
                "hasCustomScroll=true: the scroller may use CSS transforms that DOM can't measure.\n"
                "COMPARE Image 1 (BEFORE) vs Image 2 (AFTER) visually:\n"
                "  • If different text is visible between images → ISI scrolled → VERDICT: pass\n"
                "  • If images look identical → ISI did NOT scroll → VERDICT: fail"
            )
        else:
            verdict_instruction = (
                f"PRE-COMPUTED VERDICT: {pre_verdict.upper()}\n"
                f"REASON: {pre_reason}\n\n"
                f"Confirm by looking at the screenshots, then output VERDICT: {pre_verdict}."
            )

        sys_p = (
            f"{QA_PERSONA}\n\n"
            "═══ CHECK: ISI Wheel Scroll (CHECK-7) ═══\n\n"
            "You see TWO screenshots of the ISI section (blue outline):\n"
            "  Image 1: BEFORE mouse wheel event\n"
            "  Image 2: AFTER mouse wheel +400px (waited 2.5s)\n\n"
            "A pharma banner ISI with overflow content MUST respond to mouse wheel scroll.\n"
            "If the ISI fits entirely (isScrollable=false), wheel response is not required.\n\n"
            "══ DECISION ══\n\n"
            f"{verdict_instruction}\n\n"
            "State which condition applied and describe what you see in both images."
        )
        text = (
            f"ISI sel={sel}, isScrollable={isi['needsScroll']}, "
            f"scrollPx={isi['scrollablePixels']}px\n"
            f"isNativeScroll={isi['isNativeScroll']}, hasCustomScroll={isi['hasCustomScroll']}\n\n"
            f"Wheel +400px. Waited 2.5s.\n"
            f"  ISI: {pos_before:.1f}px → {pos_after:.1f}px (delta={delta_isi:+.1f}px)\n"
            f"  Page: {win_before:.1f}px → {win_after:.1f}px "
            f"(delta={delta_win:+.1f}px, leaked={leak})\n\n"
            f"Pre-computed verdict: {pre_verdict.upper()} — {pre_reason}\n\n"
            f"Look at both screenshots and confirm."
        )
        shots = [s for s in [shot_before, shot_after] if s]
        return dom_ev, sys_p, text, shots

    # ── CHECK-6: ISI Text Layout ────────────────────────────────────────────
    async def _text_layout(self, page, run_id, screenshot_dir, check_id):
        ev        = await _collect_banner_evidence(page)
        isi       = ev["isi"]
        isi_frame = ev.get("isiFrame") or page.main_frame
        pharma    = ev["pharma"]
        path      = f"{screenshot_dir}/{run_id}_{check_id.value}.png"

        await self._log(
            run_id,
            f"  Pharma={pharma['isPharmaBanner']} | "
            f"ISI found={isi.get('found')} sel={isi.get('selector')}",
            "info",
        )

        if not isi["found"]:
            shot = await ss.capture(page, path)
            shots = [shot] if shot else []
            pharma_context = self._pharma_context_str(pharma, ev)
            sys_p = (
                f"{QA_PERSONA}\n\n"
                "═══ CHECK: ISI Text Layout (CHECK-6) ═══\n\n"
                f"{pharma_context}\n\n"
                "No ISI DOM element was detected.\n\n"
                "Look at the screenshot:\n"
                "  • Branded ad (drug name visible) AND no ISI → VERDICT: fail\n"
                "  • Non-branded awareness ad → VERDICT: not_applicable\n\n"
                "Describe what you see."
            )
            text = (
                f"isiFound=false, frames={ev['framesOk']}/{ev['totalFrames']}\n"
                f"pharmaSignals={pharma['pharmaSignals']}, hasDrugName={pharma['hasDrugName']}\n"
                f"sampleText: \"{pharma['sampleText'][:200]}\""
            )
            return {"isiFound": False, "pharma": pharma}, sys_p, text, shots

        sel   = isi["selector"]
        sel_e = sel.replace("'", "\\'")

        # Run overlap scan in correct frame
        # IMPORTANT: Only scan elements visible within the ISI clip area.
        # Elements scrolled out of view still have bounding boxes but they
        # fall outside the container's visible rect — scanning them produces
        # false overlaps from scroll-clipped content.
        overlaps = await isi_frame.evaluate(f"""() => {{
            const container = document.querySelector('{sel_e}');
            if (!container) return {{overlapCount:-1, checkedElements:0, pairs:[]}};

            // Get the container's visible clip bounds
            const clipRect = container.getBoundingClientRect();
            const clipTop    = clipRect.top;
            const clipBottom = clipRect.bottom;
            const clipLeft   = clipRect.left;
            const clipRight  = clipRect.right;

            const elements = Array.from(
                container.querySelectorAll('p,span,a,h1,h2,h3,h4,h5,h6,strong,em,li,td,th')
            ).filter(el => {{
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                if (r.width < 2 || r.height < 2) return false;
                if (s.display === 'none' || s.visibility === 'hidden') return false;
                if (!(el.textContent || '').trim().length > 2) return false;
                // Only include elements whose top edge falls within the visible clip area
                // (within 5px tolerance for elements at the clip boundary)
                const visibleInClip = r.top < (clipBottom + 5) && r.bottom > (clipTop - 5)
                    && r.left < (clipRight + 5) && r.right > (clipLeft - 5);
                return visibleInClip;
            }}).slice(0, 100);

            let overlapCount = 0;
            const pairs = [];
            for (let i = 0; i < elements.length - 1; i++) {{
                for (let j = i+1; j < Math.min(i+6, elements.length); j++) {{
                    if (elements[i].contains(elements[j]) || elements[j].contains(elements[i])) continue;
                    const a = elements[i].getBoundingClientRect();
                    const b = elements[j].getBoundingClientRect();
                    const xO = Math.min(a.right, b.right)   - Math.max(a.left, b.left);
                    const yO = Math.min(a.bottom, b.bottom) - Math.max(a.top,  b.top);
                    if (xO > 4 && yO > 4) {{
                        overlapCount++;
                        if (pairs.length < 6) pairs.push({{
                            elementA: elements[i].tagName + (elements[i].id ? '#'+elements[i].id : ''),
                            elementB: elements[j].tagName + (elements[j].id ? '#'+elements[j].id : ''),
                            xOverlap: Math.round(xO), yOverlap: Math.round(yO),
                            textA: (elements[i].textContent||'').trim().substring(0,35),
                            textB: (elements[j].textContent||'').trim().substring(0,35),
                        }});
                    }}
                }}
            }}
            return {{ overlapCount, checkedElements: elements.length, pairs }};
        }}""")

        shot = await ss.capture_isi_highlighted(page, sel, path)

        dom_ev = {
            "isiFound": True, "selector": sel, "score": isi.get("score"),
            "scrollHeight": isi["scrollHeight"], "clientHeight": isi["clientHeight"],
            "textLength": isi.get("textLength", 0), "pharma": pharma,
            **overlaps,
        }

        # Pre-classify overlaps to guide LLM clearly
        real_overlaps = []
        artefact_overlaps = []
        INLINE_TAGS = {"SPAN", "A", "STRONG", "EM", "B", "I", "U", "SMALL", "SUB", "SUP"}
        for p in overlaps.get("pairs", []):
            tag_a = p["elementA"].split("#")[0].split(".")[0].upper()
            tag_b = p["elementB"].split("#")[0].split(".")[0].upper()
            both_inline = tag_a in INLINE_TAGS and tag_b in INLINE_TAGS
            x_overlap = p.get("xOverlap", 0)
            y_overlap = p.get("yOverlap", 0)
            # An overlap is an artefact ONLY if: both inline AND yOverlap < 5px
            # Large xOverlap on two A tags means they're on the same line and
            # the bounding-box measurement is a false positive from line height.
            # But if yOverlap >= 5 AND xOverlap > 50 on two A tags, those links
            # visually overlap → real issue.
            if both_inline and y_overlap < 5:
                artefact_overlaps.append(p)
            elif both_inline and x_overlap > 0 and y_overlap >= 5:
                # Same-line adjacent links: the y-overlap is from sub/superscript
                # line-height measurement, not visual overlap. Check xOverlap:
                # if xOverlap > 30px they share the same horizontal space → real.
                if x_overlap > 30:
                    real_overlaps.append(p)
                else:
                    artefact_overlaps.append(p)
            else:
                real_overlaps.append(p)

        has_real_overlaps = len(real_overlaps) > 0

        sys_p = (
            f"{QA_PERSONA}\n\n"
            "═══ CHECK: ISI Text Layout (CHECK-6) ═══\n\n"
            "You see a screenshot of the ISI section (highlighted in blue).\n"
            "ISI text MUST be FULLY READABLE — no overlapping text, no cut-off lines.\n\n"
            "The system has pre-classified the detected overlaps for you:\n\n"
            "CASE A — no real overlaps detected (overlapCount=0 OR all overlaps are artefacts):\n"
            "  Look at the screenshot. If text is readable → VERDICT: pass\n"
            "  If you can see text visually overlapping despite the classification → VERDICT: fail\n\n"
            "CASE B — real overlaps detected (block elements OR significant inline overlaps):\n"
            "  Look at the screenshot. Confirm you can see overlapping text.\n"
            "  If text is visually overlapping and unreadable → VERDICT: fail\n"
            "  If screenshot text looks fine (classification may be a bounding-box error) → VERDICT: pass\n\n"
            "CASE C — checkedElements=0 (deep iframe, no DOM access):\n"
            "  Rely ENTIRELY on the screenshot.\n"
            "  Readable text → VERDICT: pass | Visually overlapping → VERDICT: fail\n\n"
            "The SCREENSHOT is the primary evidence. DOM data informs but does not override what you SEE.\n"
            "State what you see in the screenshot, then apply the matching CASE."
        )
        pairs_str = "\n".join(
            f"  {p['elementA']}+{p['elementB']}: xO={p['xOverlap']}px yO={p['yOverlap']}px "
            f"| \"{p['textA']}\" ↔ \"{p['textB']}\""
            for p in overlaps.get("pairs", [])
        ) or "  (none)"
        real_str = "\n".join(
            f"  [REAL] {p['elementA']}+{p['elementB']}: xO={p['xOverlap']}px yO={p['yOverlap']}px "
            f"| \"{p['textA']}\" ↔ \"{p['textB']}\""
            for p in real_overlaps
        ) or "  (none)"
        art_str = "\n".join(
            f"  [artefact] {p['elementA']}+{p['elementB']}: xO={p['xOverlap']}px yO={p['yOverlap']}px"
            for p in artefact_overlaps
        ) or "  (none)"
        text = (
            f"ISI sel={sel}, score={isi.get('score')}\n"
            f"checkedElements={overlaps['checkedElements']}, overlapCount={overlaps['overlapCount']}\n\n"
            f"Pre-classified overlaps:\n"
            f"  Real overlaps (may affect readability):\n{real_str}\n"
            f"  Artefacts (bounding-box noise, safe to ignore):\n{art_str}\n\n"
            f"hasRealOverlaps={has_real_overlaps}\n\n"
            f"Look at the screenshot. Describe what you see. Apply the matching CASE."
        )
        return dom_ev, sys_p, text, [shot] if shot else []

    # ── Helpers ────────────────────────────────────────────────────────────
    @staticmethod
    def _pharma_context_str(pharma: dict, ev: dict) -> str:
        """Builds a context paragraph telling the LLM what pharma evidence was found."""
        if pharma["isPharmaBanner"]:
            return (
                f"⚠ PHARMA BANNER DETECTED:\n"
                f"  Pharma signals found: {pharma['pharmaSignals']}\n"
                f"  Drug name pattern detected: {pharma['hasDrugName']}\n"
                f"  Banner text sample: \"{pharma['sampleText'][:200]}\"\n"
                f"  This banner contains pharmaceutical content and IS subject to FDA ISI rules."
            )
        elif ev["framesErr"] > 0:
            return (
                f"ℹ Pharma detection: {ev['framesErr']} frame(s) were inaccessible "
                f"(cross-origin security). No pharma signals found in accessible frames.\n"
                f"  Treat as: look at the screenshot to determine banner type."
            )
        else:
            return (
                f"ℹ No pharma signals detected in {ev['framesOk']} frame(s).\n"
                f"  Banner text sample: \"{pharma['sampleText'][:200]}\"\n"
                f"  This appears to be a non-branded awareness banner."
            )

    @staticmethod
    def _extract(text: str) -> str:
        m = re.search(r"VERDICT\s*:\s*(pass|fail|not_applicable)", text, re.IGNORECASE)
        if m:
            return m.group(1).lower()
        lines = [ln.strip().lower() for ln in text.strip().splitlines() if ln.strip()]
        if lines:
            last = lines[-1]
            for v in ("not_applicable", "not applicable", "pass", "fail"):
                if v in last:
                    return v.replace(" ", "_")
        lower  = text.lower()
        counts = {
            "pass":           lower.count("pass"),
            "fail":           lower.count("fail"),
            "not_applicable": max(lower.count("not_applicable"), lower.count("not applicable")),
        }
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else "fail"

    async def _log(self, run_id: str, msg: str, level: str = "info") -> None:
        await broadcaster.emit(run_id, msg, level=level, agent="isi")