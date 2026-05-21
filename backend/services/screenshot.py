
import asyncio
import os
from loguru import logger


def _ensure_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


async def capture(page, path: str) -> str | None:
    try:
        _ensure_dir(path)
        await page.screenshot(path=path, full_page=False, type="png")
        return path
    except Exception as exc:
        logger.warning(f"capture({path}): {exc}")
        return None



async def capture_with_border_highlight(page, path: str) -> str | None:
    """
    Tags elements WITH a CSS border/outline/shadow with data-bm-border.
    Injects a scoped style (only [data-bm-border]) — never tags BODY/HTML/IFRAME.
    Always cleans up in a finally block.
    """
    _ensure_dir(path)
    injected = False
    try:
        await page.evaluate("""() => {
            // Never tag root/structural elements — avoids whole-page flood
            const SKIP_TAGS = new Set(['HTML','BODY','IFRAME','FRAME','SCRIPT','STYLE','META','LINK','HEAD']);
            document.querySelectorAll('*').forEach(el => {
                if (SKIP_TAGS.has(el.tagName)) return;
                try {
                    const s = window.getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    if (r.width < 2 || r.height < 2) return;

                    const bTop  = parseFloat(s.borderTopWidth)    || 0;
                    const bRt   = parseFloat(s.borderRightWidth)  || 0;
                    const bBt   = parseFloat(s.borderBottomWidth) || 0;
                    const bLt   = parseFloat(s.borderLeftWidth)   || 0;
                    const oW    = parseFloat(s.outlineWidth)      || 0;
                    const maxBW = Math.max(bTop, bRt, bBt, bLt);

                    const hasBorder  = maxBW > 0
                        && s.borderStyle !== 'none'
                        && s.borderStyle !== 'hidden';
                    const hasOutline = oW > 0
                        && s.outlineStyle !== 'none'
                        && s.outlineColor !== 'transparent'
                        && !el.hasAttribute('data-bm-border');  // skip our own injection
                    const hasShadow  = s.boxShadow && s.boxShadow !== 'none';

                    if (hasBorder || hasOutline || hasShadow) {
                        el.setAttribute('data-bm-border', '1');
                    }
                } catch(e) {}
            });

            // Scoped style — ONLY affects tagged elements, cannot cascade further
            if (!document.getElementById('__bm_border_style__')) {
                const style = document.createElement('style');
                style.id = '__bm_border_style__';
                style.textContent = '[data-bm-border] { outline: 4px solid #FF0000 !important; outline-offset: 2px !important; }';
                document.head.appendChild(style);
            }
        }""")
        injected = True
        return await capture(page, path)

    except Exception as exc:
        logger.warning(f"capture_with_border_highlight: {exc}")
        try:
            return await capture(page, path)
        except Exception:
            return None
    finally:
        if injected:
            try:
                await page.evaluate("""() => {
                    document.querySelectorAll('[data-bm-border]')
                        .forEach(el => el.removeAttribute('data-bm-border'));
                    const s = document.getElementById('__bm_border_style__');
                    if (s) s.remove();
                }""")
            except Exception as e:
                logger.warning(f"border highlight cleanup: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Full-page element screenshot (no highlight injection)
# ─────────────────────────────────────────────────────────────────────────────
async def capture_element(page, selector: str, path: str) -> str | None:
    """Screenshot a specific element; falls back to full viewport."""
    _ensure_dir(path)
    try:
        sel_e = selector.replace("'", "\\'")
        await page.evaluate(
            f"() => {{"
            f"  const el = document.querySelector('{sel_e}');"
            f"  if (el) el.scrollIntoView({{block:'nearest', behavior:'instant'}});"
            f"}}"
        )
        await asyncio.sleep(0.15)
        el = await page.query_selector(selector)
        if el:
            await el.screenshot(path=path, type="png")
            return path
    except Exception as exc:
        logger.warning(f"capture_element({selector}): {exc}")
    return await capture(page, path)


# ─────────────────────────────────────────────────────────────────────────────
# ISI highlight — FIXED blue-flood
# ─────────────────────────────────────────────────────────────────────────────
async def capture_isi_highlighted(page, selector: str, path: str) -> str | None:
    """
    Adds a 3px BLUE outline to ONLY the matched ISI element.
    Uses element.style (inline) so it only affects that one element.
    Restores original outline in a guaranteed finally block.

    KEY FIX: does NOT call capture_element() (which calls scrollIntoView
    and can throw before cleanup). Instead does everything inline here.
    """
    _ensure_dir(path)
    sel_e = selector.replace("'", "\\'")
    highlighted = False
    try:
        # Apply outline directly via style — only this one element
        highlighted = await page.evaluate(f"""() => {{
            const el = document.querySelector('{sel_e}');
            if (!el) return false;
            el.__bm_prev_outline__        = el.style.outline        || '';
            el.__bm_prev_outline_offset__ = el.style.outlineOffset  || '';
            el.style.setProperty('outline',       '3px solid #0055FF', 'important');
            el.style.setProperty('outline-offset','2px',               'important');
            return true;
        }}""")

        # Scroll into view without the helper
        if highlighted:
            try:
                await page.evaluate(
                    f"() => {{"
                    f"  const el = document.querySelector('{sel_e}');"
                    f"  if (el) el.scrollIntoView({{block:'nearest', behavior:'instant'}});"
                    f"}}"
                )
                await asyncio.sleep(0.15)
            except Exception:
                pass

        # Full viewport screenshot (ISI is in-viewport after scrollIntoView)
        return await capture(page, path)

    except Exception as exc:
        logger.warning(f"capture_isi_highlighted({selector}): {exc}")
        return await capture(page, path)
    finally:
        # Always restore original outline
        if highlighted:
            try:
                await page.evaluate(f"""() => {{
                    const el = document.querySelector('{sel_e}');
                    if (el) {{
                        const prev   = el.__bm_prev_outline__        || '';
                        const prevOff= el.__bm_prev_outline_offset__ || '';
                        el.style.outline       = prev;
                        el.style.outlineOffset = prevOff;
                    }}
                }}""")
            except Exception as e:
                logger.warning(f"isi highlight cleanup: {e}")