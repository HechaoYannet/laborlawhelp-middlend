import json
import logging

from app.core.store import BaseStore

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, data_store: BaseStore) -> None:
        self._store = data_store

    async def record_turn_success(
        self,
        *,
        trace_id: str,
        session_id: str,
        owner_type: str,
        owner_id: str,
        workflow: str,
        latency_ms: int,
        finish_reason: str,
        retry_count: int,
    ) -> None:
        payload = {
            "trace_id": trace_id,
            "session_id": session_id,
            "owner_id": owner_id,
            "workflow": workflow,
            "latency_ms": latency_ms,
            "finish_reason": finish_reason,
            "retry_count": retry_count,
            "error_code": "",
        }
        response_summary = json.dumps(
            {
                "status": "succeeded",
                "finish_reason": finish_reason,
            },
            ensure_ascii=False,
        )
        await self._save(
            trace_id=trace_id,
            owner_type=owner_type,
            owner_id=owner_id,
            session_id=session_id,
            event_type="turn_completed",
            request_payload=payload,
            response_summary=response_summary,
        )

    async def record_turn_failure(
        self,
        *,
        trace_id: str,
        session_id: str,
        owner_type: str,
        owner_id: str,
        workflow: str,
        latency_ms: int,
        finish_reason: str,
        retry_count: int,
        error_code: str,
    ) -> None:
        payload = {
            "trace_id": trace_id,
            "session_id": session_id,
            "owner_id": owner_id,
            "workflow": workflow,
            "latency_ms": latency_ms,
            "finish_reason": finish_reason,
            "retry_count": retry_count,
            "error_code": error_code,
        }
        response_summary = json.dumps(
            {
                "status": "failed",
                "error_code": error_code,
            },
            ensure_ascii=False,
        )
        await self._save(
            trace_id=trace_id,
            owner_type=owner_type,
            owner_id=owner_id,
            session_id=session_id,
            event_type="turn_failed",
            request_payload=payload,
            response_summary=response_summary,
        )

    async def _save(
        self,
        *,
        trace_id: str,
        owner_type: str,
        owner_id: str,
        session_id: str,
        event_type: str,
        request_payload: dict,
        response_summary: str,
    ) -> None:
        try:
            await self._store.save_audit_log(
                trace_id=trace_id,
                owner_type=owner_type,
                owner_id=owner_id,
                session_id=session_id,
                event_type=event_type,
                request_payload=request_payload,
                response_summary=response_summary,
            )
        except Exception:
            logger.exception(
                "audit_log_write_failed %s",
                json.dumps(
                    {
                        "trace_id": trace_id,
                        "session_id": session_id,
                        "event_type": event_type,
                    },
                    ensure_ascii=False,
                ),
            )
