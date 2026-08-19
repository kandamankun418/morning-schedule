"""スケジュールをスマホ向けの1枚のHTMLに描き出す。"""
from __future__ import annotations

import html
import json
from typing import Any, Dict, List

PAGE_TEMPLATE = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#1f6feb">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<link rel="manifest" href="./manifest.webmanifest">
<link rel="apple-touch-icon" href="./icon.png">
<title>{title}</title>
<style>
:root {{
  --bg: #f6f7f9;
  --card: #ffffff;
  --text: #16181d;
  --muted: #6b7280;
  --line: #e3e6ea;
  --accent: #1f6feb;
  --warn-bg: #fff4e5;
  --warn-line: #f0a02a;
  --warn-text: #7a4a00;
  --done: #9aa2ad;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0f1216;
    --card: #171b21;
    --text: #e8eaed;
    --muted: #9aa2ad;
    --line: #2a303a;
    --accent: #549bff;
    --warn-bg: #3a2a10;
    --warn-line: #b5801f;
    --warn-text: #ffd591;
    --done: #656d78;
  }}
}}
* {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
body {{
  margin: 0;
  padding: 0 0 3rem;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", sans-serif;
  font-size: 18px;
  line-height: 1.6;
}}
header {{
  background: var(--accent);
  color: #fff;
  padding: 1.1rem 1rem 1.2rem;
  padding-top: calc(1.1rem + env(safe-area-inset-top));
}}
header .date {{ font-size: 1rem; opacity: .9; }}
header .leave {{ font-size: 2.3rem; font-weight: 700; letter-spacing: .02em; margin: .15rem 0 0; }}
header .leave small {{ font-size: 1rem; font-weight: 400; opacity: .9; margin-left: .4rem; }}
header .slack {{ font-size: .95rem; opacity: .92; margin-top: .2rem; }}
main {{ padding: 0 .8rem; max-width: 640px; margin: 0 auto; }}
section {{
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 14px;
  margin-top: .9rem;
  overflow: hidden;
}}
h2 {{
  font-size: 1.05rem;
  margin: 0;
  padding: .8rem 1rem;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: .5rem;
}}
h2 span {{ font-size: .82rem; font-weight: 400; color: var(--muted); }}
.warn {{
  background: var(--warn-bg);
  border: 1px solid var(--warn-line);
  color: var(--warn-text);
  border-radius: 14px;
  padding: .8rem 1rem;
  margin-top: .9rem;
  font-size: .95rem;
}}
.warn p {{ margin: .25rem 0; }}
.row {{
  display: flex;
  align-items: flex-start;
  gap: .7rem;
  padding: .75rem 1rem;
  border-bottom: 1px solid var(--line);
}}
.row:last-child {{ border-bottom: 0; }}
.time {{
  flex: 0 0 4.6rem;
  font-variant-numeric: tabular-nums;
  font-weight: 700;
  font-size: 1.12rem;
  padding-top: .1rem;
}}
.body {{ flex: 1 1 auto; min-width: 0; }}
.name {{ font-size: 1.06rem; }}
.meta {{ font-size: .8rem; color: var(--muted); margin-top: .1rem; }}
.tag {{
  display: inline-block;
  font-size: .7rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0 .45rem;
  color: var(--muted);
  margin-left: .35rem;
  vertical-align: .1em;
}}
label.row {{ cursor: pointer; }}
input[type=checkbox] {{
  flex: 0 0 auto;
  width: 1.6rem;
  height: 1.6rem;
  margin: .15rem 0 0;
  accent-color: var(--accent);
}}
.row.auto {{ background: linear-gradient(90deg, transparent, transparent); opacity: .95; }}
.row.auto .time, .row.auto .name {{ color: var(--muted); font-weight: 500; }}
.row.gap {{ padding: .4rem 1rem .4rem 5.9rem; color: var(--muted); font-size: .82rem; }}
.done .name {{ text-decoration: line-through; color: var(--done); }}
.done .time {{ color: var(--done); }}
.item {{ padding: .75rem 1rem; border-bottom: 1px solid var(--line); }}
.item:last-child {{ border-bottom: 0; }}
.item .n {{ font-weight: 600; }}
.item .note {{ font-size: .9rem; color: var(--muted); margin-top: .15rem; }}
.stock {{ padding: .6rem 1rem; border-bottom: 1px solid var(--line); display: flex; justify-content: space-between; gap: .6rem; }}
.stock:last-of-type {{ border-bottom: 0; }}
.stock .q {{ color: var(--muted); font-size: .9rem; white-space: nowrap; }}
.stock.soon .d {{ color: #d9480f; font-weight: 600; }}
@media (prefers-color-scheme: dark) {{ .stock.soon .d {{ color: #ff9b6b; }} }}
.actions {{ padding: .85rem 1rem; }}
.actions a {{
  display: block;
  text-align: center;
  padding: .7rem;
  border-radius: 10px;
  border: 1px solid var(--accent);
  color: var(--accent);
  text-decoration: none;
  font-size: .95rem;
}}
footer {{ color: var(--muted); font-size: .78rem; text-align: center; padding: 1.2rem .8rem; }}
button.reset {{
  background: none; border: 1px solid var(--line); color: var(--muted);
  border-radius: 8px; padding: .35rem .7rem; font-size: .8rem; cursor: pointer;
}}
</style>
</head>
<body>
<header>
  <div class="date">{date_label}</div>
  <p class="leave">{leave_time} <small>に出発できます</small></p>
  <div class="slack">{slack_label}</div>
</header>
<main>
{warnings_html}
  <section>
    <h2>タイムライン <span>合計 {makespan} 分</span></h2>
    {timeline_html}
  </section>

  <section>
    <h2>{menu_name} <span>調理 約{bento_minutes}分</span></h2>
    {menu_html}
  </section>

  <section>
    <h2>在庫 <span>期限が近い順</span></h2>
    {stock_html}
    <div class="actions"><a href="{stock_edit_url}">在庫を編集する（GitHub）</a></div>
  </section>

  <footer>
    生成: {generated_at}<br>
    <button class="reset" id="reset">チェックをリセット</button>
  </footer>
</main>
<script>
(function () {{
  var DAY = {date_key!r};
  var boxes = document.querySelectorAll('input[type=checkbox]');
  function keyFor(i) {{ return 'ms:' + DAY + ':' + i; }}
  boxes.forEach(function (box, i) {{
    var saved = localStorage.getItem(keyFor(i));
    box.checked = saved === '1';
    box.closest('.row').classList.toggle('done', box.checked);
    box.addEventListener('change', function () {{
      localStorage.setItem(keyFor(i), box.checked ? '1' : '0');
      box.closest('.row').classList.toggle('done', box.checked);
    }});
  }});
  document.getElementById('reset').addEventListener('click', function () {{
    boxes.forEach(function (box, i) {{
      box.checked = false;
      localStorage.removeItem(keyFor(i));
      box.closest('.row').classList.remove('done');
    }});
  }});
  // 別の日のチェック状態は消しておく
  Object.keys(localStorage).forEach(function (k) {{
    if (k.indexOf('ms:') === 0 && k.indexOf('ms:' + DAY + ':') !== 0) localStorage.removeItem(k);
  }});
  if ('serviceWorker' in navigator) {{
    navigator.serviceWorker.register('./sw.js').catch(function () {{}});
  }}
}})();
</script>
</body>
</html>
"""


def _esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _minutes_label(seconds: int) -> str:
    minutes = seconds / 60.0
    if minutes < 1:
        return "{}秒".format(int(round(seconds)))
    if abs(minutes - round(minutes)) < 0.05:
        return "{}分".format(int(round(minutes)))
    return "{:.1f}分".format(minutes)


def render_timeline(rows: List[Dict[str, Any]]) -> str:
    out: List[str] = []
    for row in rows:
        if row["type"] == "gap":
            out.append(
                '<div class="row gap">ゆとり {}</div>'.format(_esc(_minutes_label(row["seconds"])))
            )
            continue

        time_label = row["start"]
        if row["end"] != row["start"]:
            meta_time = "{}〜{}".format(row["start"], row["end"])
        else:
            meta_time = row["start"]

        tags = ""
        if row["background"]:
            tags = '<span class="tag">バックグラウンド</span>'
        elif not row["attended"]:
            tags = '<span class="tag">放置OK</span>'

        meta = "{} ／ {}".format(_esc(meta_time), _esc(_minutes_label(row["seconds"])))
        inner = (
            '<div class="time">{time}</div>'
            '<div class="body"><div class="name">{name}{tags}</div>'
            '<div class="meta">{meta}</div></div>'
        ).format(time=_esc(time_label), name=_esc(row["name"]), tags=tags, meta=meta)

        if row["attended"]:
            out.append('<label class="row"><input type="checkbox">{}</label>'.format(inner))
        else:
            out.append('<div class="row auto">{}</div>'.format(inner))
    return "\n    ".join(out)


def render_menu(menu: Dict[str, Any]) -> str:
    out: List[str] = []
    for item in menu.get("items", []):
        out.append(
            '<div class="item"><div class="n">{}</div><div class="note">{}</div></div>'.format(
                _esc(item.get("name", "")), _esc(item.get("note", ""))
            )
        )
    comment = menu.get("comment")
    if comment:
        out.append('<div class="item"><div class="note">{}</div></div>'.format(_esc(comment)))
    return "\n    ".join(out)


def render_stock(stock: List[Dict[str, Any]]) -> str:
    if not stock:
        return '<div class="item"><div class="note">在庫の登録がありません。</div></div>'
    out: List[str] = []
    for item in stock:
        days = item["days_left"]
        cls = "stock soon" if days <= 3 else "stock"
        if days < 0:
            day_label = "期限切れ"
        elif days == 0:
            day_label = "今日まで"
        else:
            day_label = "あと{}日".format(days)
        out.append(
            '<div class="{cls}"><div>{name}<span class="tag">{kind}</span></div>'
            '<div class="q">{qty}{unit}・<span class="d">{days}</span></div></div>'.format(
                cls=cls,
                name=_esc(item.get("name", "")),
                kind=_esc({"frozen": "冷凍", "prepared": "作り置き", "pantry": "常温"}.get(
                    item.get("kind"), item.get("kind", "")
                )),
                qty=_esc(item.get("quantity", "")),
                unit=_esc(item.get("unit", "")),
                days=_esc(day_label),
            )
        )
    return "\n    ".join(out)


def render_page(payload: Dict[str, Any]) -> str:
    warnings = payload.get("warnings", [])
    warnings_html = ""
    if warnings:
        body = "".join("<p>{}</p>".format(_esc(w)) for w in warnings)
        warnings_html = '  <div class="warn">{}</div>'.format(body)

    slack = payload["slack_minutes"]
    if slack >= 0:
        slack_label = "目標 {} までに {} 分の余裕".format(payload["target_leave"], int(round(slack)))
    else:
        slack_label = "目標 {} を {} 分オーバー".format(payload["target_leave"], int(round(-slack)))

    return PAGE_TEMPLATE.format(
        title="{} の朝".format(payload["date"]),
        date_label=_esc(payload["date_label"]),
        leave_time=_esc(payload["leave_time"]),
        slack_label=_esc(slack_label),
        warnings_html=warnings_html,
        timeline_html=render_timeline(payload["timeline"]),
        makespan=_esc(int(round(payload["makespan_minutes"]))),
        menu_name=_esc(payload["menu"].get("menu_name", "お弁当")),
        bento_minutes=_esc(int(round(payload["bento_minutes"]))),
        menu_html=render_menu(payload["menu"]),
        stock_html=render_stock(payload["stock"]),
        stock_edit_url=_esc(payload["stock_edit_url"]),
        generated_at=_esc(payload["generated_at"]),
        date_key=payload["date"],
    )


MANIFEST = {
    "name": "朝のスケジュール",
    "short_name": "朝の段取り",
    "start_url": "./index.html",
    "scope": "./",
    "display": "standalone",
    "background_color": "#f6f7f9",
    "theme_color": "#1f6feb",
    "icons": [
        {"src": "./icon.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}
    ],
}

SERVICE_WORKER = """// オフラインでも開けるようにするための最小限のService Worker。
// 通信できるときは最新版を取りに行き、だめならキャッシュを返す。
const CACHE = 'morning-schedule-v1';
const ASSETS = ['./index.html', './manifest.webmanifest', './icon.png'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  if (event.request.method !== 'GET') return;
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy));
        return res;
      })
      .catch(() => caches.match(event.request).then((hit) => hit || caches.match('./index.html')))
  );
});
"""


def write_static(docs_dir: str) -> None:
    import os

    with open(os.path.join(docs_dir, "manifest.webmanifest"), "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(os.path.join(docs_dir, "sw.js"), "w", encoding="utf-8", newline="\n") as f:
        f.write(SERVICE_WORKER)
    # GitHub Pages が Jekyll として処理しないようにする
    with open(os.path.join(docs_dir, ".nojekyll"), "w", encoding="utf-8") as f:
        f.write("")
