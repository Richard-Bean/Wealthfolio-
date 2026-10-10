# Wealthfolio 中国金融同步连接器架构设计

本仓库为**架构设计仓库**，包含：

- `FinanceBot/` —— 金融账户同步到 Wealthfolio 的连接器项目；
- `wealthfolio_connection_v1.md` —— 与当前 CSV 主流程一致的架构设计文档；
- `运行截图转CSV.bat` —— 从持仓截图生成 Wealthfolio CSV 的一键入口。

## 截图转 CSV

将持仓截图放入：

```text
FinanceBot/data/raw/alipay
```

然后双击项目根目录的 `运行截图转CSV.bat`。输入截图样式参考：

```text
FinanceBot/docs/templates/持仓截图模板_打码.jpg
```

输出统一保存到：

```text
FinanceBot/data/export
```
