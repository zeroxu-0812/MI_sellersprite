#!/usr/bin/env python3
"""
报告整合脚本 (generate_report.py)
将AI分析文本与图表整合为完整HTML报告。
视觉规范：深蓝 + Slate灰 + 青绿点缀，上图下分析排版，咨询报告风格。
"""

import json
import os
import sys
import base64
import math
import markdown

CURRENCY_SYMBOL = "$"


def img_to_base64(img_path):
    if not os.path.exists(img_path):
        return ""
    with open(img_path, 'rb') as f:
        data = base64.b64encode(f.read()).decode('utf-8')
    return f"data:image/png;base64,{data}"


# 口吻性开头语匹配模式（实现层安全网）
import re as _re
_PREAMBLE_PATTERNS = _re.compile(
    r'^[\s\S]*?'
    r'(?:'
    r'好的[，,！!\s]|'
    r'根据您提供的|'
    r'根据所提供的|'
    r'作为[一个一名]|'
    r'我将根据|'
    r'我将对|'
    r'我将为您|'
    r'以下是我的|'
    r'以下是对|'
    r'接下来我将'
    r')'
    r'[^。\.\n]{0,120}[。\.\n]',
    _re.MULTILINE
)


def _strip_preamble(text: str) -> str:
    """过滤掉 AI 口吻性开头语（如“好的，作为……”）。"""
    if not text:
        return text
    # 只处理开头的口吻性语句（限定在文本前 3 行内）
    lines = text.split('\n')
    # 找到第一个非空行
    first_nonempty = next((i for i, l in enumerate(lines) if l.strip()), None)
    if first_nonempty is None:
        return text
    first_line = lines[first_nonempty].strip()
    # 匹配口吻性开头模式
    preamble_re = _re.compile(
        r'^(?:'
        r'好的[，,！!\s]|'
        r'没问题[，,\s]|'
        r'当然[，,\s]|'
        r'根据您提供的|'
        r'根据所提供的|'
        r'作为[一个一名]|'
        r'我将根据|'
        r'我将对|'
        r'我将为您|'
        r'以下是我的|'
        r'以下是对|'
        r'接下来我将'
        r')'
    )
    if preamble_re.match(first_line):
        # 移除该行，保留剩余内容
        lines.pop(first_nonempty)
        # 移除可能小标题行（如“### 亚马逊意大利站厨房电器品类市场分析”）——不删除，保留结构
        text = '\n'.join(lines)
    return text.lstrip('\n')


def _clean_instructional_artifacts(text: str) -> str:
    """清理模型误输出的提示词痕迹（如“必须/至少/2条”写进标题）。"""
    if not text:
        return text

    heading_re = _re.compile(r'^(\s*#{1,6}\s*)(.+?)\s*$')
    # 标题中的提示词括号（仅在出现“要求型关键词”时移除）
    noisy_paren_re = _re.compile(
        r'（[^）]*?(?:必须|至少|并给|给出|是否|高/中/低|触发阈值|监控指标|按顺序|'
        r'[0-9]+条|2-3条|短期|中期|含品牌|可执行)[^）]*）'
    )
    noisy_paren_re_en = _re.compile(
        r'\([^)]*?(?:must|at least|with evidence|trigger|threshold|2-3|[0-9]+\s*items?)'
        r'[^)]*\)', _re.IGNORECASE
    )
    instruction_line_re = _re.compile(
        r'^\s*(?:任务|输出格式|字数建议|必须覆盖|写作要求|硬性约束)\s*[:：]\s*$'
        r'|^\s*-\s*每条必须包含'
        r'|^\s*\d+\.\s*动作名称\s*\+\s*目标指标',
        _re.IGNORECASE
    )

    out_lines = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if instruction_line_re.match(line):
            continue
        m = heading_re.match(line)
        if m:
            prefix, title = m.group(1), m.group(2).strip()
            title = noisy_paren_re.sub('', title)
            title = noisy_paren_re_en.sub('', title)
            title = _re.sub(r'\s{2,}', ' ', title).strip(" ：:")
            if not title:
                continue
            line = f"{prefix}{title}"
        out_lines.append(line)

    cleaned = '\n'.join(out_lines)
    return cleaned.strip()


def _looks_like_brand_label(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 48:
        return False
    if '：' in t or ':' in t:
        return False
    if t.startswith(('增长原因', '流失原因', '原因', '行动建议', '应对建议', '建议', '风险')):
        return False
    return True


def _normalize_gain_loss_blocks(text: str) -> str:
    """
    将“1.品牌 2.增长原因 3.行动建议”修正为：
    1. 品牌
    - 增长原因...
    - 行动建议...
    """
    if not text:
        return text

    num_item_re = _re.compile(r'^\s*\d+[\.、]\s*(.+?)\s*$')
    detail_hint_re = _re.compile(r'^(?:增长原因|流失原因|原因|行动建议|应对建议|建议|风险|证据)\s*[:：]')
    lines = text.splitlines()
    out = []
    i = 0
    brand_idx = 1
    in_brand_block = False

    while i < len(lines):
        line = lines[i].strip()
        m = num_item_re.match(line)
        if not m:
            # 若处在品牌块中，保留明细行但去掉多余列表符号，避免变成独立列表项
            if in_brand_block and line.startswith(('-', '*')):
                out.append(line.lstrip('-* ').strip())
            else:
                out.append(lines[i])
            i += 1
            continue

        item_content = m.group(1).strip()

        # 明细行（如：2.增长原因：... / 3.行动建议：...）→ 去掉编号，跟随品牌行输出
        if detail_hint_re.match(item_content):
            out.append(item_content)
            in_brand_block = True
            i += 1
            continue

        # 否则当作品牌行（如：1.Philips / 4.GRUNDIG）
        if _looks_like_brand_label(item_content):
            # 仅在后续存在“编号的原因/建议”明细时触发重排，避免误伤普通编号列表
            j = i + 1
            has_detail_hint = False
            while j < len(lines):
                nxt = lines[j].strip()
                if not nxt:
                    j += 1
                    continue
                m_hint = num_item_re.match(nxt)
                if not m_hint:
                    break
                if detail_hint_re.match(m_hint.group(1).strip()):
                    has_detail_hint = True
                break
            if has_detail_hint:
                if out and out[-1].strip():
                    out.append("")
                out.append(f"{brand_idx}. {item_content}")
                brand_idx += 1
                in_brand_block = True
                i += 1
                continue

        # 默认不改
        out.append(lines[i])
        in_brand_block = False
        i += 1

    # 清理多余空行
    normalized = []
    for ln in out:
        if ln == "" and normalized and normalized[-1] == "":
            continue
        normalized.append(ln)
    return '\n'.join(normalized).strip()


def md_to_html(text, section_key=None):
    if not text:
        return ""
    text = _strip_preamble(text)
    text = _clean_instructional_artifacts(text)
    if section_key == "module2_gain_loss":
        text = _normalize_gain_loss_blocks(text)
    return markdown.markdown(text, extensions=['tables', 'fenced_code', 'nl2br'])


def fmt_val(val, fmt='str'):
    if val is None:
        return "N/A"
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return "N/A"
        if fmt == 'usd':
            return f"{CURRENCY_SYMBOL}{f:,.2f}"
        elif fmt == 'km':          # K/M 单位展示（表格中 Revenue 字段使用）
            if abs(f) >= 1_000_000:
                return f"{CURRENCY_SYMBOL}{f/1_000_000:.2f}M"
            elif abs(f) >= 1_000:
                return f"{CURRENCY_SYMBOL}{f/1_000:.1f}K"
            else:
                return f"{CURRENCY_SYMBOL}{f:.0f}"
        elif fmt == 'pct':
            return f"{f:.2f}%"
        elif fmt == 'ppt':
            return f"{f:+.2f}"
        elif fmt == 'rating':
            return f"{f:.2f}"
        elif fmt == 'int':
            return f"{int(f):,}"
        else:
            return str(val)
    except (TypeError, ValueError):
        return str(val) if val is not None else "N/A"


def build_top20_table_html(cleaned_dir, suffix=""):
    """直接从 module2_brand_landscape{suffix}.json 生成完整 20 行品牌对比表格。"""
    json_path = os.path.join(cleaned_dir, f'module2_brand_landscape{suffix}.json')
    if not os.path.exists(json_path):
        return ""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    rows = data.get('top20_comparative', [])
    if not rows:
        return ""

    header = """<table>
  <thead>
    <tr>
      <th>Rank</th><th>Brand</th><th>Revenue (Last 12M)</th>
      <th>Revenue Share</th><th>ASP</th><th>Ratings</th>
      <th>ASINs</th><th>Revenue Growth (YoY)</th>
      <th>Share Change</th><th>Rank Change</th>
    </tr>
  </thead>
  <tbody>
"""
    body = ""
    for r in rows:
        rank_last   = fmt_val(r.get('Rank_Last12'), 'int')
        brand       = r.get('Brand', 'N/A')
        rev_last    = fmt_val(r.get('Total Revenue'), 'km')
        share_last  = fmt_val(r.get('Revenue_Share'), 'pct')
        asp         = fmt_val(r.get('ASP'), 'usd')
        ratings     = fmt_val(r.get('Ratings'), 'rating')
        asins       = fmt_val(r.get('ASINs'), 'int')
        rev_growth  = fmt_val(r.get('Revenue_Change_pct'), 'pct')
        share_change = fmt_val(r.get('Share_Change'), 'ppt')
        rc_raw = r.get('Rank_Change')
        if rc_raw is None:
            rank_change = "N/A"
        else:
            try:
                rc = float(rc_raw)
                if math.isnan(rc) or math.isinf(rc):
                    rank_change = "N/A"
                elif rc > 0:
                    rank_change = f'<span class="up">▲{int(rc)}</span>'
                elif rc < 0:
                    rank_change = f'<span class="down">▼{int(abs(rc))}</span>'
                else:
                    rank_change = "—"
            except (TypeError, ValueError):
                rank_change = "N/A"

        body += f"""    <tr>
      <td class="num">{rank_last}</td>
      <td><strong>{brand}</strong></td>
      <td class="num">{rev_last}</td>
      <td class="num">{share_last}</td>
      <td class="num">{asp}</td>
      <td class="num">{ratings}</td>
      <td class="num">{asins}</td>
      <td class="num">{rev_growth}</td>
      <td class="num">{share_change}</td>
      <td class="num">{rank_change}</td>
    </tr>
"""
    return header + body + "  </tbody>\n</table>"


def build_asin_efficiency_table_html(cleaned_dir, suffix=""):
    """直接从 module6_asin_efficiency{suffix}.json 生成 Top 10 ASIN 效率表格（已筛选 Unit Sales>中位数 且 Review Count>0）。"""
    json_path = os.path.join(cleaned_dir, f'module6_asin_efficiency{suffix}.json')
    if not os.path.exists(json_path):
        return ""
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    rows = data.get('top10_efficiency', [])
    if not rows:
        return ""

    header = """<table>
  <thead>
    <tr>
      <th>Rank</th><th>ASIN</th><th>Brand</th>
      <th>Revenue (Last 12M)</th><th>Unit Sales</th>
      <th>Review Count</th><th>Efficiency Score</th>
    </tr>
  </thead>
  <tbody>
"""
    body = ""
    for i, r in enumerate(rows, 1):
        asin    = r.get('ASIN', 'N/A')
        brand   = r.get('Brand', 'N/A')
        rev     = fmt_val(r.get('Total Revenue'), 'km')
        sales   = fmt_val(r.get('Unit Sales'), 'int')
        reviews = fmt_val(r.get('Review Count'), 'int')
        eff     = fmt_val(r.get('Efficiency_Score'), 'rating')
        body += f"""    <tr>
      <td class="num">{i}</td>
      <td><code>{asin}</code></td>
      <td><strong>{brand}</strong></td>
      <td class="num">{rev}</td>
      <td class="num">{sales}</td>
      <td class="num">{reviews}</td>
      <td class="num eff-score"><strong>{eff}</strong></td>
    </tr>
"""
    return header + body + "  </tbody>\n</table>"


# ==================== HTML Report Builder ====================

CSS = """
/* ===== Reset & Base ===== */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: "Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  background: #F8FAFC;
  color: #0F172A;
  font-size: 15px;
  line-height: 1.65;
}

/* ===== Layout ===== */
.page-header {
  background: #FFFFFF;
  border-bottom: 3px solid #1D4ED8;
  padding: 28px 48px 24px;
  display: flex;
  align-items: flex-end;
  gap: 16px;
}
.page-header .header-accent {
  display: inline-block;
  width: 6px;
  height: 40px;
  background: linear-gradient(180deg, #1D4ED8 0%, #14B8A6 100%);
  border-radius: 3px;
  flex-shrink: 0;
}
.page-header h1 {
  font-size: 22px;
  font-weight: 700;
  color: #0F172A;
  line-height: 1.3;
}
.page-header .subtitle {
  font-size: 13px;
  color: #64748B;
  margin-top: 4px;
}

.layout-wrapper {
  display: flex;
  max-width: 1360px;
  margin: 0 auto;
  padding: 32px 24px 64px;
  gap: 28px;
}

/* ===== Sidebar Nav ===== */
.nav-sidebar {
  position: sticky;
  top: 24px;
  align-self: flex-start;
  width: 220px;
  flex-shrink: 0;
  background: #FFFFFF;
  border: 1px solid #E2E8F0;
  border-radius: 14px;
  padding: 16px 0;
  box-shadow: 0 2px 8px rgba(15,23,42,0.04);
  max-height: calc(100vh - 48px);
  overflow-y: auto;
}
.nav-sidebar .nav-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #94A3B8;
  text-transform: uppercase;
  padding: 0 18px 8px;
}
.nav-item {
  display: block;
  padding: 9px 18px;
  text-decoration: none;
  color: #475569;
  font-size: 13px;
  border-left: 3px solid transparent;
  transition: all 0.15s;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nav-item:hover {
  color: #1D4ED8;
  background: #EFF6FF;
  border-left-color: #1D4ED8;
}

/* ===== Main Content ===== */
.main-content { flex: 1; min-width: 0; }

/* ===== Section Card ===== */
.report-section {
  background: #FFFFFF;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(15,23,42,0.06);
  padding: 32px;
  margin-bottom: 28px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 28px;
  padding-bottom: 16px;
  border-bottom: 1px solid #E2E8F0;
}
.section-accent {
  width: 4px;
  height: 28px;
  background: #1D4ED8;
  border-radius: 2px;
  flex-shrink: 0;
}
.section-title-wrap { display: flex; flex-direction: column; gap: 2px; }
.section-title {
  font-size: 17px;
  font-weight: 700;
  color: #0F172A;
}
.section-en {
  font-size: 12px;
  color: #64748B;
  font-weight: 400;
}

/* ===== Chart Area (上方) ===== */
.chart-area {
  margin-bottom: 24px;
}
.chart-area.multi-chart {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.chart-card {
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 12px;
  padding: 20px 20px 16px;
}
.chart-card-title {
  font-size: 12px;
  font-weight: 600;
  color: #64748B;
  text-align: center;
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.chart-img { width: 100%; height: auto; border-radius: 6px; display: block; }

/* ===== Insight Area (下方) ===== */
.insight-card {
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 12px;
  padding: 24px 28px;
}
.insight-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #1D4ED8;
  text-transform: uppercase;
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.insight-label::before {
  content: '';
  display: inline-block;
  width: 20px;
  height: 2px;
  background: #1D4ED8;
  border-radius: 1px;
}
.analysis-content { color: #0F172A; font-size: 14.5px; line-height: 1.75; }
.analysis-content h3 {
  font-size: 14px;
  font-weight: 700;
  color: #1D4ED8;
  margin: 16px 0 8px;
}
.analysis-content h3:first-child { margin-top: 0; }
.analysis-content p { margin-bottom: 10px; }
.analysis-content ul, .analysis-content ol {
  padding-left: 20px;
  margin-bottom: 10px;
}
.analysis-content li { margin-bottom: 4px; }
.analysis-content strong { color: #0F172A; }

/* ===== Executive Summary ===== */
.exec-card {
  background: linear-gradient(135deg, #EFF6FF 0%, #F0FDFA 100%);
  border: 1px solid #BFDBFE;
  border-radius: 12px;
  padding: 28px 32px;
}
.exec-card .analysis-content h3 { color: #1D4ED8; }

/* ===== Table ===== */
.table-wrapper {
  overflow-x: auto;
  border-radius: 10px;
  border: 1px solid #E2E8F0;
  margin-bottom: 20px;
}
.table-wrapper table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
}
.table-wrapper thead th {
  background: #F1F5F9;
  color: #475569;
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  padding: 12px 14px;
  border-bottom: 2px solid #E2E8F0;
  text-align: left;
  white-space: nowrap;
}
.table-wrapper tbody td {
  padding: 11px 14px;
  border-bottom: 1px solid #F1F5F9;
  color: #0F172A;
  vertical-align: middle;
}
.table-wrapper tbody tr:last-child td { border-bottom: none; }
.table-wrapper tbody tr:hover td { background: #F8FAFC; }
.table-wrapper td.num { font-variant-numeric: tabular-nums; color: #475569; }
.table-wrapper td.eff-score strong { color: #1D4ED8; }
.table-wrapper code {
  background: #E2E8F0;
  padding: 2px 7px;
  border-radius: 4px;
  font-size: 11.5px;
  color: #0F172A;
}
.table-wrapper .up   { color: #14B8A6; font-weight: 700; }
.table-wrapper .down { color: #FB7185; font-weight: 700; }

/* ===== Responsive ===== */
@media (max-width: 1100px) {
  .nav-sidebar { display: none; }
  .layout-wrapper { padding: 20px 16px; }
}
@media (max-width: 768px) {
  .chart-area.multi-chart { grid-template-columns: 1fr; }
  .report-section { padding: 20px; }
}
"""


def section_header_html(icon, title, en_title):
    return f"""<div class="section-header">
  <div class="section-accent"></div>
  <div class="section-title-wrap">
    <div class="section-title">{icon} {title}</div>
    <div class="section-en">{en_title}</div>
  </div>
</div>"""


def charts_html_block(charts_dir, chart_list):
    """生成图表区 HTML（上方）。单图全宽，多图 2 列栅格。"""
    if not chart_list:
        return ""
    cards = ""
    for chart_file, chart_title in chart_list:
        chart_path = os.path.join(charts_dir, chart_file)
        if os.path.exists(chart_path):
            b64 = img_to_base64(chart_path)
            cards += f"""<div class="chart-card">
  <div class="chart-card-title">{chart_title}</div>
  <img src="{b64}" class="chart-img" />
</div>"""
    if not cards:
        return ""
    multi_cls = " multi-chart" if len(chart_list) > 1 else ""
    return f'<div class="chart-area{multi_cls}">{cards}</div>'


def insight_html_block(content_html, label="Key Insight"):
    if not content_html:
        return ""
    return f"""<div class="insight-card">
  <div class="insight-label">{label}</div>
  <div class="analysis-content">{content_html}</div>
</div>"""


def build_html_report(analysis, charts_dir, cleaned_dir=None, excl_brand=None):
    # 若是去除头部品牌版本，在标题和 header 中注明
    title = analysis.get('title', '跨境电商市场洞察报告')
    if excl_brand:
        title = f"{title}（去除 {excl_brand}）"

    # Pre-render markdown fields
    analysis['_m2_bar_html']        = md_to_html(analysis.get('module2_analysis', ''), section_key="module2_bar")
    analysis['_m2_share_rings_html'] = md_to_html(
        analysis.get('module2_share_comparison_analysis')
        or analysis.get('module2_analysis', ''),
        section_key="module2_share_rings",
    )
    analysis['_m2_gainloss_html']   = md_to_html(analysis.get('module2_gain_loss_analysis', ''), section_key="module2_gain_loss")
    analysis['_m2_top20_html']      = md_to_html(analysis.get('module2_top20_analysis', ''), section_key="module2_top20")
    analysis['_m6_html']            = md_to_html(analysis.get('module6_analysis', ''), section_key="module6")

    # Tables from JSON (不依赖 AI)；excl_brand 时读取 _excl 版本 JSON
    _suffix = "_excl" if excl_brand else ""
    top20_table  = build_top20_table_html(cleaned_dir, _suffix)  if cleaned_dir else md_to_html(analysis.get('module2_top20_table', ''), section_key="module2_top20_table")
    asin_table   = build_asin_efficiency_table_html(cleaned_dir, _suffix) if cleaned_dir else ""

    # ===== Section definitions =====
    # layout options:
    #   "stacked"       — chart上 + insight下
    #   "chart_only"    — 仅图表，无文字
    #   "text_only"     — 仅文字（exec summary / top20 analysis）
    #   "table_text"    — 表格 + insight文字
    #   "exec"          — executive summary 特殊卡片
    sections = [
        {
            "id": "executive-summary",
            "icon": "💡", "title": "核心商业洞察与行动建议", "en": "Executive Summary",
            "layout": "exec",
            "content": md_to_html(analysis.get('executive_summary', ''), section_key="exec"),
            "charts": [],
        },
        {
            "id": "market-trends",
            "icon": "📈", "title": "市场大盘趋势", "en": "Market Trends",
            "layout": "stacked",
            "content": md_to_html(analysis.get('module1_analysis', ''), section_key="module1"),
            "charts": [("module1_market_trends.png", "Monthly Revenue / Unit Sales / ASP")],
        },
        {
            "id": "brand-top10-bar",
            "icon": "🏆", "title": "品牌竞争格局 — 份额变动", "en": "Brand Share Dynamics",
            "layout": "stacked",
            "content": analysis['_m2_bar_html'],
            "charts": [("module2_brand_top10_bar.png", "Top 10 Brands — Revenue & Market Share")],
        },
        {
            "id": "brand-share-rings",
            "icon": "⭕", "title": "品牌竞争格局 — 品牌份额对比", "en": "Brand Share Comparison",
            "layout": "stacked",
            "content": analysis['_m2_share_rings_html'],
            "charts": [("module2_brand_share_rings.png", "Brand Revenue Share — Last 12M vs Prev 12M")],
        },
        {
            "id": "brand-gain-loss",
            "icon": "🚀", "title": "品牌竞争格局 — 份额增减分析", "en": "Gaining & Declining Brands",
            "layout": "stacked",
            "content": analysis['_m2_gainloss_html'],
            "charts": [("module2_brand_gain_loss.png", "Top 5 Gaining vs Top 5 Declining")],
        },
        {
            "id": "brand-top20-table",
            "icon": "📊", "title": "品牌竞争格局 — Top 20 品牌对比", "en": "Top 20 Brand Comparison",
            "layout": "table_only",
            "content": top20_table,
            "charts": [],
        },
        {
            "id": "brand-top20-analysis",
            "icon": "🔍", "title": "品牌竞争格局 — Top 20 深度分析", "en": "Top 20 Brand Analysis",
            "layout": "text_only",
            "content": analysis['_m2_top20_html'],
            "charts": [],
        },
        {
            "id": "rating-analysis",
            "icon": "⭐", "title": "产品星级门槛分析", "en": "Rating Threshold Analysis",
            "layout": "stacked",
            "content": md_to_html(analysis.get('module3_analysis', ''), section_key="module3"),
            "charts": [("module3_rating_combined.png", "Revenue & ASIN Count by Rating Group")],
        },
        {
            "id": "price-bands",
            "icon": "💰", "title": "价位段深度剥析", "en": "Price Band Analysis",
            "layout": "stacked",
            "content": md_to_html(analysis.get('module4_analysis', ''), section_key="module4"),
            "charts": [
                ("module4_price_band_bar.png", "Price Band Revenue Comparison"),
                ("module4_price_share_change.png", "Price Band Share Change (ppt)"),
            ],
        },
        {
            "id": "listing-analysis",
            "icon": "🆕", "title": "上架分析", "en": "Listing Analysis",
            "layout": "stacked",
            "content": md_to_html(analysis.get('module5_analysis', ''), section_key="module5"),
            "charts": [
                ("module5_new_asin_trend.png", "Monthly New ASIN Trend"),
                ("module5_market_share_split.png", "Market Share Split: Top vs Non-Top"),
            ],
        },
        {
            "id": "asin-efficiency",
            "icon": "⚡", "title": "ASIN 效率分析", "en": "ASIN Efficiency Analysis",
            "layout": "table_text",
            "content": analysis['_m6_html'],
            "table": asin_table,
            "charts": [],
        },
    ]

    # ===== Build nav =====
    nav_html = '<div class="nav-label">Contents</div>\n'
    for sec in sections:
        nav_html += f'<a href="#{sec["id"]}" class="nav-item">{sec["icon"]} {sec["title"]}</a>\n'

    # ===== Build sections =====
    sections_html = ""
    for sec in sections:
        hdr = section_header_html(sec["icon"], sec["title"], sec["en"])
        ch  = charts_html_block(charts_dir, sec.get("charts", []))
        layout = sec["layout"]
        content = sec.get("content", "")
        table   = sec.get("table", "")

        if layout == "exec":
            body = f'<div class="exec-card"><div class="analysis-content">{content}</div></div>'

        elif layout == "stacked":
            body = ch + insight_html_block(content)

        elif layout == "chart_only":
            body = ch

        elif layout == "text_only":
            body = insight_html_block(content, label="Data Insight")

        elif layout == "table_only":
            # content field holds the pre-built table HTML
            body = f'<div class="table-wrapper">{content}</div>' if content else ""

        elif layout == "table_text":
            tbl_part  = f'<div class="table-wrapper">{table}</div>' if table else ""
            ins_part  = insight_html_block(content, label="Data Insight") if content else ""
            body = tbl_part + ins_part

        else:
            body = ch + insight_html_block(content)

        if not body.strip():
            continue

        sections_html += f'<section id="{sec["id"]}" class="report-section">{hdr}{body}</section>\n'

    # ===== Full HTML =====
    excl_note = f" | 已去除头部品牌：{excl_brand}" if excl_brand else ""
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
{CSS}
  </style>
</head>
<body>
  <header class="page-header">
    <div class="header-accent"></div>
    <div>
      <h1>{title}</h1>
      <div class="subtitle">Market Insight Report — Powered by market-insight skill{excl_note}</div>
    </div>
  </header>
  <div class="layout-wrapper">
    <nav class="nav-sidebar">{nav_html}</nav>
    <main class="main-content">{sections_html}</main>
  </div>
</body>
</html>"""
    return html


def main():
    """
    用法（完整版）:
        generate_report.py <analysis_json> <charts_dir> <output_path> <cleaned_dir>

    用法（去除头部品牌版）:
        generate_report.py <analysis_excl_json> <charts_excl_dir> <output_excl_path> <cleaned_dir> --excl

    说明：
      - 完整版与去除头部品牌版必须分两次调用，各自传入对应的 analysis JSON 和图表目录。
      - <analysis_excl_json>：基于 _excl 数据重新生成的 AI 分析 JSON。
      - <charts_excl_dir>：由 generate_charts.py --suffix _excl 生成的图表目录。
      - --excl 标志告知脚本从 cleaned_dir 读取 _excl 版本的数据表格 JSON。
    """
    import argparse
    parser = argparse.ArgumentParser(description='生成市场洞察报告')
    parser.add_argument('analysis_json', help='AI 分析结果 JSON 文件')
    parser.add_argument('charts_dir',    help='图表目录')
    parser.add_argument('output_path',   help='输出 HTML 路径')
    parser.add_argument('cleaned_dir',   nargs='?', default=None, help='清洗后 JSON 目录（可选）')
    parser.add_argument('--currency', default='$', help='货币符号，默认 "$"')
    parser.add_argument('--excl', action='store_true',
                        help='生成去除头部品牌版：从 cleaned_dir 读取 _excl JSON，并在标题中标注')
    args = parser.parse_args()

    global CURRENCY_SYMBOL
    CURRENCY_SYMBOL = args.currency or "$"

    with open(args.analysis_json, 'r', encoding='utf-8') as f:
        analysis = json.load(f)

    charts_dir  = args.charts_dir
    output_path = args.output_path
    cleaned_dir = args.cleaned_dir

    if args.excl:
        # 去除头部品牌版：从 meta.json 读取头部品牌名称
        excl_brand = None
        if cleaned_dir:
            meta_path = os.path.join(cleaned_dir, 'meta.json')
            if os.path.exists(meta_path):
                with open(meta_path, 'r', encoding='utf-8') as mf:
                    meta = json.load(mf)
                if meta.get('has_dominant_brand') and meta.get('dominant_brand'):
                    excl_brand = meta['dominant_brand']
        html = build_html_report(analysis, charts_dir, cleaned_dir, excl_brand=excl_brand)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✓ 去除头部品牌版报告已保存：{output_path}")
    else:
        # 完整版（含头部品牌）
        html = build_html_report(analysis, charts_dir, cleaned_dir, excl_brand=None)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"✓ 完整版报告已保存：{output_path}")


if __name__ == "__main__":
    main()
