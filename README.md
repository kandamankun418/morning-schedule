# 朝のスケジュール自動生成

毎晩21時（JST）に GitHub Actions が動き、翌朝 5:00〜6:30 のタイムラインとお弁当の献立を生成して、
スマホで見られるページに反映します。**PCの電源が入っている必要はありません。**

- 公開ページ: `https://kandamankun418.github.io/morning-schedule/`
- iPhone の Safari で開き、共有ボタン →「ホーム画面に追加」でアプリのように使えます（オフラインでも開けます）

## 毎日の使い方

1. 夜のうちに生成が終わっているので、朝はホーム画面のアイコンから開くだけ
2. 終わったタスクをタップしてチェック（チェック状態は端末に保存され、日付が変わると自動で消えます）
3. お弁当のメニューと簡単な作り方は同じページの下にあります

## 手動で作り直したいとき

急な予定変更などで作り直したい場合、いちばん手軽なのは**スマホから GitHub Actions を回す**方法です。

1. `https://github.com/kandamankun418/morning-schedule/actions` を開く
2. 左の「翌朝のスケジュールを生成」を選ぶ
3. 「Run workflow」→ 必要なら日付を入れて実行（1〜2分で反映されます）

PCから実行する場合:

```bash
python src/main.py
```

```bash
python src/main.py --date 2026-08-25
```

APIを使わずに動作だけ確かめたいとき（予備の献立で生成します）:

```bash
python src/main.py --mock
```

ファイルを書き換えずに結果だけ見たいとき:

```bash
python src/main.py --mock --dry-run
```

## 設定の変え方

すべて `config/` と `data/` の JSON を書き換えるだけです。スマホからでも GitHub のWeb画面で編集できます。

### 朝のタスクや所要時間を変える — `config/tasks.json`

| 項目 | 意味 |
|---|---|
| `minutes` | 所要時間（分。小数可） |
| `attended` | `true` なら本人が張り付く必要がある。`false` なら放っておける（炊飯・レンジ待ちなど） |
| `after` | このタスクより先に終わっていないといけないタスクの `id` |
| `priority` | 大きいほど朝の早い時間に回される |
| `background` | `true` にすると出発時刻の判定から除外される（洗濯の運転など） |

新しいタスクを足すときは `id` を重複しない文字列にしてください。
`bento_done` という特別な `id` は「お弁当のおかずが全部できた時点」を意味します。

### お弁当の好みを変える — `config/preferences.json`

`likes` / `dislikes` / `allergies` に単語を並べると、翌日の提案から反映されます。
`morning_cooking_ok` を `false` にすると、朝にコンロを使わない献立だけになります。

### 在庫を管理する — `data/stock.json`

冷凍食品・作り置き・常温ストックを登録しておくと、期限が近いものから優先的に使う献立が提案されます。
生成後は、使った分が自動的に減ります。買い足したときや実際と食い違ったときは手で直してください。

ページ下部の「在庫を編集する（GitHub）」ボタンから、スマホでそのまま編集できます。

```json
{
  "id": "karaage",          // 重複しない英数字
  "name": "冷凍からあげ",
  "kind": "frozen",         // frozen(冷凍) / prepared(作り置き) / pantry(常温)
  "quantity": 12,
  "unit": "個",
  "added": "2026-08-10",
  "best_before": ""         // 空なら kind から自動判定（冷凍30日 / 作り置き4日 / 常温180日）
}
```

### 生成に使うモデルを変える — `config/settings.json`

`model` を変えるとコストが変わります（1日1回・思考トークン込みのおおよその目安）。

| モデル | 月あたりの目安 |
|---|---|
| `claude-opus-5`（既定） | 200〜300円 |
| `claude-sonnet-5` | 100〜160円 |
| `claude-haiku-4-5` | 40〜60円 |

`effort` は `low` / `medium` / `high` で、下げるとトークン消費と料金が減ります。

起床時刻や出発時刻も `settings.json` で変えられます。

## 設計メモ

**時刻の計算は Claude にやらせていません。** 献立と工程の分解（工程名・所要時間・手が離せるか・炊きたてご飯が必要か）だけを
Claude API に任せ、タイムラインの組み立ては `src/scheduler.py` が決定論的に行います。
こうすることで、生成内容がぶれても「炊飯前にご飯を詰める」といった矛盾や、時刻の足し算のズレが混入しません。

スケジューラは次の制約を守ります。

- 本人は1人しかいないので、`attended` なタスクは同時に1つだけ
- `attended=false` のタスク（炊飯・洗濯・レンジ加熱）は依存が解けた瞬間に自動で進む
- 手が空く時間には、開始できる別のタスクを詰める
- 出発時刻に間に合わない場合は警告を出し、削る候補を示す

```
config/ ─ 設定（タスク・好み・起床時刻など）
data/   ─ 在庫と履歴（生成のたびに自動更新される）
src/
  main.py       全体の流れ
  llm.py        Claude API 呼び出しと献立のスキーマ
  scheduler.py  タイムラインの組み立て（時刻計算の本体）
  render.py     スマホ向けHTMLの生成
  config.py     設定の読み書き・日時まわり
docs/   ─ GitHub Pages で公開されるファイル（自動生成）
```

## セットアップ時にやったこと

1. リポジトリを作成（public。GitHub Pages の無料枠のため）
2. `Settings → Secrets and variables → Actions` に `ANTHROPIC_API_KEY` を登録
3. `Settings → Pages` で「Deploy from a branch」→ `main` / `/docs` を選択
