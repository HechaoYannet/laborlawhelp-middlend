import ast
import json
import re
from typing import Any

_URL_PATTERN = re.compile(r"https?://[^\s)>\"]+")

_LOCAL_LABOR_TOOLS = frozenset({
    "labor_compensation_calc",
    "labor_document_gen",
    "labor_fact_extract",
    "labor_lawyer_recommend",
})


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


def _safe_json_dict(raw_output: str) -> dict[str, Any] | None:
    parsed = _try_parse_structured_output(raw_output)
    if isinstance(parsed, dict):
        return parsed
    return None


def _build_card_metadata(tool_name: str | None, raw_output: str) -> dict[str, Any] | None:
    payload = _safe_json_dict(raw_output)
    if not payload:
        return None

    if tool_name == "labor_fact_extract":
        return {
            "card_type": "fact_summary",
            "card_title": "要素抽取与案情摘要",
            "card_payload": {
                "extracted_facts": payload.get("extracted_facts", {}),
                "dispute_types": payload.get("dispute_types", []),
                "info_completeness": payload.get("info_completeness"),
                "missing_info": payload.get("missing_info", []),
                "suggested_questions": payload.get("suggested_questions", []),
                "ready_for_calculation": payload.get("ready_for_calculation"),
            },
            "card_actions": [
                {"action": "continue_consultation", "label": "继续补充案情"},
            ],
        }

    if tool_name == "labor_compensation_calc":
        return {
            "card_type": "compensation",
            "card_title": "测算赔偿项目",
            "card_payload": {
                "input_summary": payload.get("input_summary", {}),
                "calculations": payload.get("calculations", []),
                "total_amount": payload.get("total_amount"),
                "comparison": payload.get("comparison"),
                "legal_basis": payload.get("legal_basis", []),
            },
            "card_actions": [
                {"action": "generate_document", "label": "生成文书"},
                {"action": "copy_summary", "label": "复制测算摘要"},
            ],
        }

    if tool_name == "labor_document_gen":
        document_type = str(payload.get("document_type", ""))
        card_type = "document"
        if "证据" in document_type:
            card_type = "evidence"
        elif "行动清单" in document_type:
            card_type = "action_checklist"
        elif "仲裁申请" in document_type:
            card_type = "arbitration_application"
        elif "摘要" in document_type:
            card_type = "case_summary"

        return {
            "card_type": card_type,
            "card_title": "文书生成",
            "card_payload": payload,
            "card_actions": [
                {"action": "copy_document", "label": "复制文书"},
                {"action": "download_document", "label": "下载文书"},
            ],
        }

    if tool_name == "labor_lawyer_recommend":
        return {
            "card_type": "lawyer_referral",
            "card_title": "繁简分流与律师转介",
            "card_payload": payload,
            "card_actions": [
                {"action": "copy_referral", "label": "复制转介摘要"},
                {"action": "book_lawyer", "label": "预约咨询"},
            ],
        }

    return None


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
