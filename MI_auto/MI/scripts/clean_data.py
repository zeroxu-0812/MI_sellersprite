#!/usr/bin/env python3
"""
数据清洗脚本 (clean_data.py)
读取原始CSV，输出6个分析模块所需的清洗后JSON数据。

新增功能：
  - 检测 Last 12M 是否有单品牌份额 > 50%
  - 若有，额外输出去除头部品牌的 "excl" 版本 JSON（文件名加 _excl 后缀）
  - ASIN 效率计算前先筛选：Unit Sales > 中位数 且 Review Count > 0
  - 输出 meta.json 记录头部品牌信息，供后续脚本判断是否生成双版本

用法:
    python clean_data.py <csv_path> <price_bands_json> <output_dir>
    python clean_data.py <csv_path> <price_bands_json> <output_dir> --currency "€"
"""

import pandas as pd
import numpy as np
import json
import os
import argparse


def _compute_all_modules(
    df,
    df_last_12,
    df_prev_12,
    time_info,
    price_bands,
    output_dir,
    suffix="",
    currency_symbol="$",
):
    """
    计算并输出全部6个模块的JSON文件。
    suffix: "" 为完整版，"_excl" 为去除头部品牌版。
    """

    def save(name, data):
        fname = f"{name}{suffix}.json"
        with open(os.path.join(output_dir, fname), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ==================== Module 1: Market Trends ====================
    monthly = df.groupby('时间').agg({
        'Total Revenue': 'sum',
        'Unit Sales': 'sum'
    }).reset_index()
    monthly['ASP'] = (monthly['Total Revenue'] / monthly['Unit Sales'].replace(0, np.nan)).round(2)
    monthly['Total Revenue'] = monthly['Total Revenue'].round(2)
    monthly['Unit Sales'] = monthly['Unit Sales'].astype(int)
    monthly['时间'] = monthly['时间'].dt.strftime('%Y-%m')

    total_rev_last_12 = round(df_last_12['Total Revenue'].sum(), 2)
    total_rev_prev_12 = round(df_prev_12['Total Revenue'].sum(), 2)
    yoy_growth = round(((total_rev_last_12 / total_rev_prev_12) - 1) * 100, 2) if total_rev_prev_12 != 0 else 0

    # Unit Sales YoY
    total_sales_last_12 = int(df_last_12['Unit Sales'].sum())
    total_sales_prev_12 = int(df_prev_12['Unit Sales'].sum())
    sales_yoy = round(((total_sales_last_12 / total_sales_prev_12) - 1) * 100, 2) if total_sales_prev_12 != 0 else 0

    save('module1_market_trends', {
        "time_info": time_info,
        "monthly_trends": monthly.to_dict(orient='records'),
        "total_revenue_last_12": total_rev_last_12,
        "total_revenue_prev_12": total_rev_prev_12,
        "yoy_growth_pct": yoy_growth,
        "total_sales_last_12": total_sales_last_12,
        "total_sales_prev_12": total_sales_prev_12,
        "sales_yoy_pct": sales_yoy,
    })

    # ==================== Module 2: Brand Landscape ====================
    def get_brand_metrics(data):
        if data.empty:
            return pd.DataFrame()
        brand_stats = data.groupby('Brand').agg({
            'Total Revenue': 'sum',
            'Unit Sales': 'sum',
            'ASIN': 'nunique',
        }).rename(columns={'ASIN': 'ASINs'})

        def weighted_rating(group):
            total_rev = group['Total Revenue'].sum()
            if total_rev == 0:
                return round(group['Ratings'].mean(), 2)
            return round((group['Ratings'] * group['Total Revenue']).sum() / total_rev, 2)

        brand_weighted_ratings = data.groupby('Brand').apply(weighted_rating, include_groups=False)
        brand_stats['Ratings'] = brand_weighted_ratings.round(2)
        brand_stats['ASP'] = (brand_stats['Total Revenue'] / brand_stats['Unit Sales'].replace(0, np.nan)).round(2)
        brand_stats['Revenue_Share'] = (brand_stats['Total Revenue'] / brand_stats['Total Revenue'].sum() * 100).round(2)
        brand_stats['Total Revenue'] = brand_stats['Total Revenue'].round(2)
        return brand_stats

    brand_last_12 = get_brand_metrics(df_last_12)
    brand_prev_12 = get_brand_metrics(df_prev_12)

    # Top 20 comparative table
    top20_last = brand_last_12.sort_values('Total Revenue', ascending=False).head(20).copy().reset_index()
    top20_last['Rank_Last12'] = range(1, len(top20_last) + 1)

    if not brand_prev_12.empty:
        prev_ranked = brand_prev_12.sort_values('Total Revenue', ascending=False).reset_index()
        prev_ranked['Rank_Prev12'] = range(1, len(prev_ranked) + 1)
        prev_renamed = prev_ranked[['Brand', 'Total Revenue', 'Revenue_Share', 'ASP', 'Ratings', 'ASINs', 'Rank_Prev12']].rename(columns={
            'Total Revenue': 'Revenue_Prev12',
            'Revenue_Share': 'Share_Prev12',
            'ASP': 'ASP_Prev12',
            'Ratings': 'Ratings_Prev12',
            'ASINs': 'ASINs_Prev12'
        })
        top20_compare = top20_last.merge(prev_renamed, on='Brand', how='left')
    else:
        top20_compare = top20_last.copy()
        for col in ['Revenue_Prev12', 'Share_Prev12', 'ASP_Prev12', 'Ratings_Prev12', 'ASINs_Prev12', 'Rank_Prev12']:
            top20_compare[col] = np.nan

    top20_compare['Revenue_Change_pct'] = ((top20_compare['Total Revenue'] / top20_compare['Revenue_Prev12'].replace(0, np.nan) - 1) * 100).round(2)
    top20_compare['Share_Change'] = (top20_compare['Revenue_Share'] - top20_compare['Share_Prev12']).round(2)
    top20_compare['Rank_Change'] = (top20_compare['Rank_Prev12'] - top20_compare['Rank_Last12'])
    top20_compare = top20_compare.replace([np.inf, -np.inf], np.nan)

    all_prev_brands = set(brand_prev_12.index) if not brand_prev_12.empty else set()
    all_last_brands = set(brand_last_12.index) if not brand_last_12.empty else set()
    new_brands = sorted(list(all_last_brands - all_prev_brands))[:20]
    exited_brands = sorted(list(all_prev_brands - all_last_brands))[:20]

    cr3_last = round(brand_last_12.sort_values('Total Revenue', ascending=False).head(3)['Revenue_Share'].sum(), 2) if not brand_last_12.empty else 0
    cr3_prev = round(brand_prev_12.sort_values('Total Revenue', ascending=False).head(3)['Revenue_Share'].sum(), 2) if not brand_prev_12.empty else 0

    top10_last = brand_last_12.sort_values('Total Revenue', ascending=False).head(10).reset_index()
    top10_prev_for_last = brand_prev_12.reset_index() if not brand_prev_12.empty else pd.DataFrame(columns=['Brand', 'Total Revenue', 'Revenue_Share'])
    top10_compare_chart = top10_last[['Brand', 'Total Revenue', 'Revenue_Share']].merge(
        top10_prev_for_last[['Brand', 'Total Revenue', 'Revenue_Share']],
        on='Brand', how='left', suffixes=('_Last12', '_Prev12')
    ).fillna(0)

    def get_ring_data(brand_metrics):
        if brand_metrics.empty: return []
        sorted_brands = brand_metrics.sort_values('Total Revenue', ascending=False)
        top_5 = sorted_brands.head(5).copy()
        others_share = sorted_brands.iloc[5:]['Revenue_Share'].sum()
        res = top_5[['Revenue_Share']].reset_index().to_dict(orient='records')
        res.append({'Brand': 'Others', 'Revenue_Share': round(others_share, 2)})
        return res

    brand_share_ring = {
        "last_12m": get_ring_data(brand_last_12),
        "prev_12m": get_ring_data(brand_prev_12)
    }

    all_brands_merged = brand_last_12[['Revenue_Share']].join(
        brand_prev_12[['Revenue_Share']], how='outer', lsuffix='_Last12', rsuffix='_Prev12'
    ).fillna(0)
    all_brands_merged['Share_Change'] = (all_brands_merged['Revenue_Share_Last12'] - all_brands_merged['Revenue_Share_Prev12']).round(2)
    top5_gaining  = all_brands_merged.sort_values('Share_Change', ascending=False).head(5).reset_index()
    top5_declining = all_brands_merged.sort_values('Share_Change', ascending=True).head(5).reset_index()

    save('module2_brand_landscape', {
        "time_info": time_info,
        "top20_comparative": top20_compare.where(top20_compare.notna(), None).to_dict(orient='records'),
        "top10_compare_chart": top10_compare_chart.to_dict(orient='records'),
        "brand_share_ring": brand_share_ring,
        "top5_gaining": top5_gaining.to_dict(orient='records'),
        "top5_declining": top5_declining.to_dict(orient='records'),
        "new_brands": new_brands,
        "exited_brands": exited_brands,
        "cr3_last12_pct": cr3_last,
        "cr3_prev12_pct": cr3_prev,
        "cr3_change": round(cr3_last - cr3_prev, 2)
    })

    # ==================== Module 3: Rating Distribution ====================
    bins   = [0, 3.5, 3.75, 4.0, 4.25, 4.5, 4.75, 5.01]
    labels = ['<3.5', '3.5-3.75', '3.75-4.0', '4.0-4.25', '4.25-4.5', '4.5-4.75', '4.75-5.0']
    df_last_12_r = df_last_12.copy()
    df_last_12_r['Rating_Group'] = pd.cut(df_last_12_r['Ratings'], bins=bins, labels=labels, right=False)
    rating_dist = df_last_12_r.groupby('Rating_Group', observed=False).agg({
        'Total Revenue': 'sum', 'ASIN': 'nunique'
    }).rename(columns={'ASIN': 'ASINs'})
    rating_dist['Revenue_Share_pct'] = (rating_dist['Total Revenue'] / rating_dist['Total Revenue'].sum() * 100).round(2)
    rating_dist['Total Revenue'] = rating_dist['Total Revenue'].round(2)
    rating_dist = rating_dist.reset_index()
    rating_dist.columns = ['Rating_Group', 'Total_Revenue', 'ASINs', 'Revenue_Share_pct']

    save('module3_rating_distribution', {
        "time_info": time_info,
        "rating_distribution": rating_dist.to_dict(orient='records')
    })

    # ==================== Module 4: Price Band Analysis ====================
    currency_symbol = currency_symbol or "$"
    p_bins   = [0] + price_bands + [float('inf')]
    p_labels = []

    def fmt_band_value(v):
        if isinstance(v, (int, np.integer)):
            return str(int(v))
        if isinstance(v, float):
            return str(int(v)) if v.is_integer() else str(v).rstrip('0').rstrip('.')
        return str(v)

    for i in range(len(p_bins) - 1):
        left = fmt_band_value(p_bins[i])
        if p_bins[i + 1] == float('inf'):
            p_labels.append(f"{currency_symbol}{left}+")
        else:
            right = fmt_band_value(p_bins[i + 1])
            p_labels.append(f"{currency_symbol}{left}-{right}")

    df_last_12_p = df_last_12.copy()
    df_prev_12_p = df_prev_12.copy()
    df_last_12_p['Price_Group'] = pd.cut(df_last_12_p['Price'], bins=p_bins, labels=p_labels)
    df_prev_12_p['Price_Group'] = pd.cut(df_prev_12_p['Price'], bins=p_bins, labels=p_labels)

    def agg_price(data):
        g = data.groupby('Price_Group', observed=False).agg({
            'Total Revenue': 'sum', 'Unit Sales': 'sum', 'ASIN': 'nunique'
        }).rename(columns={'ASIN': 'ASINs'})
        g['ASP'] = (g['Total Revenue'] / g['Unit Sales'].replace(0, np.nan)).round(2)
        g['Revenue_Share_pct'] = (g['Total Revenue'] / g['Total Revenue'].sum() * 100).round(2)
        g['Total Revenue'] = g['Total Revenue'].round(2)
        return g

    price_last = agg_price(df_last_12_p)
    price_prev = agg_price(df_prev_12_p)

    price_merged = price_last[['Total Revenue', 'Revenue_Share_pct', 'ASP', 'ASINs']].rename(columns={
        'Total Revenue': 'Revenue_Last12', 'Revenue_Share_pct': 'Share_Last12',
        'ASP': 'ASP_Last12', 'ASINs': 'ASINs_Last12'
    }).join(price_prev[['Total Revenue', 'Revenue_Share_pct', 'ASP', 'ASINs']].rename(columns={
        'Total Revenue': 'Revenue_Prev12', 'Revenue_Share_pct': 'Share_Prev12',
        'ASP': 'ASP_Prev12', 'ASINs': 'ASINs_Prev12'
    }))
    price_merged['Revenue_Growth_pct'] = ((price_merged['Revenue_Last12'] / price_merged['Revenue_Prev12'].replace(0, np.nan) - 1) * 100).round(2)
    price_merged['Share_Change'] = (price_merged['Share_Last12'] - price_merged['Share_Prev12']).round(2)
    price_merged = price_merged.reset_index()

    save('module4_price_bands', {
        "time_info": time_info,
        "price_band_comparison": price_merged.to_dict(orient='records')
    })

    # ==================== Module 5: Listing Analysis ====================
    new_asin_monthly = df.groupby('Creation_YM').agg({'ASIN': 'nunique'}).reset_index().rename(
        columns={'Creation_YM': 'Month', 'ASIN': 'New_ASINs'})
    new_product_threshold = df['时间'].max() - pd.DateOffset(months=5)
    df_new_products = df_last_12[df_last_12['Creation date'] >= new_product_threshold].copy()

    new_product_rev_last_month = df_new_products[df_new_products['时间'] == df['时间'].max()]['Total Revenue'].sum()
    total_rev_last_month = df_last_12[df_last_12['时间'] == df['时间'].max()]['Total Revenue'].sum()
    new_product_rev_pct = round(new_product_rev_last_month / total_rev_last_month * 100, 2) if total_rev_last_month != 0 else 0

    top_10_brands = list(brand_last_12.sort_values('Total Revenue', ascending=False).head(10).index)

    def get_share_split(data, top_brands):
        if data.empty: return 0, 0
        total = data['Total Revenue'].sum()
        if total == 0:  # 该子集（如新品）均无销量估算→无收入可分，避免 0/0=nan
            return 0, 0
        top_rev = data[data['Brand'].isin(top_brands)]['Total Revenue'].sum()
        top_share = round(top_rev / total * 100, 2)
        return top_share, round(100 - top_share, 2)

    top_share_total, non_top_share_total = get_share_split(df_last_12, top_10_brands)
    top_share_new, non_top_share_new = get_share_split(df_new_products, top_10_brands)

    save('module5_listing_analysis', {
        "time_info": time_info,
        "monthly_new_asins": new_asin_monthly.tail(24).to_dict(orient='records'),
        "new_product_revenue_pct_last_month": new_product_rev_pct,
        "market_share_split": {
            "top_share_total": top_share_total,
            "non_top_share_total": non_top_share_total,
            "top_share_new": top_share_new,
            "non_top_share_new": non_top_share_new
        }
    })

    # ==================== Module 6: ASIN Efficiency ====================
    # 筛选条件：Unit Sales > 中位数 且 Review Count > 0
    asin_stats = df_last_12.groupby(['ASIN', 'Brand']).agg({
        'Total Revenue': 'sum',
        'Unit Sales': 'sum',
        'Review Count': 'max'
    }).reset_index()

    sales_median = asin_stats['Unit Sales'].median()
    asin_filtered = asin_stats[
        (asin_stats['Unit Sales'] > sales_median) &
        (asin_stats['Review Count'] > 0)
    ].copy()

    # Efficiency Score = Unit Sales / Review Count（review count已>0，无需+1）
    asin_filtered['Efficiency_Score'] = (asin_filtered['Unit Sales'] / asin_filtered['Review Count']).round(2)
    top10_eff = asin_filtered.sort_values('Efficiency_Score', ascending=False).head(10)

    save('module6_asin_efficiency', {
        "time_info": time_info,
        "filter_info": {
            "sales_median_threshold": round(float(sales_median), 1),
            "filter_desc": f"Unit Sales > {sales_median:.0f}（中位数）且 Review Count > 0"
        },
        "top10_efficiency": top10_eff.to_dict(orient='records')
    })


def clean_and_split(csv_path, price_bands, output_dir, currency_symbol="$"):
    """主入口：清洗数据，检测头部品牌，输出完整版（及可选的去除头部版）JSON。"""

    os.makedirs(output_dir, exist_ok=True)

    # ==================== Load & Basic Clean ====================
    if csv_path.lower().endswith(('.xlsx', '.xls')):
        df = pd.read_excel(csv_path)
    else:
        # 尝试 utf-8，失败则降级到 latin-1
        try:
            df = pd.read_csv(csv_path, encoding='utf-8')
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding='latin-1')
    df.columns = df.columns.str.strip()

    # 列名归一化：统一大小写差异（如 "Review count" → "Review Count"）
    col_rename = {c: c for c in df.columns}
    for c in df.columns:
        c_lower = c.lower()
        if c_lower == 'review count':
            col_rename[c] = 'Review Count'
        elif c_lower == 'review':
            col_rename[c] = 'Review Count'
        elif c_lower == 'reviews':
            col_rename[c] = 'Review Count'
        elif c_lower == 'unit sales':
            col_rename[c] = 'Unit Sales'
        elif c_lower == 'total revenue':
            col_rename[c] = 'Total Revenue'
    df = df.rename(columns=col_rename)

    # 数値字段清洗：去除千位分隔符，强制转为数値
    for col in ['Total Revenue', 'Unit Sales', 'Price', 'Ratings', 'Review Count']:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(',', '', regex=False).str.replace('-', '', regex=False).str.strip(),
                errors='coerce'
            )

    df['Creation date'] = pd.to_datetime(df['Creation date'], format='mixed', dayfirst=False)
    df['Creation_YM'] = df['Creation date'].dt.to_period('M').astype(str)
    df['时间'] = pd.to_datetime(df['时间'])
    df['ASP'] = (df['Total Revenue'] / df['Unit Sales'].replace(0, np.nan)).round(2)
    df = df.sort_values('时间').reset_index(drop=True)
    df['Brand'] = df['Brand'].fillna('Unknown')

    if 'Review Count' not in df.columns:
        df['Review Count'] = 0

    # ==================== Time Split ====================
    max_date = df['时间'].max()
    latest_month_end = max_date + pd.offsets.MonthEnd(0)
    last_12_start = (latest_month_end - pd.DateOffset(months=11)) - pd.offsets.MonthBegin(1)
    prev_12_end = last_12_start - pd.Timedelta(days=1)
    prev_12_start = (prev_12_end - pd.DateOffset(months=11)) - pd.offsets.MonthBegin(1)

    df_last_12 = df[(df['时间'] >= last_12_start) & (df['时间'] <= latest_month_end)].copy()
    df_prev_12 = df[(df['时间'] >= prev_12_start) & (df['时间'] <= prev_12_end)].copy()

    time_info = {
        "max_date": str(max_date.date()),
        "last_12_range": f"{last_12_start.strftime('%Y/%m')} ~ {latest_month_end.strftime('%Y/%m')}",
        "prev_12_range": f"{prev_12_start.strftime('%Y/%m')} ~ {prev_12_end.strftime('%Y/%m')}",
        "last_12_start": str(last_12_start.date()),
        "prev_12_start": str(prev_12_start.date()),
    }

    # ==================== 头部品牌检测（Last 12M 份额 > 50%）====================
    brand_rev_last = df_last_12.groupby('Brand')['Total Revenue'].sum()
    total_rev = brand_rev_last.sum()
    brand_share = (brand_rev_last / total_rev * 100).round(2) if total_rev > 0 else brand_rev_last * 0

    dominant_brand = None
    dominant_share = 0.0
    if not brand_share.empty:
        top_brand = brand_share.idxmax()
        top_share = float(brand_share.max())
        if top_share > 50.0:
            dominant_brand = top_brand
            dominant_share = top_share

    # 写入 meta.json
    meta = {
        "has_dominant_brand": dominant_brand is not None,
        "dominant_brand": dominant_brand,
        "dominant_brand_share_pct": dominant_share,
        "time_info": time_info,
        "currency_symbol": currency_symbol or "$",
    }
    with open(os.path.join(output_dir, 'meta.json'), 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    # ==================== 完整版 JSON ====================
    _compute_all_modules(
        df,
        df_last_12,
        df_prev_12,
        time_info,
        price_bands,
        output_dir,
        suffix="",
        currency_symbol=currency_symbol,
    )

    # ==================== 去除头部品牌版 JSON（仅在检测到时输出）====================
    if dominant_brand is not None:
        print(f"  [检测] 头部品牌 '{dominant_brand}' 份额 {dominant_share:.2f}% > 50%，将额外生成去除头部版本")
        df_excl       = df[df['Brand'] != dominant_brand].copy()
        df_last_excl  = df_last_12[df_last_12['Brand'] != dominant_brand].copy()
        df_prev_excl  = df_prev_12[df_prev_12['Brand'] != dominant_brand].copy()
        _compute_all_modules(
            df_excl,
            df_last_excl,
            df_prev_excl,
            time_info,
            price_bands,
            output_dir,
            suffix="_excl",
            currency_symbol=currency_symbol,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据清洗并生成6个模块分析JSON")
    parser.add_argument("csv_path", help="原始数据文件路径（.xlsx/.csv）")
    parser.add_argument("price_bands_json", help='价位段 JSON，例如 "[50,100,200,400]"')
    parser.add_argument("output_dir", help="输出目录")
    parser.add_argument("--currency", default="$", help='货币符号，默认 "$"')
    args = parser.parse_args()

    clean_and_split(
        args.csv_path,
        json.loads(args.price_bands_json),
        args.output_dir,
        currency_symbol=args.currency,
    )
