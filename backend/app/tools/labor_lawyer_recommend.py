"""Lawyer referral recommendation tool for labor disputes.

Produces a structured referral card payload containing complexity,
risk tags, and recommended lawyers for follow-up actions.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

try:
    from openharness.tools.base import BaseTool, ToolResult, ToolExecutionContext
except ImportError:  # pragma: no cover
    BaseTool = object  # type: ignore[assignment,misc]
    ToolResult = None  # type: ignore[assignment,misc]
    ToolExecutionContext = None  # type: ignore[assignment,misc]


class LawyerRecommendInput(BaseModel):
    """律师推荐输入参数。"""

    dispute_types: list[str] = Field(default_factory=list, description="争议类型列表")
    compensation_amount: float | None = Field(default=None, description="预估争议金额")
    info_completeness: float | None = Field(default=None, description="案情信息完整度（0-1）")
    has_written_contract: bool | None = Field(default=None, description="是否签订书面合同")
    has_social_insurance: bool | None = Field(default=None, description="是否缴纳社保")
    has_core_evidence: bool = Field(default=False, description="是否具备核心证据")
    near_deadline: bool = Field(default=False, description="是否接近仲裁时效")
    region: str = Field(default="西安", description="工作地/仲裁地")


def _calculate_complexity(params: LawyerRecommendInput) -> tuple[str, str, list[str]]:
    score = 0
    tags: list[str] = []

    dispute_count = len(params.dispute_types)
    if dispute_count >= 3:
        score += 2
        tags.append("多争议点")
    elif dispute_count >= 2:
        score += 1

    if (params.compensation_amount or 0) >= 120000:
        score += 2
        tags.append("高金额")
    elif (params.compensation_amount or 0) >= 40000:
        score += 1

    if params.info_completeness is not None and params.info_completeness < 0.6:
        score += 1
        tags.append("信息不完整")

    if params.has_core_evidence is False:
        score += 1
        tags.append("证据偏弱")

    if params.near_deadline:
        score += 2
        tags.append("时效紧迫")

    if params.has_written_contract is False:
        score += 1
        tags.append("合同缺失")

    if params.has_social_insurance is False:
        score += 1
        tags.append("社保争议")

    if score >= 6:
        return "complex", "high", tags
    if score >= 3:
        return "moderate", "medium", tags
    return "simple", "low", tags


def _recommend_lawyers(region: str, complexity: str) -> list[dict[str, Any]]:
    # Static seed list for now; can be replaced by downstream CRM/provider integration.
    candidates = [
        {
            "id": "lx001",
            "name": "王律师",
            "firm": "陕西秦衡律师事务所",
            "regions": ["西安", "陕西"],
            "specialties": ["违法解除", "仲裁申请", "赔偿测算复核"],
            "reputation_score": 92,
            "contact": "400-100-1001",
        },
        {
            "id": "lx002",
            "name": "李律师",
            "firm": "陕西德衡劳动法律中心",
            "regions": ["西安", "咸阳", "陕西"],
            "specialties": ["工资社保争议", "证据组织", "庭审代理"],
            "reputation_score": 88,
            "contact": "400-100-1002",
        },
        {
            "id": "lx003",
            "name": "赵律师",
            "firm": "西安职衡律师事务所",
            "regions": ["西安"],
            "specialties": ["复杂劳动争议", "集体争议", "执行阶段"],
            "reputation_score": 90,
            "contact": "400-100-1003",
        },
    ]

    filtered = [lawyer for lawyer in candidates if region in lawyer["regions"] or "陕西" in lawyer["regions"]]
    if not filtered:
        filtered = candidates

    if complexity == "complex":
        return sorted(filtered, key=lambda x: x["reputation_score"], reverse=True)[:3]

    return filtered[:2]


def recommend_lawyers(params: LawyerRecommendInput) -> dict[str, Any]:
    complexity, urgency, risk_tags = _calculate_complexity(params)
    lawyers = _recommend_lawyers(params.region, complexity)

    action_hint = (
        "建议立即准备仲裁材料并预约律师初审。"
        if urgency == "high"
        else "建议先完成证据补全，再决定是否委托律师。"
        if urgency == "medium"
        else "案件相对简单，可先自助维权并保留律师复核入口。"
    )

    return {
        "region": params.region,
        "complexity": complexity,
        "urgency": urgency,
        "risk_tags": risk_tags,
        "recommended_lawyers": lawyers,
        "action_hint": action_hint,
        "referral_summary": {
            "dispute_types": params.dispute_types,
            "compensation_amount": params.compensation_amount,
            "has_core_evidence": params.has_core_evidence,
            "near_deadline": params.near_deadline,
        },
    }


class LaborLawyerRecommendTool(BaseTool):  # type: ignore[misc]
    """劳动争议律师推荐与分流工具。"""

    name = "labor_lawyer_recommend"
    description = (
        "基于争议类型、金额、证据与时效风险进行复杂度分流，并生成律师推荐列表。"
        "输出结构化转介卡片数据，用于前端展示与后续预约动作。"
    )
    input_model = LawyerRecommendInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: Any) -> Any:
        params = arguments if isinstance(arguments, LawyerRecommendInput) else LawyerRecommendInput(**arguments.model_dump())
        result = recommend_lawyers(params)
        return ToolResult(output=json.dumps(result, ensure_ascii=False, indent=2))
