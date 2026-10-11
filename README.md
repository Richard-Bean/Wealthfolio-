# Wealthfolio 中国金融同步连接器架构设计

本仓库为**架构设计仓库**，包含：

- `FinanceBot/` —— 金融账户同步到 Wealthfolio 的连接器项目；
- `wealthfolio_connection_v1.md` —— 与当前 CSV 主流程一致的架构设计文档；
- `运行截图转CSV.bat` —— 从持仓截图生成 Wealthfolio CSV 的一键入口。

## 截图转 CSV

将一张或多张持仓截图放入：

```text
FinanceBot/data/raw/alipay
```

然后双击项目根目录的 `运行截图转CSV.bat`。也可以把多张图片直接拖到 BAT 上，脚本会一次处理这些图片。输入截图样式参考：

```text
FinanceBot/docs/templates/持仓截图模板_打码.jpg
```

### 多图整合与数据对比

程序可以同时处理多张截图，最终生成一份 CSV。每张截图会分别 OCR 和解析，然后统一进行数据对比：

- 对名称、基金代码、持有金额进行全面比较；
- 同一账户、同一日期下，名称高度相似或代码相同的记录视为重复候选；
- 重复记录只保留一项；
- 如果名称高度相似但代码不同（例如联接 A / 联接 C），会保留为两项；
- 如果同一代码的金额不一致，只保留一项，同时把冲突写入对比报告；
- 不同基金代码不会因为名称相似而被误合并。

### 当前暂未处理

积存金、黄金理财等非模板数据暂时无法识别为基金，也不会进入当前基金 CSV。程序会搁置并跳过这些记录，继续处理其他截图，跳过原因记录在：

```text
D:\my-code-project\Wealthfolio中国金融同步连接器架构设计\FinanceBot\data\processed\alipay\snapshot_comparison.json
```

对比过程会生成：

```text
FinanceBot/data/processed/alipay/snapshot_input.auto.json
FinanceBot/data/processed/alipay/snapshot_comparison.json
```

最终仍生成原来格式的一个 Wealthfolio CSV（不会每张截图各生成一个 CSV）：

```text
FinanceBot/data/export/wealthfolio_import_auto.csv
```

同时会在 `FinanceBot/data/processed/alipay/wealthfolio_import_auto.csv` 保留同内容的工作副本。CSV 列保持不变：

```text
date,account,activityType,symbol,isin,quantity,unitPrice,amount,currency,fee,tax,comment
```