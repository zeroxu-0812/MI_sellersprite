#!/usr/bin/env python3
"""
ai_analysis.py — 阶段三：AI 深度分析
调用智谱 GLM API，基于 clean_data.py 输出的 JSON 逐模块生成分析文本。
支持完整版（analysis.json）和去除头部品牌版（analysis_excl.json）。
"""
import json
import os
import argparse
import re

# ─── 智谱 API 配置 ──────────────────────────────────────────────────────────
ZHIPU_API_KEY = "0d774afb896648eb97c4c654beba975c.KBfoiJke0MR1OkHA"
ZHIPU_MODEL   = "glm-4-flash"   

try:
    from zhipuai import ZhipuAI
    _client = ZhipuAI(api_key=ZHIPU_API_KEY)
except ImportError:
    _client = None

# ─── 系统提示词 ──────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """你是一名资深跨境电商市场分析师（偏管理咨询风格），正在撰写商业报告正文。
写作目标：让业务负责人能直接据此做决策，而不是只看到“描述性复述”。

硬性约束：
1) 严禁以任何口吻性语句开头（如“好的”“根据你提供的数据”等），第一句必须是实质结论。
2) 所有数字、品牌、ASIN 必须来自输入 JSON；禁止编造。
3) 必须先给结论，再给证据，再给行动建议；避免空泛话术。
4) 当结论涉及原因时，需明确区分“数据事实”和“合理推断”，推断不得伪装成事实。
5) 输出使用中文，允许使用 Markdown 小标题与列表，风格专业、简洁、可执行。"""

QUALITY_NOTE = """【写作质量要求】
- 结论必须可执行：每段都尽量回答“所以应该怎么做”。
- 深度优先：不仅描述涨跌，还要解释结构变化（量价、份额、集中度、效率）。
- 证据密度：关键判断应附带具体数字或排名变化。
- 避免空话：禁用“整体向好/需持续关注”等无证据句。"""


def _ask(prompt: str) -> str:
    """调用智谱 API，返回文本结果。"""
    if _client is None:
        raise RuntimeError(
            "未找到 zhipuai 包，请先运行：pip install zhipuai"
        )
    resp = _client.chat.completions.create(
        model=ZHIPU_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        temperature=0.3,
        max_tokens=1500,
    )
    return resp.choices[0].message.content.strip()


def _currency_note(currency: str) -> str:
    currency = (currency or "$").strip() or "$"
    if currency == "$":
        return (
            "【货币单位约束】涉及价格、营收、ASP时，统一使用 $ 或“美元”，保持全篇一致。"
        )
    return (
        f"【货币单位约束】涉及价格、营收、ASP时，统一使用 {currency}。"
        "禁止使用美元、US$、USD 或 $。"
    )


def _normalize_currency_text(text: str, currency: str) -> str:
    """在非美元场景下，兜底替换模型可能输出的美元标记。"""
    currency = (currency or "$").strip() or "$"
    if currency == "$" or not text:
        return text
    text = re.sub(r"(?i)\bUSD\b", currency, text)
    text = re.sub(r"(?i)US\$", currency, text)
    text = text.replace("美元", currency)
    text = text.replace("$", currency)
    return text


def _load(cleaned_dir: str, filename: str) -> dict:
    path = os.path.join(cleaned_dir, filename)
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_analysis(cleaned_dir: str, output_dir: str,
                 suffix: str = "", purpose: str = "整体市场调研",
                 currency: str = "$") -> str:
    """
    执行一次 AI 分析并将结果写入 JSON 文件。

    参数
    ----
    cleaned_dir : 阶段一输出的 JSON 目录
    output_dir  : 分析结果输出目录
    suffix      : '' 为完整版，'_excl' 为去除头部品牌版
    purpose     : 核心商业目的（影响执行摘要的视角）

    返回
    ----
    输出文件的绝对路径
    """
    label = "完整版" if suffix == "" else "去除头部品牌版"
    print(f"\n{'='*60}")
    print(f"  AI 分析中：{label}")
    print(f"{'='*60}")

    m1   = _load(cleaned_dir, f"module1_market_trends{suffix}.json")
    m2   = _load(cleaned_dir, f"module2_brand_landscape{suffix}.json")
    m3   = _load(cleaned_dir, f"module3_rating_distribution{suffix}.json")
    m4   = _load(cleaned_dir, f"module4_price_bands{suffix}.json")
    m5   = _load(cleaned_dir, f"module5_listing_analysis{suffix}.json")
    m6   = _load(cleaned_dir, f"module6_asin_efficiency{suffix}.json")
    meta = _load(cleaned_dir, "meta.json")

    excl_note = ""
    if suffix == "_excl" and meta.get("dominant_brand"):
        excl_note = (
            f"\n\n【重要约束】本分析已剔除头部品牌 {meta['dominant_brand']}"
            f"（份额 {meta.get('dominant_brand_share_pct', '')}%）。"
            f"请勿在分析中提及该品牌，所有结论基于剔除后的市场数据。"
        )

    currency = (currency or "$").strip() or "$"
    c_note = _currency_note(currency)

    def ask_with_rules(prompt: str) -> str:
        full_prompt = f"{c_note}{excl_note}\n{QUALITY_NOTE}\n\n{prompt}"
        return _normalize_currency_text(_ask(full_prompt), currency)

    analysis = {}

    # 执行摘要
    print("  → 执行摘要...")
    analysis["executive_summary"] = ask_with_rules(
        "任务：撰写高密度执行摘要（面向业务负责人）。\n"
        f"商业目的：{purpose}\n\n"
        "输出格式（必须按顺序）：\n"
        "### 一句话结论\n"
        "### 关键洞察（3-4条）\n"
        "- 每条必须包含：数据事实（含数字）→ 商业含义 → 建议动作\n"
        "### 90天优先动作（3条）\n"
        "1. 动作名称 + 目标指标 + 预期影响\n\n"
        "字数建议：280-450字。\n\n"
        f"市场趋势数据：{json.dumps(m1, ensure_ascii=False)}\n"
        f"品牌竞争数据：{json.dumps(m2, ensure_ascii=False)}"
    )

    # 模块一
    print("  → 模块一：市场趋势...")
    analysis["module1_analysis"] = ask_with_rules(
        "任务：分析市场趋势，避免仅复述走势。\n"
        "必须覆盖：Revenue、Unit Sales、ASP 的趋势关系与量价结构。\n\n"
        "输出格式：\n"
        "### 趋势结论\n"
        "### 量价拆解（量增/价增/结构变化）\n"
        "### 关键拐点与异常月份（至少2个）\n"
        "### 业务含义与风险\n"
        "### 可执行动作（2-3条）\n\n"
        f"数据：{json.dumps(m1, ensure_ascii=False)}"
    )

    # 模块二（3个子分析）
    print("  → 模块二：品牌竞争格局...")
    analysis["module2_analysis"] = ask_with_rules(
        "任务：基于前十品牌同比变化，识别“强者更强”还是“份额再分配”。\n\n"
        "输出格式：\n"
        "### 竞争态势结论\n"
        "### 增长品牌与下滑品牌（分别至少2个，给出证据）\n"
        "### 排名变化与份额变化的错位解读\n"
        "### 对新品牌/存量品牌的策略启示\n\n"
        f"数据：{json.dumps(m2.get('top20_comparative', []), ensure_ascii=False)}"
    )
    analysis["module2_share_comparison_analysis"] = ask_with_rules(
        "任务：基于品牌份额环图与CR3，分析市场集中度和头部长尾结构变化。\n\n"
        "输出格式（标题必须使用以下四个名称，且不要把“必须/2条/高低”等要求写进标题本身）：\n"
        "### 集中度变化结论\n"
        "### 头部品牌与长尾品牌变化\n"
        "### 市场进入难度判断\n"
        "### 策略建议\n"
        "要求：\n"
        "- 第一节必须引用 CR3 变化。\n"
        "- 第三节给出进入难度评级（高/中/低）并说明依据。\n"
        "- 第四节给出2条策略建议。\n\n"
        f"环图数据：{json.dumps(m2.get('brand_share_ring', {}), ensure_ascii=False)}\n"
        f"CR3（Prev / Last / Change）："
        f"{m2.get('cr3_prev12_pct', 0)} / {m2.get('cr3_last12_pct', 0)} / {m2.get('cr3_change', 0)}"
    )
    analysis["module2_gain_loss_analysis"] = ask_with_rules(
        "任务：基于 Top 5 gaining / declining 做攻防解读，而不只是罗列名单。\n\n"
        "输出格式：\n"
        "### 份额迁移结论\n"
        "### 抢份额品牌画像\n"
        "### 流失品牌风险\n"
        "### 跟进动作\n"
        "排版要求：在“抢份额品牌画像”和“流失品牌风险”中，每个品牌必须使用如下结构：\n"
        "1. 品牌名\n"
        "- 增长原因/流失原因：...\n"
        "- 行动建议：...\n"
        "禁止写成“1.品牌 2.增长原因 3.行动建议”的串行编号。\n"
        "数量要求：两个小节都至少写2个品牌。\n\n"
        f"增长品牌：{json.dumps(m2.get('top5_gaining', []), ensure_ascii=False)}\n"
        f"下滑品牌：{json.dumps(m2.get('top5_declining', []), ensure_ascii=False)}"
    )
    analysis["module2_top20_analysis"] = ask_with_rules(
        "任务：对 Top20 做分层竞争分析，识别可切入空档。\n\n"
        "输出格式：\n"
        "### 市场分层（领导者/挑战者/机会型）\n"
        "### 关键竞争变量（价格、评分、ASIN密度、份额）\n"
        "### 可切入机会（至少2个）\n"
        "### 进入策略建议（1个保守方案 + 1个进攻方案）\n\n"
        f"数据：{json.dumps(m2.get('top20_comparative', []), ensure_ascii=False)}"
    )

    # 模块三
    print("  → 模块三：星级分析...")
    analysis["module3_analysis"] = ask_with_rules(
        "任务：分析评分门槛，明确“最低可行评分带”。\n\n"
        "输出格式：\n"
        "### 评分门槛结论\n"
        "### 各评分段的营收效率对比\n"
        "### 新品评分目标建议（短期/中期）\n"
        "### 运营动作（评价获取、差评治理）\n\n"
        f"数据：{json.dumps(m3, ensure_ascii=False)}"
    )

    # 模块四
    print("  → 模块四：价位段分析...")
    analysis["module4_analysis"] = ask_with_rules(
        "任务：做价位段策略地图，不仅判断“哪个高”，还要判断“为什么高”。\n\n"
        "输出格式：\n"
        "### 价位带总体判断\n"
        "### 机会带/防守带/高风险带（分别列出并给证据）\n"
        "### 份额变化与营收增长的背离解读\n"
        "### 定价与产品组合建议（2-3条）\n\n"
        f"数据：{json.dumps(m4, ensure_ascii=False)}"
    )

    # 模块五
    print("  → 模块五：上架分析...")
    analysis["module5_analysis"] = ask_with_rules(
        "任务：分析上新节奏与份额贡献，判断新品策略是否有效。\n\n"
        "输出格式（标题不要包含括号内要求）：\n"
        "### 上新节奏结论\n"
        "### 新品贡献评估\n"
        "### 竞争对手可能策略推断\n"
        "### 我方上新建议\n"
        "要求：\n"
        "- “竞争对手可能策略推断”必须基于数据证据。\n"
        "- “我方上新建议”需包含节奏与资源投入建议。\n\n"
        f"数据：{json.dumps(m5, ensure_ascii=False)}"
    )

    # 模块六
    print("  → 模块六：ASIN 效率分析...")
    analysis["module6_analysis"] = ask_with_rules(
        "任务：基于效率分数（Unit Sales / Review Count）识别“高效率样本”的可复制打法。\n\n"
        "输出格式（标题不要包含括号内要求）：\n"
        "### 高效率ASIN结论\n"
        "### 样本拆解\n"
        "### 可复制打法与边界条件\n"
        "### 新品运营建议\n"
        "要求：\n"
        "- “样本拆解”至少包含3个具体ASIN，且写出品牌与效率值。\n"
        "- “新品运营建议”给出2-3条可执行动作。\n\n"
        f"数据：{json.dumps(m6, ensure_ascii=False)}"
    )

    # 报告标题
    time_info = m1.get("time_info", {})
    last_12   = time_info.get("last_12_range", "")
    if suffix == "_excl" and meta.get("dominant_brand"):
        analysis["title"] = (
            f"跨境电商市场洞察报告（去除 {meta['dominant_brand']} · {last_12}）"
        )
    else:
        analysis["title"] = f"跨境电商市场洞察报告（{last_12}）"
    analysis["currency_symbol"] = currency

    # 写出结果
    out_name = "analysis_excl.json" if suffix == "_excl" else "analysis.json"
    out_path = os.path.join(output_dir, out_name)
    os.makedirs(output_dir, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)
    print(f"  ✓ 已保存：{out_path}")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Market Insight 阶段三：AI 深度分析")
    parser.add_argument("cleaned_dir", help="清洗后 JSON 目录")
    parser.add_argument("output_dir", help="输出目录")
    parser.add_argument("purpose", nargs="?", default="整体市场调研", help="核心商业目的")
    parser.add_argument("--currency", default="$", help='货币符号，默认 "$"')
    args = parser.parse_args()

    meta = _load(args.cleaned_dir, "meta.json")
    run_analysis(
        args.cleaned_dir,
        args.output_dir,
        suffix="",
        purpose=args.purpose,
        currency=args.currency,
    )
    if meta.get("has_dominant_brand"):
        run_analysis(
            args.cleaned_dir,
            args.output_dir,
            suffix="_excl",
            purpose=args.purpose,
            currency=args.currency,
        )


if __name__ == "__main__":
    main()
