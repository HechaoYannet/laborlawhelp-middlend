import json
import logging
import time
from dataclasses import dataclass, field
from uuid import uuid4

from app.adapters.openharness import openharness_client
from app.core.config import settings
from app.core.errors import AppError
from app.modules.auth import Owner
from app.modules.case_session.service import get_session
from app.modules.chat.audit import AuditService
from app.modules.chat.events import (
    content_delta_event,
    error_event,
    final_event,
    message_end_event,
    message_start_event,
    tool_call_event,
    tool_result_event,
)
from app.modules.chat.schemas import ChatRequest
from app.modules.storage import BaseStore, get_store

logger = logging.getLogger(__name__)


@dataclass
class ChatTurnState:
    assistant_id: str
    trace_id: str
    started_at: float
    full_text: str = ""
    assistant_saved: bool = False
    message_started: bool = False
    finish_reason: str = "error"
    retry_count: int = 0
    tool_events: list[dict] = field(default_factory=list)


def _log_turn(level: str, message: str, payload: dict) -> None:
    log_fn = logger.info if level == "info" else logger.error
    log_fn("%s %s", message, json.dumps(payload, ensure_ascii=False))


async def _save_failed_assistant_message(
    data_store: BaseStore,
    session_id: str,
    state: ChatTurnState,
    exc: AppError,
) -> None:
    if state.assistant_saved:
        return
    await data_store.save_message(
        session_id=session_id,
        role="assistant",
        content="",
        message_id=state.assistant_id,
        metadata={
            "status": "failed",
            "trace_id": state.trace_id,
            "error_code": exc.code,
            "retryable": exc.retryable,
        },
    )
    await data_store.update_session_activity(session_id, message_increment=1)


async def _record_success(audit_service: AuditService, owner: Owner, session_id: str, state: ChatTurnState) -> None:
    latency_ms = int((time.monotonic() - state.started_at) * 1000)
    _log_turn(
        "info",
        "chat_turn_complete",
        {
            "trace_id": state.trace_id,
            "session_id": session_id,
            "owner_id": owner.owner_id,
            "workflow": settings.oh_default_workflow,
            "latency_ms": latency_ms,
            "finish_reason": state.finish_reason,
            "retry_count": state.retry_count,
        },
    )
    await audit_service.record_turn_success(
        trace_id=state.trace_id,
        session_id=session_id,
        owner_type=owner.owner_type,
        owner_id=owner.owner_id,
        workflow=settings.oh_default_workflow,
        latency_ms=latency_ms,
        finish_reason=state.finish_reason,
        retry_count=state.retry_count,
    )


async def _record_failure(
    audit_service: AuditService,
    owner: Owner,
    session_id: str,
    state: ChatTurnState,
    error_code: str,
) -> None:
    latency_ms = int((time.monotonic() - state.started_at) * 1000)
    _log_turn(
        "error",
        "chat_turn_failed",
        {
            "trace_id": state.trace_id,
            "session_id": session_id,
            "owner_id": owner.owner_id,
            "workflow": settings.oh_default_workflow,
            "latency_ms": latency_ms,
            "finish_reason": error_code,
            "retry_count": state.retry_count,
            "error_code": error_code,
        },
    )
    await audit_service.record_turn_failure(
        trace_id=state.trace_id,
        session_id=session_id,
        owner_type=owner.owner_type,
        owner_id=owner.owner_id,
        workflow=settings.oh_default_workflow,
        latency_ms=latency_ms,
        finish_reason=error_code,
        retry_count=state.retry_count,
        error_code=error_code,
    )


async def stream_chat(owner: Owner, session_id: str, request: ChatRequest):
    session = await get_session(owner, session_id)
    data_store = get_store()
    state = ChatTurnState(
        assistant_id=str(uuid4()),
        trace_id=str(uuid4()),
        started_at=time.monotonic(),
    )
    audit_service = AuditService(data_store)

    async with data_store.acquire_session_lock(session_id):
        try:
            await data_store.save_message(session_id=session_id, role="user", content=request.message)
            await data_store.update_session_activity(session_id, message_increment=1)

            yield message_start_event(state.assistant_id, state.trace_id)
            state.message_started = True

            async for chunk in openharness_client.stream_run(
                prompt=request.message,
                session_id=session.openharness_session_id,
                user_context={
                    "owner_type": owner.owner_type,
                    "owner_id": owner.owner_id,
                },
                trace_id=state.trace_id,
                locale=request.locale,
                policy_version=request.policy_version,
                client_capabilities=request.client_capabilities,
            ):
                if chunk.type == "text" and chunk.content:
                    seq = await data_store.next_stream_seq(session_id)
                    state.full_text += chunk.content
                    yield content_delta_event(chunk.content, seq, state.trace_id)
                    continue

                if chunk.type == "tool_call":
                    yield tool_call_event(chunk, state.trace_id)
                    continue

                if chunk.type == "tool_result":
                    tool_metadata = chunk.metadata or {}
                    state.tool_events.append(
                        {
                            "tool_name": chunk.tool_name,
                            "result_summary": tool_metadata.get("result_summary") or tool_metadata.get("status", "ok"),
                            "references": tool_metadata.get("references", []),
                            "card_type": tool_metadata.get("card_type"),
                            "card_title": tool_metadata.get("card_title"),
                            "card_payload": tool_metadata.get("card_payload"),
                            "card_actions": tool_metadata.get("card_actions", []),
                            "trace_id": state.trace_id,
                        }
                    )
                    yield tool_result_event(chunk, state.trace_id)
                    continue

                if chunk.type == "final":
                    metadata = chunk.metadata or {}
                    state.finish_reason = metadata.get("finish_reason", "stop")
                    state.retry_count = int(metadata.get("retry_count", 0))
                    await data_store.save_message(
                        session_id=session_id,
                        role="assistant",
                        content=state.full_text,
                        message_id=state.assistant_id,
                        metadata={
                            "status": "succeeded",
                            "trace_id": state.trace_id,
                            "finish_reason": state.finish_reason,
                            "retry_count": state.retry_count,
                            "summary": metadata.get("summary", ""),
                            "references": metadata.get("references", []),
                            "rule_version": metadata.get("rule_version", ""),
                            "tool_events": state.tool_events,
                        },
                    )
                    state.assistant_saved = True
                    await data_store.update_session_activity(session_id, message_increment=1)

                    yield final_event(state.assistant_id, metadata, state.finish_reason, state.trace_id)
                    yield message_end_event(state.assistant_id, state.trace_id)
                    await _record_success(audit_service, owner, session_id, state)
                    return

            raise AppError(502, "OH_SERVICE_ERROR", "OpenHarness 服务暂时不可用", retryable=True)
        except AppError as exc:
            await _save_failed_assistant_message(data_store, session_id, state, exc)
            if not state.message_started:
                yield message_start_event(state.assistant_id, state.trace_id)
                state.message_started = True
            yield error_event(exc, state.trace_id)
            yield message_end_event(state.assistant_id, state.trace_id)
            await _record_failure(audit_service, owner, session_id, state, exc.code)
        except Exception:
            exc = AppError(502, "OH_SERVICE_ERROR", "OpenHarness 服务暂时不可用", retryable=True)
            await _save_failed_assistant_message(data_store, session_id, state, exc)
            if not state.message_started:
                yield message_start_event(state.assistant_id, state.trace_id)
                state.message_started = True
            yield error_event(exc, state.trace_id)
            yield message_end_event(state.assistant_id, state.trace_id)
            await _record_failure(audit_service, owner, session_id, state, exc.code)
