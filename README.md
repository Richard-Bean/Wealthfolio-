# Wealthfolio 中国金融同步连接器架构设计

本仓库为**架构设计仓库**，包含：

- `FinanceBot/` —— 金融账户同步到 Wealthfolio 的连接器项目；
- `进度核查.md` —— 架构说明、实施进度、未完成任务和风险记录；
- `运行截图转CSV.bat` —— 从持仓截图生成 Wealthfolio CSV 的一键入口。

## 数据接口结论

**支付宝、银行和券商的个人账户 API 对本项目不可行。** 普通个人项目无法获得可合法、稳定、
长期读取个人余额、持仓和完整历史流水的通用 API。现有开放接口主要面向商户、企业、收单、
清算或持牌合作方；券商交易接口也不等同于完整历史账单接口。

因此，Connector 默认解析用户主动下载的 CSV、Excel、PDF、对账单、交割单和持仓截图。API
不是项目实现的前置条件；浏览器自动化只作为用户监督下的文件下载辅助，不保存登录密码，也
不绕过验证码或平台风控。

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
- 如果同一代码的金额不一致，全部保留并标记冲突，不再任意删除；
- 不同基金代码不会因为名称相似而被误合并。

### OCR 数据校验

程序会同时读取“持有收益”和“累计收益”，用两个独立字段交叉检查 OCR 漏位、错位和小数点错误。
校验时保留 OCR 原始收益、累计收益和原始收益率，并检查：

- 持仓成本、持有金额和持有收益的关系；
- 计算收益率与截图收益率是否一致；
- 持有份额 × 单位净值是否等于持有金额；
- 持有份额 × 平均成本是否等于持仓成本。

严重不一致的数据会阻止 CSV 导出并进入人工复核。如果持有收益和累计收益一致、仅截图收益率存在
口径差异，则保留警告后继续导出。Wealthfolio 账户名统一为“蚂蚁财富”。

这些校验主要提升 OCR 识别后数据的准确性，降低识别错误对持仓成本、收益分析和后续交易推断的影响；
同一套异常检测和人工复核规则也可以用于其他基于截图 OCR 的数据入口。

基金名称先使用本地 `fund_mapping.csv` 进行高可信匹配。本地没有匹配时先保留原始 OCR 行，再调用
公开基金搜索 API 查找候选；只有基金公司、份额类别、币种和名称均匹配时才自动补全代码，歧义项进入
待确认列表。匹配结果会保存回本地映射表，后续离线复用。

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
