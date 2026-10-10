# MCP 集成说明

## MCP Server

- 麦当劳中国 MCP Server（`mcd-mcp`），`https://mcp.mcd.cn`，Streamable HTTP
- 鉴权：`Authorization: Bearer ${MCD_MCP_TOKEN}`
- 客户端：`scripts/mcd_mcp.py`

## 使用的 Tool

| Tool | 用途 |
|---|---|
| `query-nearby-stores` | 门店营业时间（识别 24 小时店）和预约时段 |
| `list-nutrition-foods` | 官方营养数据，用于按热量区间和蛋白质选餐 |
| `query-meals` | 带 `reservationDate` 获取某个时间点对应时段的菜单 |
| `calculate-price` | 实付价格 |
| `create-order` | 用户确认后预约下单 |

## 调用流程

```
作息（起床 / 上班 / 下班）→ 三个绝对时间点（自动跨天）
        ▼
query-nearby-stores → 每个时间点筛营业门店（深夜优先 24h）
        ▼
reservationTimeOptions → 时间点属于哪个时段（宵夜 / 早餐 / 下午茶…）
        ▼                         （还没开放预约 → 同一时间点、最远可预约日的菜单预览）
query-meals(reservationDate) × list-nutrition-foods → 按角色规则选餐
        ▼
calculate-price → 展示 → 用户确认 → create-order
```

## 业务价值

- 现有点餐助手都按钟表时间推荐；这里按用户的作息推荐，凌晨 1 点的班中餐和早上 7 点的睡前餐规则不同。
- 时段和营业时间来自门店实时数据，不靠写死的"早餐到 10:30"之类的规则。
- 24 小时门店筛选直接解决"深夜哪里开着"的问题。
