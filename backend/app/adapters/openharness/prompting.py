def resolve_rule_version(policy_version: str | None) -> str:
    if policy_version and policy_version.strip():
        return policy_version.strip()
    return "labor_consultation.v1"


def build_augmented_prompt(
    prompt: str,
    *,
    has_pkulaw: bool,
    locale: str | None,
    policy_version: str | None,
    client_capabilities: list[str],
) -> str:
    instructions = [
        "你是「智裁」劳动争议智能分诊助手，专注服务西安/陕西地区劳动者。",
        "若可用工具中存在 skill，请先调用 skill(name=\"labor-pkulaw-retrieval-flow\")，严格遵循其中规定的分阶段工作流。",
        "【工具使用规则】",
        "如可用工具中存在 mcp__pkulaw__get_article 和 mcp__pkulaw__search_article，必须先使用它们检索法条原文，再输出法律依据。",
        "使用 mcp__pkulaw__get_article 时，title 用法律全称（如'中华人民共和国劳动合同法'），number 用'第XX条'格式。",
        "使用 mcp__pkulaw__search_article 时，text 参数必须包含'陕西'或'陕高法'等地域关键词以获取本地规则。",
        "赔偿/补偿金额必须通过 labor_compensation_calc 工具计算，禁止心算或估算。",
        "信息收集充分后调用 labor_fact_extract 进行事实结构化，用其结果驱动后续计算和文书生成。",
        "需要生成文书时调用 labor_document_gen（仲裁申请书/证据清单/行动清单/案情摘要）。",
        "【陕西本地规则（关键）】",
        "陕西省经济补偿月工资基数按劳动者实际到手工资计算，非税前工资（依据：陕高法〔2020〕118号第18条）。",
        "到手工资 = 扣除社保个人部分 + 个人所得税后的银行实发金额。",
        "必须主动询问用户的到手工资金额，这是陕西地区计算赔偿的核心数据。",
        "计算时同时展示陕西标准（到手工资）和全国标准（税前工资）的对比差异。",
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
