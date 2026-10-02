# FinanceBot —— 中国金融账户同步到 Wealthfolio

面向个人的金融账户同步连接器框架：各金融机构（支付宝/银行等）的连接器负责把来源数据解析为标准化明细，经通用业务层计算后，导出为 [Wealthfolio](https://github.com/nnaumenko/wealthfolio) 可导入的 CSV。

## 目录结构

```
FinanceBot/
├── agent/                    # AI Agent：任务理解与流程调度（规划中：planner.py / executor.py）
├── connectors/               # 机构连接器（来源/目标适配）
│   ├── alipay/               # 支付宝（蚂蚁财富）：交割单 PDF 解析 + 净值 + 一键入口
│   ├── bank/                 # 银行（预留）
│   └── wealthfolio/          # Wealthfolio 目标适配：导入 CSV 格式
├── browser/                  # Playwright / 浏览器 Profile / RPA（预留）
│   ├── profiles/
│   └── playwright/
├── core/                     # 通用业务逻辑（与具体机构无关）
│   ├── parser/               # 通用解析器（预留）
│   ├── normalizer/           # position_calculator.py 摊薄成本持仓；validator.py 对账校验
│   └── pipeline/             # 任务编排（预留；当前编排入口在 connectors/alipay/scripts/run.py）
├── data/                     # 全局数据层
│   ├── raw/                  # 原始数据：data/raw/alipay/ 放交割单 PDF（用户投放区）
│   ├── processed/            # 处理产物：data/processed/alipay/ 放生成的 CSV（用户取件区）
│   └── export/               # 待导出/同步给外部系统的文件（预留）
├── config/
│   └── config.yaml           # 全局配置（连接器开关、账户名、目录等）
├── tests/
│   └── connectors/alipay/    # 支付宝连接器冒烟测试（不依赖 PDF/网络）
└── logs/                     # 运行日志（alipay_fund_csv.log）
```

## 快速开始（支付宝 → Wealthfolio）

```bash
cd FinanceBot   # 进入项目目录（若已在 FinanceBot/ 内则跳过）

# 1. 安装依赖
pip install -r connectors/alipay/requirements.txt

# 2. 把支付宝邮箱下载的交割单 PDF 放入 data/raw/alipay/（只放 1 份，文件名随意）

# 3. 运行（或直接双击 connectors/alipay/运行.bat）
python connectors/alipay/scripts/run.py
```

产物：`data/processed/alipay/fund_positions.csv`（持仓汇总）、`data/processed/alipay/wealthfolio_import.csv`（可直接导入 Wealthfolio）。

## 测试

```bash
python -m pytest tests/ -v
```

## 放置映射（迁移自 alipay_fund_csv）

| 原位置（alipay_fund_csv/） | 新位置 |
|---|---|
| src/statement_parser.py | connectors/alipay/statement_parser.py |
| src/nav_provider.py | connectors/alipay/nav_provider.py |
| src/position_calculator.py | core/normalizer/position_calculator.py |
| src/validator.py | core/normalizer/validator.py |
| src/exporter.py（Wealthfolio 部分） | connectors/wealthfolio/exporter.py |
| src/exporter.py（持仓汇总部分） | connectors/alipay/exporter.py |
| scripts/run.py | connectors/alipay/scripts/run.py |
| config.py | config/config.yaml + connectors/alipay/config.py（读取器） |
| data/input | data/raw/alipay |
| data/output | data/processed/alipay |
| tests/test_pipeline.py | tests/connectors/alipay/test_pipeline.py |
| 运行.bat | connectors/alipay/运行.bat |

## 演进路线

- 新增银行/券商连接器：在 `connectors/` 下平行新增目录，复用 `core/normalizer/` 的持仓计算与对账、`connectors/wealthfolio/` 的导出。
- 接入手动登录下载交割单：在 `browser/` 增加 RPA 流程，产出直接写入 `data/raw/<来源>/`。
- 任务编排自动化：实现 `agent/`，由 planner/executor 读取 `config/config.yaml` 调度各连接器。

## 隐私

交割单 PDF 含姓名、身份证号等个人信息。`.gitignore` 已忽略 `data/raw/alipay/*.pdf` 与 `data/processed/alipay/*.csv`；请勿上传到不受信任的第三方。
