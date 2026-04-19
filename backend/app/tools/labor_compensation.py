"""Labor compensation calculator with Shaanxi local rules.

Implements economic compensation calculation following:
- 《劳动合同法》第四十七条 (经济补偿)
- 《劳动合同法》第八十七条 (违法解除赔偿金 = 2 × 经济补偿)
- 《劳动合同法》第八十二条 (未签合同双倍工资)
- 陕高法〔2020〕118号 第18条 (陕西省：月工资基数按到手工资计算)
"""

from __future__ import annotations

import json
import math
from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

# OpenHarness tool base — imported at registration time.
# We defer the import so the module can be loaded without OH installed.
try:
    from openharness.tools.base import BaseTool, ToolResult, ToolExecutionContext
except ImportError:  # pragma: no cover
    BaseTool = object  # type: ignore[assignment,misc]
    ToolResult = None  # type: ignore[assignment,misc]
    ToolExecutionContext = None  # type: ignore[assignment,misc]


# ---------------------------------------------------------------------------
# Enums & Input model
# ---------------------------------------------------------------------------

class TerminationType(str, Enum):
    """劳动合同解除/终止类型"""
    ILLEGAL_TERMINATION = "illegal_termination"  # 违法解除
    LEGAL_TERMINATION = "legal_termination"      # 合法解除（经济补偿）
    UNSIGNED_CONTRACT = "unsigned_contract"       # 未签劳动合同双倍工资
    MIXED = "mixed"                              # 复合（同时存在多种情形）


class WageStandard(str, Enum):
    """工资基数标准"""
    SHAANXI_TAKE_HOME = "shaanxi_take_home"     # 陕西到手工资标准
    NATIONAL_PRE_TAX = "national_pre_tax"        # 全国通用税前工资标准


class CompensationInput(BaseModel):
    """经济补偿/赔偿金计算输入参数"""
    monthly_wage_pretax: float = Field(
        description="月工资（税前/合同约定金额），单位：元"
    )
    monthly_wage_take_home: float | None = Field(
        default=None,
        description="月到手工资（扣除社保个人部分和个税后实发金额），单位：元。"
                    "陕西省按此计算经济补偿。若未提供则使用税前工资。"
    )
    employment_start: str = Field(
        description="入职日期，格式 YYYY-MM-DD"
    )
    employment_end: str = Field(
        description="离职/终止日期，格式 YYYY-MM-DD"
    )
    termination_type: TerminationType = Field(
        default=TerminationType.ILLEGAL_TERMINATION,
        description="解除类型: illegal_termination(违法解除)/legal_termination(合法解除)/"
                    "unsigned_contract(未签合同)/mixed(复合)",
    )
    region: str = Field(
        default="shaanxi",
        description="所在地区，默认 shaanxi（陕西）。影响工资基数计算标准。"
    )
    wage_standard: WageStandard = Field(
        default=WageStandard.SHAANXI_TAKE_HOME,
        description="工资基数标准: shaanxi_take_home(陕西到手工资)/national_pre_tax(全国税前)",
    )
    local_min_wage: float | None = Field(
        default=None,
        description="当地最低工资标准（月），单位：元。未提供则使用西安2024年标准2160元。"
    )
    local_avg_wage_3x: float | None = Field(
        default=None,
        description="当地上年度职工月平均工资三倍上限。未提供则使用2024年陕西标准。"
    )
    unsigned_contract_months: int | None = Field(
        default=None,
        description="未签劳动合同的月数（适用于 unsigned_contract 类型），最多11个月。"
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 西安市 2024 年最低工资标准（一类区）
XIAN_MIN_WAGE_2024 = 2160.0

# 陕西省 2023 年全口径城镇单位就业人员月平均工资 × 3
# (2023年约 7200 元/月，三倍上限 21600 元/月) — 用于封顶
SHAANXI_AVG_WAGE_3X_2024 = 21600.0


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def _parse_date(s: str) -> date:
    return date.fromisoformat(s.strip())


def _work_years(start: date, end: date) -> float:
    """计算工作年限（劳动合同法口径：不满六个月按0.5年，六个月以上不满一年按1年）"""
    delta = end - start
    total_months = (end.year - start.year) * 12 + (end.month - start.month)
    if end.day < start.day:
        total_months -= 1
    remaining_days = (end - start.replace(year=start.year + total_months // 12,
                                           month=start.month + total_months % 12
                                           if start.month + total_months % 12 <= 12
                                           else (start.month + total_months % 12) - 12)).days
    # Simplified: use total days
    total_days = delta.days
    full_years = total_months // 12
    leftover_months = total_months % 12

    # 《劳动合同法》第47条第1款：每满一年支付一个月工资
    # 六个月以上不满一年的，按一年计算；不满六个月的，支付半个月工资
    if leftover_months >= 6:
        return float(full_years + 1)
    elif leftover_months > 0 or (total_days > full_years * 365):
        return full_years + 0.5
    else:
        return float(full_years)


def calculate_compensation(params: CompensationInput) -> dict[str, Any]:
    """计算经济补偿/赔偿金，返回结构化结果。"""
    start = _parse_date(params.employment_start)
    end = _parse_date(params.employment_end)
    work_years = _work_years(start, end)

    # 选择工资基数
    is_shaanxi = params.region.lower() in ("shaanxi", "陕西", "shanxi", "西安", "xian")
    if is_shaanxi and params.wage_standard == WageStandard.SHAANXI_TAKE_HOME:
        wage_base = params.monthly_wage_take_home or params.monthly_wage_pretax
        wage_standard_label = "陕西到手工资标准（陕高法〔2020〕118号第18条）"
    else:
        wage_base = params.monthly_wage_pretax
        wage_standard_label = "全国通用税前工资标准"

    # 上限和下限
    avg_3x = params.local_avg_wage_3x or SHAANXI_AVG_WAGE_3X_2024
    min_wage = params.local_min_wage or XIAN_MIN_WAGE_2024

    # 第47条第2款：月工资高于三倍的按三倍，且年限最高不超过12年
    capped = False
    if wage_base > avg_3x:
        wage_base = avg_3x
        capped = True
        work_years_for_calc = min(work_years, 12.0)
    else:
        work_years_for_calc = work_years

    results: dict[str, Any] = {
        "input_summary": {
            "employment_period": f"{params.employment_start} 至 {params.employment_end}",
            "work_years": work_years,
            "work_years_for_calc": work_years_for_calc,
            "monthly_wage_pretax": params.monthly_wage_pretax,
            "monthly_wage_take_home": params.monthly_wage_take_home,
            "wage_base_used": wage_base,
            "wage_standard": wage_standard_label,
            "region": params.region,
            "was_capped": capped,
        },
        "legal_basis": [],
        "calculations": [],
        "total_amount": 0.0,
        "comparison": None,
    }

    # --- 经济补偿 / 违法解除赔偿金 ---
    if params.termination_type in (TerminationType.ILLEGAL_TERMINATION,
                                    TerminationType.LEGAL_TERMINATION,
                                    TerminationType.MIXED):
        economic_compensation = wage_base * work_years_for_calc

        results["legal_basis"].append({
            "law": "《中华人民共和国劳动合同法》",
            "article": "第四十七条",
            "content": "经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资的标准向劳动者支付。"
                       "六个月以上不满一年的，按一年计算；不满六个月的，向劳动者支付半个月工资的经济补偿。",
        })

        if is_shaanxi:
            results["legal_basis"].append({
                "law": "陕西省高级人民法院民事审判第一庭关于审理劳动争议案件若干问题的解答",
                "article": "陕高法〔2020〕118号 第18条",
                "content": "劳动者主张经济补偿的月工资基数应以劳动者实际到手工资为准，"
                           "即扣除社会保险费个人缴纳部分和个人所得税后的实际所得。",
            })

        results["calculations"].append({
            "item": "经济补偿（N）",
            "formula": f"{wage_base:.0f} × {work_years_for_calc} = {economic_compensation:.0f}",
            "amount": round(economic_compensation, 2),
        })

        if params.termination_type == TerminationType.ILLEGAL_TERMINATION:
            illegal_compensation = economic_compensation * 2
            results["legal_basis"].append({
                "law": "《中华人民共和国劳动合同法》",
                "article": "第八十七条",
                "content": "用人单位违反本法规定解除或者终止劳动合同的，"
                           "应当依照本法第四十七条规定的经济补偿标准的二倍向劳动者支付赔偿金。",
            })
            results["calculations"].append({
                "item": "违法解除赔偿金（2N）",
                "formula": f"{economic_compensation:.0f} × 2 = {illegal_compensation:.0f}",
                "amount": round(illegal_compensation, 2),
            })
            results["total_amount"] += illegal_compensation
        elif params.termination_type == TerminationType.MIXED:
            # mixed: include both N and 2N line items
            illegal_compensation = economic_compensation * 2
            results["legal_basis"].append({
                "law": "《中华人民共和国劳动合同法》",
                "article": "第八十七条",
                "content": "用人单位违反本法规定解除或者终止劳动合同的赔偿金为经济补偿标准的二倍。",
            })
            results["calculations"].append({
                "item": "违法解除赔偿金（2N）",
                "formula": f"{economic_compensation:.0f} × 2 = {illegal_compensation:.0f}",
                "amount": round(illegal_compensation, 2),
            })
            results["total_amount"] += illegal_compensation
        else:
            results["total_amount"] += economic_compensation

    # --- 未签合同双倍工资差额 ---
    if params.termination_type in (TerminationType.UNSIGNED_CONTRACT, TerminationType.MIXED):
        months = params.unsigned_contract_months or 0
        months = min(months, 11)  # 最多11个月
        if months > 0:
            double_wage_diff = params.monthly_wage_pretax * months
            results["legal_basis"].append({
                "law": "《中华人民共和国劳动合同法》",
                "article": "第八十二条",
                "content": "用人单位自用工之日起超过一个月不满一年未与劳动者订立书面劳动合同的，"
                           "应当向劳动者每月支付二倍的工资。",
            })
            results["calculations"].append({
                "item": "未签合同双倍工资差额",
                "formula": f"{params.monthly_wage_pretax:.0f} × {months} = {double_wage_diff:.0f}",
                "amount": round(double_wage_diff, 2),
            })
            results["total_amount"] += double_wage_diff

    results["total_amount"] = round(results["total_amount"], 2)

    # --- 对比：陕西标准 vs 全国标准 ---
    if is_shaanxi and params.monthly_wage_take_home and params.monthly_wage_take_home != params.monthly_wage_pretax:
        national_base = params.monthly_wage_pretax
        shaanxi_base = params.monthly_wage_take_home
        if params.termination_type == TerminationType.ILLEGAL_TERMINATION:
            national_amount = national_base * work_years_for_calc * 2
            shaanxi_amount = shaanxi_base * work_years_for_calc * 2
        elif params.termination_type == TerminationType.LEGAL_TERMINATION:
            national_amount = national_base * work_years_for_calc
            shaanxi_amount = shaanxi_base * work_years_for_calc
        else:
            national_amount = national_base * work_years_for_calc * 2
            shaanxi_amount = shaanxi_base * work_years_for_calc * 2

        results["comparison"] = {
            "national_standard": {
                "wage_base": national_base,
                "amount": round(national_amount, 2),
                "label": "全国通用（税前工资）",
            },
            "shaanxi_standard": {
                "wage_base": shaanxi_base,
                "amount": round(shaanxi_amount, 2),
                "label": "陕西标准（到手工资，陕高法〔2020〕118号）",
            },
            "difference": round(national_amount - shaanxi_amount, 2),
            "note": "陕西省按到手工资计算，金额通常低于全国税前标准。"
                    "实际适用以劳动仲裁委/法院所在地标准为准。",
        }

    return results


# ---------------------------------------------------------------------------
# OpenHarness tool wrapper
# ---------------------------------------------------------------------------

class LaborCompensationTool(BaseTool):  # type: ignore[misc]
    """劳动争议经济补偿/赔偿金计算器（含陕西本地规则）"""

    name = "labor_compensation_calc"
    description = (
        "计算劳动争议中的经济补偿(N)、违法解除赔偿金(2N)、未签合同双倍工资差额。"
        "支持陕西省地方标准（到手工资基数，陕高法〔2020〕118号第18条）与全国标准对比。"
        "输入工资、在职时间、解除类型等参数，返回结构化计算结果和法律依据。"
    )
    input_model = CompensationInput

    def is_read_only(self, arguments: BaseModel) -> bool:
        return True

    async def execute(self, arguments: BaseModel, context: Any) -> Any:
        params = arguments if isinstance(arguments, CompensationInput) else CompensationInput(**arguments.model_dump())
        result = calculate_compensation(params)
        return ToolResult(output=json.dumps(result, ensure_ascii=False, indent=2))
