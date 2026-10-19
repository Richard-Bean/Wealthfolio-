# 基金净值本地缓存与每日更新

## 数据流

```text
持仓截图（金额/收益/收益率）
        +
公开净值 API（基金代码/单位净值/净值日期）
        ↓
本地 JSON 缓存
        ↓
计算持有份额与平均成本
        ↓
Wealthfolio CSV
```

核心公式：

```text
持仓总成本 = 持有金额 - 持有收益
持有份额 = 持有金额 ÷ 截图时点已发布的最新单位净值
每股平均成本 = 持仓总成本 ÷ 持有份额
```

注意：2026-10-09 17:21 的截图使用的是 2026-10-08 已结算净值，
不是当天结算后才发布的 2026-10-09 净值。`latest_nav_asof()` 已按结算时间处理该差异。

## 手工更新

```bash
python FinanceBot/scripts/update_nav_cache.py
python FinanceBot/connectors/alipay/scripts/build_snapshot_import.py
```

Windows 可双击：

- `FinanceBot/scripts/每日净值更新.bat`
- `FinanceBot/connectors/alipay/生成快照CSV.bat`

## 每日自动更新

建议在 Windows 任务计划程序中每天 21:00（Asia/Shanghai）运行：

```text
D:\my-code-project\Wealthfolio中国金融同步连接器架构设计\FinanceBot\scripts\每日净值更新.bat
```

21:00 是建议值；如果当天净值尚未发布，可再增加 22:00 重试。更新失败时保留旧缓存，不覆盖成功数据。

## 公开接口风险

| 风险 | 结论 | 缓解措施 |
|---|---|---|
| 截图/金额上传 | 不会。请求 URL 只包含基金代码 | 不把截图、金额、收益、账户放入请求 |
| 隐私痕迹 | 服务端可能记录 IP、时间和基金代码 | 低频访问；敏感场景使用授权数据源 |
| 数据不稳定 | 公开接口无 SLA，字段可能变化 | 本地缓存、解析校验、失败保留旧值、定时重试 |
| 反爬虫/限流 | 每日5只基金风险较低，批量高频可能触发限制 | 串行请求、间隔 0.3 秒、每日一次、指数退避重试 |
| 数据错误 | 接口可能延迟或回补历史净值 | 校验净值日期；截图按“当时已发布净值”取数 |

## 本地缓存

路径：

```text
FinanceBot/data/processed/market_data/净值缓存.json
```

缓存写入使用同目录临时文件和原子替换；单只基金失败不会破坏已有缓存。
