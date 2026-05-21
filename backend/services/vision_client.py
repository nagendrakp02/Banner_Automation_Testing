
from __future__ import annotations

import asyncio
import base64
import json as _json
import re
import time
from pathlib import Path

import httpx
from loguru import logger

_CANDIDATE_MODELS = [
    "qwen2.5:7b",
    "llava:latest"
    
]

MAX_RETRIES    = 3
RETRY_BACKOFF  = 2.0      # seconds; doubles each attempt
STREAM_TIMEOUT = httpx.Timeout(connect=10, read=300, write=30, pool=10)
MAX_IMAGES     = 4        # Ollama multimodal context limit
MAX_TOKENS     = 800


class OllamaVisionClient:
    """
    Agentic vision client that wraps a local Ollama instance.

    Sends screenshots as base64 images together with structured DOM
    evidence to a vision-capable LLM. Returns the full chain-of-thought
    reasoning including the mandatory VERDICT token.
    """

    def __init__(self) -> None:
        self._model: str | None = None
        self._lock = asyncio.Lock()
        self.base_url = "http://localhost:11434"  # overridden by config at runtime

    def configure(self, base_url: str, model: str) -> None:
        """Called by main.py lifespan to inject settings."""
        self.base_url = base_url.rstrip("/")
        self._model   = model   # still validated / overridden by _resolve_model


    async def judge(
        self,
        system: str,
        text: str,
        screenshot_paths: list[str],
    ) -> str:
        """
        Submit evidence to the vision model and return its full reasoning.

        Parameters
        ----------
        system:           QA persona + check-specific pass/fail rules
        text:             Structured DOM evidence (facts, measurements)
        screenshot_paths: Up to MAX_IMAGES PNG file paths
        """
        model  = await self._resolve_model()
        images = self._load_images(screenshot_paths)

        # Ollama /api/chat multimodal format
        user_message: dict = {"role": "user", "content": text}
        if images:
            user_message["images"] = images

        payload = {
            "model":   model,
            "messages": [
                {"role": "system", "content": system},
                user_message,
            ],
            "stream":  True,
            "options": {
                "temperature": 0.1,
                "num_predict": MAX_TOKENS,
                "top_p": 0.9,
            },
        }

        last_err: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response_text = await self._stream_generate(payload)
                return response_text
            except httpx.ConnectError as exc:
                last_err = exc
                logger.warning(
                    f"Ollama not reachable (attempt {attempt}/{MAX_RETRIES}). "
                    f"Is 'ollama serve' running? Base URL: {self.base_url}"
                )
            except httpx.TimeoutException as exc:
                last_err = exc
                logger.warning(f"Ollama timeout (attempt {attempt}/{MAX_RETRIES})")
            except httpx.HTTPStatusError as exc:
                last_err = exc
                logger.warning(
                    f"Ollama HTTP {exc.response.status_code} "
                    f"(attempt {attempt}/{MAX_RETRIES}): {exc.response.text[:200]}"
                )
            except Exception as exc:
                last_err = exc
                logger.warning(f"Ollama error (attempt {attempt}/{MAX_RETRIES}): {exc}")

            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF ** attempt
                logger.info(f"Retrying Ollama in {wait:.1f}s …")
                await asyncio.sleep(wait)

        raise OllamaError(
            f"Ollama unavailable after {MAX_RETRIES} attempts. "
            f"Last error: {last_err}. "
            f"Ensure Ollama is running: ollama serve && ollama pull {model}"
        )

    async def is_available(self) -> bool:
        """True if Ollama is running AND the target model is pulled."""
        info = await self.get_model_info()
        return info["ollama_running"] and info["model_pulled"]

    async def get_model_info(self) -> dict:
        """Rich health info for /health endpoint."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                resp.raise_for_status()
                data   = resp.json()
                pulled = [m["name"] for m in data.get("models", [])]

                # Resolve preferred model name
                model = await self._resolve_model()
                model_base = model.split(":")[0]
                model_pulled = any(
                    model == p or model_base in p
                    for p in pulled
                )
                vision_models = [
                    p for p in pulled
                    if any(kw in p.lower() for kw in
                           ["llava", "vision", "moondream", "minicpm", "bakllava"])
                ]
                return {
                    "ollama_running": True,
                    "active_model":   model,
                    "model_pulled":   model_pulled,
                    "vision_models":  vision_models,
                    "all_models":     pulled,
                    "ollama_url":     self.base_url,
                }
        except Exception as exc:
            return {
                "ollama_running": False,
                "active_model":   self._model,
                "model_pulled":   False,
                "vision_models":  [],
                "all_models":     [],
                "ollama_url":     self.base_url,
                "error":          str(exc),
            }

    @staticmethod
    def extract_confidence(text: str) -> int | None:
        """Parse CONFIDENCE: <0-100> from model output if present."""
        m = re.search(r"CONFIDENCE\s*:\s*(\d{1,3})", text, re.IGNORECASE)
        if m:
            return max(0, min(100, int(m.group(1))))
        return None

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _stream_generate(self, payload: dict) -> str:
        """
        Call Ollama /api/chat in streaming mode.
        Collecting all tokens avoids read-timeout on slow GPUs.
        """
        t0 = time.perf_counter()
        tokens: list[str] = []
        async with httpx.AsyncClient(timeout=STREAM_TIMEOUT) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/chat",
                json=payload,
            ) as resp:
                if resp.status_code != 200:
                    body = await resp.aread()
                    raise httpx.HTTPStatusError(
                        message=f"HTTP {resp.status_code}",
                        request=resp.request,
                        response=resp,
                    )
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = _json.loads(line)
                    except Exception:
                        continue
                    token = chunk.get("message", {}).get("content", "")
                    if token:
                        tokens.append(token)
                    if chunk.get("done"):
                        break

        result = "".join(tokens).strip()
        elapsed = (time.perf_counter() - t0) * 1000
        logger.debug(
            f"Ollama [{payload['model']}] {elapsed:.0f}ms | "
            f"{len(tokens)} tokens | {len(result)} chars"
        )
        return result

    async def _resolve_model(self) -> str:
        """
        Auto-detect best available Ollama vision model.
        Cached after first successful resolution.
        Config-provided model is tried first; falls through candidates if unavailable.
        """
        async with self._lock:
            if self._model:
                return self._model

            try:
                async with httpx.AsyncClient(timeout=8) as client:
                    resp = await client.get(f"{self.base_url}/api/tags")
                    resp.raise_for_status()
                    pulled_full = {m["name"] for m in resp.json().get("models", [])}
                    pulled_base = {m.split(":")[0] for m in pulled_full}
            except Exception as exc:
                logger.warning(f"Model resolution failed: {exc}. Defaulting to llava:13b")
                self._model = "llava:13b"
                return self._model

            for candidate in _CANDIDATE_MODELS:
                base = candidate.split(":")[0]
                if candidate in pulled_full or base in pulled_base:
                    self._model = candidate
                    logger.info(f"✓ BannerMind vision model: {self._model}")
                    return self._model

            # Nothing matched — use whatever is installed
            if pulled_full:
                self._model = next(iter(sorted(pulled_full)))
                logger.warning(f"No preferred vision model found. Using: {self._model}")
            else:
                self._model = "llava:13b"
                logger.warning(
                    "No models installed in Ollama. "
                    "Pull one: ollama pull llava:13b"
                )
            return self._model

    @staticmethod
    def _load_images(paths: list[str]) -> list[str]:
        """
        Load screenshot files as base64 strings.
        Silently skips missing/unreadable files.
        Caps at MAX_IMAGES (Ollama VRAM budget).
        """
        images: list[str] = []
        for path in paths[:MAX_IMAGES]:
            try:
                raw = Path(path).read_bytes()
                images.append(base64.standard_b64encode(raw).decode())
                logger.debug(f"  image loaded: {Path(path).name} ({len(raw)//1024}KB)")
            except Exception as exc:
                logger.warning(f"  image load failed [{path}]: {exc}")
        return images


class OllamaError(Exception):
    """Raised when Ollama is unreachable or returns an unrecoverable error."""


# Module-level singleton — configure() is called in main.py lifespan
vision_client = OllamaVisionClient()