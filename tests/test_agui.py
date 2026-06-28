"""Tests for AG-UI Gateway."""

import time

from codeops.agui import (
    AGUIContext,
    AGUIEvent,
    AGUIEventType,
    AGUIGateway,
)


def test_event_creation() -> None:
    event = AGUIEvent.text_start("msg-1")
    assert event.type == AGUIEventType.TEXT_MESSAGE_START
    assert event.message_id == "msg-1"

    event = AGUIEvent.text_content("msg-1", "Hello")
    assert event.type == AGUIEventType.TEXT_MESSAGE_CONTENT
    assert event.delta == "Hello"

    event = AGUIEvent.text_end("msg-1")
    assert event.type == AGUIEventType.TEXT_MESSAGE_END

    event = AGUIEvent.run_started()
    assert event.type == AGUIEventType.RUN_STARTED

    event = AGUIEvent.run_finished()
    assert event.type == AGUIEventType.RUN_FINISHED

    event = AGUIEvent.run_error("Test error")
    assert event.type == AGUIEventType.RUN_ERROR
    assert event.content == "Test error"


def test_event_sse_serialization() -> None:
    event = AGUIEvent.text_content("msg-1", "Hello World")
    sse = event.to_sse()
    assert sse.startswith("data: ")
    assert "TEXT_MESSAGE_CONTENT" in sse
    assert "Hello World" in sse
    assert sse.endswith("\n\n")


def test_gateway_create_session() -> None:
    gateway = AGUIGateway()
    ctx = AGUIContext(conversation_id="conv-1")
    session_id = gateway.create_session(ctx)
    assert session_id
    assert session_id == ctx.session_id


def test_gateway_stream_text() -> None:
    gateway = AGUIGateway()
    ctx = AGUIContext(conversation_id="conv-text")
    session_id = gateway.create_session(ctx)

    received_events: list[AGUIEvent] = []

    def callback(event: AGUIEvent) -> None:
        received_events.append(event)

    gateway.subscribe(session_id, callback)
    gateway.stream_text(session_id, "Hello from AG-UI!")

    time.sleep(0.05)

    assert len(received_events) == 3
    assert received_events[0].type == AGUIEventType.TEXT_MESSAGE_START
    assert received_events[1].type == AGUIEventType.TEXT_MESSAGE_CONTENT
    assert received_events[2].type == AGUIEventType.TEXT_MESSAGE_END


def test_gateway_state_management() -> None:
    gateway = AGUIGateway()
    ctx = AGUIContext(conversation_id="conv-state")
    session_id = gateway.create_session(ctx)

    gateway.emit(session_id, AGUIEvent.state_delta({"progress": 50}))
    gateway.emit(session_id, AGUIEvent.state_delta({"status": "working"}))

    state = gateway.get_state(session_id)
    assert state.get("progress") == 50
    assert state.get("status") == "working"


def test_gateway_close_session() -> None:
    gateway = AGUIGateway()
    ctx = AGUIContext(conversation_id="conv-close")
    session_id = gateway.create_session(ctx)

    gateway.close_session(session_id)
    assert session_id not in gateway._event_queues
    assert session_id not in gateway._state


def test_agui_context_defaults() -> None:
    ctx = AGUIContext(conversation_id="test-conv")
    assert ctx.conversation_id == "test-conv"
    assert ctx.user_id == "default"
    assert ctx.session_id
