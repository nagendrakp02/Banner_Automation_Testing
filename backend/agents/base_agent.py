
from __future__ import annotations

import re
import time
import traceback
from abc import ABC, abstractmethod
from datetime import datetime

from loguru import logger

from backend.core.constants import AgentName, CheckID, CheckStatus
from backend.services.vision_client import vision_client, OllamaError
from backend.services.broadcaster import broadcaster


QA_PERSONA = (
    "You are a senior QA engineer with 10 years of experience reviewing "
    "pharmaceutical digital banner advertisements for FDA regulatory compliance.\n"
    "You are looking at actual browser screenshots captured by an automated tool, "
    "combined with DOM/CSS measurements.\n\n"
    "Instructions:\n"
    "1. State what you SEE in the screenshot(s) explicitly.\n"
    "2. When a PRE-COMPUTED VERDICT is provided, trust it unless the screenshot "
    "clearly contradicts it. Do not invent contradictions that are not visible.\n"
    "3. Apply the check-specific rules systematically.\n"
    "4. End your response with EXACTLY one of these three lines:\n"
    "   VERDICT: pass\n"
    "   VERDICT: fail\n"
    "   VERDICT: not_applicable\n"
    "5. On the next line, rate your certainty:\n"
    "   CONFIDENCE: <integer 0-100>\n\n"
    "IMPORTANT: When DOM evidence is clear and unambiguous (e.g. userSelect=none, "
    "loadMs is a number, anyMovement=true), trust the measurements. "
    "Only override with visual evidence when explicitly instructed."
)



class AgentResult:
    __slots__ = (
        "check_id", "agent_name", "status", "raw_data",
        "llm_reasoning", "llm_verdict", "llm_confidence",
        "screenshot_path", "error_message", "duration_ms", "executed_at",
    )

    def __init__(
        self,
        check_id:        CheckID,
        agent_name:      AgentName,
        status:          CheckStatus,
        raw_data:        dict,
        llm_reasoning:   str  = "",
        llm_verdict:     str  = "",
        llm_confidence:  int | None = None,
        screenshot_path: str | None = None,
        error_message:   str | None = None,
        duration_ms:     float = 0.0,
    ):
        self.check_id        = check_id
        self.agent_name      = agent_name
        self.status          = status
        self.raw_data        = raw_data
        self.llm_reasoning   = llm_reasoning
        self.llm_verdict     = llm_verdict
        self.llm_confidence  = llm_confidence
        self.screenshot_path = screenshot_path
        self.error_message   = error_message
        self.duration_ms     = duration_ms
        self.executed_at     = datetime.utcnow()


class BaseAgent(ABC):
    check_id:   CheckID
    agent_name: AgentName

    async def run(self, page, run_id: str, screenshot_dir: str) -> AgentResult:
        start = time.perf_counter()
        await self._log(run_id, f"▶ {self.check_id.value}", "agent")
        try:
            # Step 1: Collect DOM/CSS evidence
            dom_ev = await self.collect_dom_evidence(page)

            # Step 2: Capture contextual screenshots
            shots = await self.capture_evidence_shots(page, run_id, screenshot_dir)
            primary = shots[0] if shots else None

            # Step 3: Build agentic prompt
            system_prompt, user_evidence = self.build_qa_prompt(dom_ev)
            await self._log(
                run_id,
                f"  → Ollama vision ({len(shots)} screenshot(s), "
                f"{len(user_evidence)} evidence chars)",
                "info",
            )

            # Step 4: LLM judges the evidence
            reasoning = await vision_client.judge(system_prompt, user_evidence, shots)
            await self._log(run_id, f"  ← {reasoning[:140]}", "agent")

            # Step 5: Extract verdict + confidence
            verdict    = self._extract_verdict(reasoning)
            confidence = vision_client.extract_confidence(reasoning)
            status = (
                CheckStatus.PASS
                if verdict in ("pass", "not_applicable")
                else CheckStatus.FAIL
            )

            dur  = (time.perf_counter() - start) * 1000
            icon = "✓" if status == CheckStatus.PASS else "✗"
            conf_str = f" conf={confidence}%" if confidence is not None else ""
            await self._log(
                run_id,
                f"{icon} {self.check_id.value}: {status.value.upper()} "
                f"({dur:.0f}ms{conf_str})",
                "result",
            )

            return AgentResult(
                check_id=self.check_id, agent_name=self.agent_name,
                status=status, raw_data=dom_ev,
                llm_reasoning=reasoning, llm_verdict=verdict,
                llm_confidence=confidence,
                screenshot_path=primary, duration_ms=dur,
            )

        except OllamaError as exc:
            dur = (time.perf_counter() - start) * 1000
            msg = str(exc)
            await self._log(run_id, f"  ⚠ Ollama unavailable: {msg[:120]}", "error")
            return AgentResult(
                check_id=self.check_id, agent_name=self.agent_name,
                status=CheckStatus.ERROR, raw_data={},
                error_message=msg,
                llm_reasoning=f"Vision model unavailable: {msg}",
                duration_ms=dur,
            )

        except Exception as exc:
            dur = (time.perf_counter() - start) * 1000
            err = str(exc) or repr(exc) or traceback.format_exc().splitlines()[-1]
            logger.exception(f"{self.agent_name}/{self.check_id}: {err}")
            await self._log(run_id, f"  ✗ ERROR: {err}", "error")
            return AgentResult(
                check_id=self.check_id, agent_name=self.agent_name,
                status=CheckStatus.ERROR, raw_data={},
                error_message=err, duration_ms=dur,
            )



    @abstractmethod
    async def collect_dom_evidence(self, page) -> dict:
        """Pure DOM/CSS measurements. No interpretation — facts only."""

    @abstractmethod
    async def capture_evidence_shots(
        self, page, run_id: str, screenshot_dir: str
    ) -> list[str]:
        """
        Return list of screenshot file paths (first is the primary/display shot).
        Each screenshot should be contextually meaningful for the LLM.
        """

    @abstractmethod
    def build_qa_prompt(self, dom_ev: dict) -> tuple[str, str]:
        """
        Returns (system_prompt, user_evidence_text).
        system_prompt: QA persona + check rules + pass/fail criteria
        user_evidence: formatted DOM facts the LLM uses alongside screenshots
        """


    @staticmethod
    def _extract_verdict(text: str) -> str:
        """
        Robust VERDICT extraction from free-form LLM output.
        Priority: explicit token > last-line keyword > frequency count.
        """
        # 1. Explicit VERDICT: token
        m = re.search(
            r"VERDICT\s*:\s*(pass|fail|not_applicable)",
            text, re.IGNORECASE,
        )
        if m:
            return m.group(1).lower()

        # 2. Last non-empty line keyword
        lines = [ln.strip().lower() for ln in text.strip().splitlines() if ln.strip()]
        if lines:
            last = lines[-1]
            for v in ("not_applicable", "not applicable", "pass", "fail"):
                if v in last:
                    return v.replace(" ", "_")

        # 3. Frequency count as final fallback
        lower = text.lower()
        counts = {
            "pass":           lower.count("pass"),
            "fail":           lower.count("fail"),
            "not_applicable": max(
                lower.count("not_applicable"),
                lower.count("not applicable"),
            ),
        }
        best = max(counts, key=counts.get)
        return best if counts[best] > 0 else "fail"

    async def _log(self, run_id: str, msg: str, level: str = "info") -> None:
        await broadcaster.emit(run_id, msg, level=level, agent=self.agent_name.value)