---
name: mcd-shift-clock
description: 给夜班、倒班、倒时差的人按"自己的早上"点麦当劳：把起床、班中、下班三餐映射到门店真实的供餐时段（早餐/午餐/下午茶/夜市/宵夜）和营业时间，深夜优先 24 小时门店，下班睡前那餐不给咖啡因。当用户提到夜班、倒班、上大夜、值班、倒时差、"凌晨几点能吃到什么"时使用。
---

# 倒班生物钟点餐（mcd-shift-clock）

## 需要的 MCP

麦当劳 MCP Server（`mcd-mcp`，`https://mcp.mcd.cn`）。

## 工作流程

1. **收集作息**：起床日期和时间、上班时间、下班时间（跨天会自动处理），以及上班地点。
2. **排时间线**：
   - 起床餐 = 起床后 30 分钟，可以有咖啡，350~650 kcal；
   - 班中餐 = 上班和下班的中点，400~700 kcal；
   - 下班餐 = 下班后 20 分钟，250~450 kcal，**不给咖啡因**，因为接下来要睡觉。
3. **找门店**：`query-nearby-stores`（`searchType=2`，`beType=1`）。每个时间点只考虑在营业的门店，`businessStartTime=00:00` 且 `businessEndTime=23:59` 的是 24 小时门店，深夜优先。
4. **对上时段菜单**：从 `reservationTimeOptions` 找出包含这个时间点的时段（同一个凌晨 1 点，可能是"宵夜"也可能是"夜市"），`query-meals` 带 `reservationDate` 拿到对应的菜单。如果那个时间还没开放预约，就用最远可预约日的同一时间点预览菜单，并说明是预估。
5. **选餐**：`list-nutrition-foods` 提供营养数据。主食要求蛋白质 ≥ 10g，热量贴近该餐区间；配饮按规则选（起床餐优先美式或鲜萃咖啡，下班餐选热量最低、无咖啡因的）；甜品和含糖饮料都不选。
6. **算价**：`calculate-price`。
7. **下单**：用户确认后调用 `create-order`（带 `reservationDate`、`takeWayCode`）。

## 规则

- 结果只是饮食安排的参考，不构成医疗或营养建议。
- 金额只看 `calculate-price`；`create-order` 必须在用户确认后才能调用。

## 辅助脚本

```bash
python3 scripts/shift_clock.py plan --city 广州市 --keyword 中山大学附属第一医院 \
  --date 2026-10-11 --wake 16:00 --shift-start 19:00 --shift-end 07:00
python3 scripts/shift_clock.py stores24 --city 广州市 --keyword 中山大学附属第一医院
```
