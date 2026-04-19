"""Labor dispute fact extraction / structuring tool.

Parses a free-form case description and extracts structured fields that
downstream tools (compensation calculator, document generator) can consume.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

try:
    from openharness.tools.base import BaseTool, ToolResult, ToolExecutionContext
except ImportError:  # pragma: no cover
    BaseTool = object  # type: ignore[assignment,misc]
    ToolResult = None  # type: ignore[assignment,misc]
    ToolExecutionContext = None  # type: ignore[assignment,misc]


class FactExtractInput(BaseModel):
    """案情事实提取输入"""
    case_description: str = Field(
        description="用户描述的案情事实原文，可以是多轮对话拼接的完整描述"
    )
    # 以下为 LLM 从对话中提取后填入的结构化字段
    applicant_name: str | None = Field(default=None, description="当事人姓名")
    applicant_gender: str | None = Field(default=None, description="当事人性别")
    respondent_name: str | None = Field(default=None, description="用人单位名称")
    employment_start: str | None = Field(default=None, description="入职日期 YYYY-MM-DD")
    employment_end: str | None = Field(default=None, description="离职/终止日期 YYYY-MM-DD")
    position: str | None = Field(default=None, description="工作岗位")
    monthly_wage_pretax: float | None = Field(default=None, description="月工资（税前/合同金额）")
    monthly_wage_take_home: float | None = Field(default=None, description="月到手工资")
    termination_reason: str | None = Field(default=None, description="解除/终止原因描述")
    has_written_contract: bool | None = Field(default=None, description="是否签订了书面劳动合同")
    has_social_insurance: bool | None = Field(default=None, description="单位是否缴纳了社保")
    region: str | None = Field(default=None, description="工作地/仲裁地")
    overtime_claimed: bool | None = Field(default=None, description="是否涉及加班费争议")
    other_claims: list[str] | None = Field(default=None, description="其他诉求描述")


def _analyze_dispute_type(params: FactExtractInput) -> list[str]:
    """分析争议类型"""
    types = []
    desc = (params.case_description or "").lower()
    reason = (params.termination_reason or "").lower()

    # 违法解除
    keywords_illegal = ["违法解除", "非法辞退", "强制辞退", "被迫离职", "违法终止",
                        "无故辞退", "口头辞退", "调岗降薪", "逼迫离职"]
    if any(k in desc or k in reason for k in keywords_illegal):
        types.append("违法解除劳动合同")

    # 未签合同
    if params.has_written_contract is False or "未签" in desc or "没签合同" in desc:
        types.append("未签订书面劳动合同")

    # 拖欠工资
    keywords_wage = ["拖欠工资", "欠薪", "工资未发", "克扣工资"]
    if any(k in desc for k in keywords_wage):
        types.append("拖欠工资")

    # 加班费
    if params.overtime_claimed or "加班" in desc:
        types.append("加班费争议")

    # 社保
    if params.has_social_insurance is False or "未缴社保" in desc or "没交社保" in desc:
        types.append("未依法缴纳社会保险")

    # 工伤
    if "工伤" in desc:
        types.append("工伤待遇争议")

    if not types:
        types.append("劳动争议（待进一步确认类型）")

    return types


def _identify_missing_info(params: FactExtractInput) -> list[dict[str, str]]:
    """识别缺失的关键信息"""
    missing = []

    if not params.applicant_name:
        missing.append({"field": "applicant_name", "label": "当事人姓名", "priority": "必要"})
    if not params.respondent_name:
        missing.append({"field": "respondent_name", "label": "用人单位名称", "priority": "必要"})
    if not params.employment_start:
        missing.append({"field": "employment_start", "label": "入职日期", "priority": "必要"})
    if not params.employment_end:
        missing.append({"field": "employment_end", "label": "离职日期", "priority": "必要"})
    if params.monthly_wage_pretax is None:
        missing.append({"field": "monthly_wage_pretax", "label": "月工资（合同/税前）", "priority": "必要"})
    if params.monthly_wage_take_home is None:
        missing.append({"field": "monthly_wage_take_home", "label": "月到手工资",
                        "priority": "重要（陕西地区按到手工资计算补偿金）"})
    if not params.termination_reason:
        missing.append({"field": "termination_reason", "label": "解除/终止原因", "priority": "必要"})
    if params.has_written_contract is None:
        missing.append({"field": "has_written_contract", "label": "是否签了劳动合同", "priority": "重要"})
    if not params.region:
        missing.append({"field": "region", "label": "工作地/仲裁地", "priority": "重要（影响适用标准）"})

    return missing


def _suggest_next_questions(missing: list[dict[str, str]], params: FactExtractInput) -> list[str]:
    """根据缺失信息生成追问建议"""
    questions = []
    for item in missing[:3]:  # 最多3个追问
        field = item["field"]
        if field == "monthly_wage_take_home":
            questions.append("您每月实际到手（扣除社保和个税后银行到账）的工资是多少？"
                             "这在陕西地区是计算经济补偿的重要依据。")
        elif field == "employment_start":
            questions.append("您是什么时候入职的？具体到年月即可。")
        elif field == "employment_end":
            questions.append("您是什么时候离职的？或者目前还在职？")
        elif field == "termination_reason":
            questions.append("公司是以什么理由/方式与您解除劳动关系的？是否有书面通知？")
        elif field == "has_written_contract":
            questions.append("您入职时有没有签书面劳动合同？")
        elif field == "respondent_name":
            questions.append("您的用人单位全称是什么？")
        elif field == "region":
            questions.append("您的工作地点在哪个城市？")
        else:
            questions.append(f"请提供{item['label']}的信息。")
    return questions


def extract_facts(params: FactExtractInput) -> dict[str, Any]:
    """从案情描述中提取结构化事实"""
    dispute_types = _analyze_dispute_type(params)
    missing = _identify_missing_info(params)
    questions = _suggest_next_questions(missing, params)

    # 判断信息是否充分
    required_fields = ["applicant_name", "respondent_name", "employment_start",
                       "employment_end", "monthly_wage_pretax", "termination_reason"]
    filled = sum(1 for f in required_fields if getattr(params, f) is not None)
    completeness = filled / len(required_fields)

    result = {
        "extracted_facts": {
            "applicant": {
                "name": params.applicant_name,
                "gender": params.applicant_gender,
            },
            "respondent": {
                "name": params.respondent_name,
            },
            "employment": {
                "start": params.employment_start,
                "end": params.employment_end,
                "position": params.position,
                "monthly_wage_pretax": params.monthly_wage_pretax,
                "monthly_wage_take_home": params.monthly_wage_take_home,
                "has_written_contract": params.has_written_contract,
                "has_social_insurance": params.has_social_insurance,
            },
            "termination": {
                "reason": params.termination_reason,
            },
            "region": params.region or "待确认",
        },
        "dispute_types": dispute_types,
        "info_completeness": round(completeness, 2),
        "missing_info": missing,
        "suggested_questions": questions,
        "ready_for_calculation": completeness >= 0.8,
        "ready_for_document": completeness >= 0.6,
        "notes": [],
    }

    # 添加地域提示
    region = (params.region or "").lower()
    if region in ("陕西", "shaanxi", "西安", "xian", "shanxi"):
        result["notes"].append(
            "陕西地区适用到手工资标准计算经济补偿金（陕高法〔2020〕118号第18条），"
            "建议确认到手工资金额。"
        )
    elif not params.region:
        result["notes"].append(
            "未确认工作地区。若在陕西/西安，适用到手工资标准（非税前），可能影响补偿金计算。"
        )

    # 时效提示
    if params.employment_end:
        try:
            end_date = date.fromisoformat(params.employment_end)
            days_since = (date.today() - end_date).days
            if days_since > 300:
                result["notes"].append(
                    f"⚠️ 距离离职已{days_since}天，劳动仲裁时效为1年，请尽快行动。"
                )
        except ValueError:
            pass

    return result


# ---------------------------------------------------------------------------
# OpenHarness tool wrapper
# ---------------------------------------------------------------------------

class LaborFactExtractTool(BaseTool):  # type: ignore[misc]
    """劳动争议案情事实提取与结构化工具"""

    name = "labor_fact_extract"
    description = (
        "从用户描述的劳动争议案情中提取结构化事实字段。"
        "分析争议类型，识别缺失关键信息，生成追问建议。"
        "判断信息是否充分以进行赔偿计算和文书生成。"
        "应在多轮对话收集信息后调用，将散落的事实整理为统一结构。"
    )
    input_model = FactExtractInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: Any) -> Any:
        params = arguments if isinstance(arguments, FactExtractInput) else FactExtractInput(**arguments.model_dump())
        result = extract_facts(params)
        return ToolResult(output=json.dumps(result, ensure_ascii=False, indent=2))
