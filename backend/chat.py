"""WebSocket-based live chat broadcaster.

This is intentionally small + in-memory.  Persistence lives in MongoDB
(`db.chat_messages`); the broadcaster only routes packets between connected
sockets so every viewer sees new messages without polling.
"""
import asyncio
import json
import logging
from typing import Dict

from fastapi import WebSocket

logger = logging.getLogger("streamhub.chat")


class ChatHub:
    def __init__(self) -> None:
        self._clients: Dict[int, WebSocket] = {}
        self._lock = asyncio.Lock()
        self._next_id = 0

    async def connect(self, ws: WebSocket) -> int:
        await ws.accept()
        async with self._lock:
            self._next_id += 1
            cid = self._next_id
            self._clients[cid] = ws
        return cid

    async def disconnect(self, cid: int) -> None:
        async with self._lock:
            self._clients.pop(cid, None)

    async def broadcast(self, payload: dict) -> None:
        msg = json.dumps(payload, default=str)
        dead: list[int] = []
        # Snapshot so we don't mutate during iteration
        for cid, ws in list(self._clients.items()):
            try:
                await ws.send_text(msg)
            except Exception as e:  # noqa: BLE001
                logger.debug("ws send failed cid=%s: %s", cid, e)
                dead.append(cid)
        if dead:
            async with self._lock:
                for cid in dead:
                    self._clients.pop(cid, None)


hub = ChatHub()
