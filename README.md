# Wealthfolio 中国金融同步连接器

把支付宝等来源的持仓截图、账单和交割单，经过 OCR、解析、校验、去重和对账后，生成可导入 Wealthfolio 的 CSV。

## 普通用户：只需三步

### 1. 放入截图

把一张或多张支付宝持仓截图放入：

```text
FinanceBot/data/raw/alipay
```

支持 `.jpg`、`.jpeg`、`.png` 和 `.bmp`。截图样式参考：

```text
FinanceBot/docs/templates/持仓截图模板_打码.jpg
```

### 2. 双击运行

双击项目根目录的：

```text
运行截图转CSV.bat
```

无需手动执行 Python 命令。程序会自动完成：

```text
截图 OCR
→ 页面模板识别
→ 持仓和交易解析
→ 多图去重与冲突比较
→ 本地净值缓存
→ 金额、收益、份额和成本校验
→ 生成 Wealthfolio CSV
```

### 3. 查看并导入结果

最终可导入 Wealthfolio 的文件是：

```text
FinanceBot/data/export/wealthfolio_import_auto.csv
```

导入前请查看：

```text
FinanceBot/data/processed/reconciliation/alipay/snapshot_comparison.json
```

重点检查：

- 同代码金额冲突；
- 待确认基金映射；
- `manual_review` 或严重校验错误；
- 被跳过的非基金资产；
- 账户名是否为“蚂蚁财富”；
- 日期、份额、平均成本和收益是否合理。

严重校验错误会阻止 CSV 导出。确认或修复后再重新运行。

## 常见问题

- **重新运行后 CSV 没更新**：关闭正在占用 CSV 的 Excel 等程序，再双击 BAT。
- **提示输入目录没有图片**：确认截图位于 `FinanceBot/data/raw/alipay`，且格式为 JPG、JPEG、PNG 或 BMP。
- **某些积存金或黄金理财被跳过**：当前版本主要支持基金持仓模板；跳过原因会写入对比报告。
- **同一只基金出现金额冲突**：不要直接删除，先核对原始截图和报告中的冲突记录。
- **想处理支付宝交割单 PDF、更新净值或运行测试**：这是开发者/高级用法，请查看 `docs/OPERATIONS.md`。

## 项目文档

- `AGENTS.md`：Coding Agent 的稳定规则和上下文路由；
- `STATUS.md`：当前进度、风险和阶段路线；
- `docs/ARCHITECTURE.md`：系统架构和设计决策；
- `docs/DATA_SCHEMA.md`：统一数据模型；
- `docs/CONNECTOR_SPEC.md`：Connector 规范；
- `docs/SECURITY.md`：安全和隐私边界；
- `docs/OPERATIONS.md`：高级运行、测试、人工复核和故障排查；
- `docs/archive/2026-10-进度核查.md`：历史归档。

## 数据接口说明

支付宝、银行和券商的个人账户 API 对普通个人项目不可行。因此，项目默认解析用户主动下载的 CSV、Excel、PDF、对账单、交割单和持仓截图。浏览器自动化只作为用户监督下的下载辅助，不保存登录密码，也不绕过验证码或平台风控。

## 隐私

截图、PDF 和生成的财务 CSV 只应在本机处理。不要把包含姓名、身份证号、完整账单或账户明细的原始文件上传到不受信任的服务。