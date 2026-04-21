import asyncio
from collections.abc import AsyncGenerator
import json
import logging
import time
from pathlib import Path

import httpx
from openai import APIConnectionError, APIError, APITimeoutError

from app.adapters.openharness.enrichment import (
    _build_card_metadata,
    _build_summary,
    _dedupe_references,
    _extract_references_from_output,
    _summarize_tool_result,
    _tool_allowed_by_policy,
)
from app.adapters.openharness.local_tools import ALL_LOCAL_TOOLS
from app.adapters.openharness.prompting import build_augmented_prompt, resolve_rule_version
from app.adapters.openharness.types import OHChunk
from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

# Lazy-loaded OpenHarness imports (only needed in library mode)
_oh_runtime_module = None
_oh_events_module = None
_oh_openai_client_patched = False
_oh_openai_retry_patched = False


def _load_oh_modules():
    global _oh_runtime_module, _oh_events_module
    if _oh_runtime_module is None:
        from openharness.ui import runtime as _rt
        from openharness.engine import stream_events as _ev
        _oh_runtime_module = _rt
        _oh_events_module = _ev
    return _oh_runtime_module, _oh_events_module


def _normalize_assistant_reasoning_content(openai_message: dict) -> dict:
    if settings.oh_lib_keep_empty_reasoning_content:
        return openai_message
    if openai_message.get("role") != "assistant":
        return openai_message
    if openai_message.get("reasoning_content") != "":
        return openai_message

    normalized = dict(openai_message)
    normalized.pop("reasoning_content", None)
    return normalized


def _patch_openai_assistant_message_conversion() -> None:
    global _oh_openai_client_patched
    if _oh_openai_client_patched:
        return

    from openharness.api import openai_client as oh_openai_client

    original_convert_assistant_message = oh_openai_client._convert_assistant_message

    def patched_convert_assistant_message(msg):
        openai_message = original_convert_assistant_message(msg)
        return _normalize_assistant_reasoning_content(openai_message)

    oh_openai_client._convert_assistant_message = patched_convert_assistant_message
    _oh_openai_client_patched = True

    if not settings.oh_lib_keep_empty_reasoning_content:
        logger.warning("oh_library_patch drop_empty_reasoning_content_for_assistant_tool_calls enabled")


def _is_retryable_openai_stream_error(
    exc: Exception,
    original_retryable_checker,
) -> bool:
    if original_retryable_checker(exc):
        return True

    if isinstance(exc, (APIConnectionError, APITimeoutError)):
        return True

    if isinstance(exc, httpx.TransportError):
        return True

    if isinstance(exc, APIError):
        status = getattr(exc, "status_code", None)
        if status in {408, 409, 429, 500, 502, 503, 504}:
            return True

    lowered = str(exc).lower()
    return any(
        marker in lowered
        for marker in (
            "incomplete chunked read",
            "peer closed connection",
            "connection reset",
            "remote protocol error",
            "stream closed",
        )
    )


def _patch_openai_retryable_errors() -> None:
    global _oh_openai_retry_patched
    if _oh_openai_retry_patched:
        return

    from openharness.api import openai_client as oh_openai_client

    original_retryable_checker = oh_openai_client.OpenAICompatibleClient._is_retryable

    def patched_retryable_checker(exc: Exception) -> bool:
        return _is_retryable_openai_stream_error(exc, original_retryable_checker)

    oh_openai_client.OpenAICompatibleClient._is_retryable = staticmethod(patched_retryable_checker)
    _oh_openai_retry_patched = True
    logger.warning("oh_library_patch broaden_openai_retryable_stream_errors enabled")


def _error_event_to_app_error(message: str, *, recoverable: bool) -> AppError:
    lowered = (message or "").lower()
    if "timeout" in lowered or "timed out" in lowered:
        return AppError(
            status_code=504,
            code="OH_UPSTREAM_TIMEOUT",
            message=message,
            retryable=recoverable,
            details={"event_error": message},
        )

    return AppError(
        status_code=502,
        code="OH_SERVICE_ERROR",
        message=message,
        retryable=recoverable,
        details={"event_error": message},
    )


def _apply_tool_policy(bundle: object, policy: str) -> None:
    if (policy or "").strip().lower() in {"", "full"}:
        return

    current_registry = getattr(bundle, "tool_registry", None)
    if current_registry is None:
        return

    from openharness.tools.base import ToolRegistry

    filtered_registry = ToolRegistry()
    kept_names: list[str] = []
    for tool in current_registry.list_tools():
        if _tool_allowed_by_policy(tool.name, policy):
            filtered_registry.register(tool)
            kept_names.append(tool.name)

    if not kept_names:
        logger.warning("oh_library_tool_policy=%s removed all tools; keeping original registry", policy)
        return

    bundle.tool_registry = filtered_registry
    engine = getattr(bundle, "engine", None)
    if engine is not None:
        setattr(engine, "_tool_registry", filtered_registry)

    logger.warning(
        "oh_library_tool_policy=%s applied; kept %d tools: %s",
        policy,
        len(kept_names),
        ", ".join(kept_names[:12]),
    )


def _register_mcp_tools(bundle: object) -> list[str]:
    current_registry = getattr(bundle, "tool_registry", None)
    mcp_manager = getattr(bundle, "mcp_manager", None)
    if current_registry is None or mcp_manager is None:
        return []

    from openharness.tools.mcp_tool import McpToolAdapter

    existing_names = {tool.name for tool in current_registry.list_tools()}
    added_names: list[str] = []

    for tool_info in mcp_manager.list_tools():
        adapter = McpToolAdapter(mcp_manager, tool_info)
        if not _tool_allowed_by_policy(adapter.name, settings.oh_lib_tool_policy):
            continue
        if adapter.name in existing_names:
            continue
        current_registry.register(adapter)
        existing_names.add(adapter.name)
        added_names.append(adapter.name)

    engine = getattr(bundle, "engine", None)
    if engine is not None:
        setattr(engine, "_tool_registry", current_registry)

    return added_names


async def _recover_failed_mcp_connections(bundle: object, *, session_id: str | None) -> None:
    mcp_manager = getattr(bundle, "mcp_manager", None)
    if mcp_manager is None:
        return

    statuses = list(mcp_manager.list_statuses())
    failed = [status for status in statuses if getattr(status, "state", None) == "failed"]
    if not failed:
        return

    logger.warning(
        "oh_library_mcp_reconnect_attempt session_id=%s failed_servers=%s",
        session_id or "__default__",
        ", ".join(f"{status.name}:{status.detail}" for status in failed),
    )

    try:
        await mcp_manager.reconnect_all()
    except Exception:
        logger.warning(
            "oh_library_mcp_reconnect_failed session_id=%s",
            session_id or "__default__",
            exc_info=True,
        )
        return

    added_tool_names = _register_mcp_tools(bundle)
    refreshed_statuses = list(mcp_manager.list_statuses())
    logger.warning(
        "oh_library_mcp_reconnect_complete session_id=%s statuses=%s added_tools=%s",
        session_id or "__default__",
        ", ".join(f"{status.name}:{status.state}" for status in refreshed_statuses) or "none",
        ", ".join(added_tool_names) if added_tool_names else "<none>",
    )


class OpenHarnessClient:
    def __init__(self):
        self._bundles: dict[str, object] = {}  # session_id -> RuntimeBundle
        self._bundle_lock = asyncio.Lock()
        self._extra_skill_dirs = (
            Path(__file__).resolve().parents[3] / "agent-skills",
        )

    async def _get_or_create_bundle(self, session_id: str | None):
        runtime_mod, _ = _load_oh_modules()
        key = session_id or "__default__"
        async with self._bundle_lock:
            if key not in self._bundles:
                # Build an explicit API client to bypass OH provider detection
                # (which would use CodexApiClient for the default codex profile)
                api_client = None
                if settings.oh_lib_api_key and settings.oh_lib_base_url:
                    _patch_openai_assistant_message_conversion()
                    _patch_openai_retryable_errors()
                    from openharness.api.openai_client import OpenAICompatibleClient
                    api_client = OpenAICompatibleClient(
                        api_key=settings.oh_lib_api_key,
                        base_url=settings.oh_lib_base_url,
                        timeout=settings.oh_read_timeout_sec,
                    )
                bundle = await runtime_mod.build_runtime(
                    model=settings.oh_lib_model or None,
                    api_format=settings.oh_lib_api_format or None,
                    base_url=settings.oh_lib_base_url or None,
                    api_key=settings.oh_lib_api_key or None,
                    api_client=api_client,
                    cwd=settings.oh_lib_cwd or None,
                    max_turns=settings.oh_lib_max_turns,
                    permission_mode="full_auto",
                    permission_prompt=None,
                    ask_user_prompt=None,
                    extra_skill_dirs=self._extra_skill_dirs,
                )
                # Force FULL_AUTO permission mode so MCP tools are not blocked.
                # build_runtime's merge_cli_overrides silently drops permission_mode
                # because Settings uses nested permission.mode, not a flat field.
                from openharness.permissions.modes import PermissionMode
                from openharness.config.settings import PermissionSettings
                from openharness.permissions import PermissionChecker
                bundle.engine.set_permission_checker(
                    PermissionChecker(PermissionSettings(mode=PermissionMode.FULL_AUTO))
                )
                # Register local labor tools (compensation calc, doc gen, fact extract)
                try:
                    for tool in ALL_LOCAL_TOOLS:
                        bundle.tool_registry.register(tool)
                    logger.warning(
                        "oh_local_tools_registered count=%d names=%s",
                        len(ALL_LOCAL_TOOLS),
                        ", ".join(t.name for t in ALL_LOCAL_TOOLS),
                    )
                except Exception:
                    logger.warning("oh_local_tools_registration_failed", exc_info=True)
                _apply_tool_policy(bundle, settings.oh_lib_tool_policy)
                logger.warning(
                    "oh_library_bundle_ready session_key=%s api_client=%s tools=%d mcp=%s",
                    key,
                    type(getattr(bundle, "api_client", None)).__name__,
                    len(bundle.tool_registry.list_tools()) if getattr(bundle, "tool_registry", None) else 0,
                    ", ".join(
                        f"{status.name}:{status.state}"
                        for status in bundle.mcp_manager.list_statuses()
                    ) if getattr(bundle, "mcp_manager", None) else "none",
                )
                self._bundles[key] = bundle
            return self._bundles[key]

    async def _library_stream_run(
        self,
        *,
        prompt: str,
        session_id: str | None,
        trace_id: str,
        locale: str | None,
        policy_version: str | None,
        client_capabilities: list[str],
    ) -> AsyncGenerator[OHChunk, None]:
        _, events_mod = _load_oh_modules()
        bundle = await self._get_or_create_bundle(session_id)
        await _recover_failed_mcp_connections(bundle, session_id=session_id)
        full_text_parts: list[str] = []
        gathered_references: list[dict[str, str]] = []
        prompt_to_submit = self._augment_prompt(
            prompt,
            has_pkulaw=any(status.name == "pkulaw" and status.state == "connected" for status in bundle.mcp_manager.list_statuses()),
            locale=locale,
            policy_version=policy_version,
            client_capabilities=client_capabilities,
        )
        logger.warning(
            "oh_library_submit session_id=%s api_client=%s tools=%d tool_names=%s",
            session_id or "__default__",
            type(getattr(bundle, "api_client", None)).__name__,
            len(bundle.tool_registry.list_tools()) if getattr(bundle, "tool_registry", None) else 0,
            ", ".join(tool.name for tool in bundle.tool_registry.list_tools()[:12])
            if getattr(bundle, "tool_registry", None)
            else "n/a",
        )
        try:
            async for event in bundle.engine.submit_message(prompt_to_submit):
                if isinstance(event, events_mod.AssistantTextDelta):
                    full_text_parts.append(event.text)
                    yield OHChunk(type="text", content=event.text)
                elif isinstance(event, events_mod.ToolExecutionStarted):
                    yield OHChunk(
                        type="tool_call",
                        tool_name=event.tool_name,
                        args=event.tool_input if isinstance(event.tool_input, dict) else {},
                    )
                elif isinstance(event, events_mod.ToolExecutionCompleted):
                    references = _extract_references_from_output(event.output, event.tool_name)
                    gathered_references.extend(references)
                    card_metadata = _build_card_metadata(event.tool_name, event.output)
                    yield OHChunk(
                        type="tool_result",
                        tool_name=event.tool_name,
                        metadata={
                            "status": "error" if event.is_error else "ok",
                            "trace_id": trace_id,
                            "result_summary": _summarize_tool_result(
                                event.tool_name,
                                event.output,
                                references,
                                is_error=event.is_error,
                            ),
                            "references": references,
                            "card_type": card_metadata.get("card_type") if card_metadata else None,
                            "card_title": card_metadata.get("card_title") if card_metadata else None,
                            "card_payload": card_metadata.get("card_payload") if card_metadata else None,
                            "card_actions": card_metadata.get("card_actions") if card_metadata else [],
                        },
                    )
                elif isinstance(event, events_mod.AssistantTurnComplete):
                    # Only emit the final chunk when the model has no more
                    # tool calls to execute (i.e. the conversation loop is
                    # truly finished).  Intermediate turns that trigger tool
                    # execution contain tool_uses and should be skipped here
                    # so the async generator continues to yield tool events.
                    if event.message.tool_uses:
                        continue
                    full_text = "".join(full_text_parts).strip() or event.message.text
                    yield OHChunk(
                        type="final",
                        metadata={
                            "summary": _build_summary(full_text),
                            "references": _dedupe_references(gathered_references),
                            "rule_version": resolve_rule_version(policy_version),
                            "finish_reason": "stop",
                            "trace_id": trace_id,
                            "retry_count": 0,
                        },
                    )
                elif isinstance(event, events_mod.ErrorEvent):
                    logger.error("oh_library_error trace_id=%s message=%s", trace_id, event.message)
                    raise _error_event_to_app_error(event.message, recoverable=event.recoverable)
        except AppError:
            raise
        except Exception as exc:
            logger.exception(
                "oh_library_submit_failed trace_id=%s session_id=%s error_type=%s error=%s",
                trace_id,
                session_id or "__default__",
                type(exc).__name__,
                exc,
            )
            # Graceful degradation: when the agent exhausts its turn budget
            # (MaxTurnsExceeded), return whatever text and references have
            # been accumulated so far instead of surfacing a raw error.
            if type(exc).__name__ == "MaxTurnsExceeded":
                full_text = "".join(full_text_parts).strip()
                logger.warning(
                    "oh_library_max_turns_graceful trace_id=%s max_turns=%s "
                    "collected_text_len=%d refs=%d",
                    trace_id,
                    getattr(exc, "max_turns", "?"),
                    len(full_text),
                    len(gathered_references),
                )
                yield OHChunk(
                    type="final",
                    metadata={
                        "summary": _build_summary(full_text),
                        "references": _dedupe_references(gathered_references),
                        "rule_version": resolve_rule_version(policy_version),
                        "finish_reason": "max_turns",
                        "trace_id": trace_id,
                        "retry_count": 0,
                    },
                )
                return
            raise AppError(
                status_code=502,
                code="OH_SERVICE_ERROR",
                message="OpenHarness 库调用异常",
                retryable=False,
                details={"error": str(exc)},
            ) from exc

    async def close(self):
        if not self._bundles:
            return

        try:
            runtime_mod, _ = _load_oh_modules()
        except ModuleNotFoundError:
            logger.warning("OpenHarness runtime modules unavailable during shutdown; clearing cached bundles only")
            self._bundles.clear()
            return

        async with self._bundle_lock:
            for key, bundle in list(self._bundles.items()):
                try:
                    await runtime_mod.close_runtime(bundle)
                except Exception:
                    logger.warning("Failed to close OH bundle %s", key, exc_info=True)
            self._bundles.clear()

    async def _mock_stream_run(self, prompt: str, trace_id: str) -> AsyncGenerator[OHChunk, None]:
        _ = prompt
        yield OHChunk(type="tool_call", tool_name="intent_router", args={"topic": "labor_dispute"})
        yield OHChunk(
            type="tool_result",
            tool_name="intent_router",
            metadata={"status": "ok", "trace_id": trace_id, "result_summary": "classified as labor dispute"},
        )
        parts = [
            "根据你提供的信息，先不要签署任何自愿离职文件。",
            "建议立即固定证据，包括劳动合同、工资记录和辞退沟通截图。",
            "可以先按未依法解除劳动合同方向准备仲裁材料。",
        ]
        for part in parts:
            yield OHChunk(type="text", content=part)
        yield OHChunk(
            type="final",
            metadata={
                "summary": "已给出初步维权路径和证据清单",
                "references": [],
                "rule_version": "v2.2",
                "finish_reason": "stop",
                "trace_id": trace_id,
                "retry_count": 0,
            },
        )

    def _augment_prompt(
        self,
        prompt: str,
        *,
        has_pkulaw: bool,
        locale: str | None,
        policy_version: str | None,
        client_capabilities: list[str],
    ) -> str:
        return build_augmented_prompt(
            prompt,
            has_pkulaw=has_pkulaw,
            locale=locale,
            policy_version=policy_version,
            client_capabilities=client_capabilities,
        )

    def _upstream_error(self, code: str, *, retryable: bool, details: dict | None = None) -> AppError:
        messages = {
            "OH_SERVICE_ERROR": "OpenHarness 服务暂时不可用",
            "OH_PROTOCOL_ERROR": "OpenHarness 协议解析异常",
            "OH_UPSTREAM_TIMEOUT": "OpenHarness 请求超时",
            "OH_UPSTREAM_4XX": "OpenHarness 请求被上游拒绝",
            "OH_UPSTREAM_5XX": "OpenHarness 上游服务异常",
        }
        return AppError(
            status_code=502 if code != "OH_UPSTREAM_TIMEOUT" else 504,
            code=code,
            message=messages[code],
            retryable=retryable,
            details=details or {},
        )

    def _http_status_error(self, status_code: int) -> AppError:
        if 400 <= status_code < 500:
            return self._upstream_error("OH_UPSTREAM_4XX", retryable=False, details={"upstream_status": status_code})
        return self._upstream_error("OH_UPSTREAM_5XX", retryable=True, details={"upstream_status": status_code})

    def _event_to_chunk(self, event_name: str, data: dict, *, trace_id: str, retry_count: int) -> OHChunk | None:
        if event_name == "content_delta":
            return OHChunk(type="text", content=str(data.get("delta", "")))
        if event_name == "tool_call":
            return OHChunk(type="tool_call", tool_name=data.get("tool_name"), args=data.get("args", {}))
        if event_name == "tool_result":
            raw_output = data.get("tool_output") or data.get("output") or data.get("result")
            references = _extract_references_from_output(str(raw_output or ""), str(data.get("tool_name") or ""))
            return OHChunk(
                type="tool_result",
                tool_name=data.get("tool_name"),
                metadata={
                    "status": "error" if data.get("is_error") else "ok",
                    "result_summary": data.get("result_summary")
                    or _summarize_tool_result(
                        str(data.get("tool_name") or ""),
                        str(raw_output or ""),
                        references,
                        is_error=bool(data.get("is_error")),
                    ),
                    "references": references,
                    "trace_id": trace_id,
                },
            )
        if event_name == "final":
            metadata = dict(data)
            metadata["trace_id"] = metadata.get("trace_id", trace_id)
            metadata["finish_reason"] = metadata.get("finish_reason", "stop")
            metadata["retry_count"] = metadata.get("retry_count", retry_count)
            metadata["summary"] = metadata.get("summary") or "已完成本轮劳动争议分析。"
            metadata["references"] = _dedupe_references(metadata.get("references", []))
            metadata["rule_version"] = metadata.get("rule_version") or "labor_consultation.v1"
            return OHChunk(type="final", metadata=metadata)
        return None

    async def _stream_remote_once(
        self,
        *,
        prompt: str,
        session_id: str | None,
        user_context: dict,
        trace_id: str,
        locale: str | None,
        policy_version: str | None,
        client_capabilities: list[str],
        retry_count: int,
    ) -> AsyncGenerator[OHChunk, None]:
        url = f"{settings.oh_base_url.rstrip('/')}{settings.oh_stream_path}"
        payload = {
            "prompt": prompt,
            "session_id": session_id,
            "workflow": settings.oh_default_workflow,
            "user_context": user_context,
            "output_format": "stream",
            "trace_id": trace_id,
            "locale": locale,
            "policy_version": policy_version,
            "client_capabilities": client_capabilities,
        }
        headers = {
            "Authorization": f"Bearer {settings.oh_api_key}",
            "Content-Type": "application/json",
        }
        timeout = httpx.Timeout(
            connect=settings.oh_connect_timeout_sec,
            read=settings.oh_read_timeout_sec,
            write=settings.oh_read_timeout_sec,
            pool=settings.oh_connect_timeout_sec,
        )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code >= 400:
                        raise self._http_status_error(response.status_code)

                    event_name = ""
                    protocol_errors = 0
                    business_chunk_seen = False
                    started_at = time.monotonic()
                    line_iter = response.aiter_lines()

                    while True:
                        try:
                            if not business_chunk_seen:
                                remaining = settings.oh_first_chunk_timeout_sec - (time.monotonic() - started_at)
                                if remaining <= 0:
                                    raise self._upstream_error("OH_UPSTREAM_TIMEOUT", retryable=True)
                                raw_line = await asyncio.wait_for(line_iter.__anext__(), timeout=remaining)
                            else:
                                raw_line = await line_iter.__anext__()
                        except StopAsyncIteration:
                            return
                        except asyncio.TimeoutError as exc:
                            raise self._upstream_error("OH_UPSTREAM_TIMEOUT", retryable=True) from exc

                        line = raw_line.strip()
                        if not line:
                            continue
                        if line.startswith("event:"):
                            event_name = line.removeprefix("event:").strip()
                            continue
                        if not line.startswith("data:"):
                            continue

                        data_text = line.removeprefix("data:").strip()
                        try:
                            data = json.loads(data_text)
                        except json.JSONDecodeError:
                            protocol_errors += 1
                            logger.warning(
                                "oh_protocol_skip_invalid_json %s",
                                json.dumps(
                                    {
                                        "trace_id": trace_id,
                                        "session_id": session_id,
                                        "protocol_errors": protocol_errors,
                                    },
                                    ensure_ascii=False,
                                ),
                            )
                            if protocol_errors >= settings.oh_protocol_error_threshold:
                                raise self._upstream_error("OH_PROTOCOL_ERROR", retryable=False)
                            continue

                        chunk = self._event_to_chunk(
                            event_name,
                            data if isinstance(data, dict) else {},
                            trace_id=trace_id,
                            retry_count=retry_count,
                        )
                        if chunk is None:
                            protocol_errors += 1
                            logger.warning(
                                "oh_protocol_skip_unknown_event %s",
                                json.dumps(
                                    {
                                        "trace_id": trace_id,
                                        "session_id": session_id,
                                        "event_name": event_name,
                                        "protocol_errors": protocol_errors,
                                    },
                                    ensure_ascii=False,
                                ),
                            )
                            if protocol_errors >= settings.oh_protocol_error_threshold:
                                raise self._upstream_error("OH_PROTOCOL_ERROR", retryable=False)
                            continue

                        business_chunk_seen = True
                        yield chunk
        except AppError:
            raise
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout) as exc:
            raise self._upstream_error("OH_UPSTREAM_TIMEOUT", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise self._upstream_error("OH_SERVICE_ERROR", retryable=True, details={"http_error": str(exc)}) from exc
        except Exception as exc:
            raise self._upstream_error("OH_SERVICE_ERROR", retryable=True) from exc

    def _retry_delay(self, attempt: int) -> float:
        schedule = settings.oh_retry_backoff_schedule
        index = min(attempt - 1, len(schedule) - 1)
        return schedule[index]

    async def _remote_stream_run(
        self,
        *,
        prompt: str,
        session_id: str | None,
        user_context: dict,
        trace_id: str,
        locale: str | None,
        policy_version: str | None,
        client_capabilities: list[str],
    ) -> AsyncGenerator[OHChunk, None]:
        started_at = time.monotonic()
        owner_id = str(user_context.get("owner_id", ""))
        max_attempts = settings.oh_retry_max_attempts
        attempts = 0
        finish_reason = "unknown"

        while attempts < max_attempts:
            attempts += 1
            saw_business_chunk = False
            saw_final = False
            try:
                async for chunk in self._stream_remote_once(
                    prompt=prompt,
                    session_id=session_id,
                    user_context=user_context,
                    trace_id=trace_id,
                    locale=locale,
                    policy_version=policy_version,
                    client_capabilities=client_capabilities,
                    retry_count=attempts - 1,
                ):
                    saw_business_chunk = True
                    if chunk.type == "final":
                        saw_final = True
                        finish_reason = (chunk.metadata or {}).get("finish_reason", "stop")
                    yield chunk

                if not saw_business_chunk:
                    raise self._upstream_error("OH_SERVICE_ERROR", retryable=True)
                if not saw_final:
                    raise self._upstream_error("OH_SERVICE_ERROR", retryable=False)

                latency_ms = int((time.monotonic() - started_at) * 1000)
                logger.info(
                    "oh_stream_complete %s",
                    json.dumps(
                        {
                            "trace_id": trace_id,
                            "session_id": session_id,
                            "owner_id": owner_id,
                            "workflow": settings.oh_default_workflow,
                            "latency_ms": latency_ms,
                            "finish_reason": finish_reason,
                            "retry_count": attempts - 1,
                        },
                        ensure_ascii=False,
                    ),
                )
                return
            except AppError as exc:
                can_retry = exc.retryable and not saw_business_chunk and attempts < max_attempts
                if can_retry:
                    delay = self._retry_delay(attempts)
                    logger.warning(
                        "oh_stream_retry %s",
                        json.dumps(
                            {
                                "trace_id": trace_id,
                                "session_id": session_id,
                                "owner_id": owner_id,
                                "workflow": settings.oh_default_workflow,
                                "retry_count": attempts,
                                "next_delay_sec": delay,
                                "error_code": exc.code,
                            },
                            ensure_ascii=False,
                        ),
                    )
                    await asyncio.sleep(delay)
                    continue

                latency_ms = int((time.monotonic() - started_at) * 1000)
                logger.error(
                    "oh_stream_failed %s",
                    json.dumps(
                        {
                            "trace_id": trace_id,
                            "session_id": session_id,
                            "owner_id": owner_id,
                            "workflow": settings.oh_default_workflow,
                            "latency_ms": latency_ms,
                            "finish_reason": exc.code,
                            "retry_count": attempts - 1,
                            "error_code": exc.code,
                        },
                        ensure_ascii=False,
                    ),
                )
                raise

    async def stream_run(
        self,
        *,
        prompt: str,
        session_id: str | None,
        user_context: dict,
        trace_id: str,
        locale: str | None = None,
        policy_version: str | None = None,
        client_capabilities: list[str] | None = None,
    ) -> AsyncGenerator[OHChunk, None]:
        mode = settings.oh_mode
        if settings.oh_use_mock or mode == "mock":
            async for chunk in self._mock_stream_run(prompt, trace_id):
                yield chunk
            return

        if mode == "library":
            async for chunk in self._library_stream_run(
                prompt=prompt,
                session_id=session_id,
                trace_id=trace_id,
                locale=locale,
                policy_version=policy_version,
                client_capabilities=client_capabilities or [],
            ):
                yield chunk
            return

        async for chunk in self._remote_stream_run(
            prompt=self._augment_prompt(
                prompt,
                has_pkulaw=True,
                locale=locale,
                policy_version=policy_version,
                client_capabilities=client_capabilities or [],
            ),
            session_id=session_id,
            user_context=user_context,
            trace_id=trace_id,
            locale=locale,
            policy_version=policy_version,
            client_capabilities=client_capabilities or [],
        ):
            yield chunk


openharness_client = OpenHarnessClient()
