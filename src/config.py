"""設定ファイルの読み書きと、日時まわりの小道具。"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

JST = timezone(timedelta(hours=9))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT, "config")
DATA_DIR = os.path.join(ROOT, "data")
DOCS_DIR = os.path.join(ROOT, "docs")


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_settings() -> Dict[str, Any]:
    return load_json(os.path.join(CONFIG_DIR, "settings.json"))


def load_tasks() -> Dict[str, Any]:
    return load_json(os.path.join(CONFIG_DIR, "tasks.json"))


def load_preferences() -> Dict[str, Any]:
    return load_json(os.path.join(CONFIG_DIR, "preferences.json"))


def load_stock() -> Dict[str, Any]:
    return load_json(os.path.join(DATA_DIR, "stock.json"))


def load_history() -> Dict[str, Any]:
    return load_json(os.path.join(DATA_DIR, "history.json"))


def now_jst() -> datetime:
    return datetime.now(JST)


def parse_hhmm(value: str) -> int:
    """'05:00' -> 起点0:00からの秒数。"""
    hh, mm = value.split(":")
    return int(hh) * 3600 + int(mm) * 60


def fmt_hhmm(base_seconds: int, offset_seconds: int) -> str:
    total = base_seconds + offset_seconds
    hh = (total // 3600) % 24
    mm = (total % 3600) // 60
    return "{:02d}:{:02d}".format(int(hh), int(mm))


# 在庫の種類ごとの、期限が明記されていない場合の既定の日持ち
DEFAULT_SHELF_LIFE_DAYS = {"frozen": 30, "prepared": 4, "pantry": 180}


def stock_expiry(item: Dict[str, Any]) -> date:
    """在庫アイテムの期限日を返す。best_before があればそれを、なければ kind から推定。"""
    if item.get("best_before"):
        return date.fromisoformat(item["best_before"])
    added_raw = item.get("added") or now_jst().date().isoformat()
    added = date.fromisoformat(added_raw)
    days = DEFAULT_SHELF_LIFE_DAYS.get(item.get("kind", "pantry"), 30)
    return added + timedelta(days=days)


def stock_with_expiry(stock: Dict[str, Any], today: date) -> List[Dict[str, Any]]:
    """在庫に「あと何日」を付けて、期限が近い順に並べたリストを返す。"""
    out = []
    for item in stock.get("items", []):
        if float(item.get("quantity", 0)) <= 0:
            continue
        expiry = stock_expiry(item)
        enriched = dict(item)
        enriched["expiry"] = expiry.isoformat()
        enriched["days_left"] = (expiry - today).days
        out.append(enriched)
    out.sort(key=lambda x: x["days_left"])
    return out
