"""分步学习教练 · 后端。启动：uvicorn app:app --host 0.0.0.0 --port 8000

学习者端：/#learner      照顾者端：/#caregiver
数据：data/coach/tasks/<任务id>/task.json + photo.jpg + cards/<i>.png（不保存练习视频）
"""
import io
import json
import os
import sys
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
import coach  # noqa: E402
import safety  # noqa: E402
import agents  # noqa: E402
from spark import _client, _parse  # noqa: E402

app = FastAPI(title="Step coach")
TOKEN = os.getenv("APP_TOKEN")  # 公网访问口令；本机调试可不设
DATA = ROOT / "data/coach/tasks"
DATA.mkdir(parents=True, exist_ok=True)
LOCK = threading.Lock()


@app.middleware("http")
async def guard(request, call_next):
    if TOKEN and request.url.path.startswith("/api/") and TOKEN not in (request.headers.get("x-k"), request.query_params.get("k")):
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    return await call_next(request)


# ---------- 存取 ----------
def _dir(tid: str) -> Path:
    d = DATA / tid
    if not d.exists():
        raise HTTPException(404, "task not found")
    return d


def load(tid: str) -> dict:
    return json.loads((_dir(tid) / "task.json").read_text())


def save(t: dict):
    with LOCK:
        p = DATA / t["id"] / "task.json"
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(t, ensure_ascii=False, indent=1))
        tmp.replace(p)


STUDENTS = ROOT / "data/coach/students.json"


def students() -> list[dict]:
    return json.loads(STUDENTS.read_text()) if STUDENTS.exists() else []


def _learner(t: dict, sid: str) -> dict:
    """每个学生在每个任务上各自的提示级别和历史。"""
    n = len(t["steps"])
    L = t.setdefault("learners", {}).setdefault(sid, {"levels": [3] * n, "history": [[] for _ in range(n)]})
    L["levels"] = (L["levels"] + [3] * n)[:n]
    L["history"] = (L["history"] + [[] for _ in range(n)])[:n]
    return L


def _small_jpeg(raw: bytes, side=1280) -> bytes:
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(400, "not an image")
    h, w = img.shape[:2]
    k = min(1.0, side / max(h, w))
    return cv2.imencode(".jpg", cv2.resize(img, (int(w * k), int(h * k))), [cv2.IMWRITE_JPEG_QUALITY, 88])[1].tobytes()


def _draw(tid: str, idx: list[int]):
    """后台画图卡（并行），每画完一张就写回 task.json。"""
    d = DATA / tid
    t0 = load(tid)
    steps = t0["steps"]
    (d / "cards").mkdir(exist_ok=True)
    anchor_p = d / "anchor.png"
    if not anchor_p.exists():   # 统一物品：先画一张“这件事用到的所有东西”，之后每张图卡都以它为参考
        photo = (d / "photo.jpg").read_bytes() if (d / "photo.jpg").exists() else None
        try:
            anchor_p.write_bytes(coach.make_anchor(t0["goal"], steps, photo, t0.get("style", "illustration")))
        except Exception as e:  # noqa
            print("anchor failed", e)
    anchor = anchor_p.read_bytes() if anchor_p.exists() else None

    def one(i):
        try:
            c = coach.make_card(steps[i], anchor, done=[s["text"] for s in steps[:i]], style=t0.get("style", "illustration"))
            (d / "cards" / f"{i}a.png").write_bytes(c["before"])
            (d / "cards" / f"{i}.png").write_bytes(c["png"])
            chk = c["check"]
            state = "unsafe" if chk.get("unsafe") else "ready" if chk.get("ok") else "check"
            st = {"state": state, "why": chk.get("why"), "v": int(time.time()), "record": bool(chk.get("record"))}
        except Exception as e:  # noqa
            st = {"state": "error", "why": str(e)[:200]}
        with LOCK:
            t = json.loads((d / "task.json").read_text())
            if i < len(t["steps"]):
                t["steps"][i]["card"] = st
            (d / "task.json").write_text(json.dumps(t, ensure_ascii=False, indent=1))

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(one, idx))


# ---------- 学生 ----------
class NewStudent(BaseModel):
    name: str


@app.get("/api/students")
def list_students():
    return students()


@app.post("/api/students")
def add_student(req: NewStudent):
    st = students()
    sid = uuid.uuid4().hex[:6]
    st.append({"id": sid, "name": req.name.strip()[:40]})
    STUDENTS.write_text(json.dumps(st, ensure_ascii=False, indent=1))
    return {"id": sid, "name": req.name.strip()[:40]}


# ---------- 任务 ----------
@app.post("/api/tasks")
async def create_task(goal: str = Form(...), photo: UploadFile | None = File(None), style: str = Form("illustration"),
                      media: str = Form("live")):
    """media = "live"（默认：不用图片，AI 看着镜头一步步语音指导；照片可选）、"photos"（每步拍真实照片）或 "ai"（AI 画图卡草稿）。"""
    tid = uuid.uuid4().hex[:10]
    d = DATA / tid
    d.mkdir(parents=True)
    photos = []
    if photo is not None:
        jpg = _small_jpeg(await photo.read())
        (d / "photo.jpg").write_bytes(jpg)
        photos = [jpg]
    seen = coach.see(goal, photos)
    pl = coach.plan(goal, seen)
    t = {"id": tid, "goal": goal, "title": pl.get("title") or goal, "created": time.time(), "approved": False,
         "seen": seen, "refuse": pl.get("refuse"), "problems": pl.get("problems", []),
         "steps": [dict(s, card={"state": {"ai": "drawing", "photos": "needs_photo"}.get(media, "none")}) for s in pl.get("steps", [])],
         "levels": [3] * len(pl.get("steps", [])), "history": [[] for _ in pl.get("steps", [])],
         "sessions": [], "has_photo": bool(photos), "assigned": [], "learners": {},
         "style": "realistic" if style == "realistic" else "illustration", "media": media if media in ("ai", "photos") else "live", "order": "flex"}
    (d / "task.json").write_text(json.dumps(t, ensure_ascii=False, indent=1))
    if t["steps"] and not t["refuse"] and t["media"] == "ai":
        threading.Thread(target=_draw, args=(tid, list(range(len(t["steps"])))), daemon=True).start()
    return t


@app.get("/api/tasks")
def list_tasks(student: str | None = None):
    out = []
    for p in sorted(DATA.glob("*/task.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        if p.parent.name.startswith("_"):   # 已归档
            continue
        t = json.loads(p.read_text())
        row = {k: t.get(k) for k in ("id", "title", "goal", "approved", "created", "has_photo")}
        row |= {"n_steps": len(t["steps"]), "assigned": t.get("assigned", []),
                "per_student": {sid: {"levels": _learner(t, sid)["levels"],
                                      "n_sessions": sum(1 for x in t["sessions"] if x.get("student") == sid and x.get("end")),
                                      "mastered": _mastered(t, sid)} for sid in t.get("assigned", [])}}
        if student and student not in row["assigned"]:
            continue
        out.append(row)
    return out


@app.get("/api/tasks/{tid}")
def get_task(tid: str):
    t = load(tid)
    for st in t["steps"]:   # 旧任务没有 hazards 字段：按统一安全规则现算
        st.setdefault("hazards", safety.hazards(st))
    t.setdefault("order", "flex")
    if t["steps"] and any(st.get("needs") is None for st in t["steps"]):   # 旧任务：推断步骤之间真正的先后依赖
        _set_order(t)
        save(t)
    return t


def _set_order(t: dict):
    for st, nd in zip(t["steps"], coach.infer_order(t["title"], t["steps"])):
        st["needs"] = nd


def _reorder_bg(tid: str):
    def run():
        t = load(tid)
        _set_order(t)
        save(t)
    threading.Thread(target=run, daemon=True).start()


class StepEdit(BaseModel):
    text: str
    cue: str | None = None
    done_state: str | None = None
    objects: list[str] | None = None
    safety: str | None = None
    chunk: int | None = None


class TaskEdit(BaseModel):
    order: str | None = None     # flex = 合理的顺序都可以 | fixed = 每次同一个顺序
    assigned: list[str] | None = None
    title: str | None = None
    approved: bool | None = None
    steps: list[StepEdit] | None = None


@app.patch("/api/tasks/{tid}")
def edit_task(tid: str, req: TaskEdit):
    t = load(tid)
    redraw = []
    if req.title is not None:
        t["title"] = req.title
    if req.steps is not None:
        old = {s["text"]: s for s in t["steps"]}
        new = []
        for i, s in enumerate(req.steps):
            prev = old.get(s.text)
            row = {k: v for k, v in s.model_dump().items() if v is not None}
            if prev:   # 文字没变：保留图卡（图卡文件按位置存，位置变了也重画）
                keep_card = prev.get("card") if t["steps"].index(prev) == i else None
                if prev.get("photo"):   # 真实照片跟着步骤走，位置变了也不用重拍
                    keep_card = prev.get("card")
                row = {**prev, **row, "card": keep_card or {"state": {"ai": "drawing", "photos": "needs_photo"}.get(t.get("media"), "none")}}
                if not keep_card and t.get("media") == "ai":
                    redraw.append(i)
            else:
                row.setdefault("objects", [])
                row.setdefault("done_state", s.text)
                if t.get("media") == "ai":
                    row["card"] = {"state": "drawing"}
                    redraw.append(i)
                else:
                    row["card"] = {"state": "needs_photo" if t.get("media") == "photos" else "none"}
            row["hazards"] = safety.hazards(row)
            new.append(row)
        changed = [x["text"] for x in t["steps"]] != [x["text"] for x in new]
        t["steps"] = new
        if changed:   # 步骤变了：先退回固定顺序，后台重新推断依赖
            for i, row in enumerate(new):
                row["needs"] = [i - 1] if i else []
        for sid in list(t.get("learners", {})):
            _learner(t, sid)
    if req.order in ("flex", "fixed"):
        t["order"] = req.order
    if req.approved is not None:
        t["approved"] = req.approved
    if req.assigned is not None:
        t["assigned"] = req.assigned
        for sid in req.assigned:
            _learner(t, sid)
    save(t)
    if req.steps is not None and changed:
        _reorder_bg(tid)
    if redraw:
        threading.Thread(target=_draw, args=(tid, redraw), daemon=True).start()
    return t


@app.post("/api/tasks/{tid}/steps/{i}/photo")
async def step_photo(tid: str, i: int, photo: UploadFile = File(...)):
    """老师给这一步拍的真实照片（引导拍照）。照片就是示范，不经过 AI 改动。"""
    t = load(tid)
    if not 0 <= i < len(t["steps"]):
        raise HTTPException(404)
    name = f"p_{uuid.uuid4().hex[:8]}.jpg"
    (_dir(tid) / "cards").mkdir(exist_ok=True)
    (_dir(tid) / "cards" / name).write_bytes(_small_jpeg(await photo.read(), 1280))
    t["steps"][i]["photo"] = name
    t["steps"][i]["card"] = {"state": "photo", "v": int(time.time())}
    save(t)
    return t["steps"][i]


@app.post("/api/tasks/{tid}/steps/{i}/voice")
async def step_voice(tid: str, i: int, audio: UploadFile = File(...)):
    """老师给这一步录的口令（真人声音，学生熟悉的声音，比合成音自然）。"""
    t = load(tid)
    if not 0 <= i < len(t["steps"]):
        raise HTTPException(404)
    raw = await audio.read()
    if len(raw) > 3_000_000:
        raise HTTPException(413, "too long")
    ext = "m4a" if "mp4" in (audio.content_type or "") or "m4a" in (audio.filename or "") else "webm"
    name = f"v_{uuid.uuid4().hex[:8]}.{ext}"
    (_dir(tid) / "cards").mkdir(exist_ok=True)
    (_dir(tid) / "cards" / name).write_bytes(raw)
    t["steps"][i]["voice"] = name
    save(t)
    return t["steps"][i]


@app.delete("/api/tasks/{tid}/steps/{i}/voice")
def del_voice(tid: str, i: int):
    t = load(tid)
    t["steps"][i].pop("voice", None)
    save(t)
    return t["steps"][i]


@app.get("/api/tasks/{tid}/voice/{name}")
def voice_file(tid: str, name: str):
    p = _dir(tid) / "cards" / Path(name).name
    if not p.exists() or not p.name.startswith("v_"):
        raise HTTPException(404)
    return FileResponse(p, media_type="audio/mp4" if p.suffix == ".m4a" else "audio/webm")


@app.post("/api/tasks/{tid}/draw_missing")
def draw_missing(tid: str):
    """可选：给还没有照片的步骤生成 AI 图卡草稿。"""
    t = load(tid)
    idx = [i for i, s in enumerate(t["steps"]) if not s.get("photo")]
    for i in idx:
        t["steps"][i]["card"] = {"state": "drawing"}
    save(t)
    if idx:
        threading.Thread(target=_draw, args=(tid, idx), daemon=True).start()
    return {"drawing": idx}


@app.post("/api/tasks/{tid}/steps/{i}/redraw")
def redraw(tid: str, i: int):
    t = load(tid)
    t["steps"][i]["card"] = {"state": "drawing"}
    save(t)
    threading.Thread(target=_draw, args=(tid, [i]), daemon=True).start()
    return {"ok": True}


@app.get("/api/tasks/{tid}/cards/{name}.png")
def card(tid: str, name: str):
    """name = "3"（动作中，也是静态图卡）或 "3a"（动作之前）。返回压缩过的 JPEG（原图 PNG 约 1.5MB）。"""
    import re as _re
    if not _re.fullmatch(r"\d+a?", name):
        raise HTTPException(404)
    t = load(tid)
    i = int(name.rstrip("a"))
    if i < len(t["steps"]) and t["steps"][i].get("photo"):   # 有真实照片就用照片（没有“动作前”那一帧）
        if name.endswith("a"):
            raise HTTPException(404)
        return FileResponse(_dir(tid) / "cards" / t["steps"][i]["photo"], media_type="image/jpeg",
                            headers={"Cache-Control": "max-age=3600"})
    png = _dir(tid) / "cards" / f"{name}.png"
    if not png.exists():
        raise HTTPException(404)
    jpg = png.with_suffix(".jpg")
    if not jpg.exists() or jpg.stat().st_mtime < png.stat().st_mtime:
        import cv2
        img = cv2.imread(str(png))
        img = cv2.resize(img, (768, 768), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(jpg), img, [cv2.IMWRITE_JPEG_QUALITY, 84])
    return FileResponse(jpg, media_type="image/jpeg", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/tasks/{tid}/anchor.png")
def anchor_img(tid: str):
    p = _dir(tid) / "anchor.png"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


@app.get("/api/tasks/{tid}/photo.jpg")
def photo(tid: str):
    p = _dir(tid) / "photo.jpg"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")


@app.delete("/api/tasks/{tid}")
def archive(tid: str):
    d = _dir(tid)
    d.rename(d.with_name("_archived_" + d.name))
    return {"ok": True}


# ---------- 练习 ----------
class StartReq(BaseModel):
    student: str


@app.post("/api/tasks/{tid}/sessions")
def start_session(tid: str, req: StartReq):
    t = load(tid)
    L = _learner(t, req.student)
    s = {"id": uuid.uuid4().hex[:8], "student": req.student, "start": time.time(), "end": None,
         "levels": list(L["levels"]), "results": {}}
    t["sessions"].append(s)
    save(t)
    _live(s["id"]).update(student=req.student)
    return {"session": s["id"], "levels": s["levels"], "level_names": coach.LEVELS}


# ---------- 练习时：镜头一边看一边提示；老师实时看到 ----------
# LIVE 只在内存里：每个正在练习的学生最新一帧 + 模型看到了什么。不存视频；
# 只有"这一步做完了"的那一帧作为证据小图存盘，老师在数据表里可以点开核对。
LIVE: dict[str, dict] = {}
WATCH_LOG = ROOT / "data/coach/watch_log.jsonl"


def _live(sid: str) -> dict:
    return LIVE.setdefault(sid, {"ts": time.time(), "ev": {}, "confirm": None, "help": False, "events": []})


@app.post("/api/tasks/{tid}/judge")
async def judge(tid: str, step: int = Form(...), session: str = Form(""), view: str = Form("back"), done: str = Form(""),
                frames: list[UploadFile] = File(...)):
    t = load(tid)
    imgs = [await f.read() for f in frames][-3:]
    st = t["steps"][step]
    ref = None
    if st.get("photo") and (_dir(tid) / "cards" / st["photo"]).exists():
        ref = _small_jpeg((_dir(tid) / "cards" / st["photo"]).read_bytes(), 640)
    t0 = time.time()
    try:
        if t.get("order", "flex") == "flex":
            done_set = {int(x) for x in done.split(",") if x.strip().isdigit()}
            res = coach.watch_flex(imgs, t["steps"], done_set, t["title"], step, ref, view)
            if res.get("step") is not None:
                step = res["step"]
                st = t["steps"][step]
        else:
            res = coach.watch(imgs, t["steps"], step, ref, view)
    except Exception as e:  # 模型偶尔超时：前端当作没看清，继续下一轮
        res = {"status": "unclear", "seeing": None, "hint": None, "error": str(e)[:200]}
    res["ms"] = int((time.time() - t0) * 1000)
    with open(WATCH_LOG, "a") as f:
        f.write(json.dumps({"ts": round(t0, 1), "task": tid, "session": session, "step": step, **res}) + "\n")
    if session:
        L = _live(session)
        last = _small_jpeg(imgs[-1], 640)
        if L.get("step") != step:
            L["step_t0"] = time.time()
        L.update(ts=time.time(), task=tid, title=t["title"], step=step, total=len(t["steps"]), text=st["text"],
                 status=res["status"], seeing=res.get("seeing"), hint=res.get("hint"), frame=last)
        if res["status"] == "done":
            L["ev"][step] = last
        if res["status"] in ("unsafe", "ahead", "wrong") and (not L["events"] or L["events"][-1][1:3] != [step, res["status"]]):
            L["events"].append([time.time(), step, res["status"], res.get("seeing")])
        res["confirmed"] = L.get("confirm") == step
    return res


class StepResult(BaseModel):
    step: int
    result: str          # clean | error | help
    secs: float = 0
    errors: int = 0
    verified: str = "camera"   # camera = 镜头确认 | teacher = 老师确认 | self = 旧版：学生自己点（不算独立）


@app.post("/api/tasks/{tid}/sessions/{sid}/step")
def record_step(tid: str, sid: str, r: StepResult):
    t = load(tid)
    s = next((x for x in t["sessions"] if x["id"] == sid), None)
    if not s:
        raise HTTPException(404, "session not found")
    cell = {"result": r.result, "level": s["levels"][r.step], "secs": round(r.secs, 1), "errors": r.errors,
            "verified": r.verified}
    L = LIVE.get(sid) or {}
    ev = L.get("ev", {}).get(r.step) or (L.get("frame") if r.verified == "teacher" else None)
    if ev:   # 证据小图：这一步做完那一刻的画面
        (_dir(tid) / "evidence").mkdir(exist_ok=True)
        name = f"{sid}_{r.step}.jpg"
        (_dir(tid) / "evidence" / name).write_bytes(ev)
        cell["evidence"] = name
    if L.get("events"):
        cell["flags"] = sorted({e[2] for e in L["events"] if e[1] == r.step})
    s["results"][str(r.step)] = cell
    if L:
        L["confirm"] = None
        L["help"] = False
    save(t)
    return {"ok": True}


@app.get("/api/tasks/{tid}/evidence/{name}")
def evidence(tid: str, name: str):
    p = _dir(tid) / "evidence" / Path(name).name
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg")


class IntentReq(BaseModel):
    student: str
    said: str


@app.post("/api/intent")
def intent(req: IntentReq):
    """学生说"今天想做什么" → 只在老师批准、分给这个学生的任务里找。找不到就记下来交给老师。"""
    tasks = [t for t in list_tasks(req.student) if t.get("approved")]
    res = coach.intent(req.said, tasks) if tasks else {"task_id": None, "say": "Let's ask your teacher to add that."}
    if not res.get("task_id"):
        p = ROOT / "data/coach/requests.json"
        reqs = json.loads(p.read_text()) if p.exists() else []
        reqs.append({"student": req.student, "said": req.said[:200], "ts": time.time(), "done": False})
        p.write_text(json.dumps(reqs, ensure_ascii=False, indent=1))
    return res


@app.get("/api/requests")
def requests_list():
    p = ROOT / "data/coach/requests.json"
    names = {x["id"]: x["name"] for x in students()}
    reqs = json.loads(p.read_text()) if p.exists() else []
    return [dict(r, i=i, name=names.get(r["student"], "?")) for i, r in enumerate(reqs) if not r.get("done")]


@app.post("/api/requests/{i}/done")
def request_done(i: int):
    p = ROOT / "data/coach/requests.json"
    reqs = json.loads(p.read_text())
    reqs[i]["done"] = True
    p.write_text(json.dumps(reqs, ensure_ascii=False, indent=1))
    return {"ok": True}


@app.post("/api/tasks/{tid}/ready")
async def ready(tid: str, frames: list[UploadFile] = File(...)):
    """开始前看一眼桌上：要用的东西齐了没有。"""
    t = load(tid)
    items = sorted({o for s in t["steps"] for o in s.get("objects", [])})[:8]
    imgs = [await f.read() for f in frames]
    try:
        return coach.ready(imgs, t["title"], items)
    except Exception as e:
        return {"have": [], "missing": [], "say": "", "error": str(e)[:200]}


@app.post("/api/tasks/{tid}/ask")
async def ask(tid: str, step: int = Form(...), q: str = Form(...), frame: UploadFile | None = File(None)):
    """练习中学生按住说话问问题 → 看着镜头回答一句。"""
    t = load(tid)
    try:
        return coach.answer(await frame.read() if frame else None, t["title"], t["steps"], step, q[:300])
    except Exception:
        return {"say": "Good question. Let's ask your teacher."}


@app.get("/api/live")
def live():
    """老师端：正在练习的学生（最近 30 秒有画面的）。"""
    names = {x["id"]: x["name"] for x in students()}
    out = []
    for sid, L in list(LIVE.items()):
        if time.time() - L["ts"] > 30 or "task" not in L:
            continue
        out.append({"session": sid, "student": names.get(L.get("student"), L.get("student")), "task": L["task"],
                    "title": L.get("title"), "step": L.get("step"), "total": L.get("total"), "text": L.get("text"),
                    "status": L.get("status"), "seeing": L.get("seeing"), "hint": L.get("hint"), "help": L.get("help"),
                    "stuck_secs": int(time.time() - L.get("step_t0", time.time())),
                    "events": [e[1:] for e in L["events"][-5:]], "ts": L["ts"]})
    return out


@app.get("/api/live/{sid}/frame.jpg")
def live_frame(sid: str):
    L = LIVE.get(sid)
    if not L or not L.get("frame"):
        raise HTTPException(404)
    return Response(L["frame"], media_type="image/jpeg", headers={"Cache-Control": "no-store"})


class ConfirmReq(BaseModel):
    step: int


@app.post("/api/live/{sid}/confirm")
def live_confirm(sid: str, req: ConfirmReq):
    """老师确认这一步做完了（老师在旁边看到了，或看了实时画面）。"""
    _live(sid)["confirm"] = req.step
    return {"ok": True}


@app.post("/api/live/{sid}/help")
def live_help(sid: str):
    L = _live(sid)
    L["help"] = True
    L["events"].append([time.time(), L.get("step"), "help", None])
    return {"ok": True}


@app.post("/api/live/{sid}/confirmed")
def live_poll(sid: str):
    return {"confirmed": (LIVE.get(sid) or {}).get("confirm")}


@app.post("/api/tasks/{tid}/sessions/{sid}/end")
def end_session(tid: str, sid: str):
    t = load(tid)
    s = next((x for x in t["sessions"] if x["id"] == sid), None)
    if not s:
        raise HTTPException(404, "session not found")
    s["end"] = time.time()
    s["note"] = _auto_note(t, s)
    L = _learner(t, s.get("student", "_"))
    for k, v in s["results"].items():   # 更新这个学生每一步的提示级别
        i = int(k)
        if i < len(L["history"]):
            L["history"][i].append([v["result"], v["level"]])
            L["levels"][i] = coach.next_level([tuple(x) for x in L["history"][i]], L["levels"][i])
    res = s["results"].values()
    if s.get("source") != "teacher":
        agents.log(t, "Coach", f"Coached {_name(s.get('student'))} through {len(s['results'])}/{len(t['steps'])} steps: "
                   f"{sum(1 for v in res if v.get('verified') == 'camera')} confirmed by camera, "
                   f"{sum(1 for v in res if v.get('verified') == 'teacher')} by teacher.")
    save(t)
    threading.Thread(target=_after_session, args=(tid, s.get("student")), daemon=True).start()
    return {"levels": L["levels"], "mastered": _mastered(t, s.get("student", "_"))}


# ---------- 多 agent：Monitor（代码）→ Tuner（Wonder，提修改）→ 老师批准；Analyst（Wonder，写汇报） ----------
def _name(sid):
    return next((x["name"] for x in students() if x["id"] == sid), sid or "student")


def _watch_rows(tid: str) -> list[dict]:
    if not WATCH_LOG.exists():
        return []
    out = []
    for line in WATCH_LOG.read_text().splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("task") == tid:
            out.append(r)
    return out


def _monitor(tid: str) -> dict:
    return agents.health(load(tid), _watch_rows(tid))


def _tune(tid: str, steps: list[int] | None = None) -> list[dict]:
    hl = _monitor(tid)
    t = load(tid)
    open_steps = {p["step"] for p in t.get("proposals", []) if p["status"] == "open"}
    todo = [i for i in (steps if steps is not None else hl["flagged"]) if i not in open_steps]
    made = []
    for i in todo:
        try:
            made.append(agents.tune(t, i, hl["steps"][i]))
        except Exception as e:  # noqa: BLE001
            agents.log(t, "Tuner", f"Could not analyse step {i + 1}: {str(e)[:80]}")
    t = load(tid)   # 重新读，避免覆盖期间的新数据
    t.setdefault("proposals", []).extend(made)
    for p in made:
        agents.log(t, "Tuner", f"Step {p['step'] + 1}: {p['problem']} Proposed: {p['change']}")
    save(t)
    return made


def _analyse(tid: str, student: str) -> dict:
    t = load(tid)
    prog = progress(tid, student)
    if not prog["sessions"]:
        raise HTTPException(400, "no practice yet")
    rep = agents.analyst(t, _name(student), agents.facts(t, prog, _monitor(tid)))
    t = load(tid)
    t.setdefault("reports", {})[student] = rep
    agents.log(t, "Analyst", f"Wrote a progress report for {_name(student)} ({prog['pct'][-1]}% independent last session).")
    save(t)
    return rep


def _after_session(tid: str, student: str | None):
    """练习结束后自动跑：Monitor 统计 → 有问题的步骤交给 Tuner → Analyst 更新汇报。"""
    try:
        hl = _monitor(tid)
        t = load(tid)
        agents.log(t, "Monitor", f"Checked {hl['n_checks']} camera judgments, avg {hl['avg_ms']} ms. "
                   + (f"Problem steps: {', '.join(str(i + 1) for i in hl['flagged'])}." if hl["flagged"] else "No problems found."))
        save(t)
        if hl["flagged"]:
            _tune(tid)
        if student:
            _analyse(tid, student)
    except Exception as e:  # noqa: BLE001
        print("after_session failed:", e)


@app.get("/api/tasks/{tid}/agents")
def agents_view(tid: str, student: str | None = None):
    t = load(tid)
    return {"health": _monitor(tid), "proposals": [p for p in t.get("proposals", []) if p["status"] == "open"],
            "report": (t.get("reports") or {}).get(student) if student else None,
            "log": list(reversed(t.get("agent_log", [])))[:30]}


@app.post("/api/tasks/{tid}/tune")
def tune_now(tid: str, step: int | None = None):
    return _tune(tid, [step] if step is not None else None)


@app.post("/api/tasks/{tid}/analyse")
def analyse_now(tid: str, student: str):
    return _analyse(tid, student)


@app.post("/api/tasks/{tid}/proposals/{pid}/{action}")
def proposal_action(tid: str, pid: str, action: str):
    """老师批准（apply）或忽略（dismiss）Tuner 的修改方案。"""
    t = load(tid)
    p = next((x for x in t.get("proposals", []) if x["id"] == pid and x["status"] == "open"), None)
    if not p or action not in ("apply", "dismiss"):
        raise HTTPException(404)
    p["status"] = "applied" if action == "apply" else "dismissed"
    if action == "apply" and p.get("new_steps"):
        i = p["step"]
        old = t["steps"][i]
        rows = []
        for k, ns in enumerate(p["new_steps"]):
            row = {**(old if k == 0 else {}), **{x: ns.get(x) for x in ("text", "cue", "done_state", "objects", "safety")}}
            row.setdefault("chunk", old.get("chunk", 1))
            row["card"] = {"state": "none"} if not old.get("photo") or len(p["new_steps"]) > 1 else old["card"]
            if len(p["new_steps"]) > 1:
                row.pop("photo", None)
            row["hazards"] = safety.hazards(row)
            rows.append(row)
        t["steps"][i:i + 1] = rows
        extra = len(rows) - 1
        if extra:   # 拆步：旧记录里这一步之后的步骤号往后挪，数据表不会错位
            for ses in t["sessions"]:
                ses["results"] = {str(int(k) + extra if int(k) > i else int(k)): v for k, v in ses["results"].items()}
                if isinstance(ses.get("levels"), list) and len(ses["levels"]) > i:
                    ses["levels"] = ses["levels"][:i + 1] + [ses["levels"][i]] * extra + ses["levels"][i + 1:]
        for sid in list(t.get("learners", {})):   # 拆步后每个学生的提示级别跟着对齐
            L = t["learners"][sid]
            for key in ("levels", "history"):
                v = L.get(key)
                if isinstance(v, list) and len(v) > i:
                    L[key] = v[:i] + [v[i]] * len(rows) + v[i + 1:]
    agents.log(t, "Teacher", f"{'Applied' if action == 'apply' else 'Dismissed'} the fix for step {p['step'] + 1}.")
    if action == "apply" and len(p.get("new_steps") or []) > 1:
        for k, row in enumerate(t["steps"]):
            row["needs"] = [k - 1] if k else []
        save(t)
        _reorder_bg(tid)
        return t
    save(t)
    return t


# 任务分析数据的标准提示代码（参考 AFIRM 数据表），从最独立到最多帮助
CODES = ["I", "IS", "VB", "G", "M", "P"]
CODE_NAMES = {"I": "Independent", "IS": "Independent with visual/video support", "VB": "Verbal prompt",
              "G": "Gestural prompt", "M": "Model", "P": "Physical prompt", "H": "Needed adult help (code it)"}


def _code(v: dict) -> str | None:
    """一格数据的代码：老师录入/修改的优先；app 练习自动推出。"""
    if not v:
        return None
    if v.get("code"):
        return v["code"]
    if v.get("result") == "help":
        return "H"
    if v.get("verified") == "self" or v.get("result") == "self":   # 没有被镜头或老师确认：不算独立
        return "IS"
    return "I" if v.get("level") == 0 and v.get("result") == "clean" else "IS"


def _mastered(t: dict, sid: str, need=3) -> bool:
    """学会 = 这个学生最近连续 need 次练习，每一步都是 I（独立完成）。"""
    done = [s for s in t["sessions"] if s.get("end") and s.get("student") == sid]
    if len(done) < need:
        return False
    for s in done[-need:]:
        if any(_code(s["results"].get(str(i))) != "I" for i in range(len(t["steps"]))):
            return False
    return True


# ---------- 老师录入 / 修改数据 ----------
class ManualReq(BaseModel):
    student: str
    codes: list[str | None]
    setting: str = "school"
    note: str = ""
    date: float | None = None


@app.post("/api/tasks/{tid}/manual")
def manual_session(tid: str, req: ManualReq):
    """老师上课时一步点一个代码，保存成一次练习记录。"""
    t = load(tid)
    if any(c and c not in CODES for c in req.codes):
        raise HTTPException(400, "bad code")
    now = req.date or time.time()
    s = {"id": uuid.uuid4().hex[:8], "student": req.student, "start": now, "end": now, "source": "teacher",
         "setting": req.setting, "note": req.note[:500], "levels": [None] * len(t["steps"]),
         "results": {str(i): {"code": c, "result": "clean" if c == "I" else "prompted"} for i, c in enumerate(req.codes) if c}}
    _learner(t, req.student)
    t["sessions"].append(s)
    save(t)
    return {"session": s["id"]}


class CellReq(BaseModel):
    step: int
    code: str | None


@app.post("/api/tasks/{tid}/sessions/{sid}/code")
def edit_cell(tid: str, sid: str, req: CellReq):
    """老师修改任意一格（如实打分：自动记录的数据也以老师为准）。"""
    t = load(tid)
    s = next((x for x in t["sessions"] if x["id"] == sid), None)
    if not s or (req.code and req.code not in CODES):
        raise HTTPException(400, "bad session or code")
    cell = s["results"].setdefault(str(req.step), {})
    if req.code:
        cell["code"] = req.code
        cell["edited"] = True
    else:
        s["results"].pop(str(req.step), None)
    save(t)
    return {"ok": True}


@app.get("/api/tasks/{tid}/progress")
def progress(tid: str, student: str):
    t = load(tid)
    n = len(t["steps"])
    done = [s for s in t["sessions"] if s.get("end") and s["results"] and s.get("student") == student]
    done.sort(key=lambda s: s["start"])
    grid = [[{"code": _code(s["results"].get(str(i))), "err": bool((s["results"].get(str(i)) or {}).get("errors")),
              "edited": bool((s["results"].get(str(i)) or {}).get("edited")),
              "v": (s["results"].get(str(i)) or {}).get("verified") or ("teacher" if s.get("source") == "teacher" and s["results"].get(str(i)) else None),
              "ev": (s["results"].get(str(i)) or {}).get("evidence"),
              "flags": (s["results"].get(str(i)) or {}).get("flags", [])} for s in done] for i in range(n)]
    pct = [round(100 * sum(1 for i in range(n) if grid[i][j]["code"] == "I") / max(1, n)) for j in range(len(done))]
    step_mastered = [len(row) >= 3 and all(c["code"] == "I" for c in row[-3:]) for row in grid]
    return {"steps": [s["text"] for s in t["steps"]], "sessions": [{"id": s["id"], "date": s["start"], "setting": s.get("setting", "school"),
            "source": s.get("source", "app"), "note": s.get("note", "")} for s in done], "grid": grid, "pct": pct,
            "trend": [round(p * n / 100) for p in pct], "dates": [s["start"] for s in done],
            "n_steps": n, "step_mastered": step_mastered, "mastered": _mastered(t, student),
            "codes": CODES, "code_names": CODE_NAMES}


def _auto_note(t: dict, s: dict) -> str:
    """学生用 app 练习后自动生成的观察备注：只陈述发生了什么，不做推断。"""
    parts = []
    for k, v in sorted(s["results"].items(), key=lambda x: int(x[0])):
        i = int(k) + 1
        if v.get("result") == "help":
            parts.append(f"asked for help at step {i}")
        elif v.get("errors"):
            parts.append(f"step {i} needed {v['errors']} correction{'s' if v['errors'] > 1 else ''}")
        elif v.get("result") == "self":
            parts.append(f"step {i} marked done by student (camera could not confirm)")
        for fl in v.get("flags", []):
            parts.append({"unsafe": f"unsafe action seen at step {i}", "ahead": f"tried to skip step {i}",
                          "wrong": f"step {i} started the wrong way"}.get(fl, f"{fl} at step {i}"))
    n_done = len(s["results"])
    cam = sum(1 for v in s["results"].values() if v.get("verified") == "camera")
    tch = sum(1 for v in s["results"].values() if v.get("verified") == "teacher")
    head = (f"Practiced on the app, {n_done}/{len(t['steps'])} steps reached "
            f"({cam} confirmed by camera, {tch} confirmed by teacher).")
    return head + (" " + "; ".join(parts).capitalize() + "." if parts else " No help or corrections needed.")


def _date(ts: float) -> str:
    return time.strftime("%m/%d", time.localtime(ts))


@app.get("/api/tasks/{tid}/datasheet.csv")
def datasheet(tid: str, student: str):
    """标准任务分析数据表：步骤 × 日期，每格一个提示代码。可直接导入表格或 IEP 系统。"""
    import csv
    p = progress(tid, student)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Step"] + [f"{_date(s['date'])} ({s['setting']})" for s in p["sessions"]])
    for i, txt in enumerate(p["steps"]):
        w.writerow([f"{i + 1}. {txt}"] + [c["code"] or "" for c in p["grid"][i]])
    w.writerow(["% steps independent (I)"] + [f"{x}%" for x in p["pct"]])
    w.writerow([])
    w.writerow(["Codes: " + "; ".join(f"{k} = {v}" for k, v in CODE_NAMES.items())])
    name = next((x["name"] for x in students() if x["id"] == student), "student")
    from fastapi.responses import Response
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{name}-{load(tid)["title"]}.csv"'.replace(" ", "_")})


@app.get("/api/tasks/{tid}/sessions.csv")
def sessions_csv(tid: str, student: str):
    """每次练习一行（日期、x/y、百分比、备注）：和 SpedTrack 这类系统的录入方式一致，可直接抄录或粘贴。"""
    import csv
    from fastapi.responses import Response
    p = progress(tid, student)
    n = p["n_steps"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Date", "Setting", "Recorded by", "Independent steps", "Percent independent", "Note"])
    for j, sess in enumerate(p["sessions"]):
        w.writerow([time.strftime("%Y-%m-%d", time.localtime(sess["date"])), sess["setting"],
                    "teacher" if sess["source"] == "teacher" else "student app", f"{round(p['pct'][j] * n / 100)}/{n}",
                    f"{p['pct'][j]}%", sess.get("note", "")])
    return Response(buf.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="sessions.csv"'})


@app.get("/api/tasks/{tid}/iep_note")
def iep_note(tid: str, student: str):
    """IEP 进度说明：完全由数据计算出来（不让 AI 编写数字）。"""
    p = progress(tid, student)
    t = load(tid)
    name = next((x["name"] for x in students() if x["id"] == student), "The student")
    n, S = p["n_steps"], len(p["sessions"])
    if not S:
        return {"text": f"No data yet for {name} on \"{t['title']}\"."}
    first, last = p["pct"][0], p["pct"][-1]
    still = [f"step {i + 1} ({p['steps'][i]})" for i in range(n) if p["grid"][i][-1]["code"] != "I"]
    settings = sorted({s["setting"] for s in p["sessions"]})
    text = (f"From {_date(p['sessions'][0]['date'])} to {_date(p['sessions'][-1]['date'])}, {name} practiced the "
            f"{n}-step task \"{t['title']}\" in {S} session{'s' if S > 1 else ''} ({', '.join(settings)}). "
            f"Independent steps went from {round(first * n / 100)}/{n} ({first}%) at baseline to "
            f"{round(last * n / 100)}/{n} ({last}%) in the most recent session. ")
    text += (f"Still needing support: {', '.join(still)}." if still else "All steps were completed independently in the most recent session.")
    if p["mastered"]:
        text += " Mastery criterion met (all steps independent in 3 consecutive sessions)."
    return {"text": text}


REPORT = """You are writing a short weekly progress note for a special-education teacher or parent about a learner
practicing "{title}". The learner's first name is {name}. Use plain, warm, factual language; no diagnosis, no medical or behavioral claims, no scores
about the person, only what the data shows. Each cell is a standard prompt code.
DATA (one row per step, one entry per practice session, oldest first):
{rows}
Return ONLY JSON {{"summary": "2-3 sentences", "wins": ["..."], "watch": ["step that still needs support and how"],
"suggestion": "one concrete next step for the caregiver, e.g. split a step or fade a prompt",
"iep_line": "one sentence in the style of an IEP progress note, with numbers from the data"}}"""


@app.post("/api/tasks/{tid}/report")
def report(tid: str, student: str):
    p = progress(tid, student)
    name = next((x["name"] for x in students() if x["id"] == student), "the learner")
    rows = "\n".join(f"Step {i + 1} '{txt}': " + ", ".join((c["code"] or "-") for c in p["grid"][i])
                     for i, txt in enumerate(p["steps"]))
    rows += "\nCodes: " + "; ".join(f"{k} = {v}" for k, v in CODE_NAMES.items())
    if not p["dates"]:
        raise HTTPException(400, "no practice yet")
    resp = _client.responses.create(model=coach.WONDER, max_output_tokens=4000, reasoning={"effort": "low"},
                                    input=REPORT.format(title=load(tid)["title"], rows=rows, name=name))
    return _parse(resp.output_text)


# ---------- 语音 ----------
@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """浏览器录的 webm/mp4 → 16k 单声道 wav → Muse Voice Transcribe（/v1/asr/transcribe，只收 WAV）。"""
    import subprocess
    import tempfile
    import imageio_ffmpeg
    import requests
    raw = await audio.read()
    with tempfile.TemporaryDirectory() as td:
        src, dst = Path(td) / ("in" + Path(audio.filename or "a.webm").suffix), Path(td) / "out.wav"
        src.write_bytes(raw)
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(src), "-ac", "1", "-ar", "16000", str(dst)],
                       check=True, capture_output=True)
        wav = dst.read_bytes()
    base = os.getenv("META_BASE_URL", "https://api.meta.ai/v1")
    r = requests.post(f"{base}/asr/transcribe", timeout=120,
                      headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}", "Accept": "application/json"},
                      files={"request": (None, json.dumps({"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV",
                                                           "mode": "PUSH_TO_TALK"}), "application/json"),
                             "audio": ("speech.wav", wav, "audio/wav")})
    if r.status_code >= 400:
        raise HTTPException(502, f"transcribe {r.status_code}: {r.text[:200]}")
    body = r.json()
    texts = []

    def walk(x):  # 返回结构没写清楚：把所有 transcript/text 字段收集起来
        if isinstance(x, dict):
            for k, v in x.items():
                if k in ("transcript", "text") and isinstance(v, str):
                    texts.append(v)
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(body)
    return {"text": " ".join(t.strip() for t in texts if t.strip()), "raw": body}


STATIC = ROOT / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
