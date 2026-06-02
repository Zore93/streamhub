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


class VideoStatusHub:
    """Topic-based broadcaster: one subscriber set per `video_id`.

    Used by the watch page to receive realtime `{progress, status, renditions}`
    updates while a freshly uploaded video is still transcoding.  Replaces the
    old HTTP polling loop entirely.
    """

    def __init__(self) -> None:
        self._topics: Dict[str, Dict[int, WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._next_id = 0

    async def connect(self, video_id: str, ws: WebSocket) -> int:
        await ws.accept()
        async with self._lock:
            self._next_id += 1
            cid = self._next_id
            self._topics.setdefault(video_id, {})[cid] = ws
        return cid

    async def disconnect(self, video_id: str, cid: int) -> None:
        async with self._lock:
            topic = self._topics.get(video_id)
            if not topic:
                return
            topic.pop(cid, None)
            if not topic:
                self._topics.pop(video_id, None)

    async def publish(self, video_id: str, payload: dict) -> None:
        msg = json.dumps({"type": "video.status", "video_id": video_id, "data": payload}, default=str)
        topic = self._topics.get(video_id)
        if not topic:
            return
        dead: list[int] = []
        for cid, ws in list(topic.items()):
            try:
                await ws.send_text(msg)
            except Exception as e:  # noqa: BLE001
                logger.debug("video.status send failed cid=%s: %s", cid, e)
                dead.append(cid)
        if dead:
            async with self._lock:
                for cid in dead:
                    topic.pop(cid, None)
                if not topic:
                    self._topics.pop(video_id, None)


video_status_hub = VideoStatusHub()
