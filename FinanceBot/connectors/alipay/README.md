# connectors/alipay —— 支付宝（蚂蚁财富）连接器

把**蚂蚁财富「基金交易明细」交割单 PDF**（支付宝邮箱下载的那份）解析为标准化交易明细，并驱动整条流水线，最终产出：
1. **持仓汇总 CSV**（`fund_positions.csv`，每只基金一行：份额/成本/最新净值/市值/盈亏）
2. **Wealthfolio 导入流水 CSV**（`wealthfolio_import.csv`，逐笔 buy/sell 活动）

归属说明（按 FinanceBot 架构）：
- 本目录 = 支付宝**来源适配**：PDF 解析、天天基金净值数据源、连接器配置与一键入口；
- 持仓计算（摊薄成本法）与对账校验 → `core/normalizer/`（通用业务逻辑）；
- Wealthfolio 导入格式导出 → `connectors/wealthfolio/`（目标适配）。

## 快速开始

前置要求：Windows 下安装 Python 3.12（`运行.bat` 已指向本机完整路径）；依赖 `pip install -r requirements.txt`。

```bash
# 1. 把支付宝邮箱下载的交割单 PDF 放进 data/raw/alipay/（文件名随意，目录里只放 1 份）
# 2. 运行
python connectors/alipay/scripts/run.py
# 或指定文件：python connectors/alipay/scripts/run.py /path/to/xxx.pdf
```

产物在 `data/processed/alipay/` 下。运行结束打印对账结果（✔ = 解析完整、记账无误）。

## 目录结构

```
connectors/alipay/
├── 运行.bat                  # Windows 双击启动器（显式调用 Python 完整路径）
├── config.py                  # 连接器运行时配置：从仓库根 config/config.yaml 读取 alipay 段
├── requirements.txt           # 依赖清单
├── statement_parser.py        # PDF解析：交割单 → 交易明细表（支付宝专属）
├── nav_provider.py            # 净值获取：天天基金公开接口 → 最新净值/基金名称
├── exporter.py                # 持仓汇总 CSV 导出
├── scripts/
│   └── run.py                 # 一键入口：解析→净值→计算→导出→校验
└── README.md
```

配套目录（仓库根下）：
- `data/raw/alipay/`        放交割单 PDF（用户操作区）
- `data/processed/alipay/`  生成的 CSV（用户取件区）
- `core/normalizer/`        position_calculator.py（摊薄成本法）、validator.py（对账校验）
- `connectors/wealthfolio/` exporter.py（Wealthfolio 导入 CSV）
- `config/config.yaml`      全局配置（账户名、联网开关、目录）
- `logs/`                   run.py 运行日志（alipay_fund_csv.log）

## 数据流

```
交割单PDF ──statement_parser──> 交易明细DataFrame ──nav_provider──> 最新净值
                                      │                              │
                                      └──position_calculator──> 持仓表 ──exporter──> 两个CSV
                                                                              │
                                                                              └──validator──> 对账报告
```

## 关键口径（维护时先读这里）

| 事项 | 口径 | 位置 |
|---|---|---|
| 买入成本 | 成本 = Σ确认金额（蚂蚁 APP 持有成本口径，含手续费） | `core/normalizer/position_calculator.py` `_apply_buy` |
| 卖出扣成本 | 摊薄成本法：成本 -= 成本 × (卖出份额/卖出前份额) | `core/normalizer/position_calculator.py` `_apply_sell` |
| 转换方向 | 「申请份额」有值=转出(卖出)；「申请金额」有值=转入(买入) | `core/normalizer/position_calculator.py` `_classify` |
| 现金分红 | 不影响份额与成本 | `core/normalizer/position_calculator.py` `_apply_ignore` |
| Wealthfolio 买入 | amount=确认金额-手续费，fee=手续费 → 成本基础=确认金额 | `connectors/wealthfolio/exporter.py` |
| 净值兜底 | 联网拉取失败时用交割单最后一笔确认净值 | `core/normalizer/position_calculator.py` `compute_positions` |

## 维护指南（改什么、去哪改）

| 需求 | 改动位置 |
|---|---|
| 蚂蚁改版、PDF 列顺序变了 | `statement_parser.py` 顶部的列索引映射 |
| 新增业务类型（如「定期开放赎回」） | `core/normalizer/position_calculator.py` 的关键词元组 |
| 换成先进先出等其他成本法 | `core/normalizer/position_calculator.py` 的 `_apply_sell` |
| 净值接口字段变了 | `nav_provider.py` 顶部的两个正则 |
| 换净值数据源（如天天基金其他接口） | `nav_provider.py` 的 `fetch_one` |
| 改账户名 / 是否联网 / 输入输出目录 | `config/config.yaml` 的 `connectors.alipay` 段 |
| Wealthfolio 列格式变了 | `connectors/wealthfolio/exporter.py` 的 `WEALTHFOLIO_COLUMNS` |

## 隐私说明

- 交割单 PDF 含姓名、身份证号等个人信息：解析器**只提取交易字段**（日期/代码/名称/金额/份额/手续费），不读入证件信息；生成的 CSV 同样只有交易字段。
- `.gitignore` 已忽略 `data/raw/alipay/*.pdf` 与 `data/processed/alipay/*.csv`，防止敏感数据入库；请勿把交割单 PDF 或 CSV 上传到不受信任的第三方。

## 已知边界

- QDII 基金净值更新滞后（T+1~T+2），`fund_positions.csv` 中的「净值日期」会标注实际净值归属日。
- 持仓市值 = 份额 × 最新净值，与支付宝 APP 实时估值可能存在小幅差异（口径不同）。
- 交割单默认仅覆盖申请的时间段；跨多年持仓需分时段申请多份 PDF，分别运行后自行合并。


## 截图获取方式

截图保存位置：

```text
data/raw/alipay/
```

操作路径：

> 打开支付宝，点击下方“理财”，下拉总资产后点击“基金”，再点击“我的总资产”进行截图。

需要保留基金名称、持有金额、持有收益和持有收益率。关键数字的打码样式参考：

```text
FinanceBot/docs/templates/持仓截图模板_打码.jpg
```


## 截图一键转换（不使用交易流水）

将新截图放入 `data/raw/alipay/`，双击：

```text
运行截图转CSV.bat
```

流水线会自动完成：

```text
截图 -> Windows OCR -> 结构化持仓 JSON -> 公开净值API -> 持有份额/平均成本 -> Wealthfolio CSV
```

输出：

```text
data/processed/alipay/wealthfolio_import_auto.csv
data/export/wealthfolio_import_auto.csv
```

支持右键“以管理员身份运行”之外的普通双击。也可以把图片路径作为参数传给 BAT。若布局不是支付宝/养基宝“我的持有”列表布局，需要新增 OCR 布局适配规则。
