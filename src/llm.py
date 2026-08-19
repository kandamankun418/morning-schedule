"""Claude API に「お弁当の献立」と「その工程」を考えてもらう部分。

Claude に任せるのは献立と工程の分解まで。時刻の計算は scheduler.py が行う。
生成が多少ぶれても、タイムラインの整合性だけは必ず保たれる。
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

MENU_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "menu_name": {"type": "string", "description": "お弁当全体の呼び名。例: からあげ弁当"},
        "items": {
            "type": "array",
            "description": "お弁当に入れる品目",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "品目名"},
                    "note": {"type": "string", "description": "簡単な作り方メモ（1〜2文）"},
                    "uses_stock": {
                        "type": "array",
                        "description": "この品目で使う在庫のid。使わないなら空配列",
                        "items": {"type": "string"},
                    },
                },
                "required": ["name", "note", "uses_stock"],
                "additionalProperties": False,
            },
        },
        "steps": {
            "type": "array",
            "description": "朝の調理工程を、時系列で実行できる粒度に分けたもの",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "工程名。例: 卵焼きを焼く"},
                    "minutes": {"type": "number", "description": "所要時間（分）"},
                    "attended": {
                        "type": "boolean",
                        "description": "本人が手を離せない工程なら true。レンジ加熱の待ちや粗熱取りなど放っておける工程は false",
                    },
                    "needs_rice": {
                        "type": "boolean",
                        "description": "炊きあがったご飯が必要な工程なら true",
                    },
                },
                "required": ["name", "minutes", "attended", "needs_rice"],
                "additionalProperties": False,
            },
        },
        "stock_consumed": {
            "type": "array",
            "description": "この献立で消費する在庫と数量",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "quantity": {"type": "number"},
                },
                "required": ["id", "quantity"],
                "additionalProperties": False,
            },
        },
        "comment": {
            "type": "string",
            "description": "ひとこと（在庫の使い切りや前日準備の提案など。1〜2文）",
        },
    },
    "required": ["menu_name", "items", "steps", "stock_consumed", "comment"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """あなたは、平日の朝に自分でお弁当を作る人のための献立アシスタントです。

守ること:
- 朝の限られた時間で、無理なく作りきれる献立だけを提案する
- 冷凍食品や前日の作り置きを積極的に使い、朝の手間を減らす
- 在庫リストにあるものを優先的に使う。特に「期限まであと何日」が少ないものから使い切る
- 直近の履歴と主菜がかぶらないようにする（3日以内に出したメインは避ける）
- 工程は「実際に手を動かす順番」で並べ、1工程あたり1〜8分程度の粒度に分ける
- レンジ加熱の待ち時間・粗熱を取る時間など、放っておける工程は attended=false にする
- 炊きあがったご飯が必要な工程は needs_rice=true にする。
  ただし「お弁当箱にご飯を詰める」工程はスケジュール側に組み込み済みなので steps には入れない
- 所要時間は実際に手を動かす時間を正直に見積もる。短く見せかけない
"""


def _weekday_ja(iso_date: str) -> str:
    from datetime import date

    names = ["月", "火", "水", "木", "金", "土", "日"]
    return names[date.fromisoformat(iso_date).weekday()]


def build_user_prompt(
    target_date: str,
    budget: Dict[str, float],
    stock: List[Dict[str, Any]],
    history: List[Dict[str, Any]],
    preferences: Dict[str, Any],
) -> str:
    lines: List[str] = []
    lines.append("【日付】{}（{}曜日）".format(target_date, _weekday_ja(target_date)))
    lines.append("")
    lines.append("【お弁当の調理に使える時間】")
    lines.append("- 目安: {} 分".format(budget["target"]))
    lines.append("- 上限: {} 分（これを超えると出発に間に合わない）".format(budget["max"]))
    lines.append(
        "- 炊飯の待ち時間が {} 分あり、その間にコンロやレンジを使う工程を進められる。"
        "工程の合計をこの待ち時間に収められると理想的".format(budget["rice_wait"])
    )
    lines.append("")

    lines.append("【いまある在庫】（期限が近い順）")
    if stock:
        for item in stock:
            lines.append(
                "- id={id} / {name} / {qty}{unit} / 種類={kind} / 期限まであと{days}日".format(
                    id=item["id"],
                    name=item["name"],
                    qty=item.get("quantity"),
                    unit=item.get("unit", ""),
                    kind=item.get("kind", ""),
                    days=item["days_left"],
                )
            )
    else:
        lines.append("- （在庫の登録なし）")
    lines.append("")

    lines.append("【直近のお弁当履歴】")
    if history:
        for h in history[:10]:
            names = "、".join(h.get("items", []))
            lines.append("- {}: {}（{}）".format(h.get("date"), h.get("menu_name"), names))
    else:
        lines.append("- （履歴なし）")
    lines.append("")

    lines.append("【好み・条件】")
    lines.append("- スタイル: {}".format(preferences.get("style", "おまかせ")))
    lines.append("- 冷凍食品を使う: {}".format("はい" if preferences.get("use_frozen_food") else "いいえ"))
    lines.append("- 作り置きを使う: {}".format("はい" if preferences.get("use_make_ahead") else "いいえ"))
    lines.append("- 朝のコンロ調理: {}".format("可" if preferences.get("morning_cooking_ok") else "不可"))
    for key, label in (("likes", "好きなもの"), ("dislikes", "苦手なもの"), ("allergies", "アレルギー")):
        values = preferences.get(key) or []
        if values:
            lines.append("- {}: {}".format(label, "、".join(values)))
    always = preferences.get("always_available") or []
    if always:
        lines.append("- 常備しているもの: {}".format("、".join(always)))
    for note in preferences.get("notes") or []:
        lines.append("- {}".format(note))
    lines.append("")
    lines.append("以上を踏まえて、明日のお弁当の献立と朝の調理工程を組み立ててください。")
    return "\n".join(lines)


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def generate_menu(
    model: str,
    effort: str,
    user_prompt: str,
    api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Claude API を呼んで献立と工程を得る。"""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    base_kwargs: Dict[str, Any] = {
        "model": model,
        "max_tokens": 16000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    try:
        response = client.messages.create(
            output_config={
                "effort": effort,
                "format": {"type": "json_schema", "schema": MENU_SCHEMA},
            },
            **base_kwargs
        )
    except TypeError:
        # SDK が output_config に未対応な場合のフォールバック
        fallback_prompt = (
            user_prompt
            + "\n\n次のJSONスキーマに厳密に従い、JSONのみを出力してください（説明文は不要）:\n"
            + json.dumps(MENU_SCHEMA, ensure_ascii=False)
        )
        base_kwargs["messages"] = [{"role": "user", "content": fallback_prompt}]
        response = client.messages.create(**base_kwargs)

    if getattr(response, "stop_reason", None) == "refusal":
        raise RuntimeError("Claude が生成を拒否しました。プロンプトを確認してください。")

    text = next((b.text for b in response.content if b.type == "text"), "")
    if not text:
        raise RuntimeError(
            "Claude から本文が返りませんでした（stop_reason={}）".format(
                getattr(response, "stop_reason", "?")
            )
        )

    data = _extract_json(text)
    usage = getattr(response, "usage", None)
    if usage is not None:
        data["_usage"] = {
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None),
        }
    return data


def fallback_menu(stock: List[Dict[str, Any]]) -> Dict[str, Any]:
    """API が使えないときの保険。在庫の先頭から機械的に組み立てる。"""
    main = next((s for s in stock if s.get("kind") == "frozen"), None)
    side = next((s for s in stock if s.get("kind") == "prepared"), None)

    items: List[Dict[str, Any]] = [{"name": "ご飯", "note": "炊きたてを詰める。", "uses_stock": []}]
    steps: List[Dict[str, Any]] = []
    consumed: List[Dict[str, Any]] = []

    if main:
        items.append(
            {"name": main["name"], "note": "袋の表示どおりに加熱する。", "uses_stock": [main["id"]]}
        )
        steps.append(
            {
                "name": "{}を加熱する".format(main["name"]),
                "minutes": 6,
                "attended": True,
                "needs_rice": False,
            }
        )
        consumed.append({"id": main["id"], "quantity": 3})
    if side:
        items.append({"name": side["name"], "note": "カップに取り分ける。", "uses_stock": [side["id"]]})
        steps.append(
            {
                "name": "{}を詰める".format(side["name"]),
                "minutes": 2,
                "attended": True,
                "needs_rice": False,
            }
        )
        consumed.append({"id": side["id"], "quantity": 1})

    items.append({"name": "卵焼き", "note": "卵2個に少量の砂糖と塩で焼く。", "uses_stock": []})
    steps.append({"name": "卵焼きを焼く", "minutes": 7, "attended": True, "needs_rice": False})
    steps.append({"name": "おかずの粗熱を取る", "minutes": 5, "attended": False, "needs_rice": False})

    return {
        "menu_name": "在庫活用のお弁当",
        "items": items,
        "steps": steps,
        "stock_consumed": consumed,
        "comment": "APIを使わずに生成した予備の献立です。",
        "_fallback": True,
    }
