# Market Insight — 跨境电商市场洞察报告生成器

将亚马逊等平台的原始销售数据（Excel/CSV）一键转化为包含可视化图表与 AI 深度洞察的报告，支持 HTML / PDF / PPT 三种输出格式。

---

## ⚠️ AI 助手必读：运行前必须先问用户 4 个问题

**在执行任何脚本之前，必须先向用户依次确认以下 4 个问题，全部收到答复后再运行。**

---

### 问题一：核心商业目的

> 请问本次分析的核心商业目的是什么？
>
> 1. **整体市场调研** — 全面了解市场规模、竞争格局与趋势
> 2. **新品切入市场** — 寻找市场空白，评估入场机会
> 3. **竞品防御** — 监控竞争对手动态，制定应对策略
> 4. **自定义** — 请直接描述您的具体目的

→ 对应参数：`--purpose`

---

### 问题二：价位段分组

> 如何划分价位段？请选择或提供价格分段节点：
>
> 1. **低中高端** `[20,50,100,200]` — 适用于低价消费品，分为 5 个价位段
> 2. **标准消费** `[50,100,200,400]` — 适用于普通消费电子产品
> 3. **高端产品** `[100,200,400,600]` — 适用于中高端产品或专业设备
> 4. **🤖 AI 推荐** — 先读取数据的价格分布（最小值、最大值、四分位数），由 AI 根据实际价格区间推荐最合适的分段节点（**推荐使用**）
> 5. **自定义** — 我来输入自定义的价格分组节点

**AI 推荐价位段的操作步骤（选项 4）：**
1. 先运行以下命令获取价格分布信息：
   ```bash
   python3 -c "
   import pandas as pd
   df = pd.read_excel('你的数据文件.xlsx')
   price_col = [c for c in df.columns if 'price' in c.lower() or '价格' in c][0]
   print(df[price_col].describe())
   print('四分位数:', df[price_col].quantile([0.25, 0.5, 0.75]).to_dict())
   "
   ```
2. 将输出结果发给 AI，由 AI 给出推荐分段节点

→ 对应参数：`--price-bands`

---

### 问题三：货币单位

> 数据中的价格和销售额使用什么货币单位？
>
> 1. **美元** `$`（默认）
> 2. **欧元** `€`
> 3. **英镑** `£`
> 4. **人民币** `¥`
> 5. **其他** — 请直接输入货币符号

→ 对应参数：`--currency`

---

### 问题四：输出格式

> 报告需要输出为哪种格式？
>
> 1. **HTML**（默认，推荐）— 直接在浏览器中查看，图表清晰，文件体积小
> 2. **PDF** — 适合打印或发送给他人，布局固定
> 3. **PPT** — 适合演示汇报，每个分析模块对应一张幻灯片
> 4. **全部生成** — 同时输出 HTML + PDF + PPT

→ 对应参数：`--format`（可选值：`html` / `pdf` / `ppt` / `all`，默认 `html`）

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> Python 版本要求：**3.9+**

### 2. 准备数据

将原始数据文件（`.xlsx` 或 `.csv`）放入任意目录。数据需包含以下字段：

| 字段 | 说明 |
|---|---|
| `ASIN` | 产品唯一标识符 |
| `Brand` | 品牌名称 |
| `Price` | 产品售价 |
| `Ratings` | 产品星级评分 |
| `Creation date` | 产品上架时间 |
| `Unit Sales` | 销售件数 |
| `Total Revenue` | 总销售额 |
| `时间` | 数据记录月份（YYYY-MM 格式） |
| `Review Count` | 评论数量（也支持 `review count`、`reviews` 等变体） |

> 建议数据涵盖 **24 个月**，以支持完整的同比（YOY）分析。

### 3. 一键运行

```bash
python run.py \
  --data ./data/FR10153400031.xlsx \
  --price-bands "[50,100,200,400]" \
  --purpose "整体市场调研" \
  --currency "€" \
  --format html \
  --output ./output
```

**参数说明：**

| 参数 | 必填 | 说明 | 示例 |
|---|---|---|---|
| `--data` | ✅ | 原始数据文件路径 | `./data/sales.xlsx` |
| `--price-bands` | ✅ | 价位段分组节点（JSON 数组） | `"[50,100,200,400]"` |
| `--purpose` | 可选 | 核心商业目的，影响 AI 分析视角 | `"新品切入市场评估"` |
| `--currency` | 可选 | 货币单位符号，默认 `$` | `"€"` |
| `--format` | 可选 | 输出格式：`html`/`pdf`/`ppt`/`all`，默认 `html` | `"pdf"` |
| `--output` | 可选 | 输出目录，默认 `./output` | `"./my_report"` |

### 4. 查看报告

运行完成后，在输出目录中找到：

```
output/
├── report.html          # 完整版 HTML 报告
├── report.pdf           # 完整版 PDF 报告（--format pdf/all 时生成）
├── report.pptx          # 完整版 PPT 报告（--format ppt/all 时生成）
├── report_excl.html     # 去除头部品牌版（仅当某品牌份额 > 50% 时生成）
├── report_excl.pdf      # 去除头部品牌版 PDF
├── report_excl.pptx     # 去除头部品牌版 PPT
├── cleaned/             # 阶段一：清洗后的 JSON 数据
├── charts/              # 阶段二：完整版图表
└── charts_excl/         # 阶段二：去除头部品牌版图表
```

---

## 报告包含的分析模块

| 模块 | 内容 |
|---|---|
| 核心商业洞察与行动建议 | 执行摘要，与商业目的强相关 |
| 一、市场大盘趋势 | Revenue / Unit Sales / ASP 月度三折线 |
| 二、品牌竞争格局 | 份额变动、环状图、增减分析、Top 20 对比表 |
| 三、产品星级门槛 | 各星级区间的 Revenue 分布与 ASIN 数量 |
| 四、价位段深度剥析 | 各价位段竞争强度与增长机会 |
| 五、上架分析 | 新品入场节奏与市场份额影响 |
| 六、ASIN 效率分析 | Top 10 高效率 ASIN 表格 + AI 洞察 |

---

## 头部品牌自动检测

若 Last 12M 内某品牌市场份额超过 **50%**，工具将自动：
1. 额外生成一套剔除该品牌的数据、图表与 AI 分析
2. 输出 `report_excl.*`（去除头部品牌版报告，格式与主报告相同）

两份报告的图表和 AI 分析文本完全独立，不存在内容复用。

---

## AI 配置

AI 分析默认使用**智谱 GLM-4-Flash** 模型。如需更换模型，编辑 `scripts/ai_analysis.py` 顶部的配置：

```python
ZHIPU_API_KEY = "your_api_key_here"
ZHIPU_MODEL   = "glm-4-flash"   # 可改为 glm-4、glm-4-plus 等
```

---

## 目录结构

```
market_insight/
├── run.py                  # 一键运行入口
├── requirements.txt        # Python 依赖
├── README.md               # 本文件
└── scripts/
    ├── clean_data.py       # 阶段一：数据清洗
    ├── generate_charts.py  # 阶段二：可视化图表
    ├── ai_analysis.py      # 阶段三：AI 深度分析（调用智谱 API）
    ├── generate_report.py  # 阶段四：报告整合渲染（HTML）
    └── export.py           # 阶段五：HTML 转 PDF / PPT 导出
```
