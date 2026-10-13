#!/usr/bin/env python3
"""
可视化脚本 (generate_charts.py)
读取清洗后的6个模块JSON数据，为每个模块生成图表PNG。
配色规范：深蓝 + Slate灰 + 青绿点缀（咨询报告 / BI Dashboard 风格）
"""

import json
import os
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np

# ==================== Color System ====================
# 主色板
C = {
    'primary':    '#1D4ED8',   # Primary Blue — 主标题、主趋势线、主柱
    'deep_navy':  '#0F172A',   # Deep Navy — 大标题、核心图表主色
    'blue2':      '#3B82F6',   # Secondary Blue — 对比维度柱
    'teal':       '#14B8A6',   # Teal Accent — 增长、机会、正向
    'amber':      '#F59E0B',   # Amber — 提醒、观察点
    'rose':       '#FB7185',   # Rose — 负向数据
    'slate_line': '#94A3B8',   # 辅助线、次要趋势
    'slate_weak': '#CBD5E1',   # 弱化柱 / 历史周期
    'border':     '#E2E8F0',   # 边框
    'bg_chart':   '#F8FAFC',   # 图表面板背景
    'text_main':  '#0F172A',
    'text_sub':   '#475569',
    'text_note':  '#64748B',
}

# 品牌定序色（Top 10 品牌，Others 固定用 #E2E8F0）
BRAND_PALETTE = [
    '#1D4ED8', '#3B82F6', '#14B8A6', '#0F766E',
    '#F59E0B', '#F97316', '#8B5CF6', '#64748B',
    '#94A3B8', '#CBD5E1',
]
OTHERS_COLOR = '#E2E8F0'
CURRENCY_SYMBOL = '$'

def get_brand_color_map(brands_ordered):
    """
    为品牌列表建立稳定颜色映射（按首次出现顺序分配 BRAND_PALETTE）。
    'Others' 固定使用 OTHERS_COLOR。
    """
    cmap = {}
    idx = 0
    for b in brands_ordered:
        if b == 'Others':
            cmap[b] = OTHERS_COLOR
        elif b not in cmap:
            cmap[b] = BRAND_PALETTE[idx % len(BRAND_PALETTE)]
            idx += 1
    return cmap

def setup_fonts():
    font_candidates = ['WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'DejaVu Sans']
    for font in font_candidates:
        try:
            matplotlib.font_manager.findfont(font, fallback_to_default=False)
            plt.rcParams['font.sans-serif'] = [font] + plt.rcParams.get('font.sans-serif', [])
            plt.rcParams['axes.unicode_minus'] = False
            return
        except Exception:
            continue
    plt.rcParams['axes.unicode_minus'] = False

setup_fonts()

# 全局 rcParams — 统一图表底色与网格风格
plt.rcParams.update({
    'figure.facecolor':  C['bg_chart'],
    'axes.facecolor':    C['bg_chart'],
    'axes.edgecolor':    C['border'],
    'axes.labelcolor':   C['text_sub'],
    'axes.titlecolor':   C['text_main'],
    'xtick.color':       C['text_note'],
    'ytick.color':       C['text_note'],
    'grid.color':        C['border'],
    'grid.linewidth':    0.8,
    'axes.grid':         True,
    'axes.spines.top':   False,
    'axes.spines.right': False,
})

def format_revenue(val):
    """将数值格式化为 K/M 单位字符串（用于图表标签和坐标轴）。"""
    if val is None or (isinstance(val, float) and (np.isnan(val) or np.isinf(val))):
        return "N/A"
    val = float(val)
    if abs(val) >= 1_000_000:
        return f"{CURRENCY_SYMBOL}{val/1_000_000:.1f}M"
    elif abs(val) >= 1_000:
        return f"{CURRENCY_SYMBOL}{val/1_000:.1f}K"
    else:
        return f"{CURRENCY_SYMBOL}{val:.0f}"

def save_fig(fig, path, dpi=150):
    fig.tight_layout(pad=2.0)
    fig.savefig(path, dpi=dpi, bbox_inches='tight',
                facecolor=C['bg_chart'], edgecolor='none')
    plt.close(fig)


# ==================== Module 1: Market Trends ====================
def chart_module1(data, charts_dir):
    trends = data['monthly_trends']
    months  = [r['时间'] for r in trends]
    revenues = [r['Total Revenue'] for r in trends]
    asps    = [r['ASP'] for r in trends]
    sales   = [r['Unit Sales'] for r in trends]
    short_months = [m[2:] for m in months]
    x = range(len(months))

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 13), sharex=True)
    fig.suptitle('Market Trends Overview', fontsize=16, fontweight='bold',
                 color=C['deep_navy'], y=0.99)

    # Revenue
    ax1.fill_between(x, revenues, alpha=0.12, color=C['primary'])
    ax1.plot(x, revenues, color=C['primary'], linewidth=2.5, marker='o', markersize=4)
    ax1.set_ylabel('Revenue', color=C['text_sub'])
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: format_revenue(v)))
    ax1.set_title('Monthly Revenue', fontsize=12, fontweight='bold',
                  color=C['text_main'], pad=8, loc='left')

    # Unit Sales
    ax2.fill_between(x, sales, alpha=0.12, color=C['teal'])
    ax2.plot(x, sales, color=C['teal'], linewidth=2.5, marker='o', markersize=4)
    ax2.set_ylabel('Unit Sales', fontsize=11, color=C['text_sub'])
    ax2.set_title('Monthly Unit Sales', fontsize=12, fontweight='bold',
                  color=C['text_main'], pad=8, loc='left')

    # ASP
    ax3.fill_between(x, asps, alpha=0.10, color=C['amber'])
    ax3.plot(x, asps, color=C['amber'], linewidth=2.5, marker='s', markersize=4)
    ax3.set_ylabel(f'ASP ({CURRENCY_SYMBOL})', fontsize=11, color=C['text_sub'])
    ax3.set_title('Monthly ASP', fontsize=12, fontweight='bold',
                  color=C['text_main'], pad=8, loc='left')
    ax3.set_xticks(list(x))
    ax3.set_xticklabels(short_months, rotation=45, ha='right', fontsize=8)

    save_fig(fig, os.path.join(charts_dir, 'module1_market_trends.png'))


# ==================== Module 2: Brand Landscape ====================
def chart_module2(data, charts_dir):
    # ---- 1. Top 10 Comparative Bar Chart ----
    top10 = data['top10_compare_chart']
    brands_raw = [r['Brand'] for r in top10]
    brand_cmap = get_brand_color_map(brands_raw)

    brands    = [b[:14] for b in brands_raw]
    rev_last  = [r['Total Revenue_Last12'] / 1_000_000 for r in top10]
    rev_prev  = [r['Total Revenue_Prev12'] / 1_000_000 for r in top10]
    share_last = [r['Revenue_Share_Last12'] for r in top10]
    share_prev = [r['Revenue_Share_Prev12'] for r in top10]

    x = np.arange(len(brands))
    width = 0.35

    fig, ax = plt.subplots(figsize=(14, 8))
    # Prev 12M — 弱化色
    rects1 = ax.bar(x - width/2, rev_prev, width, label='Prev 12M',
                    color=C['slate_weak'], alpha=0.9)
    # Last 12M — 品牌主色
    rects2 = ax.bar(x + width/2, rev_last, width, label='Last 12M',
                    color=[brand_cmap.get(b, C['primary']) for b in brands_raw])

    # Y 轴 K/M 格式
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: format_revenue(v)))

    for i, rect in enumerate(rects1):
        h = rect.get_height()
        if h > 0:
            ax.text(rect.get_x() + rect.get_width()/2., h,
                    f'{share_prev[i]:.1f}%', ha='center', va='bottom',
                    fontsize=7.5, color=C['text_note'])
    for i, rect in enumerate(rects2):
        h = rect.get_height()
        ax.text(rect.get_x() + rect.get_width()/2., h,
                f'{share_last[i]:.1f}%', ha='center', va='bottom',
                fontsize=8, fontweight='bold', color=C['text_main'])

    ax.set_ylabel('Revenue', fontsize=11, color=C['text_sub'])
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: format_revenue(v)))
    ax.set_title('Top 10 Brands — Revenue & Market Share',
                 fontsize=14, fontweight='bold', color=C['deep_navy'], pad=16, loc='left')
    ax.set_xticks(x)
    ax.set_xticklabels(brands, rotation=40, ha='right')
    ax.legend(framealpha=0.9)
    save_fig(fig, os.path.join(charts_dir, 'module2_brand_top10_bar.png'))

    # ---- 2. Brand Share Comparison Rings (Left donut + Right legend) ----
    ring_data = data['brand_share_ring']

    # 收集所有品牌（保证跨两张环图颜色一致）
    all_brands_ordered = []
    for r in ring_data.get('prev_12m', []):
        if r['Brand'] not in all_brands_ordered:
            all_brands_ordered.append(r['Brand'])
    for r in ring_data.get('last_12m', []):
        if r['Brand'] not in all_brands_ordered:
            all_brands_ordered.append(r['Brand'])
    ring_cmap = get_brand_color_map(all_brands_ordered)

    def plot_donut_with_legend(ax_donut, ax_legend, data_list, period_label, time_range,
                                cr3=None):
        labels  = [r['Brand'] for r in data_list]
        sizes   = [r['Revenue_Share'] for r in data_list]
        colors  = [ring_cmap.get(b, C['slate_weak']) for b in labels]

        if not sizes or not np.all(np.isfinite(sizes)) or all((s or 0) <= 0 for s in sizes):
            # 全零/空（该时段无品牌收入）→ 画占位符，避免 matplotlib All-zero 崩溃
            ax_donut.axis('off'); ax_legend.axis('off')
            ax_donut.text(0.5, 0.5, 'No data', ha='center', va='center',
                          fontsize=10, color=C['text_note'], transform=ax_donut.transAxes)
            ax_donut.set_title(f'{period_label}\n{time_range}',
                               fontsize=11, fontweight='bold', color=C['text_main'], pad=10)
            return

        wedges, _ = ax_donut.pie(
            sizes, colors=colors, startangle=90,
            wedgeprops=dict(width=0.45, edgecolor='white', linewidth=1.5),
            counterclock=False,
        )

        # 中心文字
        center_lines = [period_label, '']
        if cr3 is not None:
            center_lines = [f'CR3', f'{cr3:.1f}%', period_label]
        ax_donut.text(0, 0.12, center_lines[0], ha='center', va='center',
                      fontsize=10, color=C['text_note'])
        if len(center_lines) >= 2:
            ax_donut.text(0, -0.12, center_lines[1], ha='center', va='center',
                          fontsize=14, fontweight='bold', color=C['deep_navy'])
        if len(center_lines) >= 3:
            ax_donut.text(0, -0.38, center_lines[2], ha='center', va='center',
                          fontsize=8, color=C['text_note'])

        ax_donut.set_title(f'{period_label}\n{time_range}',
                           fontsize=11, fontweight='bold', color=C['text_main'], pad=10)

        # 图例（右侧）
        ax_legend.axis('off')
        legend_y = 0.95
        row_h = 0.88 / max(len(data_list), 1)
        for i, (label, size) in enumerate(zip(labels, sizes)):
            y = legend_y - i * row_h
            # 色块
            rect = mpatches.FancyBboxPatch((0.0, y - 0.03), 0.08, 0.06,
                                           boxstyle="round,pad=0.01",
                                           facecolor=ring_cmap.get(label, C['slate_weak']),
                                           edgecolor='none',
                                           transform=ax_legend.transAxes, clip_on=False)
            ax_legend.add_patch(rect)
            # 品牌名 + 份额
            ax_legend.text(0.12, y, f'{label}', fontsize=9,
                           color=C['text_main'], va='center',
                           transform=ax_legend.transAxes)
            ax_legend.text(0.98, y, f'{size:.2f}%', fontsize=9,
                           color=C['text_sub'], va='center', ha='right',
                           transform=ax_legend.transAxes)

    # 计算 CR3
    cr3_last  = data.get('cr3_last12_pct')
    cr3_prev  = data.get('cr3_prev12_pct')
    ti = data.get('time_info', {})

    # 布局：[donut_prev | legend_prev | donut_last | legend_last]
    fig, axes = plt.subplots(1, 4, figsize=(18, 8),
                             gridspec_kw={'width_ratios': [2, 1, 2, 1]})
    fig.suptitle('Brand Revenue Share Comparison — Last 12M vs Prev 12M',
                 fontsize=14, fontweight='bold', color=C['deep_navy'], y=1.01)

    plot_donut_with_legend(axes[0], axes[1],
                           ring_data.get('prev_12m', []),
                           'Prev 12M', ti.get('prev_12_range', ''), cr3=cr3_prev)
    plot_donut_with_legend(axes[2], axes[3],
                           ring_data.get('last_12m', []),
                           'Last 12M', ti.get('last_12_range', ''), cr3=cr3_last)

    save_fig(fig, os.path.join(charts_dir, 'module2_brand_share_rings.png'))

    # ---- 3. Top 5 Gaining vs Top 5 Declining ----
    gaining  = data['top5_gaining']
    declining = data['top5_declining']

    all_change = [r['Share_Change'] for r in gaining] + [r['Share_Change'] for r in declining]
    all_brands_gl = [r['Brand'][:14] for r in gaining] + [r['Brand'][:14] for r in declining]
    bar_colors = [C['teal']] * len(gaining) + [C['rose']] * len(declining)

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar(range(len(all_change)), all_change, color=bar_colors, width=0.6)
    ax.axhline(0, color=C['text_note'], linewidth=0.8)

    for bar, val in zip(bars, all_change):
        yv = bar.get_height()
        y_text = yv + 0.04 if yv >= 0 else yv - 0.04
        va = 'bottom' if yv >= 0 else 'top'
        ax.text(bar.get_x() + bar.get_width()/2, y_text,
                f'{val:+.2f}ppt', ha='center', va=va,
                fontsize=9, fontweight='bold',
                color=C['text_main'])

    ax.set_xticks(range(len(all_change)))
    ax.set_xticklabels(all_brands_gl, rotation=40, ha='right')
    ax.set_ylabel('Market Share Change (ppt)', fontsize=11, color=C['text_sub'])
    ax.set_title('Top 5 Gaining vs Top 5 Declining Brands',
                 fontsize=13, fontweight='bold', color=C['deep_navy'], pad=16, loc='left')
    ax.margins(y=0.18)

    gain_patch   = mpatches.Patch(color=C['teal'],  label='Gaining')
    decline_patch = mpatches.Patch(color=C['rose'], label='Declining')
    ax.legend(handles=[gain_patch, decline_patch], framealpha=0.9)
    save_fig(fig, os.path.join(charts_dir, 'module2_brand_gain_loss.png'))


# ==================== Module 3: Rating Distribution ====================
def chart_module3(data, charts_dir):
    dist   = data['rating_distribution']
    groups  = [r['Rating_Group'] for r in dist]
    revenues = [r['Total_Revenue'] for r in dist]
    shares  = [r['Revenue_Share_pct'] for r in dist]
    asins   = [r['ASINs'] for r in dist]
    x = np.arange(len(groups))

    # 颜色：按份额高低映射 primary / blue2 / slate_weak
    def bar_color(s):
        if s >= 30:
            return C['primary']
        elif s >= 10:
            return C['blue2']
        else:
            return C['slate_weak']
    bar_colors = [bar_color(s) for s in shares]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=False)
    fig.suptitle('Rating Distribution Overview', fontsize=15, fontweight='bold',
                 color=C['deep_navy'], y=0.99)

    ax1.bar(x, revenues, color=bar_colors, alpha=0.9, width=0.6)
    ax1.set_title('Revenue by Rating Group', fontsize=12, fontweight='bold',
                  color=C['text_main'], loc='left')
    ax1.set_ylabel(f'Revenue ({CURRENCY_SYMBOL})', color=C['text_sub'])
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: format_revenue(v)))
    ax1.set_xticks(x)
    ax1.set_xticklabels(groups, rotation=0)
    # 标注份额
    for i, (rect_x, rev, sh) in enumerate(zip(x, revenues, shares)):
        ax1.text(rect_x, rev * 1.01, f'{sh:.1f}%', ha='center', va='bottom',
                 fontsize=8.5, color=C['text_sub'])

    ax2.bar(x, asins, color=C['blue2'], alpha=0.85, width=0.6)
    ax2.set_title('ASIN Count by Rating Group', fontsize=12, fontweight='bold',
                  color=C['text_main'], loc='left')
    ax2.set_ylabel('ASIN Count', color=C['text_sub'])
    ax2.set_xticks(x)
    ax2.set_xticklabels(groups, rotation=0)

    save_fig(fig, os.path.join(charts_dir, 'module3_rating_combined.png'))


# ==================== Module 4: Price Band Analysis ====================
def chart_module4(data, charts_dir):
    bands  = data['price_band_comparison']
    groups = [r['Price_Group'] for r in bands]
    rev_last  = [r['Revenue_Last12'] for r in bands]
    rev_prev  = [r['Revenue_Prev12'] for r in bands]
    share_change = [r['Share_Change'] for r in bands]
    x = np.arange(len(groups))
    width = 0.35

    # Chart 1: Revenue Comparison
    fig1, ax1 = plt.subplots(figsize=(12, 7))
    ax1.bar(x - width/2, rev_prev, width, label='Prev 12M',
            color=C['slate_weak'], alpha=0.9)
    ax1.bar(x + width/2, rev_last, width, label='Last 12M',
            color=C['primary'])
    ax1.set_title('Price Band Revenue Comparison',
                  fontsize=14, fontweight='bold', color=C['deep_navy'], pad=16, loc='left')
    ax1.set_xticks(x)
    ax1.set_xticklabels(groups)
    ax1.set_ylabel('Revenue', color=C['text_sub'])
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: format_revenue(v)))
    ax1.legend(framealpha=0.9)
    save_fig(fig1, os.path.join(charts_dir, 'module4_price_band_bar.png'))

    # Chart 2: Share Change
    fig2, ax2 = plt.subplots(figsize=(12, 6))
    colors = [C['teal'] if v >= 0 else C['rose'] for v in share_change]
    bars = ax2.bar(groups, share_change, color=colors, alpha=0.9, width=0.5)
    ax2.axhline(0, color=C['text_note'], linewidth=0.8)
    for bar, val in zip(bars, share_change):
        yv = bar.get_height()
        y_text = yv + 0.03 if yv >= 0 else yv - 0.03
        va = 'bottom' if yv >= 0 else 'top'
        ax2.text(bar.get_x() + bar.get_width()/2, y_text,
                 f'{val:+.2f}ppt', ha='center', va=va,
                 fontsize=9.5, fontweight='bold',
                 color=C['text_main'])
    ax2.set_title('Price Band Market Share Change (ppt)',
                  fontsize=14, fontweight='bold', color=C['deep_navy'], pad=16, loc='left')
    ax2.set_ylabel('Share Change (ppt)', color=C['text_sub'])
    ax2.margins(y=0.18)
    save_fig(fig2, os.path.join(charts_dir, 'module4_price_share_change.png'))


# ==================== Module 5: Listing Analysis ====================
def chart_module5(data, charts_dir):
    # Chart 1: New ASIN Trend
    new_asins = data['monthly_new_asins']
    months = [r['Month'][2:] for r in new_asins]
    counts = [r['New_ASINs'] for r in new_asins]

    fig1, ax1 = plt.subplots(figsize=(12, 6))
    ax1.bar(months, counts, color=C['teal'], alpha=0.85, width=0.6)
    ax1.set_title('Monthly New ASIN Trend',
                  fontsize=14, fontweight='bold', color=C['deep_navy'], pad=16, loc='left')
    ax1.set_ylabel('ASIN Count', color=C['text_sub'])
    plt.setp(ax1.get_xticklabels(), rotation=45, ha='right', fontsize=8)
    save_fig(fig1, os.path.join(charts_dir, 'module5_new_asin_trend.png'))

    # Chart 2: Market Share Split — Two Donuts with legends
    split = data['market_share_split']
    donut_colors = [C['primary'], C['slate_weak']]
    labels = ['Top Brands', 'Non-Top Brands']

    fig2, axes = plt.subplots(1, 4, figsize=(16, 7),
                              gridspec_kw={'width_ratios': [2, 1, 2, 1]})
    fig2.suptitle('Market Share Split: Top Brands vs Others',
                  fontsize=14, fontweight='bold', color=C['deep_navy'], y=1.01)

    def draw_split_donut(ax_d, ax_l, vals, title):
        if not vals or not np.all(np.isfinite(vals)) or all(v <= 0 for v in vals):
            # 全零/空（如新品均无销量估算）→ 画占位符，避免 matplotlib All-zero 崩溃
            ax_d.axis('off'); ax_l.axis('off')
            ax_d.text(0.5, 0.5, 'No data', ha='center', va='center',
                      fontsize=10, color=C['text_note'], transform=ax_d.transAxes)
            ax_d.set_title(title, fontsize=11, fontweight='bold', color=C['text_main'], pad=10)
            return
        wedges, _ = ax_d.pie(
            vals, colors=donut_colors, startangle=90,
            wedgeprops=dict(width=0.42, edgecolor='white', linewidth=1.5),
            counterclock=False,
        )
        ax_d.text(0, 0, f'{vals[0]:.1f}%\nvs\n{vals[1]:.1f}%',
                  ha='center', va='center', fontsize=10,
                  color=C['deep_navy'], fontweight='bold')
        ax_d.set_title(title, fontsize=11, fontweight='bold',
                       color=C['text_main'], pad=10)
        ax_l.axis('off')
        for i, (lbl, clr) in enumerate(zip(labels, donut_colors)):
            y = 0.65 - i * 0.3
            rect = mpatches.FancyBboxPatch((0.0, y - 0.04), 0.1, 0.08,
                                           boxstyle="round,pad=0.01",
                                           facecolor=clr, edgecolor='none',
                                           transform=ax_l.transAxes, clip_on=False)
            ax_l.add_patch(rect)
            ax_l.text(0.15, y, f'{lbl}\n{vals[i]:.1f}%',
                      fontsize=9, color=C['text_main'], va='center',
                      transform=ax_l.transAxes)

    draw_split_donut(axes[0], axes[1],
                     [split['top_share_total'], split['non_top_share_total']],
                     'Total Market')
    draw_split_donut(axes[2], axes[3],
                     [split['top_share_new'], split['non_top_share_new']],
                     'New Product Market')

    save_fig(fig2, os.path.join(charts_dir, 'module5_market_share_split.png'))


def main(cleaned_dir, charts_dir, suffix="", currency="$"):
    """
    suffix: "" 为完整版，"_excl" 为去除头部品牌版。
    当 suffix="_excl" 时，优先读取 <module>_excl.json，若不存在则跳过。
    """
    global CURRENCY_SYMBOL
    CURRENCY_SYMBOL = currency

    os.makedirs(charts_dir, exist_ok=True)
    modules = [
        ('module1_market_trends',       chart_module1),
        ('module2_brand_landscape',     chart_module2),
        ('module3_rating_distribution', chart_module3),
        ('module4_price_bands',         chart_module4),
        ('module5_listing_analysis',    chart_module5),
    ]
    for module_name, func in modules:
        filename = f"{module_name}{suffix}.json"
        path = os.path.join(cleaned_dir, filename)
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            func(data, charts_dir)
            print(f"  ✓ {filename}")
        elif suffix:
            # _excl 版本 JSON 不存在时跳过（不影响完整版）
            print(f"  [跳过] {filename} 不存在")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='生成市场洞察图表')
    parser.add_argument('cleaned_dir', help='清洗后 JSON 目录')
    parser.add_argument('charts_dir',  help='图表输出目录')
    parser.add_argument('--suffix', default='', help='JSON 文件后缀，如 _excl')
    parser.add_argument('--currency', default='$', help='货币符号，默认 "$"')
    args = parser.parse_args()
    main(args.cleaned_dir, args.charts_dir, args.suffix, args.currency)
