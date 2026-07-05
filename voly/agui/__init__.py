"""
AG-UI Gateway — протокол связи агентов с пользовательским интерфейсом.

Реализует Agent-User Interaction Protocol (CopilotKit):
    - Real-time стриминг состояния агента в UI
    - События: text, tool_calls, state, generative UI
    - SSE (Server-Sent Events) для стриминга
    - HTTP API для отправки команд агенту

Формат событий AG-UI:
    TEXT_MESSAGE_START    — начало текстового сообщения
    TEXT_MESSAGE_CONTENT  — фрагмент текста (delta)
    TEXT_MESSAGE_END      — завершение текстового сообщения
    TOOL_CALL_START       — начало вызова инструмента
    TOOL_CALL_ARGS        — аргументы инструмента (delta)
    TOOL_CALL_END         — завершение вызова инструмента
    STATE_SNAPSHOT        — полный снимок состояния
    STATE_DELTA           — частичное обновление состояния
    RUN_STARTED           — запуск ран-лупа агента
    RUN_FINISHED          — завершение ран-лупа
"""

from __future__ import annotations

import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generator


class AGUIEventType(Enum):
    TEXT_MESSAGE_START = "TEXT_MESSAGE_START"
    TEXT_MESSAGE_CONTENT = "TEXT_MESSAGE_CONTENT"
    TEXT_MESSAGE_END = "TEXT_MESSAGE_END"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_ARGS = "TOOL_CALL_ARGS"
    TOOL_CALL_END = "TOOL_CALL_END"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"
    STATE_SNAPSHOT = "STATE_SNAPSHOT"
    STATE_DELTA = "STATE_DELTA"
    RUN_STARTED = "RUN_STARTED"
    RUN_FINISHED = "RUN_FINISHED"
    RUN_ERROR = "RUN_ERROR"
    CUSTOM = "CUSTOM"
    META = "META"


@dataclass
class AGUIEvent:
    type: AGUIEventType
    message_id: str = ""
    content: str = ""
    tool_call_id: str = ""
    tool_name: str = ""
    delta: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    custom_type: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0

    def __post_init__(self) -> None:
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    def to_sse(self) -> str:
        payload = {"type": self.type.value, "timestamp": self.timestamp}
        if self.message_id:
            payload["messageId"] = self.message_id
        if self.content:
            payload["content"] = self.content
        if self.tool_call_id:
            payload["toolCallId"] = self.tool_call_id
        if self.tool_name:
            payload["toolName"] = self.tool_name
        if self.delta:
            payload["delta"] = self.delta
        if self.state:
            payload["state"] = self.state
        if self.custom_type:
            payload["customType"] = self.custom_type
        if self.meta:
            payload["meta"] = self.meta
        return f"data: {json.dumps(payload)}\n\n"

    @classmethod
    def text_start(cls, message_id: str = "") -> AGUIEvent:
        return cls(type=AGUIEventType.TEXT_MESSAGE_START, message_id=message_id or str(uuid.uuid4()))

    @classmethod
    def text_content(cls, message_id: str, content: str) -> AGUIEvent:
        return cls(type=AGUIEventType.TEXT_MESSAGE_CONTENT, message_id=message_id, delta=content)

    @classmethod
    def text_end(cls, message_id: str) -> AGUIEvent:
        return cls(type=AGUIEventType.TEXT_MESSAGE_END, message_id=message_id)

    @classmethod
    def tool_start(cls, tool_call_id: str, tool_name: str) -> AGUIEvent:
        return cls(type=AGUIEventType.TOOL_CALL_START, tool_call_id=tool_call_id, tool_name=tool_name)

    @classmethod
    def tool_args(cls, tool_call_id: str, delta: str) -> AGUIEvent:
        return cls(type=AGUIEventType.TOOL_CALL_ARGS, tool_call_id=tool_call_id, delta=delta)

    @classmethod
    def tool_end(cls, tool_call_id: str) -> AGUIEvent:
        return cls(type=AGUIEventType.TOOL_CALL_END, tool_call_id=tool_call_id)

    @classmethod
    def tool_result(cls, tool_call_id: str, result: str) -> AGUIEvent:
        return cls(type=AGUIEventType.TOOL_CALL_RESULT, tool_call_id=tool_call_id, content=result)

    @classmethod
    def state_snapshot(cls, state: dict[str, Any]) -> AGUIEvent:
        return cls(type=AGUIEventType.STATE_SNAPSHOT, state=state)

    @classmethod
    def state_delta(cls, delta: dict[str, Any]) -> AGUIEvent:
        return cls(type=AGUIEventType.STATE_DELTA, state=delta)

    @classmethod
    def run_started(cls) -> AGUIEvent:
        return cls(type=AGUIEventType.RUN_STARTED)

    @classmethod
    def run_finished(cls) -> AGUIEvent:
        return cls(type=AGUIEventType.RUN_FINISHED)

    @classmethod
    def run_error(cls, error: str) -> AGUIEvent:
        return cls(type=AGUIEventType.RUN_ERROR, content=error)


@dataclass
class AGUIContext:
    conversation_id: str
    user_id: str = "default"
    session_id: str = ""
    agent_id: str = ""
    project_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.session_id:
            self.session_id = str(uuid.uuid4())


class AGUIGateway:
    def __init__(self, remote_client: Any | None = None):
        self._remote_client = remote_client
        self._event_queues: dict[str, queue.Queue[AGUIEvent | None]] = {}
        self._subscribers: dict[str, list[Callable[[AGUIEvent], None]]] = {}
        self._state: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def create_session(self, ctx: AGUIContext) -> str:
        session_id = ctx.session_id
        with self._lock:
            self._event_queues[session_id] = queue.Queue()
            self._state[session_id] = {}
        self.emit(session_id, AGUIEvent.run_started())
        return session_id

    def emit(self, session_id: str, event: AGUIEvent) -> None:
        with self._lock:
            if session_id in self._event_queues:
                self._event_queues[session_id].put(event)
            if session_id in self._state:
                if event.type == AGUIEventType.STATE_SNAPSHOT:
                    self._state[session_id].update(event.state)
                elif event.type == AGUIEventType.STATE_DELTA:
                    self._state[session_id].update(event.state)

        if self._remote_client:
            try:
                payload = {
                    "type": event.type.value,
                    "timestamp": event.timestamp,
                    "messageId": event.message_id,
                    "content": event.content,
                    "delta": event.delta,
                    "toolCallId": event.tool_call_id,
                    "toolName": event.tool_name,
                    "state": event.state,
                }
                self._remote_client.emit_event(session_id, payload)
            except Exception:
                pass

        if session_id in self._subscribers:
            for callback in self._subscribers[session_id]:
                try:
                    callback(event)
                except Exception:
                    pass

    def stream_text(self, session_id: str, text: str) -> None:
        msg_id = str(uuid.uuid4())
        self.emit(session_id, AGUIEvent.text_start(msg_id))
        self.emit(session_id, AGUIEvent.text_content(msg_id, text))
        self.emit(session_id, AGUIEvent.text_end(msg_id))

    def stream_tool_call(self, session_id: str, tool_name: str, args: str, result: str = "") -> None:
        tool_id = str(uuid.uuid4())
        self.emit(session_id, AGUIEvent.tool_start(tool_id, tool_name))
        self.emit(session_id, AGUIEvent.tool_args(tool_id, args))
        self.emit(session_id, AGUIEvent.tool_end(tool_id))
        if result:
            self.emit(session_id, AGUIEvent.tool_result(tool_id, result))

    def subscribe(self, session_id: str, callback: Callable[[AGUIEvent], None]) -> None:
        with self._lock:
            if session_id not in self._subscribers:
                self._subscribers[session_id] = []
            self._subscribers[session_id].append(callback)

    def unsubscribe(self, session_id: str, callback: Callable[[AGUIEvent], None]) -> None:
        with self._lock:
            if session_id in self._subscribers:
                self._subscribers[session_id] = [
                    cb for cb in self._subscribers[session_id] if cb is not callback
                ]

    def get_state(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._state.get(session_id, {}))

    def close_session(self, session_id: str) -> None:
        self.emit(session_id, AGUIEvent.run_finished())
        with self._lock:
            self._event_queues.pop(session_id, None)
            self._state.pop(session_id, None)
            self._subscribers.pop(session_id, None)

    def sse_stream(self, session_id: str) -> Generator[str, None, None]:
        q = self._event_queues.get(session_id)
        if not q:
            yield f"data: {json.dumps({'type': 'RUN_ERROR', 'content': 'session not found'})}\n\n"
            return

        yield ":ok\n\n"
        while True:
            try:
                event = q.get(timeout=30.0)
                if event is None:
                    break
                yield event.to_sse()
            except queue.Empty:
                yield f": heartbeat {int(time.time())}\n\n"

    def to_sse_response(self, session_id: str, status: str = "200 OK") -> str:
        headers = (
            f"HTTP/1.1 {status}\r\n"
            "Content-Type: text/event-stream\r\n"
            "Cache-Control: no-cache\r\n"
            "Connection: keep-alive\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "\r\n"
        )
        body = []
        for sse_chunk in self.sse_stream(session_id):
            body.append(sse_chunk)
            if AGUIEventType.RUN_FINISHED.value in sse_chunk:
                break
        return headers + "".join(body)


def create_agui_gateway(remote_url: str = "") -> AGUIGateway:
    from voly.agui.remote import create_remote_agui_client

    client = create_remote_agui_client(remote_url)
    return AGUIGateway(remote_client=client)
