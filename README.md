# MI_sellersprite —— 卖家精灵市场洞察管线

从卖家精灵（sellersprite）网站 API 抓取类目数据，清洗成 24 个月销量长表，生成六大模块的市场洞察 HTML 报告。

三段式管线：**采集 → 清洗 → 报告**，终端交互菜单驱动，可整跑也可单段跑。

```
选站点 + 浏品类 → 翻页抓父 ASIN → 24 月窗口清洗 → MI 引擎 → report.html
   stages/crawl.py      stages/clean.py      stages/report.py
```

## 快速开始

```bash
cd MI_sellersprite
PYTHONPATH=. MI_auto/.venv/bin/python main.py
```

> 首次运行前需在浏览器登录 [sellersprite.com](https://www.sellersprite.com) 并在 competing-lookup 页面访问一次（建立查询 session）。cookie 自动从浏览器读取到 `.superpowers/sdd/v3_cookie.txt`。

菜单：

| 选项 | 功能 |
|---|---|
| 1 | 全流程（采集 → 清洗 → 报告） |
| 2 | 仅采集 |
| 3 | 从已有数据继续（选历史 run → 清洗 + 报告） |
| 4 | 仅清洗（选历史 run） |
| 5 | 仅报告（选历史 run） |
| 6 | 刷新 cookie（从浏览器读） |
| 0 | 退出 |

## 目录结构

```
MI_sellersprite/
├── main.py                # 交互主菜单
├── run_all.py             # 共享工具：infer_crawl_date / recommend_bands / currency_for / run_mi
│                          #   （含离线 CLI：--input raw.json 旁路抓取）
├── run_dir.py             # run 目录与产物路径管理
├── category_search.py     # 类目树逐级浏览 + 关键词搜索（本地缓存过滤）
├── categories.json        # 类目名 → node 字典
├── conftest.py            # pytest sys.path 注入
├── stages/                # 三段式阶段
│   ├── crawl.py           # ① 选站点+品类 → 抓父 ASIN → raw.json / raw.xlsx
│   ├── clean.py           # ② 24 月窗口 + 9 字段 → input.xlsx
│   └── report.py          # ③ 子进程调 MI 引擎 → report_*.html
├── tests/                 # 单元 + e2e 离线测试（42 passed / 6 skipped）
├── MI_SELLERSPRITE/       # 卖家精灵网站 API 抓取层
│   ├── website_scraper.py     # competing-lookup 抓取（父 ASIN 维度 + 归并自检）
│   ├── verify_coverage.py     # 数据源完整性交叉校验
│   └── refresh_cookie.py      # 从浏览器刷新 cookie
├── MI_auto/               # MI 报告引擎（脚本不改动）
│   ├── sellersprite_to_mi.py  # raw JSON → MI 合规长表（convert_data / raw_to_xlsx）
│   ├── MI/run.py              # 报告生成入口（被 report 阶段子进程调用）
│   └── MI/scripts/            # clean_data / generate_charts / generate_report / ai_analysis / export
├── output/                # ⚠️ 每次 run 的产物（gitignored）
├── .superpowers/sdd/      # ⚠️ cookie + 探测脚本（gitignored）
└── categories_cache.json  # 类目树缓存（gitignored，运行时自动刷新）
```

## 输出产物

每次 run 在 `output/<站点>_<类目>_<时间戳>/` 下生成：

| 文件 | 说明 | 阶段 |
|---|---|---|
| `raw.json` / `raw.xlsx` | 抓取的原始数据（父 ASIN + amzUnitTrends 月销量） | 采集 |
| `crawl_meta.json` | 抓取元信息（站点 / node / 父 ASIN 数 / 归并自检结果） | 采集 |
| `input.xlsx` | 清洗后长表（24 月窗口，9 字段） | 清洗 |
| `clean_meta.json` | 清洗元信息（窗口 / 行数 / 零销量注入数） | 清洗 |
| `mi_out/report_*.html` | **最终报告**（浏览器打开） | 报告 |
| `mi_out/analysis.json` | AI 分析结论 | 报告 |
| `mi_out/cleaned/module1-6*.json` | 六模块指标数据 | 报告 |
| `mi_out/charts/*.png` | 报告图表 | 报告 |

mac 打开报告：`open output/<run 目录>/mi_out/report_*.html`

## 关键约束（重要）

- **抓取走网站 API** `www.sellersprite.com/v3/api/competing-lookup`，cookie 里的 `Sprite-X-Token`（JWT）鉴权。扩展接口（`e.sellersprite.com`）对现有账号全 403，已弃用移除。
- **严格限流 ~10 req/min**：超速静默回空（`code:OK` 但 `data:null`）。页间延时 7s；`_post_page` 对 `data:null` 按 20/40/60/60s 退避重试。**若持续回空 = 被限流，停手冷却几分钟即恢复**，不是账号配额耗尽。验证/试跑用小类目（几百品以内）避免把自己推进限流。
- **`order.field` 必须是 `total_units`**（`amz_unit` 已失效，会被静默回空）；请求须带全套浏览器头 + 与 body 匹配的 referer。
- **维度 = 父 ASIN**：`symbolFlag=False` 抓父根 + 全部子变体，按 `parent` 归并，月销量同月求和（`website_scraper._group_by_parent`）。每条抓取后跑 `verify_parent_merge` 四重守恒自检。
- **真实月销量 = `amzUnitTrends`**（驼峰）；`trends` 字段是放大假数据，弃用。
- **清洗窗口恒为最近 24 个月**（`[max_dk - 23 月, max_dk]`，缺月不补零）；无销量估算的品补零销量占位行进计数。

## 测试

```bash
cd MI_sellersprite
PYTHONPATH=. MI_auto/.venv/bin/python -m pytest tests/    # 42 passed / 6 skipped
```

## 离线 / 自动化用法

不走交互菜单，直接用已有 raw.json 跑清洗 + 报告：

```bash
PYTHONPATH=. MI_auto/.venv/bin/python run_all.py --input <path>/raw.json --market US
```

## 注意

- `.env`、`.superpowers/`、`*.token_cache*.json`、`output/` 含敏感凭证或产物，已在 `.gitignore`，**勿提交**。
- cookie 路径由 `website_scraper.py` 用 `Path(__file__).parents[1] / ".superpowers/sdd/v3_cookie.txt"` 自解析，随目录移动无需改代码。
- `MI_auto/.venv/` 为 Python 3.12 虚拟环境（gitignored）。如需重建：`python3.12 -m venv MI_auto/.venv && MI_auto/.venv/bin/pip install -r MI_SELLERSPRITE/requirements.txt -r MI_auto/MI/requirements.txt`。
- 抓取层目录保留原名 `MI_SELLERSPRITE/`（sys.path 引用此名，勿改名）。
