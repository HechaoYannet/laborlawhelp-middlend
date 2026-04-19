import json
import logging
import time
from uuid import uuid4

from app.adapters.openharness_client import openharness_client
from app.core.auth import Owner
from app.core.config import settings
from app.core.errors import AppError
from app.core.sse import sse_event
from app.core.store import store
from app.models.schemas import ChatRequest
from app.services.audit_service import AuditService
from app.services.session_service import get_session

logger = logging.getLogger(__name__)


async def stream_chat(owner: Owner, session_id: str, request: ChatRequest):
    session = await get_session(owner, session_id)
    trace_id = str(uuid4())
    started_at = time.monotonic()
    audit_service = AuditService(store)

    async with store.acquire_session_lock(session_id):
        assistant_id = str(uuid4())
        full_text = ""
        assistant_saved = False
        message_started = False
        finish_reason = "error"
        retry_count = 0

        try:
            await store.save_message(session_id=session_id, role="user", content=request.message)
            await store.update_session_activity(session_id, message_increment=1)

            yield sse_event("message_start", {"message_id": assistant_id, "trace_id": trace_id})
            message_started = True

            async for chunk in openharness_client.stream_run(
                prompt=request.message,
                session_id=session.openharness_session_id,
                user_context={
                    "owner_type": owner.owner_type,
                    "owner_id": owner.owner_id,
                },
                trace_id=trace_id,
                locale=request.locale,
                policy_version=request.policy_version,
                client_capabilities=request.client_capabilities,
            ):
                if chunk.type == "text" and chunk.content:
                    seq = await store.next_stream_seq(session_id)
                    full_text += chunk.content
                    yield sse_event("content_delta", {"delta": chunk.content, "seq": seq, "trace_id": trace_id})
                    continue

                if chunk.type == "tool_call":
                    yield sse_event(
                        "tool_call",
                        {
                            "tool_name": chunk.tool_name,
                            "args": chunk.args or {},
                            "trace_id": trace_id,
                        },
                    )
                    continue

                if chunk.type == "tool_result":
                    tool_metadata = chunk.metadata or {}
                    yield sse_event(
                        "tool_result",
                        {
                            "tool_name": chunk.tool_name,
                            "result_summary": tool_metadata.get("result_summary") or tool_metadata.get("status", "ok"),
                            "references": tool_metadata.get("references", []),
                            "trace_id": trace_id,
                        },
                    )
                    continue

                if chunk.type == "final":
                    metadata = chunk.metadata or {}
                    finish_reason = metadata.get("finish_reason", "stop")
                    retry_count = int(metadata.get("retry_count", 0))
                    await store.save_message(
                        session_id=session_id,
                        role="assistant",
                        content=full_text,
                        message_id=assistant_id,
                        metadata={
                            "status": "succeeded",
                            "trace_id": trace_id,
                            "finish_reason": finish_reason,
                            "retry_count": retry_count,
                            "summary": metadata.get("summary", ""),
                            "references": metadata.get("references", []),
                            "rule_version": metadata.get("rule_version", ""),
                        },
                    )
                    assistant_saved = True
                    await store.update_session_activity(session_id, message_increment=1)

                    yield sse_event(
                        "final",
                        {
                            "message_id": assistant_id,
                            "summary": metadata.get("summary", ""),
                            "references": metadata.get("references", []),
                            "rule_version": metadata.get("rule_version", "v2.2"),
                            "finish_reason": finish_reason,
                            "trace_id": trace_id,
                        },
                    )
                    yield sse_event("message_end", {"message_id": assistant_id, "trace_id": trace_id})
                    latency_ms = int((time.monotonic() - started_at) * 1000)
                    logger.info(
                        "chat_turn_complete %s",
                        json.dumps(
                            {
                                "trace_id": trace_id,
                                "session_id": session_id,
                                "owner_id": owner.owner_id,
                                "workflow": settings.oh_default_workflow,
                                "latency_ms": latency_ms,
                                "finish_reason": finish_reason,
                                "retry_count": retry_count,
                            },
                            ensure_ascii=False,
                        ),
                    )
                    await audit_service.record_turn_success(
                        trace_id=trace_id,
                        session_id=session_id,
                        owner_type=owner.owner_type,
                        owner_id=owner.owner_id,
                        workflow=settings.oh_default_workflow,
                        latency_ms=latency_ms,
                        finish_reason=finish_reason,
                        retry_count=retry_count,
                    )
                    return

            raise AppError(502, "OH_SERVICE_ERROR", "OpenHarness 服务暂时不可用", retryable=True)
        except AppError as exc:
            if not assistant_saved:
                await store.save_message(
                    session_id=session_id,
                    role="assistant",
                    content="",
                    message_id=assistant_id,
                    metadata={
                        "status": "failed",
                        "trace_id": trace_id,
                        "error_code": exc.code,
                        "retryable": exc.retryable,
                    },
                )
                await store.update_session_activity(session_id, message_increment=1)

            if not message_started:
                yield sse_event("message_start", {"message_id": assistant_id, "trace_id": trace_id})
                message_started = True

            yield sse_event(
                "error",
                {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                    "trace_id": trace_id,
                },
            )
            yield sse_event("message_end", {"message_id": assistant_id, "trace_id": trace_id})
            latency_ms = int((time.monotonic() - started_at) * 1000)
            logger.error(
                "chat_turn_failed %s",
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "owner_id": owner.owner_id,
                        "workflow": settings.oh_default_workflow,
                        "latency_ms": latency_ms,
                        "finish_reason": exc.code,
                        "retry_count": retry_count,
                        "error_code": exc.code,
                    },
                    ensure_ascii=False,
                ),
            )
            await audit_service.record_turn_failure(
                trace_id=trace_id,
                session_id=session_id,
                owner_type=owner.owner_type,
                owner_id=owner.owner_id,
                workflow=settings.oh_default_workflow,
                latency_ms=latency_ms,
                finish_reason=exc.code,
                retry_count=retry_count,
                error_code=exc.code,
            )
        except Exception:
            if not assistant_saved:
                await store.save_message(
                    session_id=session_id,
                    role="assistant",
                    content="",
                    message_id=assistant_id,
                    metadata={
                        "status": "failed",
                        "trace_id": trace_id,
                        "error_code": "OH_SERVICE_ERROR",
                        "retryable": True,
                    },
                )
                await store.update_session_activity(session_id, message_increment=1)

            if not message_started:
                yield sse_event("message_start", {"message_id": assistant_id, "trace_id": trace_id})
                message_started = True

            yield sse_event(
                "error",
                {
                    "code": "OH_SERVICE_ERROR",
                    "message": "OpenHarness 服务暂时不可用",
                    "retryable": True,
                    "trace_id": trace_id,
                },
            )
            yield sse_event("message_end", {"message_id": assistant_id, "trace_id": trace_id})
            latency_ms = int((time.monotonic() - started_at) * 1000)
            logger.error(
                "chat_turn_failed %s",
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "owner_id": owner.owner_id,
                        "workflow": settings.oh_default_workflow,
                        "latency_ms": latency_ms,
                        "finish_reason": "OH_SERVICE_ERROR",
                        "retry_count": retry_count,
                        "error_code": "OH_SERVICE_ERROR",
                    },
                    ensure_ascii=False,
                ),
            )
            await audit_service.record_turn_failure(
                trace_id=trace_id,
                session_id=session_id,
                owner_type=owner.owner_type,
                owner_id=owner.owner_id,
                workflow=settings.oh_default_workflow,
                latency_ms=latency_ms,
                finish_reason="OH_SERVICE_ERROR",
                retry_count=retry_count,
                error_code="OH_SERVICE_ERROR",
            )
