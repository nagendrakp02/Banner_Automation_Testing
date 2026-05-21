
import asyncio

from backend.agents.base_agent import BaseAgent, QA_PERSONA
from backend.core.constants import AgentName, CheckID
from backend.services import screenshot as ss



_BORDER_SCAN_JS = """() => {
    const results = [];
    const seen    = new Set();
    const SKIP    = new Set(['HTML','BODY','IFRAME','FRAME','SCRIPT','STYLE','HEAD','META','LINK']);

    function inspect(el) {
        if (!el || seen.has(el) || SKIP.has(el.tagName)) return;
        seen.add(el);
        try {
            const s = window.getComputedStyle(el);
            const r = el.getBoundingClientRect();
            if (r.width < 2 || r.height < 2) return;

            const bTop = parseFloat(s.borderTopWidth)    || 0;
            const bRt  = parseFloat(s.borderRightWidth)  || 0;
            const bBt  = parseFloat(s.borderBottomWidth) || 0;
            const bLt  = parseFloat(s.borderLeftWidth)   || 0;
            const oW   = parseFloat(s.outlineWidth)      || 0;
            const maxB = Math.max(bTop, bRt, bBt, bLt);

            const hasBorder  = maxB > 0
                && s.borderStyle !== 'none' && s.borderStyle !== 'hidden';
            const hasOutline = oW > 0
                && s.outlineStyle !== 'none' && s.outlineStyle !== 'hidden'
                && s.outlineColor !== 'transparent';
            const hasShadow  = s.boxShadow && s.boxShadow !== 'none';

            if (hasBorder || hasOutline || hasShadow) {
                results.push({
                    element:      el.tagName + (el.id ? '#' + el.id : ''),
                    className:    (el.className || '').toString().substring(0, 40),
                    borderTop:    bTop+'px', borderRight: bRt+'px',
                    borderBot:    bBt+'px',  borderLeft:  bLt+'px',
                    borderStyle:  s.borderStyle,
                    borderColor:  s.borderColor,
                    outlineWidth: oW+'px',
                    outlineStyle: s.outlineStyle,
                    outlineColor: s.outlineColor,
                    boxShadow:    s.boxShadow.substring(0, 80),
                    width:        Math.round(r.width),
                    height:       Math.round(r.height),
                });
            }
        } catch(e) {}
    }
    Array.from(document.querySelectorAll('*')).slice(0, 400).forEach(inspect);
    return results;
}"""

_BG_DETECT_JS = """() => {
    const CANDIDATES = [
        '#wrapper','#container','#banner','#ad',
        '.wrapper','.container','.banner',
        '[class*="gwd-page"]','[class*="page-content"]',
        'body > div:first-child','body',
    ];
    for (const sel of CANDIDATES) {
        try {
            const el = document.querySelector(sel);
            if (!el) continue;
            const r = el.getBoundingClientRect();
            if (r.width < 10 || r.height < 10) continue;
            const s  = window.getComputedStyle(el);
            const bg = s.backgroundColor;
            const isTransparent = bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent';
            const isWhite = bg === 'rgb(255, 255, 255)' || bg === 'rgba(255, 255, 255, 1)';
            if (!isTransparent && !isWhite) {
                return {
                    hasDistinctBg: true, bgColor: bg,
                    element: el.tagName + (el.id ? '#'+el.id : ''),
                    width: Math.round(r.width), height: Math.round(r.height),
                };
            }
        } catch(e) {}
    }
    // Gradient / image background on body
    try {
        const bs = window.getComputedStyle(document.body);
        if (bs.backgroundImage && bs.backgroundImage !== 'none') {
            return {
                hasDistinctBg: true,
                bgColor: 'gradient/image: ' + bs.backgroundImage.substring(0, 80),
                element: 'BODY (background-image)',
                width: document.body.scrollWidth,
                height: document.body.scrollHeight,
            };
        }
    } catch(e) {}
    return { hasDistinctBg: false, bgColor: null };
}"""



class RenderAgent(BaseAgent):
    check_id   = CheckID.BANNER_VISIBLE
    agent_name = AgentName.RENDER

    async def collect_dom_evidence(self, page) -> dict:
        return await page.evaluate("""() => {
            const allEls = document.querySelectorAll('*');
            const visible = Array.from(allEls).filter(el => {
                try {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 0 && r.height > 0
                        && s.display    !== 'none'
                        && s.visibility !== 'hidden'
                        && parseFloat(s.opacity || '1') > 0;
                } catch(e) { return false; }
            });
            const imgs   = Array.from(document.querySelectorAll('img'));
            const broken = imgs.filter(i => !i.complete || i.naturalWidth === 0);
            return {
                readyState:       document.readyState,
                bodyWidth:        document.body?.scrollWidth  || 0,
                bodyHeight:       document.body?.scrollHeight || 0,
                visibleElements:  visible.length,
                totalElements:    allEls.length,
                imageCount:       imgs.length,
                brokenImageCount: broken.length,
                brokenImageSrcs:  broken.slice(0,3).map(i => i.src.split('/').pop()),
                scriptCount:      document.querySelectorAll('script[src]').length,
                pageTitle:        document.title || '',
                hasBodyContent:   (document.body?.innerHTML || '').trim().length > 50,
                consoleErrors:    [],
            };
        }""")

    async def capture_evidence_shots(self, page, run_id, screenshot_dir):
        path = f"{screenshot_dir}/{run_id}_{self.check_id.value}.png"
        shot = await ss.capture(page, path)
        return [shot] if shot else []

    def build_qa_prompt(self, ev: dict) -> tuple[str, str]:
        sys = (
            f"{QA_PERSONA}\n\n"
            "═══ CHECK: Banner Visible (CHECK-1) ═══\n\n"
            "PASS criteria (ALL must be true):\n"
            "  • Screenshot shows recognisable banner content\n"
            "  • bodyWidth > 0 AND bodyHeight > 0\n"
            "  • visibleElements > 0\n"
            "  • Not a browser error page\n\n"
            "FAIL criteria (ANY sufficient):\n"
            "  • Screenshot completely blank or shows browser error\n"
            "  • brokenImageCount equals imageCount\n"
            "  • readyState not 'complete' AND page looks empty\n\n"
            "NOTE: Partially loaded banner with some content = PASS."
        )
        broken_info = (
            f"{ev['brokenImageCount']} broken: {', '.join(ev['brokenImageSrcs'])}"
            if ev["brokenImageCount"] else "none broken"
        )
        text = (
            f"readyState={ev['readyState']}\n"
            f"bodyWidth={ev['bodyWidth']}px, bodyHeight={ev['bodyHeight']}px\n"
            f"visibleElements={ev['visibleElements']}/{ev['totalElements']}\n"
            f"images={ev['imageCount']} ({broken_info})\n"
            f"scriptCount={ev['scriptCount']}\n"
            f"pageTitle=\"{ev['pageTitle'][:70]}\"\n"
            f"hasBodyContent={ev['hasBodyContent']}\n\n"
            f"Describe what you see. Apply PASS/FAIL criteria."
        )
        return sys, text


class VisualAgent(BaseAgent):
    check_id   = CheckID.BORDER_DETECTED
    agent_name = AgentName.VISUAL

    async def collect_dom_evidence(self, page) -> dict:
        """Scan ALL frames for CSS borders + background-colour boundaries."""
        all_border_els: list[dict] = []
        bg_info = {"hasDistinctBg": False, "bgColor": None, "element": None}
        frames_scanned = 0

        for frame in page.frames:
            frames_scanned += 1
            try:
                borders = await frame.evaluate(_BORDER_SCAN_JS)
                all_border_els.extend(borders)
            except Exception:
                pass
            try:
                bg = await frame.evaluate(_BG_DETECT_JS)
                if bg.get("hasDistinctBg") and not bg_info["hasDistinctBg"]:
                    bg_info = bg
            except Exception:
                pass

        has_any_border  = len(all_border_els) > 0
        has_distinct_bg = bg_info.get("hasDistinctBg", False)

        return {
            "framesScanned":       frames_scanned,
            "hasAnyBorder":        has_any_border,
            "borderElementCount":  len(all_border_els),
            "borderElements":      all_border_els[:8],
            "hasDistinctBg":       has_distinct_bg,
            "bgColor":             bg_info.get("bgColor"),
            "bgElement":           bg_info.get("element"),
            "deterministicResult": "PASS" if (has_any_border or has_distinct_bg) else "NEEDS_VISUAL_CHECK",
        }

    async def capture_evidence_shots(self, page, run_id, screenshot_dir):
        path_hl = f"{screenshot_dir}/{run_id}_{self.check_id.value}_highlighted.png"
        path_pl = f"{screenshot_dir}/{run_id}_{self.check_id.value}_plain.png"
        hl = await ss.capture_with_border_highlight(page, path_hl)
        pl = await ss.capture(page, path_pl)
        return [s for s in [hl, pl] if s]

    def build_qa_prompt(self, ev: dict) -> tuple[str, str]:
        sys = (
            f"{QA_PERSONA}\n\n"
            "═══ CHECK: Border Detected (CHECK-2) ═══\n\n"
            "Image 1 (HIGHLIGHTED): CSS border/outline/shadow elements shown as 4px RED overlays.\n"
            "Image 2 (PLAIN): banner as a user sees it.\n\n"
            "Pharma compliance: banner MUST have a VISIBLE BOUNDARY from surrounding page.\n"
            "CSS border OR coloured/gradient background both satisfy this.\n\n"
            "══ PRE-COMPUTED SIGNALS (system scanned ALL iframes — trust these) ══\n"
            "  deterministicResult=PASS  → CSS border OR coloured background found.\n"
            "  deterministicResult=NEEDS_VISUAL_CHECK → nothing found in CSS scan.\n\n"
            "══ RULES ══\n\n"
            "RULE 1: deterministicResult=PASS\n"
            "  → VERDICT: pass  [mandatory — do not override]\n\n"
            "RULE 2: deterministicResult=NEEDS_VISUAL_CHECK\n"
            "  → Examine Image 2 carefully.\n"
            "  → Any colour difference at banner edges vs white page → VERDICT: pass\n"
            "  → Banner pure white, no visible edge at all → VERDICT: fail\n\n"
            "If deterministicResult=PASS you MUST output VERDICT: pass."
        )
        els = ev.get("borderElements", [])
        el_lines = "\n".join(
            f"  {e.get('element','?')} ({e.get('width','?')}×{e.get('height','?')}px): "
            f"border={e.get('borderTop','?')}/{e.get('borderRight','?')} "
            f"color={e.get('borderColor','?')} shadow={str(e.get('boxShadow',''))[:30]}"
            for e in els[:5]
        ) or "  (none found in any frame)"

        text = (
            f"PRE-COMPUTED RESULT: {ev.get('deterministicResult','UNKNOWN')}\n\n"
            f"CSS scan ({ev.get('framesScanned',1)} frame(s) including iframes):\n"
            f"  hasAnyBorder={ev['hasAnyBorder']} ({ev.get('borderElementCount',0)} element(s))\n"
            f"Border elements:\n{el_lines}\n\n"
            f"Background colour:\n"
            f"  hasDistinctBg={ev['hasDistinctBg']}\n"
            f"  bgColor={ev.get('bgColor','none/white')}\n"
            f"  bgElement={ev.get('bgElement','n/a')}\n\n"
            f"If deterministicResult=PASS → VERDICT: pass immediately.\n"
            f"If NEEDS_VISUAL_CHECK → describe Image 2 then decide."
        )
        return sys, text



class InteractionAgent(BaseAgent):
    check_id   = CheckID.COPY_SELECTION_DISABLED
    agent_name = AgentName.INTERACTION

    async def collect_dom_evidence(self, page) -> dict:
        css = await page.evaluate("""() => {
            const body = window.getComputedStyle(document.body);
            const html = window.getComputedStyle(document.documentElement);
            const textEls = Array.from(
                document.querySelectorAll('p,span,div,h1,h2,h3,h4,li,td')
            ).filter(el => (el.textContent||'').trim().length > 5).slice(0,6);
            return {
                bodyUserSelect: body.userSelect || body.webkitUserSelect || 'auto',
                htmlUserSelect: html.userSelect || html.webkitUserSelect || 'auto',
                elementSamples: textEls.map(el => {
                    const s = window.getComputedStyle(el);
                    return {
                        tag:        el.tagName,
                        userSelect: s.userSelect || s.webkitUserSelect || 'auto',
                        textSnip:   (el.textContent||'').trim().substring(0,30),
                    };
                }),
            };
        }""")
        await page.keyboard.press("Control+a")
        await asyncio.sleep(0.35)
        css["keyboardSelectedLength"] = await page.evaluate(
            "() => window.getSelection()?.toString().length ?? 0"
        )
        return css

    async def capture_evidence_shots(self, page, run_id, screenshot_dir):
        await page.keyboard.press("Control+a")
        await asyncio.sleep(0.2)
        path = f"{screenshot_dir}/{run_id}_{self.check_id.value}.png"
        shot = await ss.capture(page, path)
        await page.keyboard.press("Escape")
        return [shot] if shot else []

    def build_qa_prompt(self, ev: dict) -> tuple[str, str]:
        # Pre-compute verdict from DOM evidence
        body_select  = ev["bodyUserSelect"]
        selected_len = ev["keyboardSelectedLength"]

        if body_select == "none":
            pre_verdict = "pass"
            pre_reason  = "bodyUserSelect='none' — CSS user-select:none blocks text selection at the browser engine level."
        elif selected_len == 0:
            pre_verdict = "pass"
            pre_reason  = f"bodyUserSelect='{body_select}' but Ctrl+A selected 0 characters — text is not selectable in practice."
        else:
            pre_verdict = "fail"
            pre_reason  = f"bodyUserSelect='{body_select}' AND Ctrl+A selected {selected_len} characters — text CAN be selected and copied."

        sys = (
            f"{QA_PERSONA}\n\n"
            "═══ CHECK: Copy Selection Disabled (CHECK-3) ═══\n\n"
            "Screenshot taken AFTER Ctrl+A. Blue text highlights = selection enabled.\n\n"
            f"PRE-COMPUTED VERDICT: {pre_verdict.upper()}\n"
            f"REASON: {pre_reason}\n\n"
            "This verdict is derived directly from CSS properties and browser selection measurement.\n"
            "Trust it unless the screenshot shows something clearly contradictory.\n"
            f"Output VERDICT: {pre_verdict}."
        )
        samples = " | ".join(
            f"{s['tag']}={s['userSelect']} (\"{s['textSnip']}\")"
            for s in ev.get("elementSamples", [])[:3]
        ) or "(no text elements)"
        text = (
            f"bodyUserSelect={ev['bodyUserSelect']}\n"
            f"htmlUserSelect={ev['htmlUserSelect']}\n"
            f"keyboardSelectedLength={ev['keyboardSelectedLength']} chars after Ctrl+A\n"
            f"Elements: {samples}\n\n"
            f"Pre-computed verdict: {pre_verdict.upper()} — {pre_reason}\n"
            f"Confirm visually, then output VERDICT: {pre_verdict}."
        )
        return sys, text


class PerformanceAgent(BaseAgent):
    check_id   = CheckID.BANNER_LOAD_TIME
    agent_name = AgentName.PERFORMANCE

    async def collect_dom_evidence(self, page) -> dict:
        return await page.evaluate("""() => {
            const t   = window.performance.timing;
            const res = performance.getEntriesByType('resource');
            const loadMs = t.loadEventEnd > 0
                ? Math.round(t.loadEventEnd - t.navigationStart) : null;
            const slowRes = res
                .filter(r => r.duration > 500)
                .sort((a,b) => b.duration - a.duration)
                .slice(0,5)
                .map(r => ({
                    name:       r.name.split('/').pop().substring(0,40),
                    durationMs: Math.round(r.duration),
                    sizeKB:     Math.round((r.transferSize||0)/1024),
                    type:       r.initiatorType,
                }));
            return {
                loadMs,
                domContentLoadedMs: Math.round(t.domContentLoadedEventEnd - t.navigationStart),
                ttfbMs:             Math.round(t.responseStart - t.navigationStart),
                resourceCount:      res.length,
                transferSizeKB:     Math.round(res.reduce((s,r)=>s+(r.transferSize||0),0)/1024),
                slowResources:      slowRes,
                thresholdMs:        60000,
                loadGrade: loadMs === null ? 'unknown'
                    : loadMs <= 3000       ? 'excellent'
                    : loadMs <= 10000      ? 'good'
                    : loadMs <= 30000      ? 'acceptable'
                    : loadMs <= 60000      ? 'slow'
                    : 'over_threshold',
            };
        }""")

    async def capture_evidence_shots(self, page, run_id, screenshot_dir):
        path = f"{screenshot_dir}/{run_id}_{self.check_id.value}.png"
        shot = await ss.capture(page, path)
        return [shot] if shot else []

    def build_qa_prompt(self, ev: dict) -> tuple[str, str]:
        sys = (
            f"{QA_PERSONA}\n\n"
            "═══ CHECK: Banner Load Time (CHECK-4) ═══\n\n"
            "PASS: loadMs not null AND loadMs ≤ 60,000ms\n"
            "FAIL: loadMs > 60,000ms OR loadMs is null\n\n"
            "Grade: ≤3s=excellent | ≤10s=good | ≤30s=acceptable | ≤60s=slow | >60s=FAIL"
        )
        slow_lines = "\n".join(
            f"  [{r['type']}] {r['name']}: {r['durationMs']}ms ({r['sizeKB']}KB)"
            for r in ev.get("slowResources", [])
        ) or "  (none > 500ms)"
        text = (
            f"loadMs={ev['loadMs']}ms (threshold=60,000ms)\n"
            f"domContentLoadedMs={ev['domContentLoadedMs']}ms\n"
            f"ttfbMs={ev['ttfbMs']}ms\n"
            f"resources={ev['resourceCount']}, transferKB={ev['transferSizeKB']}\n"
            f"loadGrade={ev['loadGrade']}\n"
            f"Slow resources:\n{slow_lines}\n\n"
            f"Give verdict."
        )
        return sys, text