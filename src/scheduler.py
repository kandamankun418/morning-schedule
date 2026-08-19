"""朝のタイムラインを組み立てる決定論的スケジューラ。

役割分担のうち「時刻計算」を担当する部分。Claude には献立と工程の分解だけを
任せ、ここでは依存関係とリソース（本人は1人しかいない）を守って
分単位のタイムラインを確定させる。

考え方:
  - attended=True のタスクは「本人が張り付く」ので、同時に1つしか実行できない
  - attended=False のタスク（炊飯・洗濯）は依存が解けた瞬間に自動で進行する
  - 手が空く時間には、開始可能な attended タスクを詰める（バックフィル）
  - 優先度は priority を第一、クリティカルパス長を第二の基準にする
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

BENTO_DONE = "bento_done"  # 「お弁当のおかずが全部できた」を表す仮想マイルストーン


class SchedulingError(Exception):
    pass


@dataclass
class Task:
    id: str
    name: str
    seconds: int
    attended: bool
    after: List[str] = field(default_factory=list)
    priority: int = 0
    background: bool = False
    kind: str = "fixed"  # fixed | bento


@dataclass
class Slot:
    task: Task
    start: int  # 起床からの経過秒
    end: int


def _minutes_to_seconds(minutes: Any) -> int:
    return int(round(float(minutes) * 60))


def build_tasks(task_defs: List[Dict[str, Any]], bento_steps: List[Dict[str, Any]]) -> List[Task]:
    """設定ファイルの固定タスク＋Claudeが出したお弁当工程を Task の一覧にする。"""
    bento_ids: List[str] = []
    tasks: List[Task] = []

    previous_bento: Optional[str] = None
    for i, step in enumerate(bento_steps, start=1):
        sid = "bento_{}".format(i)
        after: List[str] = []
        # お弁当のおかず作りは順番に進む。前の工程が終わってから次に着手する。
        # （手のかからない工程＝レンジ加熱や粗熱取りは、次の工程と自然に並行する）
        if previous_bento is not None:
            after.append(previous_bento)
        if step.get("needs_rice"):
            after.append("rice_cook")
        bento_ids.append(sid)
        previous_bento = sid
        tasks.append(
            Task(
                id=sid,
                name=step["name"],
                seconds=max(_minutes_to_seconds(step.get("minutes", 1)), 30),
                attended=bool(step.get("attended", True)),
                after=after,
                priority=0,
                background=False,
                kind="bento",
            )
        )

    for d in task_defs:
        after = [a for a in d.get("after", []) if a != BENTO_DONE]
        if BENTO_DONE in d.get("after", []):
            after.extend(bento_ids)
        tasks.append(
            Task(
                id=d["id"],
                name=d["name"],
                seconds=_minutes_to_seconds(d.get("minutes", 0)),
                attended=bool(d.get("attended", True)),
                after=after,
                priority=int(d.get("priority", 0)),
                background=bool(d.get("background", False)),
                kind="fixed",
            )
        )

    known = {t.id for t in tasks}
    for t in tasks:
        for dep in t.after:
            if dep not in known:
                raise SchedulingError(
                    "タスク '{}' が存在しない依存 '{}' を参照しています".format(t.id, dep)
                )
    return tasks


def _critical_path_lengths(tasks: List[Task]) -> Dict[str, int]:
    """各タスクについて「そこから最後までに最低限かかる時間」を求める。

    background タスク（洗濯の運転など）は出発時刻を左右しないので 0 として扱う。
    """
    by_id = {t.id: t for t in tasks}
    successors: Dict[str, List[str]] = {t.id: [] for t in tasks}
    for t in tasks:
        for dep in t.after:
            successors[dep].append(t.id)

    memo: Dict[str, int] = {}
    visiting = set()

    def walk(tid: str) -> int:
        if tid in memo:
            return memo[tid]
        if tid in visiting:
            raise SchedulingError("タスクの依存関係が循環しています: {}".format(tid))
        visiting.add(tid)
        task = by_id[tid]
        own = 0 if task.background else task.seconds
        tail = 0
        for s in successors[tid]:
            tail = max(tail, walk(s))
        visiting.discard(tid)
        memo[tid] = own + tail
        return memo[tid]

    for t in tasks:
        walk(t.id)
    return memo


def schedule(tasks: List[Task]) -> List[Slot]:
    """依存関係とリソース制約を守ってタスクを配置する（リストスケジューリング）。"""
    by_id = {t.id: t for t in tasks}
    cpl = _critical_path_lengths(tasks)

    finish: Dict[str, int] = {}
    slots: List[Slot] = []
    remaining = set(by_id)
    cursor = 0  # 本人の手が空く時刻
    guard = 0

    while remaining:
        guard += 1
        if guard > 10000:
            raise SchedulingError("スケジューリングが収束しませんでした")

        # 1) 依存が解けた「手のかからない」タスクは即座に走り出す
        moved = True
        while moved:
            moved = False
            for tid in sorted(remaining):
                t = by_id[tid]
                if t.attended:
                    continue
                if not all(d in finish for d in t.after):
                    continue
                start = max([finish[d] for d in t.after] or [0])
                finish[tid] = start + t.seconds
                slots.append(Slot(t, start, finish[tid]))
                remaining.discard(tid)
                moved = True

        if not remaining:
            break

        # 2) 手を動かすタスクを1つ選ぶ
        candidates = []
        for tid in remaining:
            t = by_id[tid]
            if not t.attended or not all(d in finish for d in t.after):
                continue
            earliest = max([finish[d] for d in t.after] or [0])
            candidates.append((max(cursor, earliest), -(t.priority * 1000000 + cpl[tid]), tid))

        if not candidates:
            raise SchedulingError(
                "配置できないタスクが残りました（依存関係を確認してください）: {}".format(
                    ", ".join(sorted(remaining))
                )
            )

        candidates.sort()
        start, _, tid = candidates[0]
        t = by_id[tid]
        finish[tid] = start + t.seconds
        slots.append(Slot(t, start, finish[tid]))
        remaining.discard(tid)
        cursor = finish[tid]

    slots.sort(key=lambda s: (s.start, 1 if s.task.background else 0, 0 if s.task.attended else 1, s.task.id))
    return slots


def makespan(slots: List[Slot]) -> int:
    """出発できる時刻（起床からの経過秒）。バックグラウンド作業は含めない。"""
    ends = [s.end for s in slots if not s.task.background]
    return max(ends) if ends else 0


def summarize(slots: List[Slot]) -> Dict[str, int]:
    """内訳を集計する（分単位）。"""
    attended = sum(s.task.seconds for s in slots if s.task.attended)
    bento = sum(s.task.seconds for s in slots if s.task.kind == "bento")
    return {
        "attended_minutes": round(attended / 60, 1),
        "bento_minutes": round(bento / 60, 1),
        "makespan_minutes": round(makespan(slots) / 60, 1),
    }
