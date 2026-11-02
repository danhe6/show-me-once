"""分步学习教练的核心：看清东西 → 拆步骤（任务分析）→ 画图卡并核对 → 练习时判断每一步。

模型分工：
- Spark（看图快）：从照片里读出物品、按钮、标签；练习时看镜头判断这一步做完没有；核对图卡。
- Wonder（agent）：按特教的任务分析规则拆步骤、给每步写可观察的结束状态，并自我检查。
- Muse Image：以学习者自己拍的照片为参考，画出每一步。
"""
import base64
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from spark import _client, _parse
import safety

SPARK = os.getenv("META_MODEL", "muse-spark-1.3")
WONDER = os.getenv("META_WONDER", "muse-wonder-1.0")
BASE = os.getenv("META_BASE_URL", "https://api.meta.ai/v1")


def _img(b: bytes, mime="image/jpeg") -> dict:
    return {"type": "input_image", "image_url": f"data:{mime};base64," + base64.b64encode(b).decode()}


def _ask(model: str, text: str, images: list[bytes] = (), effort="low", max_out=6000) -> dict:
    content = [{"type": "input_text", "text": text}] + [_img(b) for b in images]
    resp = _client.responses.create(model=model, max_output_tokens=max_out, reasoning={"effort": effort},
                                    input=[{"type": "message", "role": "user", "content": content}])
    return _parse(resp.output_text)


# ---------- 1. 看清东西 ----------
SEE_PROMPT = """You are helping someone with an intellectual disability learn a hands-on task: "{goal}".
Look at the photo(s) of THEIR OWN things. Describe only what is visible. Return ONLY JSON:
{{"object": "what the main thing is (brand/model if printed)",
  "controls": [{{"name": "e.g. power button", "label_text": "text printed on it or null", "color": "...", "where": "e.g. top right of the front panel"}}],
  "parts": ["other relevant visible parts or items, e.g. water tank, lid, cup"],
  "printed_instructions": "any instructions printed on the object, verbatim, or null",
  "missing": "if something needed for the task cannot be seen, say what photo to take (one short sentence), else null"}}"""


def see(goal: str, photos: list[bytes]) -> dict:
    if not photos:
        return {"object": None, "controls": [], "parts": [], "printed_instructions": None, "missing": None}
    return _ask(SPARK, SEE_PROMPT.format(goal=goal), photos, effort="low")


# ---------- 2. 拆步骤（任务分析） ----------
PLAN_PROMPT = """You are a special-education teacher writing a task analysis so a teen or adult with an
intellectual disability can learn: "{goal}".
What we can see of THEIR OWN things (from a photo): {seen}

Rules (follow all):
1. One physical action per step. 4 to 10 steps total. Skip nothing a beginner would need.
2. Each "text" starts with a verb, at most 8 words, plain English, no jargon (e.g. "Press the blue button on the right.").
3. Refer to things by what the learner can SEE: color, position, printed label. Use the real controls listed above.
4. "cue" = the single key word for a quick reminder (e.g. "Cup.", "Lid.", "Blue button.").
5. "done_state" = what a camera looking at the counter/table would see when the step is finished (concrete and visible,
   e.g. "a mug sits under the spout"). Never use "the person understands" or anything invisible.
6. "objects" = 1-3 short noun phrases a camera should track for this step (e.g. "mug", "water tank").
7. "safety" = a short warning if the step involves heat, blades, electricity near water, or chemicals; else null.
   Safety rules (the steps themselves must follow these; add an extra step when a rule needs one):
{safety_rules}
8. Group steps into chunks of 2-4 for chaining: "chunk" = 1, 2, 3...
   "needs" = the step numbers (1-based) that MUST be finished before this step can be done (real dependencies only:
   you cannot pour water before boiling it; but opening the tea bag and boiling water can happen in any order).
9. A caregiver supervises the first practices. Everyday household tasks (kettle, microwave, coffee maker, toaster,
   washing machine, folding, packing, simple food prep) are ALLOWED: just mark risky steps with "safety".
   Set "refuse" (short reason) ONLY if the task is not hands-on or involves {refuse}. Otherwise "refuse" must be null.
Before answering, re-check every step against rules 1-6 and fix any that break them.
Return ONLY JSON:
{{"title": "short task name, e.g. Make coffee", "refuse": null,
  "steps": [{{"text": "...", "cue": "...", "done_state": "...", "objects": ["..."], "safety": null, "chunk": 1, "needs": []}}]}}"""


def _problems(steps: list[dict]) -> list[str]:
    out = []
    for i, s in enumerate(steps, 1):
        n = len(re.findall(r"[A-Za-z']+", s.get("text", "")))
        if n > 9:
            out.append(f"step {i} has {n} words (max 8)")
        if not s.get("done_state"):
            out.append(f"step {i} has no done_state")
        if not s.get("objects"):
            out.append(f"step {i} has no objects")
    return out


def plan(goal: str, seen: dict) -> dict:
    p = PLAN_PROMPT.format(goal=goal, seen=json.dumps(seen, ensure_ascii=False), safety_rules=safety.plan_text(), refuse=safety.REFUSE)
    res = _ask(WONDER, p, effort="low", max_out=8000)
    probs = _problems(res.get("steps", []))
    if probs and not res.get("refuse"):  # 不合规就让 Wonder 自己改一遍
        res = _ask(WONDER, p + "\n\nYour previous answer broke these rules: " + "; ".join(probs)
                   + "\nPrevious answer:\n" + json.dumps(res) + "\nFix it and return the full JSON again.",
                   effort="low", max_out=8000)
    n = len(res.get("steps", []))
    for i, st in enumerate(res.get("steps", [])):
        st["hazards"] = safety.hazards(st)
        raw = st.get("needs")
        st["needs"] = sorted({int(x) - 1 for x in raw if str(x).isdigit() and 0 < int(x) <= n and int(x) - 1 != i}) \
            if isinstance(raw, list) else ([i - 1] if i else [])
    res["problems"] = _problems(res.get("steps", []))
    return res


# ---------- 3. 图卡（两帧：动作之前 → 动作进行中，前端循环播放成 2 秒小动画） ----------
STYLE = ("Flat, friendly vector illustration for a picture card. Soft warm colors, plain light cream background, "
         "simple shapes, no clutter. Hands are drawn the same way in every card (light skin tone, simple sleeves). "
         "Any arrow is one bold solid teal (#3F9E8F) arrow. NO words, letters or numbers anywhere. "
         "Careful technique: hands hold things only by their handles; the free hand rests flat on the counter, "
         "away from the action.")

ANCHOR = STYLE + """ Draw ONLY the items needed for the task "{goal}" ({items}), arranged neatly on a kitchen counter
or table, front view, so each item is easy to recognise. This picture is the reference for every step card.
Show everything in its STARTING state, before the task begins: containers empty, ingredients in their own
bowls or packages, appliances off and unplugged.
NO arrows, NO water drops, NO symbols, NO hands, NO decorations: just the items.
Give each item a clearly different color (e.g. white kettle, blue mug) so they are easy to tell apart."""

BEFORE = STYLE + """ Use EXACTLY the same items as the reference image (same shapes, colors, controls, same viewpoint).
Steps already finished (the scene must show their results): {done}.
Show the moment JUST BEFORE this step: "{text}". Hands are in place, ready to do it. Key part: {objects}.
NO arrows and NO symbols in this frame. Only items that matter for this step are in focus."""

AFTER = STYLE + """ The FIRST reference image is the previous frame. Keep everything identical (same items, colors,
viewpoint, hands, background) and change only what this action changes. Show the action happening: "{text}".
Add exactly ONE teal arrow that shows this motion, next to the key part: {objects}. No other arrows or symbols."""


def _muse(prompt: str, refs: list[bytes]) -> bytes:
    body = {"model": "muse-image-1.0", "size": "1024x1024", "output_format": "png", "response_format": "b64_json",
            "prompt": prompt, "tool_enablement": {"enable_image_search": False, "enable_web_search": False}}
    url = f"{BASE}/images/generations"
    if refs:
        body["images"] = [{"image_url": ("data:image/png;base64," if r[:4] == b"\x89PNG" else "data:image/jpeg;base64,")
                           + base64.b64encode(r).decode()} for r in refs]
        url = f"{BASE}/images/edits"
    for attempt in range(3):
        r = requests.post(url, json=body, timeout=300, headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"})
        if r.status_code < 400:
            return base64.b64decode(r.json()["data"][0]["b64_json"])
        if r.status_code not in (429, 500, 502, 503):
            break
        import time
        time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Muse Image {r.status_code}: {r.text[:300]}")


REALISTIC = ("Realistic, clear instructional photo style suitable for teens and adults (not childish), soft natural light, "
             "plain uncluttered light background.")


def _styled(prompt: str, style: str) -> str:
    """写实风格：替换开头的画风描述（适合初高中和成年学生）。"""
    if style != "realistic":
        return prompt
    first = "Flat, friendly vector illustration for a picture card. Soft warm colors, plain light cream background, simple shapes, no clutter."
    return prompt.replace(first, REALISTIC)


def make_anchor(goal: str, steps: list[dict], photo: bytes | None, style: str = "illustration") -> bytes:
    """统一物品：所有图卡都以这张为参考。有照片时以照片为准重画成同一画风。"""
    items = sorted({o for s in steps for o in s.get("objects", [])})
    return _muse(_styled(ANCHOR.format(goal=goal, items=", ".join(items)), style), [photo] if photo else [])


CHECK_CARD = """These two frames make a 2-second animation that should teach the step: "{text}" (key parts: {objects}).
Frame 1 = just before, frame 2 = the action. A beginner with an intellectual disability will copy EXACTLY what the
hands do, so judge safety strictly.
"unsafe" = true if any of these is shown: {rules}; or anything else a careful teacher would never model.
Otherwise false.
Hands must look anatomically normal (five normal fingers, natural proportions); distorted hands make "ok" false.
"ok" = true only if not unsafe AND the action and part are right AND both frames show the same items AND no text.
Return ONLY JSON {{"ok": true|false, "unsafe": true|false, "why": "one short sentence"}}"""


def check_card(before: bytes, after: bytes, step: dict) -> dict:
    return _ask(SPARK, CHECK_CARD.format(rules=safety.check_text(), text=step["text"], objects=", ".join(step.get("objects", []))),
                [before, after], effort="low")


SIMPLE = STYLE.split(" Careful technique")[0] + """ Same items as the reference image. Show: "{text}"."""


def _safe_muse(prompt: str, simple: str, refs: list[bytes]) -> bytes:
    """内容过滤偶尔误拦（如插电源）：换成最简单的描述再试一次。"""
    try:
        return _muse(prompt, refs)
    except RuntimeError as e:
        if "content_policy" not in str(e):
            raise
        return _muse(simple, refs)


NOHANDS = STYLE.split(" Careful technique")[0] + """ Use EXACTLY the same items as the reference image.
Steps already finished (the scene must show their results): {done}.
Draw ONLY the objects for this step, NO hands and NO people: "{text}". Show the end position of the objects,
with ONE teal arrow showing how they move. Key part: {objects}. {rules}"""


def make_card(step: dict, anchor: bytes | None, tries: int = 2, done: list[str] = (), style: str = "illustration") -> dict:
    """画两帧并核对；危险的画面最多重画 3 次，仍危险就标记 unsafe（照顾者端不能确认）。"""
    last = None
    objs = ", ".join(step.get("objects", []))
    if step.get("safety") or safety.hazards(step):
        # 危险步骤（烫、电、刀）不画手：AI 画的“安全动作”不可靠。只画物品 + 箭头，并建议照顾者亲手录示范。
        png = _safe_muse(_styled(NOHANDS.format(rules=safety.picture_text(safety.hazards(step) or ["heat"]), text=step["text"], objects=objs, done="; ".join(done) or "none"), style),
                         SIMPLE.format(text=step["text"]) + " No hands, no people.", [anchor] if anchor else [])
        chk = check_card(png, png, step)
        chk["unsafe"] = False if "hand" not in (chk.get("why") or "").lower() else chk.get("unsafe")
        chk["record"] = True
        return {"png": png, "before": png, "check": chk}
    for k in range(3):
        if k >= tries and not (last and last["check"].get("unsafe")):
            break
        simple = SIMPLE.format(text=step["text"])
        before = _safe_muse(_styled(BEFORE.format(text=step["text"], objects=objs, done="; ".join(done) or "none"), style),
                            simple, [anchor] if anchor else [])
        after = _safe_muse(_styled(AFTER.format(text=step["text"], objects=objs), style), simple, [before] + ([anchor] if anchor else []))
        chk = check_card(before, after, step)
        last = {"png": after, "before": before, "check": chk}
        if chk.get("ok"):
            break
    return last


# ---------- 4. 练习时看镜头：一边看一边提示 ----------
VIEW_NOTE = {
    "front": ("The phone stands IN FRONT of the learner and faces them (front camera), so you see the learner's face, "
              "body and hands from the front, with the table between you. Their right hand appears on the LEFT side "
              "of the image. Judge the hands and items on the table; ignore faces and the background."),
    "back": "The phone looks at the work area (table or counter) from the learner's side.",
}
WATCH = """You are a calm job coach watching a learner (teen or adult with an intellectual disability) through a phone
camera on a stand. {view_note}
They are on step {n} of {total}: "{text}".
When this step is finished the camera should see: {done_state}.
Things that matter for this step: {objects}.
Previous step (should already be done): {prev}.
Next step (must NOT be done yet): {next}.
{ref_note}
The LAST {k} images are camera frames about 0.6 s apart, oldest first. Compare them to see the MOTION:
what the hands are doing right now, and whether the scene is changing.
{watch_rules}
Return ONLY JSON:
{{"seeing": "what the learner is doing right now, at most 10 words, starting with 'You are' (or 'I can't see your hands')",
  "status": "not_started" | "working" | "done" | "wrong" | "ahead" | "unsafe" | "unclear",
  "hint": "the single next tiny action, at most 8 calm words, or null if done",
  "evidence": "if done: the visible thing that proves it, else null"}}
Status rules:
- "done": the finished state is clearly visible in the newest frame. Be strict: if unsure, use "working".
- "working": they are doing this step or getting ready; hint = the next small movement.
- "not_started": nothing related to this step is happening yet; hint = how to start.
- "wrong": they are clearly doing something else or using the wrong item; hint = how to fix.
- "ahead": they skipped this step and are doing the next step; hint = go back to this step.
- "unsafe": {unsafe_def}; hint = "Stop. Put it down. Wait for your teacher."
- "unclear": the hands or the key items are not in view; hint = how to move the phone or the items."""


def watch(frames: list[bytes], steps: list[dict], i: int, ref: bytes | None = None, view: str = "back") -> dict:
    s = steps[i]
    hz = s.get("hazards") or safety.hazards(s)
    rules = safety.watch_text(hz)
    imgs = ([ref] if ref else []) + list(frames)
    p = WATCH.format(n=i + 1, total=len(steps), text=s["text"], done_state=s.get("done_state", ""),
                     objects=", ".join(s.get("objects", [])),
                     prev=steps[i - 1]["text"] if i > 0 else "none",
                     next=steps[i + 1]["text"] if i + 1 < len(steps) else "none (this is the last step)",
                     ref_note=("The FIRST image is the teacher's reference photo of this step being done correctly "
                               "(different person/angle is fine)." if ref else ""),
                     k=len(frames),
                     view_note=("The phone stands IN FRONT of the learner and faces them (front camera), so you see "
                                "the learner's face, body and hands from the front, with the table between you. "
                                "Their right hand appears on the LEFT side of the image. Judge the hands and items on the table; "
                                "ignore faces and the background." if view == "front" else
                                "The phone looks at the work area (table or counter) from the learner's side."),
                     watch_rules=("Safety: watch for " + rules + ".") if rules else "",
                     unsafe_def=rules or "something that could hurt them is about to happen")
    res = _ask(SPARK, p, imgs, effort="minimal", max_out=1500)
    if res.get("status") not in ("not_started", "working", "done", "wrong", "ahead", "unsafe", "unclear"):
        res["status"] = "unclear"
    return res


ORDER = """These are the steps of "{title}", written by a teacher:
{steps}
For each step, list the step numbers that MUST be finished before it can be done. Only real dependencies: something
physically needed (water must be boiled before pouring) or a safety reason. If two steps can happen in either order,
neither needs the other. Return ONLY JSON: {{"needs": [[numbers for step 1], [numbers for step 2], ...]}}"""


def infer_order(title: str, steps: list[dict]) -> list[list[int]]:
    """推断每一步真正依赖哪些步骤（0 开始的下标）。失败时退回固定顺序。"""
    n = len(steps)
    try:
        res = _ask(WONDER, ORDER.format(title=title, steps="\n".join(f"{i + 1}. {s['text']}" for i, s in enumerate(steps))),
                   effort="low", max_out=3000)
        out = []
        for i, row in enumerate(res.get("needs", [])[:n]):
            out.append(sorted({int(x) - 1 for x in row if str(x).isdigit() and 0 < int(x) <= n and int(x) - 1 != i}))
        if len(out) == n:
            return out
    except Exception:  # noqa: BLE001
        pass
    return [[i - 1] if i else [] for i in range(n)]


def available(steps: list[dict], done: set[int]) -> list[int]:
    """现在可以做的步骤：还没做、依赖都做完了。"""
    return [i for i, s in enumerate(steps) if i not in done and all(j in done for j in (s.get("needs") if s.get("needs") is not None else ([i - 1] if i else [])))]


WATCH_FLEX = """You are a calm job coach watching a learner (teen or adult with an intellectual disability) through a phone
camera. {view_note}
Task: "{title}". The steps can be done in any order that respects their dependencies.
Already finished: {done}.
Steps they may do now (any of these is fine): {avail}.
Steps that must WAIT (something else first): {locked}.
{ref_note}
The LAST {k} images are camera frames about 0.6 s apart, oldest first. Compare them to see the MOTION.
{watch_rules}
Return ONLY JSON:
{{"seeing": "what the learner is doing right now, at most 10 words, starting with 'You are' (or 'I can't see your hands')",
  "step": the number of the step they are working on or just finished (from the lists above), or null,
  "status": "idle" | "working" | "done" | "too_early" | "wrong" | "unsafe" | "unclear",
  "hint": "the single next tiny action, at most 8 calm words, or null",
  "evidence": "if done: the visible thing that proves it, else null"}}
Status rules:
- "done": that step's finished state is clearly visible in the newest frame. Be strict.
- "working": they are doing one of the steps they may do now.
- "idle": nothing is happening; hint = suggest ONE step they may do now.
- "too_early": they are doing a step that must wait; hint = what to do first.
- "wrong": they are doing a step the wrong way or with the wrong item; hint = how to fix.
- "unsafe": {unsafe_def}; hint = "Stop. Put it down. Wait for your teacher."
- "unclear": hands or items not in view; hint = how to move the phone or items."""


def watch_flex(frames: list[bytes], steps: list[dict], done: set[int], title: str, focus: int | None = None,
               ref: bytes | None = None, view: str = "back") -> dict:
    avail = available(steps, done)
    locked = [i for i in range(len(steps)) if i not in done and i not in avail]
    fmt = lambda ids: "; ".join(f"{i + 1}. {steps[i]['text']} (done when: {steps[i].get('done_state', '')})" for i in ids) or "none"  # noqa: E731
    hz = sorted({h for i in avail for h in (steps[i].get("hazards") or safety.hazards(steps[i]))})
    rules = safety.watch_text(hz)
    p = WATCH_FLEX.format(
        view_note=VIEW_NOTE.get(view, VIEW_NOTE["back"]), title=title,
        done="; ".join(f"{i + 1}. {steps[i]['text']}" for i in sorted(done)) or "nothing yet",
        avail=fmt(avail), locked=fmt(locked),
        ref_note=("The FIRST image is the teacher's reference photo of step %d being done correctly." % (focus + 1)) if ref and focus is not None else "",
        k=len(frames), watch_rules=("Safety: watch for " + rules + ".") if rules else "",
        unsafe_def=rules or "something that could hurt them is about to happen")
    res = _ask(SPARK, p, ([ref] if ref else []) + list(frames), effort="minimal", max_out=1500)
    if res.get("status") not in ("idle", "working", "done", "too_early", "wrong", "unsafe", "unclear"):
        res["status"] = "unclear"
    try:
        k = int(res.get("step")) - 1
        res["step"] = k if 0 <= k < len(steps) else None
    except (TypeError, ValueError):
        res["step"] = None
    if res["status"] == "done" and res["step"] not in avail:   # 只能勾掉"现在可以做"的步骤
        res["status"] = "too_early" if res["step"] in locked else "working"
    res["available"] = avail
    return res


def judge(frame: bytes, steps: list[dict], i: int) -> dict:   # 旧接口，保留给旧脚本
    return watch([frame], steps, i)


# ---------- 6. 对话式教练：听学生说想做什么 → 看桌上东西齐不齐 → 回答学生的问题 ----------
INTENT = """A learner (teen or adult with an intellectual disability) was asked "What do you want to do today?"
They said: "{said}"
Tasks their teacher has approved for them: {tasks}
Pick the task they mean. Speech-to-text can be messy, so match by meaning ("tea" = "Make a cup of tea").
Return ONLY JSON: {{"task_id": "id from the list, or null if none fits",
 "say": "what the coach says back, at most 14 warm, simple words"}}
If a task fits, "say" confirms it (e.g. "Great, let's make tea together!").
If none fits, "say" is kind (e.g. "That sounds fun! I'll ask your teacher to add it.")."""


def intent(said: str, tasks: list[dict]) -> dict:
    lst = json.dumps([{"id": t["id"], "title": t["title"]} for t in tasks])
    res = _ask(SPARK, INTENT.format(said=said, tasks=lst), effort="minimal", max_out=800)
    if res.get("task_id") not in {t["id"] for t in tasks}:
        res["task_id"] = None
    return res


READY = """A learner is about to start the task "{title}". The phone camera looks at their table.
Things they will need: {items}.
Count only separate things you can pick up or move (a kettle's switch or base is part of the kettle; ignore
things that only appear later, like hot water). Look at the newest frame. Return ONLY JSON:
{{"have": ["needed things you can clearly see"], "missing": ["needed things you cannot see"],
 "say": "at most 16 warm, simple words: name what you see, then ask for what is missing (or say we are ready)"}}"""


def ready(frames: list[bytes], title: str, items: list[str]) -> dict:
    res = _ask(SPARK, READY.format(title=title, items=", ".join(items)), list(frames)[-1:], effort="minimal", max_out=800)
    res.setdefault("missing", [])
    return res


ANSWER = """You are a calm, kind job coach. A learner with an intellectual disability is doing "{title}",
step {n} of {total}: "{text}". They asked you: "{q}"
The image is what the camera sees right now.
Answer in at most 15 simple words, one idea, about THIS step only. Use what you see (colors, left/right from the
learner's side). Never give medical advice. If they ask to skip or to do something unsafe, gently say no and
suggest asking the teacher. Return ONLY JSON: {{"say": "..."}}"""


def answer(frame: bytes | None, title: str, steps: list[dict], i: int, q: str) -> dict:
    return _ask(SPARK, ANSWER.format(title=title, n=i + 1, total=len(steps), text=steps[i]["text"], q=q),
                [frame] if frame else [], effort="minimal", max_out=800)


# ---------- 5. 提示逐步撤除 ----------
LEVELS = ["independent", "word", "picture", "model"]   # 由弱到强；"help" 单独记录


def next_level(history: list[tuple[str, int]], current: int) -> int:
    """history：这一步过去每次练习的 (结果, 当时的提示级别)；结果 'clean' 一次做对 / 'error' 出过错 / 'help' 请人帮忙。
    规则：出错或请人帮忙 → 提示加强一级；在当前级别连续 2 次做对 → 提示减弱一级；
    'self'（镜头没看清、学习者自己点了完成）不改变级别。"""
    if not history:
        return current
    if history[-1][0] in ("error", "help"):
        return min(current + 1, len(LEVELS) - 1)
    tail = history[-2:]
    if len(tail) == 2 and all(r == "clean" and lv == current for r, lv in tail):
        return max(current - 1, 0)
    return current
