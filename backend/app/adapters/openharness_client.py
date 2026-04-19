import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
import ast
import json
import logging
import re
import time
from typing import Any
from pathlib import Path

import httpx

from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

# Lazy-loaded OpenHarness imports (only needed in library mode)
_oh_runtime_module = None
_oh_events_module = None


def _load_oh_modules():
    global _oh_runtime_module, _oh_events_module
    if _oh_runtime_module is None:
        from openharness.ui import runtime as _rt
        from openharness.engine import stream_events as _ev
        _oh_runtime_module = _rt
        _oh_events_module = _ev
    return _oh_runtime_module, _oh_events_module


@dataclass
class OHChunk:
    type: str
    content: str | None = None
    tool_name: str | None = None
    args: dict | None = None
    metadata: dict | None = None


_URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")


def _is_pkulaw_tool(tool_name: str | None) -> bool:
    if not tool_name:
        return False
    lowered = tool_name.lower()
    return "pkulaw" in lowered or lowered.startswith("mcp__pkulaw__")


def _try_parse_structured_output(raw_output: str) -> Any | None:
    text = (raw_output or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None


def _truncate(value: str, *, limit: int = 240) -> str:
    collapsed = " ".join((value or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[: limit - 3]}..."


def _walk_reference_candidates(node: Any, bucket: list[dict[str, str]]) -> None:
    if isinstance(node, dict):
        title = (
            node.get("title")
            or node.get("name")
            or node.get("docTitle")
            or node.get("doc_title")
            or node.get("law_name")
            or node.get("case_name")
            or node.get("citation")
        )
        url = (
            node.get("source_url")
            or node.get("url")
            or node.get("link")
            or node.get("href")
            or node.get("docUrl")
            or node.get("doc_url")
        )
        snippet = (
            node.get("excerpt")
            or node.get("snippet")
            or node.get("summary")
            or node.get("content")
            or node.get("description")
            or node.get("text")
        )
        if isinstance(title, str) or isinstance(url, str) or isinstance(snippet, str):
            bucket.append(
                {
                    "title": _truncate(str(title or "")),
                    "url": str(url or ""),
                    "snippet": _truncate(str(snippet or ""), limit=320),
                }
            )
        for value in node.values():
            _walk_reference_candidates(value, bucket)
        return

    if isinstance(node, list):
        for item in node:
            _walk_reference_candidates(item, bucket)


def _normalize_reference(ref: dict[str, str]) -> dict[str, str] | None:
    title = ref.get("title", "").strip()
    url = ref.get("url", "").strip()
    snippet = ref.get("snippet", "").strip()
    if not title and not url and not snippet:
        return None
    return {
        "title": title,
        "url": url,
        "snippet": snippet,
    }


def _extract_references_from_output(raw_output: str, tool_name: str | None) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    structured = _try_parse_structured_output(raw_output)
    if structured is not None:
        _walk_reference_candidates(structured, refs)

    normalized = []
    seen: set[tuple[str, str, str]] = set()
    for item in refs:
        normalized_item = _normalize_reference(item)
        if not normalized_item:
            continue
        key = (
            normalized_item["title"].lower(),
            normalized_item["url"].lower(),
            normalized_item["snippet"].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(normalized_item)

    if normalized:
        return normalized[:8]

    if _is_pkulaw_tool(tool_name):
        urls = _URL_PATTERN.findall(raw_output or "")
        lines = [line.strip() for line in (raw_output or "").splitlines() if line.strip()]
        title = lines[0] if lines else tool_name or "pkulaw_reference"
        snippet = lines[1] if len(lines) > 1 else _truncate(raw_output or "", limit=200)
        fallback = _normalize_reference(
            {
                "title": _truncate(title),
                "url": urls[0] if urls else "",
                "snippet": snippet,
            }
        )
        return [fallback] if fallback else []

    return []


def _dedupe_references(references: list[dict[str, str]]) -> list[dict[str, str]]:
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for reference in references:
        normalized = _normalize_reference(reference)
        if not normalized:
            continue
        key = (
            normalized["title"].lower(),
            normalized["url"].lower(),
            normalized["snippet"].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped[:8]


def _summarize_tool_result(
    tool_name: str | None,
    raw_output: str,
    references: list[dict[str, str]],
    *,
    is_error: bool,
) -> str:
    if is_error:
        return "tool execution failed"
    if references:
        return f"retrieved {len(references)} legal reference(s)"
    if _is_pkulaw_tool(tool_name):
        return "pkulaw retrieval completed"
    return _truncate(raw_output or "ok", limit=120) or "ok"


def _build_summary(text: str) -> str:
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return "已完成本轮劳动争议分析。"
    first_sentence = re.split(r"(?<=[。！？.!?])\s+", collapsed, maxsplit=1)[0].strip()
    if first_sentence:
        return _truncate(first_sentence, limit=120)
    return _truncate(collapsed, limit=120)


def _resolve_rule_version(policy_version: str | None) -> str:
    if policy_version and policy_version.strip():
        return policy_version.strip()
    return "labor_consultation.v1"


_LOCAL_LABOR_TOOLS = frozenset({
    "labor_compensation_calc",
    "labor_document_gen",
})


def _tool_allowed_by_policy(tool_name: str, policy: str) -> bool:
    normalized = (policy or "").strip().lower()
    if normalized in {"", "full"}:
        return True
    if normalized == "legal_minimal":
        return (
            tool_name == "skill"
            or tool_name == "list_mcp_resources"
            or tool_name == "read_mcp_resource"
            or tool_name.startswith("mcp__pkulaw__")
            or tool_name in _LOCAL_LABOR_TOOLS
        )
    return True


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


class OpenHarnessClient:
    def __init__(self):
        self._bundles: dict[str, object] = {}  # session_id -> RuntimeBundle
        self._bundle_lock = asyncio.Lock()
        self._extra_skill_dirs = (
            Path(__file__).resolve().parents[2] / "agent-skills",
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
                    from openharness.api.openai_client import OpenAICompatibleClient
                    api_client = OpenAICompatibleClient(
                        api_key=settings.oh_lib_api_key,
                        base_url=settings.oh_lib_base_url,
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
                    from app.tools import ALL_LOCAL_TOOLS
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
                            "rule_version": _resolve_rule_version(policy_version),
                            "finish_reason": "stop",
                            "trace_id": trace_id,
                            "retry_count": 0,
                        },
                    )
                elif isinstance(event, events_mod.ErrorEvent):
                    logger.error("oh_library_error trace_id=%s message=%s", trace_id, event.message)
                    if not event.recoverable:
                        raise AppError(
                            status_code=502,
                            code="OH_SERVICE_ERROR",
                            message=f"OpenHarness 引擎错误: {event.message}",
                            retryable=False,
                        )
        except AppError:
            raise
        except Exception as exc:
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
        instructions = [
            "你是「智裁」劳动争议智能分诊助手，专注服务西安/陕西地区劳动者。",
            "若可用工具中存在 skill，请先调用 skill(name=\"labor_pkulaw_retrieval_flow\")，严格遵循其中规定的分阶段工作流。",

            # --- 工具使用规则 ---
            "【工具使用规则】",
            "如可用工具中存在 mcp__pkulaw__get_article 和 mcp__pkulaw__search_article，必须先使用它们检索法条原文，再输出法律依据。",
            "使用 mcp__pkulaw__get_article 时，title 用法律全称（如'中华人民共和国劳动合同法'），number 用'第XX条'格式。",
            "使用 mcp__pkulaw__search_article 时，text 参数必须包含'陕西'或'陕高法'等地域关键词以获取本地规则。",
            "赔偿/补偿金额必须通过 labor_compensation_calc 工具计算，禁止心算或估算。",
            "信息收集充分后调用 labor_fact_extract 进行事实结构化，用其结果驱动后续计算和文书生成。",
            "需要生成文书时调用 labor_document_gen（仲裁申请书/证据清单/行动清单/案情摘要）。",

            # --- 陕西本地规则 ---
            "【陕西本地规则（关键）】",
            "陕西省经济补偿月工资基数按劳动者实际到手工资计算，非税前工资（依据：陕高法〔2020〕118号第18条）。",
            "到手工资 = 扣除社保个人部分 + 个人所得税后的银行实发金额。",
            "必须主动询问用户的到手工资金额，这是陕西地区计算赔偿的核心数据。",
            "计算时同时展示陕西标准（到手工资）和全国标准（税前工资）的对比差异。",

            # --- 输出要求 ---
            "【输出要求】",
            "金额、赔偿测算、时效边界不得伪造；若信息不足，必须说明假设或缺失字段。",
            "引用法条必须来自 PKULaw 工具检索结果，不得编造法条编号或案例号。",
            "回答采用结构化格式：案情摘要→法律分析→赔偿计算表→维权建议→风险提示→法律依据引用。",
            "重要法律概念采用双层输出：先用通俗语言解释，再给出专业法律表述。",
            "最终回答覆盖：简要结论、事实要点、维权步骤、法律依据、是否建议律师介入。",
        ]
        if locale:
            instructions.append(f"回复语言优先使用：{locale}。")
        if policy_version:
            instructions.append(f"规则版本偏好：{policy_version}。")
        if client_capabilities:
            instructions.append(f"前端能力声明：{', '.join(client_capabilities)}。")
        if not has_pkulaw:
            instructions.append('⚠️ 当前未检测到 PKULaw MCP 工具；如无法核验法律依据，请明确标注"法律依据待在线核验，以下结论仅供参考"。')

        joined = "\n".join(f"- {line}" for line in instructions)
        return f"[Middleware Instructions]\n{joined}\n\n[User Request]\n{prompt.strip()}"

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
