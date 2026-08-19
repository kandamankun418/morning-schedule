"""朝のスケジュールを生成して docs/index.html を更新する。

使い方:
    python src/main.py                # 翌朝のぶんを生成
    python src/main.py --date 2026-08-25
    python src/main.py --mock         # APIを呼ばず、予備の献立で動作確認
"""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import date, timedelta
from typing import Any, Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import llm  # noqa: E402
import render  # noqa: E402
import scheduler  # noqa: E402

WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


def compute_budget(settings: Dict[str, Any], task_defs: List[Dict[str, Any]]) -> Dict[str, float]:
    """お弁当の調理に割り当てられる時間を求める。"""
    wake = config.parse_hhmm(settings["wake_time"])
    latest = config.parse_hhmm(settings["latest_leave"])
    window_minutes = (latest - wake) / 60.0

    fixed_attended = sum(
        float(t.get("minutes", 0)) for t in task_defs if t.get("attended", True)
    )
    rice_wait = next(
        (float(t["minutes"]) for t in task_defs if t["id"] == "rice_cook"), 30.0
    )

    absolute_max = max(window_minutes - fixed_attended, 5.0)
    bento_cfg = settings.get("bento", {})
    return {
        "target": round(min(float(bento_cfg.get("target_minutes", 25)), absolute_max), 1),
        "max": round(min(float(bento_cfg.get("max_minutes", 40)), absolute_max), 1),
        "absolute_max": round(absolute_max, 1),
        "rice_wait": rice_wait,
        "window": round(window_minutes, 1),
    }


def build_timeline_rows(slots: List[scheduler.Slot], base: int) -> List[Dict[str, Any]]:
    """タイムライン表示用の行を作る。手が空く時間は「ゆとり」として挟む。"""
    rows: List[Dict[str, Any]] = []
    prev_attended_end = 0
    for slot in slots:
        if slot.task.attended:
            gap = slot.start - prev_attended_end
            if gap >= 60:
                rows.append({"type": "gap", "seconds": gap})
            prev_attended_end = max(prev_attended_end, slot.end)
        rows.append(
            {
                "type": "task",
                "id": slot.task.id,
                "name": slot.task.name,
                "start": config.fmt_hhmm(base, slot.start),
                "end": config.fmt_hhmm(base, slot.end),
                "seconds": slot.task.seconds,
                "attended": slot.task.attended,
                "background": slot.task.background,
                "kind": slot.task.kind,
            }
        )
    return rows


def apply_stock_consumption(stock: Dict[str, Any], consumed: List[Dict[str, Any]]) -> List[str]:
    """使った在庫を減らす。減らせなかったぶんは注意として返す。"""
    notes: List[str] = []
    by_id = {item["id"]: item for item in stock.get("items", [])}
    for entry in consumed or []:
        item = by_id.get(entry.get("id"))
        if item is None:
            notes.append("在庫に見当たらない id を消費しようとしました: {}".format(entry.get("id")))
            continue
        want = float(entry.get("quantity", 0))
        have = float(item.get("quantity", 0))
        used = min(want, have)
        item["quantity"] = round(have - used, 2)
        if used < want:
            notes.append(
                "{} の在庫が足りません（必要 {} / 実際 {}）".format(item["name"], want, have)
            )
    return notes


def update_history(history: Dict[str, Any], target_date: str, menu: Dict[str, Any], keep: int) -> None:
    entries = [e for e in history.get("entries", []) if e.get("date") != target_date]
    entries.insert(
        0,
        {
            "date": target_date,
            "menu_name": menu.get("menu_name", ""),
            "items": [i.get("name", "") for i in menu.get("items", [])],
        },
    )
    history["entries"] = entries[:keep]


def main() -> int:
    parser = argparse.ArgumentParser(description="翌朝のスケジュールとお弁当を生成する")
    parser.add_argument("--date", help="対象の日付 (YYYY-MM-DD)。省略時は翌日")
    parser.add_argument("--mock", action="store_true", help="APIを呼ばずに予備の献立で生成する")
    parser.add_argument("--dry-run", action="store_true", help="ファイルを書き換えずに結果だけ表示する")
    args = parser.parse_args()

    settings = config.load_settings()
    task_defs = config.load_tasks()["tasks"]
    preferences = config.load_preferences()
    stock_raw = config.load_stock()
    history = config.load_history()

    if args.date:
        target = date.fromisoformat(args.date)
    else:
        target = config.now_jst().date() + timedelta(days=1)
    target_iso = target.isoformat()

    stock_list = config.stock_with_expiry(stock_raw, target)
    budget = compute_budget(settings, task_defs)

    warnings: List[str] = []

    # --- 献立の生成 ---
    menu: Dict[str, Any]
    if args.mock:
        menu = llm.fallback_menu(stock_list)
    else:
        prompt = llm.build_user_prompt(
            target_iso, budget, stock_list, history.get("entries", []), preferences
        )
        try:
            menu = llm.generate_menu(settings["model"], settings.get("effort", "medium"), prompt)
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            warnings.append("献立の生成に失敗したため、予備の献立を表示しています（{}）".format(exc))
            menu = llm.fallback_menu(stock_list)

    # --- スケジューリング ---
    base = config.parse_hhmm(settings["wake_time"])
    target_leave = config.parse_hhmm(settings["target_leave"])
    latest_leave = config.parse_hhmm(settings["latest_leave"])

    tasks = scheduler.build_tasks(task_defs, menu.get("steps", []))
    slots = scheduler.schedule(tasks)
    summary = scheduler.summarize(slots)
    end = scheduler.makespan(slots)

    if base + end > latest_leave:
        over = round((base + end - latest_leave) / 60.0)
        warnings.append(
            "この工程では出発が {} 分遅れます。おかずを1品減らすか、"
            "冷凍食品・作り置きに置き換えてください。".format(over)
        )
        cut = [s.task.name for s in slots if s.task.kind == "bento" and s.task.attended]
        if cut:
            warnings.append("削る候補: {}".format("、".join(cut[-2:])))

    laundry = next((s for s in slots if s.task.id == "laundry_run"), None)
    if laundry and base + laundry.end > latest_leave:
        warnings.append(
            "洗濯は {} ごろ終わります（出発には影響しません）".format(
                config.fmt_hhmm(base, laundry.end)
            )
        )

    for note in apply_stock_consumption(stock_raw, menu.get("stock_consumed", [])):
        warnings.append(note)

    expiring = [s for s in stock_list if s["days_left"] <= 1]
    for item in expiring:
        warnings.append(
            "{} の期限が近づいています（{}）".format(
                item["name"], "期限切れ" if item["days_left"] < 0 else "あと{}日".format(item["days_left"])
            )
        )

    repo = settings.get("github_repo") or ""
    stock_edit_url = (
        "https://github.com/{}/edit/main/data/stock.json".format(repo) if repo else "#"
    )

    payload = {
        "date": target_iso,
        "date_label": "{}年{}月{}日（{}）".format(
            target.year, target.month, target.day, WEEKDAYS[target.weekday()]
        ),
        "leave_time": config.fmt_hhmm(base, end),
        "target_leave": settings["target_leave"],
        "latest_leave": settings["latest_leave"],
        "slack_minutes": round((target_leave - (base + end)) / 60.0, 1),
        "makespan_minutes": summary["makespan_minutes"],
        "bento_minutes": summary["bento_minutes"],
        "timeline": build_timeline_rows(slots, base),
        "menu": menu,
        "stock": config.stock_with_expiry(stock_raw, target),
        "stock_edit_url": stock_edit_url,
        "warnings": warnings,
        "generated_at": config.now_jst().strftime("%Y-%m-%d %H:%M JST"),
    }

    print("対象日      : {}".format(target_iso))
    print("献立        : {}".format(menu.get("menu_name")))
    print("出発可能    : {}（目標 {} / 限界 {}）".format(
        payload["leave_time"], settings["target_leave"], settings["latest_leave"]))
    print("お弁当調理  : 約{}分（目安 {}分 / 上限 {}分）".format(
        summary["bento_minutes"], budget["target"], budget["max"]))
    for w in warnings:
        print("  ! {}".format(w))

    if args.dry_run:
        print("\n--dry-run のためファイルは書き換えていません。")
        return 0

    os.makedirs(config.DOCS_DIR, exist_ok=True)
    render.write_static(config.DOCS_DIR)
    with open(os.path.join(config.DOCS_DIR, "index.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render.render_page(payload))
    config.save_json(os.path.join(config.DOCS_DIR, "schedule.json"), payload)

    stock_raw["updated"] = target_iso
    config.save_json(os.path.join(config.DATA_DIR, "stock.json"), stock_raw)
    update_history(history, target_iso, menu, int(settings.get("history_keep_days", 14)))
    config.save_json(os.path.join(config.DATA_DIR, "history.json"), history)

    print("\ndocs/index.html を更新しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
