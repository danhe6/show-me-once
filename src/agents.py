"""多 agent 分工（10/28）。

  Coach agent（coach.watch / ready / answer，Spark）：练习时实时看、提示、回答。要快，单独跑。
  Monitor（本文件 health()，纯代码，不用 AI）：从镜头判断日志里统计每一步：判断次数、看不清比例、出错/跳步、速度。
      数字必须准，所以用代码算。发现问题的步骤交给 Tuner。
  Tuner agent（Wonder）：针对出问题的一步，读统计 + 镜头最近看到的描述，提出一个修改方案
      （改写"做完的样子"、拆成两步、换手机位置、补一张照片）。只是提议：老师点"Apply"才生效。
  Analyst agent（Wonder）：读代码算好的数据（每步的提示代码、掌握情况、跳步/危险标记），
      给老师写汇报和下周建议。数字全部来自代码，AI 只解释、不编数字。

每次 agent 做了什么都记到 task["agent_log"]，老师端显示成时间线。
"""
import json
import time
import uuid
from collections import defaultdict

from coach import WONDER, _ask

# ---------- Monitor：纯代码统计 ----------
UNCLEAR_BAD = 0.35   # 一步里超过 35% 的判断是"看不清"
SLOW_MS = 4500       # 平均一次判断超过 4.5 秒
MIN_N = 6            # 至少有 6 次判断才下结论


def health(t: dict, rows: list[dict]) -> dict:
    """rows = watch_log 里这个任务的记录。返回每一步的统计 + 有问题的步骤。"""
    per = defaultdict(lambda: {"n": 0, "unclear": 0, "wrong": 0, "ahead": 0, "unsafe": 0, "done": 0, "ms": 0, "errors": 0,
                               "seen": []})
    for r in rows:
        i = r.get("step")
        if i is None or i >= len(t["steps"]):
            continue
        p = per[i]
        p["n"] += 1
        p["ms"] += r.get("ms", 0)
        st = r.get("status")
        if st in p:
            p[st] += 1
        if r.get("error"):
            p["errors"] += 1
        if r.get("seeing"):
            p["seen"].append(f"{st}: {r['seeing']}")
    steps, flagged = [], []
    for i, s in enumerate(t["steps"]):
        p = per[i]
        n = p["n"]
        row = {"step": i, "text": s["text"], "n": n,
               "unclear_pct": round(100 * p["unclear"] / n) if n else 0,
               "avg_ms": round(p["ms"] / n) if n else 0,
               "wrong": p["wrong"], "ahead": p["ahead"], "unsafe": p["unsafe"], "errors": p["errors"],
               "recent_seen": p["seen"][-8:]}
        why = []
        if n >= MIN_N and p["unclear"] / n > UNCLEAR_BAD:
            why.append(f"camera could not see this step {row['unclear_pct']}% of the time")
        if n >= MIN_N and row["avg_ms"] > SLOW_MS:
            why.append(f"slow checks ({row['avg_ms']} ms)")
        if p["errors"] >= 3:
            why.append(f"{p['errors']} model errors")
        if p["unsafe"]:
            why.append(f"unsafe action seen {p['unsafe']} time(s)")
        row["problems"] = why
        if why:
            flagged.append(i)
        steps.append(row)
    total = sum(x["n"] for x in steps)
    return {"steps": steps, "flagged": flagged, "n_checks": total,
            "avg_ms": round(sum(per[i]["ms"] for i in per) / total) if total else 0}


# ---------- Tuner agent ----------
TUNE = """You are a special-education task-analysis expert helping a teacher fix ONE step of "{title}" that the
camera coach has trouble with. The coach looks at the table through a phone camera and decides when the step is done
by comparing what it sees with the step's "done_state".

All steps: {all_steps}
The problem step (#{n}): {step}
Monitor statistics for this step (computed by code, do not change them): {stats}
What the camera recently reported during this step: {seen}

Propose ONE fix. Options:
- "rewrite": clearer, more visible done_state and/or objects (most common fix for "could not see").
- "split": the step hides two actions; replace it with two steps.
- "camera": the step happens out of view; tell the teacher where to put the phone.
- "photo": the camera needs a reference; ask the teacher to take a photo of the finished step.
- "safety": an unsafe action was seen; make the step safer (follow safe technique) and keep the teacher close.
Each step text: starts with a verb, at most 8 words. done_state: something a camera can clearly see.
Return ONLY JSON:
{{"kind": "rewrite" | "split" | "camera" | "photo" | "safety",
  "problem": "one plain sentence for the teacher: what goes wrong",
  "change": "one plain sentence: what you propose",
  "new_steps": [{{"text": "...", "cue": "...", "done_state": "...", "objects": ["..."], "safety": null}}]
}}
"new_steps" replaces the problem step (1 item for rewrite/safety, 2 for split, [] for camera/photo)."""


def tune(t: dict, i: int, stat: dict) -> dict:
    s = t["steps"][i]
    stats = {k: stat[k] for k in ("n", "unclear_pct", "avg_ms", "wrong", "ahead", "unsafe", "problems")}
    res = _ask(WONDER, TUNE.format(title=t["title"], all_steps=json.dumps([x["text"] for x in t["steps"]]), n=i + 1,
                                   step=json.dumps({k: s.get(k) for k in ("text", "cue", "done_state", "objects", "safety")}),
                                   stats=json.dumps(stats), seen=json.dumps(stat.get("recent_seen", []))),
               effort="low", max_out=4000)
    if res.get("kind") not in ("rewrite", "split", "camera", "photo", "safety"):
        res["kind"] = "camera"
    if res["kind"] in ("camera", "photo"):
        res["new_steps"] = []
    return {"id": uuid.uuid4().hex[:6], "step": i, "step_text": s["text"], "ts": time.time(), "status": "open",
            "stats": stats, **{k: res.get(k) for k in ("kind", "problem", "change", "new_steps")}}


# ---------- Analyst agent ----------
ANALYST = """You are an assistant to a special-education teacher. Write a short progress report about {name}
learning "{title}". Use ONLY the facts below. They were computed by code. Never invent or change a number;
if you mention a number, it must appear in FACTS. No diagnosis, no medical or behavioral claims, no judging the person.
Plain, warm, professional English a teacher can paste into notes.

FACTS:
{facts}

Return ONLY JSON:
{{"summary": "2-3 sentences",
  "wins": ["short bullet", "..."],
  "concerns": ["short bullet about a step that still needs support, or an unsafe/skip flag", "..."],
  "next_week": [{{"step": 1, "action": "one concrete teaching action, e.g. fade to a verbal prompt, model this step, practice this chunk alone"}}],
  "iep_line": "one sentence in IEP progress-note style using numbers from FACTS"}}"""


def facts(t: dict, prog: dict, hl: dict) -> dict:
    """给 Analyst 的事实：全部由代码算。"""
    n, S = prog["n_steps"], len(prog["sessions"])
    per_step = []
    for i in range(n):
        codes = [c["code"] or "-" for c in prog["grid"][i]]
        flags = sorted({f for c in prog["grid"][i] for f in (c.get("flags") or [])})
        per_step.append({"step": i + 1, "text": prog["steps"][i], "codes_oldest_first": codes,
                         "mastered_3x_I": prog["step_mastered"][i], "flags": flags,
                         "camera_confirmed": sum(1 for c in prog["grid"][i] if c.get("v") == "camera")})
    return {"sessions": S, "pct_independent_by_session": prog["pct"],
            "baseline_pct": prog["pct"][0] if S else None, "latest_pct": prog["pct"][-1] if S else None,
            "steps_mastered": sum(prog["step_mastered"]), "n_steps": n, "task_mastered": prog["mastered"],
            "per_step": per_step,
            "camera_trouble_steps": [s["step"] + 1 for s in hl["steps"] if s["problems"]],
            "code_meaning": prog["code_names"]}


def analyst(t: dict, name: str, f: dict) -> dict:
    res = _ask(WONDER, ANALYST.format(name=name, title=t["title"], facts=json.dumps(f, ensure_ascii=False)),
               effort="low", max_out=5000)
    res["ts"] = time.time()
    res["facts"] = {k: f[k] for k in ("sessions", "baseline_pct", "latest_pct", "steps_mastered", "n_steps")}
    return res


def log(t: dict, agent: str, did: str):
    t.setdefault("agent_log", []).append({"ts": time.time(), "agent": agent, "did": did})
    t["agent_log"] = t["agent_log"][-60:]
