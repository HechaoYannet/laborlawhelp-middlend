"""Labor dispute document generator tool.

Generates structured legal documents for labor disputes:
- 劳动仲裁申请书 (Arbitration application)
- 证据清单 (Evidence list)
- 维权行动清单 (Action checklist)
"""

from __future__ import annotations

import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

try:
    from openharness.tools.base import BaseTool, ToolResult, ToolExecutionContext
except ImportError:  # pragma: no cover
    BaseTool = object  # type: ignore[assignment,misc]
    ToolResult = None  # type: ignore[assignment,misc]
    ToolExecutionContext = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------

class DocumentType(str, Enum):
    ARBITRATION_APPLICATION = "arbitration_application"  # 劳动仲裁申请书
    EVIDENCE_LIST = "evidence_list"                      # 证据清单
    ACTION_CHECKLIST = "action_checklist"                 # 维权行动清单
    CASE_SUMMARY = "case_summary"                        # 案情摘要卡片


class DocumentInput(BaseModel):
    """文书生成输入参数"""
    document_type: DocumentType = Field(
        description="要生成的文书类型: arbitration_application(仲裁申请书)/"
                    "evidence_list(证据清单)/action_checklist(行动清单)/case_summary(案情摘要)"
    )
    # 当事人信息
    applicant_name: str = Field(description="申请人姓名")
    applicant_gender: str | None = Field(default=None, description="申请人性别")
    applicant_id_number: str | None = Field(default=None, description="申请人身份证号（可选，会脱敏处理）")
    applicant_phone: str | None = Field(default=None, description="申请人联系电话")
    applicant_address: str | None = Field(default=None, description="申请人住址")

    respondent_name: str = Field(description="被申请人/用人单位名称")
    respondent_address: str | None = Field(default=None, description="被申请人地址")
    respondent_legal_rep: str | None = Field(default=None, description="法定代表人姓名")

    # 案件事实
    employment_start: str | None = Field(default=None, description="入职日期 YYYY-MM-DD")
    employment_end: str | None = Field(default=None, description="离职日期 YYYY-MM-DD")
    position: str | None = Field(default=None, description="工作岗位")
    monthly_wage: float | None = Field(default=None, description="月工资（元）")
    monthly_wage_take_home: float | None = Field(default=None, description="月到手工资（元）")

    # 争议要点
    dispute_summary: str = Field(
        description="争议事实简要描述，如：公司以调岗降薪方式迫使本人离职，属于违法解除劳动合同"
    )
    claims: list[str] | None = Field(
        default=None,
        description="仲裁请求列表，如：['支付违法解除赔偿金28000元', '支付未签合同双倍工资差额']"
    )
    compensation_amount: float | None = Field(
        default=None,
        description="赔偿/补偿总金额（元），来自 labor_compensation_calc 的计算结果"
    )

    # 证据相关
    evidence_items: list[str] | None = Field(
        default=None,
        description="已有证据描述列表，如：['劳动合同复印件', '工资银行流水', '解除通知书']"
    )

    region: str = Field(default="西安", description="仲裁委所在地区")


# ---------------------------------------------------------------------------
# Document generators
# ---------------------------------------------------------------------------

def _mask_id(id_number: str | None) -> str:
    if not id_number or len(id_number) < 8:
        return id_number or "（未提供）"
    return id_number[:6] + "****" + id_number[-4:]


def _generate_arbitration_application(p: DocumentInput) -> dict[str, Any]:
    """生成劳动仲裁申请书模板"""
    today = date.today().isoformat()

    claims_text = ""
    if p.claims:
        for i, claim in enumerate(p.claims, 1):
            claims_text += f"  {i}. {claim}；\n"
    else:
        claims_text = "  1. 依法支付经济补偿/赔偿金；\n  2. （请根据实际情况补充）\n"

    body = f"""劳动人事争议仲裁申请书

申请人：{p.applicant_name}，{p.applicant_gender or '（性别）'}，身份证号：{_mask_id(p.applicant_id_number)}
住址：{p.applicant_address or '（请填写）'}
联系电话：{p.applicant_phone or '（请填写）'}

被申请人：{p.respondent_name}
住所地：{p.respondent_address or '（请填写）'}
法定代表人：{p.respondent_legal_rep or '（请填写）'}

仲裁请求：
{claims_text}
事实与理由：

申请人于{p.employment_start or '（入职日期）'}入职被申请人处，担任{p.position or '（岗位）'}一职，月工资{p.monthly_wage or '（金额）'}元（到手工资{p.monthly_wage_take_home or '（金额）'}元）。

{p.dispute_summary}

根据《中华人民共和国劳动合同法》相关规定，被申请人应当依法承担相应法律责任。{"经计算，被申请人应支付赔偿/补偿金共计" + f"{p.compensation_amount:.0f}元。" if p.compensation_amount else ""}

为维护申请人合法权益，特依法申请仲裁，请求裁如所请。

此致
{p.region}市劳动人事争议仲裁委员会

                                          申请人：{p.applicant_name}
                                          日  期：{today}

附：证据材料清单（另附）
"""

    return {
        "document_type": "劳动仲裁申请书",
        "content": body,
        "notes": [
            "⚠️ 本文书为模板，需根据实际情况修改完善",
            "仲裁时效：劳动争议申请仲裁的时效期间为一年（《劳动争议调解仲裁法》第27条）",
            f"管辖：{p.region}市劳动人事争议仲裁委员会",
            "材料准备：需提交申请书正本一份、副本按被申请人数量提交",
        ],
        "region": p.region,
    }


def _generate_evidence_list(p: DocumentInput) -> dict[str, Any]:
    """生成证据清单"""
    # 标准证据项目
    standard_evidence = [
        {"name": "劳动合同", "purpose": "证明劳动关系成立及合同约定条款", "source": "本人持有/公司签章", "priority": "必要"},
        {"name": "工资银行流水", "purpose": "证明每月实际到手工资金额", "source": "银行打印并盖章", "priority": "必要"},
        {"name": "社保缴纳记录", "purpose": "证明劳动关系存续期间及社保缴费基数", "source": "社保局打印", "priority": "必要"},
        {"name": "解除/终止劳动合同通知书", "purpose": "证明解除方式及理由", "source": "公司出具", "priority": "必要"},
        {"name": "工资条/薪资确认单", "purpose": "证明工资构成明细", "source": "公司发放", "priority": "重要"},
        {"name": "考勤记录", "purpose": "证明实际出勤情况", "source": "公司系统/打卡记录", "priority": "补充"},
        {"name": "工作沟通记录", "purpose": "证明工作内容及解除过程", "source": "微信/钉钉/邮件截图", "priority": "重要"},
        {"name": "入职登记表", "purpose": "证明入职时间及岗位", "source": "公司签章", "priority": "补充"},
    ]

    # 合并用户已有证据
    user_items = []
    if p.evidence_items:
        for item in p.evidence_items:
            user_items.append({
                "name": item,
                "status": "已有",
            })

    # 匹配缺失
    user_names = {item["name"] for item in user_items} if user_items else set()
    missing = []
    for std in standard_evidence:
        found = any(std["name"] in uname or uname in std["name"] for uname in user_names)
        if not found:
            missing.append(std)

    return {
        "document_type": "证据清单",
        "standard_evidence": standard_evidence,
        "user_provided": user_items,
        "missing_evidence": missing,
        "tips": [
            "银行流水建议打印近12个月完整记录",
            "微信/钉钉聊天记录建议做公证或区块链存证",
            "解除通知若未书面送达，可用录音录像补充",
            "陕西地区：工资流水是证明到手工资的关键证据（陕高法〔2020〕118号）",
        ],
        "region": p.region,
    }


def _generate_action_checklist(p: DocumentInput) -> dict[str, Any]:
    """生成维权行动清单"""
    checklist = [
        {
            "step": 1,
            "action": "固定和保全证据",
            "detail": "立即保存劳动合同、工资流水、解除通知、工作沟通记录等。电子证据建议截图+录屏双重保存。",
            "deadline": "立即",
            "status": "待办",
        },
        {
            "step": 2,
            "action": "确认仲裁时效",
            "detail": "劳动争议仲裁时效为1年，从知道或应当知道权利被侵害之日起算。"
                      f"离职日期{p.employment_end or '（待确认）'}起算。",
            "deadline": "确认后尽快",
            "status": "待办",
        },
        {
            "step": 3,
            "action": "到银行打印工资流水",
            "detail": "携带身份证到工资卡开户行打印近12个月流水并加盖银行章。"
                      "陕西地区按到手工资计算补偿金，流水是核心证据。",
            "deadline": "1-3个工作日",
            "status": "待办",
        },
        {
            "step": 4,
            "action": "查询社保缴纳记录",
            "detail": f"登录{p.region}市人社局官网或到社保窗口打印参保证明。",
            "deadline": "1-3个工作日",
            "status": "待办",
        },
        {
            "step": 5,
            "action": "撰写仲裁申请书",
            "detail": "按照模板填写完整，确认仲裁请求金额。建议请专业人士审核。",
            "deadline": "3-5个工作日",
            "status": "待办",
        },
        {
            "step": 6,
            "action": "提交仲裁申请",
            "detail": f"携带申请书（正本+副本）、证据材料、身份证复印件，到{p.region}市劳动人事争议仲裁委员会立案窗口提交。",
            "deadline": "材料齐备后",
            "status": "待办",
        },
        {
            "step": 7,
            "action": "评估是否聘请律师",
            "detail": "金额较大或案情复杂建议聘请专业劳动法律师。"
                      f"{'涉及金额' + f'{p.compensation_amount:.0f}元' + '，建议咨询律师意见。' if p.compensation_amount and p.compensation_amount > 10000 else ''}",
            "deadline": "建议在提交仲裁前",
            "status": "待办",
        },
    ]

    return {
        "document_type": "维权行动清单",
        "checklist": checklist,
        "important_reminders": [
            "⏰ 不要签署任何自愿离职文件",
            "📱 保持与公司通信记录的完整性，不要删除聊天记录",
            "💰 仲裁不收费，无需缴纳仲裁费用",
            f"📍 管辖：{p.region}市劳动人事争议仲裁委员会",
        ],
        "region": p.region,
    }


def _generate_case_summary(p: DocumentInput) -> dict[str, Any]:
    """生成案情摘要卡片"""
    return {
        "document_type": "案情摘要卡片",
        "parties": {
            "applicant": {
                "name": p.applicant_name,
                "gender": p.applicant_gender,
            },
            "respondent": {
                "name": p.respondent_name,
                "legal_rep": p.respondent_legal_rep,
            },
        },
        "employment": {
            "period": f"{p.employment_start or '?'} 至 {p.employment_end or '?'}",
            "position": p.position,
            "monthly_wage_pretax": p.monthly_wage,
            "monthly_wage_take_home": p.monthly_wage_take_home,
        },
        "dispute": {
            "summary": p.dispute_summary,
            "claims": p.claims or [],
            "compensation_amount": p.compensation_amount,
        },
        "region": p.region,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------------------
# OpenHarness tool wrapper
# ---------------------------------------------------------------------------

class LaborDocumentTool(BaseTool):  # type: ignore[misc]
    """劳动争议文书生成器"""

    name = "labor_document_gen"
    description = (
        "生成劳动争议相关法律文书模板，包括：仲裁申请书、证据清单、维权行动清单、案情摘要卡片。"
        "输入当事人信息、案件事实、争议要点等参数，返回结构化文书内容。"
        "文书为模板性质，需用户根据实际情况修改完善。"
    )
    input_model = DocumentInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: Any) -> Any:
        params = arguments if isinstance(arguments, DocumentInput) else DocumentInput(**arguments.model_dump())

        generators = {
            DocumentType.ARBITRATION_APPLICATION: _generate_arbitration_application,
            DocumentType.EVIDENCE_LIST: _generate_evidence_list,
            DocumentType.ACTION_CHECKLIST: _generate_action_checklist,
            DocumentType.CASE_SUMMARY: _generate_case_summary,
        }

        generator = generators[params.document_type]
        result = generator(params)
        return ToolResult(output=json.dumps(result, ensure_ascii=False, indent=2))
