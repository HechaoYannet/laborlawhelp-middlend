import asyncio

from app.core.store import InMemoryStore
from app.services.audit_service import AuditService


def test_audit_service_records_success_and_failure() -> None:
    test_store = InMemoryStore()
    service = AuditService(test_store)

    async def run() -> None:
        await service.record_turn_success(
            trace_id="trace-success",
            session_id="session-1",
            owner_type="anonymous",
            owner_id="anon-user",
            workflow="labor_consultation",
            latency_ms=123,
            finish_reason="stop",
            retry_count=0,
        )
        await service.record_turn_failure(
            trace_id="trace-failed",
            session_id="session-1",
            owner_type="anonymous",
            owner_id="anon-user",
            workflow="labor_consultation",
            latency_ms=456,
            finish_reason="OH_UPSTREAM_TIMEOUT",
            retry_count=1,
            error_code="OH_UPSTREAM_TIMEOUT",
        )

    asyncio.run(run())

    assert len(test_store.audit_logs) == 2
    success_log = test_store.audit_logs[0]
    failed_log = test_store.audit_logs[1]

    assert success_log.event_type == "turn_completed"
    assert success_log.request_payload["workflow"] == "labor_consultation"
    assert success_log.request_payload["error_code"] == ""

    assert failed_log.event_type == "turn_failed"
    assert failed_log.trace_id == "trace-failed"
    assert failed_log.request_payload["retry_count"] == 1
    assert failed_log.request_payload["error_code"] == "OH_UPSTREAM_TIMEOUT"
