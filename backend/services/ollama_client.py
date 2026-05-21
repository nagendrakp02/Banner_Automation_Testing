
import base64
import os
import httpx
import json as json_mod
from loguru import logger

TEXT_MODEL   = os.getenv("OLLAMA_TEXT_MODEL",   "qwen2.5:7b")
VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "llava:latest")
OLLAMA_BASE  = os.getenv("OLLAMA_BASE_URL",     "http://localhost:11434")

STREAM_TIMEOUT  = 480   # 8 min — llava on CPU can be slow
CONNECT_TIMEOUT = 10


class OllamaError(Exception):
    pass


class OllamaClient:

    async def text(self, system: str, user: str) -> str:
        """Fast text-only reasoning. No images. Uses TEXT_MODEL (qwen2.5:7b)."""
        return await self._stream(TEXT_MODEL, system, user, images=[])

    async def vision(self, system: str, user: str, image_paths: list[str]) -> str:
        """
        Vision + text reasoning. Uses VISION_MODEL (llava:13b).
        Falls back to text-only if no valid images.
        """
        images = []
        for p in (image_paths or []):
            if not p:
                continue
            try:
                with open(p, "rb") as f:
                    images.append(base64.b64encode(f.read()).decode())
            except Exception as exc:
                logger.warning(f"  Screenshot encode failed ({p}): {exc}")
        model = VISION_MODEL if images else TEXT_MODEL
        return await self._stream(model, system, user, images=images)

    async def _stream(
        self, model: str, system: str, user: str, images: list[str]
    ) -> str:
        user_msg: dict = {"role": "user", "content": user}
        if images:
            user_msg["images"] = images

        payload = {
            "model":   model,
            "messages": [
                {"role": "system", "content": system},
                user_msg,
            ],
            "stream":  True,
            "options": {
                "temperature": 0.05,
                "num_predict": 600,
                "top_p":       0.9,
            },
        }
        timeout = httpx.Timeout(
            connect=CONNECT_TIMEOUT,
            read=STREAM_TIMEOUT,
            write=30,
            pool=10,
        )
        try:
            tokens = []
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST", f"{OLLAMA_BASE}/api/chat", json=payload
                ) as resp:
                    if resp.status_code != 200:
                        body = await resp.aread()
                        raise OllamaError(
                            f"Ollama HTTP {resp.status_code}: {body[:200]}"
                        )
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json_mod.loads(line)
                        except Exception:
                            continue
                        tok = chunk.get("message", {}).get("content", "")
                        if tok:
                            tokens.append(tok)
                        if chunk.get("done"):
                            break

            result = "".join(tokens).strip()
            logger.debug(f"[{model}] {len(result)} chars → {result[:80]}")
            return result

        except httpx.ConnectError as exc:
            raise OllamaError(
                f"Cannot connect to Ollama at {OLLAMA_BASE}. "
                f"Run: ollama serve\n{exc}"
            ) from exc
        except OllamaError:
            raise
        except Exception as exc:
            raise OllamaError(f"Ollama stream error ({model}): {exc}") from exc

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as c:
                r = await c.get(f"{OLLAMA_BASE}/api/tags")
                return r.status_code == 200
        except Exception:
            return False


ollama_client = OllamaClient()