# MI-auto 运行说明

MI-auto 现在只有一个本地流程:

- `MI/`:读取整理好的 Excel/CSV,生成 Market Insight 报告(HTML / PDF / PPT)。

源数据需要手动准备好(符合下方字段要求的 `.xlsx` 或 `.csv`),直接传给 `MI/run.py` 即可。

---

## 一、输入数据要求

准备一份符合以下字段的 `.xlsx` 或 `.csv`,放入任意目录:

| 字段 | 说明 |
|---|---|
| `ASIN` | 产品唯一标识符 |
| `Brand` | 品牌名称 |
| `Price` | 产品售价 |
| `Ratings` | 产品星级评分 |
| `Creation date` | 产品上架时间 |
| `Unit Sales` | 销售件数 |
| `Total Revenue` | 总销售额 |
| `时间` | 数据记录月份,建议为 `YYYY-MM` |
| `Review Count` | 评论数量,也支持 `review count`、`review`、`reviews` 等变体 |

建议数据覆盖 **24 个月**,以支持完整的同比(Last 12M vs Prev 12M)分析。

---

## 二、安装依赖

```bash
cd /Users/haiyi/Desktop/project/MI_auto/MI
python3 -m pip install -r requirements.txt
```

Python 版本建议 3.9+。

---

## 三、完整运行流程:Excel/CSV 生成 HTML 报告

```bash
cd /Users/haiyi/Desktop/project/MI_auto/MI

python3 run.py \
  --data "/你的数据文件.xlsx" \
  --price-bands '[50,100,200,400]' \
  --purpose "整体市场调研" \
  --currency "$" \
  --format html \
  --output ./output
```

报告会生成到:

```text
/Users/haiyi/Desktop/project/MI_auto/MI/output/report_YYYYMMDD_HHMMSS.html
```

打开最新 HTML 报告:

```bash
open "$(ls -t /Users/haiyi/Desktop/project/MI_auto/MI/output/report_*.html | head -1)"
```

> Mac 终端里也可以在输入 `--data ` 后把文件拖进终端,自动填入完整路径。

---

## 四、运行前需要确认的 4 个参数

### 1. 核心商业目的:`--purpose`

常用选项:

- `整体市场调研`:了解市场规模、竞争格局与趋势。
- `新品切入市场`:寻找市场空白,评估入场机会。
- `竞品防御`:监控竞争对手动态,制定应对策略。
- 自定义:直接写具体分析目的。

### 2. 价位段分组:`--price-bands`

示例:

```bash
--price-bands '[50,100,200,400]'
```

常用预设:

| 场景 | 参数 |
|---|---|
| 低中高端 | `[20,50,100,200]` |
| 标准消费 | `[50,100,200,400]` |
| 高端产品 | `[100,200,400,600]` |

如果不确定价位段,可以先查看价格分布:

```bash
python3 -c "
import pandas as pd
df = pd.read_excel('/你的数据文件.xlsx')
price_col = [c for c in df.columns if 'price' in c.lower() or '价格' in c][0]
print(df[price_col].describe())
print('四分位数:', df[price_col].quantile([0.25, 0.5, 0.75]).to_dict())
"
```

将四分位数结果发给 AI,由 AI 推荐合适的分段节点。

### 3. 货币单位:`--currency`

示例:

```bash
--currency "$"
--currency "€"
--currency "£"
--currency "¥"
```

### 4. 输出格式:`--format`

可选值:

| 参数 | 输出 |
|---|---|
| `html` | HTML 报告,默认推荐 |
| `pdf` | HTML + PDF |
| `ppt` | HTML + PPT |
| `all` | HTML + PDF + PPT |

---

## 五、常用命令速查

```bash
cd /Users/haiyi/Desktop/project/MI_auto/MI
python3 run.py \
  --data "/path/to/data.xlsx" \
  --price-bands '[50,100,200,400]' \
  --purpose "整体市场调研" \
  --currency "$" \
  --format html \
  --output ./output
open "$(ls -t ./output/report_*.html | head -1)"
```

---

## 六、输出文件说明

`MI/output/` 中常见输出:

| 文件/目录 | 说明 |
|---|---|
| `report_*.html` | 完整版 HTML 报告 |
| `report_*.pdf` | PDF 报告,使用 `--format pdf/all` 时生成 |
| `report_*.pptx` | PPT 报告,使用 `--format ppt/all` 时生成 |
| `report_excl_*.html` | 去除头部品牌版报告,仅当某品牌 Last 12M 份额 > 50% 时生成 |
| `cleaned/` | 清洗后的 JSON 数据(6 个分析模块) |
| `charts/` | 完整版图表 |
| `charts_excl/` | 去除头部品牌版图表 |

报告含 6 个分析模块:市场大盘趋势、品牌竞争格局、星级门槛、价位段、上架分析、ASIN 效率。当 Last 12M 某品牌份额 > 50% 时,会额外生成一套独立的"去除头部品牌版"报告(`report_excl_*`)。

---

## 七、当前限制

- `MI/run.py` 的 `--data` 只能是整理好的 `.xlsx` 或 `.csv`,不直接支持 ZIP。
- 同比分析要求数据覆盖约 24 个月;不足时同比相关列会为空。
- AI 分析默认配置在 `MI/scripts/ai_analysis.py` 中维护(默认使用智谱 GLM-4-Flash)。
