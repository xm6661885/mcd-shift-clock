#!/usr/bin/env python3
"""倒班生物钟点餐：按"你的早上"而不是钟表时间推荐。

夜班护士、倒班工人、刚倒时差的人，起床可能是下午四点、下班可能是凌晨两点。
这个脚本把一天按你的作息分成「起床餐 / 班中餐 / 下班餐 / 睡前」，
再映射到门店真实的供餐时段（早餐/午餐/夜市/宵夜）和营业时间，挑出 24 小时门店。

示例：
  python3 scripts/shift_clock.py plan --city 广州市 --keyword 中山大学附属第一医院 \
      --wake 16:00 --shift-start 19:00 --shift-end 07:00 --date 2026-10-11
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mcd_mcp import (MCPError, McdMCP, Nutrition, fen_to_yuan, find_slot,  # noqa: E402
                     find_stores, fmt_time, is_24h, menu_items, parse_time, store_args,
                     store_slots)

CAFFEINE = ("咖啡", "美式", "奶铁", "拿铁", "卡布奇诺", "玛奇朵", "浓缩", "红茶", "可乐", "阿芙佳朵")
SUGARY = ("可乐", "雪碧", "新地", "麦旋风", "雪冰", "派", "冰淇淋", "圆筒", "芬达")

# role -> (kcal range, caffeine allowed, label)
ROLES = {
    "wake": ((350, 650), True, "起床餐（你的早餐）"),
    "mid": ((400, 700), True, "班中餐"),
    "off": ((250, 450), False, "下班餐（睡前别太撑，不要咖啡因）"),
}


def timeline(date: str, wake: str, shift_start: str, shift_end: str) -> list[dict]:
    """Return absolute times for each meal role. Night shifts roll into the next day."""
    w = parse_time(f"{date} {wake}")
    ss = parse_time(f"{date} {shift_start}")
    if ss < w:
        ss += timedelta(days=1)
    se = parse_time(f"{date} {shift_end}")
    while se <= ss:
        se += timedelta(days=1)
    mid = ss + (se - ss) / 2
    return [
        {"role": "wake", "at": fmt_time(w + timedelta(minutes=30))},
        {"role": "mid", "at": fmt_time(mid.replace(second=0, microsecond=0))},
        {"role": "off", "at": fmt_time(se + timedelta(minutes=20))},
    ]


def choose(menu: list[dict], nut: Nutrition, role: str) -> dict | None:
    (lo, hi), caffeine_ok, _ = ROLES[role]
    known = []
    for m in menu:
        n = nut.get(m["name"])
        if not n or m["price"] <= 0 or any(w in m["name"] for w in SUGARY):
            continue
        if not caffeine_ok and any(w in m["name"] for w in CAFFEINE):
            continue
        known.append((m, n))
    mains = sorted((x for x in known if x[1]["protein"] >= 10),
                   key=lambda x: (abs(x[1]["energyKcal"] - (lo + hi) / 2 * 0.75), -x[1]["protein"]))
    if not mains:
        return None
    main, mn = mains[0]
    picks = [(main, mn)]
    budget = hi - mn["energyKcal"]
    drinks = [x for x in known if x[0]["code"] != main["code"] and x[1]["protein"] < 10
              and x[1]["energyKcal"] <= budget]
    if role == "wake":
        coffee = [x for x in drinks if any(w in x[0]["name"] for w in ("美式", "鲜萃咖啡", "奶铁"))]
        drinks = coffee or drinks
    if drinks:
        picks.append(min(drinks, key=lambda x: x[1]["energyKcal"] if role == "off" else -x[1]["protein"]))
    total = {k: sum(n[k] for _, n in picks) for k in ("energyKcal", "protein", "fat", "carbohydrate")}
    return {"items": [{"code": m["code"], "name": m["name"]} for m, _ in picks], "nutrition": total}


def _slot_or_preview(store: dict, at: str) -> tuple[dict | None, str | None]:
    """Real slot when `at` is reservable; otherwise the same clock time on the furthest reservable
    day, so the preview uses the right daypart menu (breakfast at 07:20, not whatever is on now)."""
    slot = find_slot(store, at)
    if slot:
        return slot, at
    days = sorted({x["date"] for x in store_slots(store)})
    for day in reversed(days):
        proxy = f"{day} {at.split(' ')[1]}"
        hit = find_slot(store, proxy)
        if hit:
            return hit, proxy
    return None, None


def plan(client: McdMCP, city: str, keyword: str, date: str, wake: str, ss: str, se: str) -> dict:
    stores = [s for s in find_stores(client, "pickup", city=city, keyword=keyword)
              if s.get("businessStatus", True)]
    if not stores:
        raise MCPError("附近没有门店")
    nut = Nutrition.load(client)
    meals = []
    for t in timeline(date, wake, ss, se):
        hm = t["at"].split(" ")[1]
        open_now = [s for s in stores if is_24h(s) or s["businessStartTime"] <= hm <= s["businessEndTime"]]
        entry = {**t, "label": ROLES[t["role"]][2], "plan": None,
                 "open24h": [s["storeName"] for s in stores if is_24h(s)][:3]}
        if not open_now:
            entry["note"] = "这个时间附近没有营业门店，建议上一餐多备一份"
        for s in open_now[:3]:
            slot, when = _slot_or_preview(s, t["at"])
            args = store_args(s, when)
            try:
                menu = menu_items(client.data("query-meals", args))
            except MCPError:
                continue
            pick = choose(menu, nut, t["role"])
            if not pick:
                continue
            items = [{"productCode": i["code"], "quantity": 1} for i in pick["items"]]
            try:
                price = client.data("calculate-price", {**args, "items": items})
            except MCPError:
                continue
            entry["plan"] = {"storeCode": s["storeCode"], "storeName": s["storeName"],
                             "hours": f"{s['businessStartTime']}-{s['businessEndTime']}",
                             "daypart": slot["name"] if slot else "当前时段",
                             "reservable": bool(slot) and when == t["at"],
                             **pick, "total": fen_to_yuan(price.get("price")),
                             "request": {**args, "items": items} if when == t["at"] else None}
            break
        if entry["plan"] is None and "note" not in entry:
            entry["note"] = "该时间暂无可预约的时段（门店只开放约 1 天内的预约），到时再查即可"
        meals.append(entry)
    return {"date": date, "wake": wake, "shift": f"{ss}-{se}", "meals": meals}


def render(p: dict) -> str:
    lines = [f"作息：{p['wake']} 起床，{p['shift']} 上班", ""]
    for m in p["meals"]:
        lines.append(f"· {m['at']} {m['label']}")
        pl = m["plan"]
        if pl:
            n = pl["nutrition"]
            lines.append(f"  {pl['storeName']}（{pl['hours']}，{pl['daypart']}）："
                         f"{' + '.join(i['name'] for i in pl['items'])}，¥{pl['total']:.2f}")
            lines.append(f"  约 {n['energyKcal']} kcal，蛋白质 {n['protein']}g"
                         + ("" if pl["reservable"] else "（该时间预约尚未开放，按同时段菜单预估）"))
        else:
            lines.append(f"  {m.get('note', '')}")
            if m["open24h"]:
                lines.append(f"  附近 24 小时门店：{'、'.join(m['open24h'])}")
    lines.append("")
    lines.append("营养来自 list-nutrition-foods，价格来自 calculate-price；仅供参考，不构成医疗或营养建议。")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="倒班族按生物钟点餐")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--city", required=True)
    p.add_argument("--keyword", required=True, help="上班地点")
    p.add_argument("--date", required=True, help="起床那天 yyyy-MM-dd")
    p.add_argument("--wake", required=True, help="起床时间 HH:mm")
    p.add_argument("--shift-start", required=True, help="上班 HH:mm")
    p.add_argument("--shift-end", required=True, help="下班 HH:mm（跨天自动处理）")
    p.add_argument("--json", action="store_true")
    s = sub.add_parser("stores24", help="列出附近 24 小时门店")
    s.add_argument("--city", required=True)
    s.add_argument("--keyword", required=True)
    o = sub.add_parser("order", help="按 plan 输出的 request 下单（需 --confirm）")
    o.add_argument("--request", required=True)
    o.add_argument("--take-way", default="take-in-store")
    o.add_argument("--confirm", action="store_true")
    a = ap.parse_args(argv)
    if getattr(a, "confirm", None) is False:
        # Orders and cancellations change the account: refuse before touching the network.
        print("未带 --confirm：请先向用户确认门店、时间、餐品与价格后再执行。", file=sys.stderr)
        return 2
    try:
        client = McdMCP(client_name="mcd-shift-clock")
        if a.cmd == "plan":
            r = plan(client, a.city, a.keyword, a.date, a.wake, a.shift_start, a.shift_end)
            print(json.dumps(r, ensure_ascii=False, indent=2) if a.json else render(r))
        elif a.cmd == "stores24":
            for st in find_stores(client, "pickup", city=a.city, keyword=a.keyword):
                if is_24h(st):
                    print(f"{st['storeName']}  {st.get('distance')}m  {st.get('address')}")
        else:
            print(json.dumps(client.data("create-order", {**json.loads(a.request), "takeWayCode": a.take_way}),
                             ensure_ascii=False, indent=2))
    except (MCPError, ValueError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
