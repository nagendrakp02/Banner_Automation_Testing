
"""services/broadcaster.py — WebSocket pub/sub for live agent logs."""
import json
from datetime import datetime
from typing import Callable
from loguru import logger
 
 
class RunBroadcaster:
    def __init__(self):
        self._subs: dict[str, set[Callable]] = {}
 
    def subscribe(self, run_id: str, cb: Callable):
        self._subs.setdefault(run_id, set()).add(cb)
 
    def unsubscribe(self, run_id: str, cb: Callable):
        if run_id in self._subs:
            self._subs[run_id].discard(cb)
 
    async def emit(
        self,
        run_id: str,
        message: str,
        level: str = "info",
        agent: str | None = None,
    ):
        payload = json.dumps({
            "run_id":    run_id,
            "level":     level,
            "agent":     agent,
            "message":   message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
        for cb in list(self._subs.get(run_id, [])):
            try:
                await cb(payload)
            except Exception as exc:
                logger.warning(f"WS send failed: {exc}")
 
 
broadcaster = RunBroadcaster()