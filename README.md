# alipay_fund_csv —— 支付宝基金交割单 → CSV 转换工具

把**蚂蚁财富「基金交易明细」交割单 PDF**（支付宝邮箱下载的那份），一键转换为：
1. **持仓汇总 CSV**（`fund_positions.csv`）：每只基金一行，含份额、成本、最新净值、市值、盈亏
2. **Wealthfolio 导入流水 CSV**（`wealthfolio_import.csv`）：逐笔 buy/sell 活动，可直接导入 [Wealthfolio](https://github.com/nnaumenko/wealthfolio)

---

## 快速开始

### 前置要求（只需准备一次）
- **Windows**：安装 Python 3（推荐 3.12+，从 python.org 下载，安装时勾选 "Add Python to PATH"）。本项目根目录的 `运行.bat` 已直接调用已安装 Python 的完整路径，无需额外配置。
- **macOS / Linux**：系统自带 `python3`（macOS 若没有，可 `brew install python`）。
- 安装依赖：在项目目录执行 `pip install -r requirements.txt`（macOS 用 `pip3`）。

### 方式一：双击运行（Windows 推荐）
1. 把支付宝邮箱下载的交割单 PDF 放进 `data/input/`（**目录里保持只有 1 个 PDF，文件名随意**）
2. 双击项目根目录的 **`运行.bat`**
3. 窗口显示「成功！两份 CSV 已生成到 data\output 目录」即完成，按任意键关闭

### 方式二：命令行运行
```bash
# ---- Windows（PowerShell / CMD）----
cd D:\my-code-project\Wealthfolio中国金融同步连接器架构设计\alipay_fund_csv   # 先进项目目录
python scripts/run.py                                            # 自动使用 data\input 下的唯一 PDF
python scripts/run.py data\input\对账单.pdf                      # 或手动指定某个 PDF

# ---- macOS / Linux ----
cd /你的路径/alipay_fund_csv
python3 scripts/run.py                                           # macOS / Linux 用 python3
python3 scripts/run.py data/input/对账单.pdf                     # 或手动指定某个 PDF
```

产物在 `data/output/` 下（`fund_positions.csv` + `wealthfolio_import.csv`）。运行结束会打印对账结果（✔ = 解析完整、记账无误）。

> **输入 PDF 自动识别规则**：`data/input/` 下**恰好 1 个 PDF** 时自动使用（文件名随意）；没有或超过 1 个时，回退寻找默认名「交割单.pdf」，找不到会提示你用命令行指定。

## 目录结构

```
alipay_fund_csv/
├── 运行.bat                  # Windows 双击启动器（显式调用 Python 完整路径，无需配 PATH）
├── config.py                  # 全局配置：自动识别 data/input 唯一 PDF、输出目录、账户名、是否联网
├── requirements.txt           # 依赖清单
├── src/                       # 核心代码（每个模块职责单一，无黑箱）
│   ├── statement_parser.py    # PDF解析：交割单 → 交易明细表
│   ├── position_calculator.py # 持仓计算：明细 → 持仓（摊薄成本法）
│   ├── nav_provider.py        # 净值获取：天天基金公开接口 → 最新净值/基金名称
│   ├── exporter.py            # CSV导出：持仓汇总 + Wealthfolio 导入流水
│   └── validator.py           # 对账校验：独立复算，交叉核对
├── scripts/
│   └── run.py                 # 一键入口：解析→净值→计算→导出→校验
├── data/
│   ├── input/                 # 放交割单 PDF（用户操作区）
│   └── output/                # 生成的 CSV（用户取件区）
└── tests/
    └── test_pipeline.py       # 冒烟测试（不依赖PDF/网络）
```

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
| 买入成本 | 成本 = Σ确认金额（蚂蚁 APP 持有成本口径，含手续费） | `position_calculator._apply_buy` |
| 卖出扣成本 | 摊薄成本法：成本 -= 成本 × (卖出份额/卖出前份额) | `position_calculator._apply_sell` |
| 转换方向 | 「申请份额」有值=转出(卖出)；「申请金额」有值=转入(买入) | `position_calculator._classify` |
| 现金分红 | 不影响份额与成本 | `position_calculator._apply_ignore` |
| Wealthfolio 买入 | amount=确认金额-手续费，fee=手续费 → 成本基础=确认金额 | `exporter.export_wealthfolio_csv` |
| 净值兜底 | 联网拉取失败时用交割单最后一笔确认净值 | `position_calculator.compute_positions` |

## 维护指南（改什么、去哪改）

| 需求 | 改动位置 |
|---|---|
| 蚂蚁改版、PDF 列顺序变了 | `src/statement_parser.py` 顶部的列索引映射 |
| 新增业务类型（如「定期开放赎回」） | `src/position_calculator.py` 的关键词元组 |
| 换成先进先出等其他成本法 | `src/position_calculator.py` 的 `_apply_sell` |
| 净值接口字段变了 | `src/nav_provider.py` 顶部的两个正则 |
| 换净值数据源（如天天基金其他接口） | `src/nav_provider.py` 的 `fetch_one` |
| 改账户名 / 是否联网 / 输出目录 | `config.py` |
| 改输入 PDF 的自动识别规则 | `config.py` 的 `find_input_pdf()`（规则：input 下唯一 PDF 自动用，否则回退「交割单.pdf」） |
| Wealthfolio 列格式变了 | `src/exporter.py` 的 `WEALTHFOLIO_COLUMNS` |

## 隐私说明

- 交割单 PDF 含姓名、身份证号等个人信息：解析器**只提取交易字段**（日期/代码/名称/金额/份额/手续费），不读入证件信息；生成的 CSV 同样只有交易字段。
- 请勿把交割单 PDF 或 CSV 上传到不受信任的第三方。

## 已知边界

- QDII 基金净值更新滞后（T+1~T+2），`fund_positions.csv` 中的「净值日期」会标注实际净值归属日。
- 持仓市值 = 份额 × 最新净值，与支付宝 APP 实时估值可能存在小幅差异（口径不同）。
- 交割单默认仅覆盖申请的时间段；跨多年持仓需分时段申请多份 PDF，分别运行后自行合并。
