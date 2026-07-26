from __future__ import annotations
import asyncio
import json
from collections import defaultdict


class TaskSSEBroker:
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)

    def subscribe(self, task_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[task_id].append(q)
        return q

    def unsubscribe(self, task_id: str, q: asyncio.Queue):
        if q in self._subscribers[task_id]:
            self._subscribers[task_id].remove(q)

    async def broadcast(self, task_id: str, event: str, data: dict):
        msg = f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        for q in self._subscribers.get(task_id, []):
            await q.put(msg)


sse_broker = TaskSSEBroker()
