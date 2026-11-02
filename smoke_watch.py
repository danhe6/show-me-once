"""冒烟测试（10/28）：多帧实时判断 + 证据小图 + 老师实时面板 + 老师确认 + 录音 + 安全规则。
用真实 Spark 调用。帧用泡茶任务里的图卡（第 1 步“放茶包”的动作前/动作后两帧 + 第 2 步图），看模型能否说出“正在做什么”。
不会改正式数据：在任务副本 _smoke_watch 上跑，跑完改名归档。
"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402
import safety  # noqa: E402

src = app.DATA / "ac801abc93"
tid = "smokew" + time.strftime("%H%M%S")
dst = app.DATA / tid
shutil.copytree(src, dst, ignore=shutil.ignore_patterns("evidence"))
t = json.loads((dst / "task.json").read_text())
t["id"] = tid
t["sessions"] = []
(dst / "task.json").write_text(json.dumps(t))

c = TestClient(app.app)
H = {"x-k": app.TOKEN or ""}
ok = lambda r: (r.raise_for_status(), r.json())[1]  # noqa: E731

print("== hazards per step (safety rules)")
for s in ok(c.get(f"/api/tasks/{tid}", headers=H))["steps"]:
    print(f"  {s['text']:<40} {s['hazards']}")

S = ok(c.post(f"/api/tasks/{tid}/sessions", json={"student": "672fd5"}, headers=H))["session"]
cards = dst / "cards"
cases = [
    ("step1 frames before→after (should be working/done)", 0, ["0a.jpg", "0a.jpg", "0.jpg"]),
    ("step1 but showing step-2 picture (ahead/wrong?)", 0, ["1a.jpg", "1.jpg", "1.jpg"]),
    ("step6 pour (hazard rules on)", 5, ["5a.jpg", "5.jpg", "5.jpg"]),
]
for name, step, fs in cases:
    files = [("frames", (f, (cards / f).read_bytes(), "image/jpeg")) for f in fs if (cards / f).exists()]
    r = ok(c.post(f"/api/tasks/{tid}/judge", data={"step": step, "session": S}, files=files, headers=H))
    print(f"== {name}\n  {json.dumps(r, ensure_ascii=False)}")

print("== live panel")
for x in ok(c.get("/api/live", headers=H)):
    print(" ", {k: x[k] for k in ("student", "title", "step", "status", "seeing", "help", "events")})
print("  frame:", c.get(f"/api/live/{S}/frame.jpg", headers=H).status_code)

print("== teacher confirm → next judge says confirmed")
ok(c.post(f"/api/live/{S}/confirm", json={"step": 0}, headers=H))
print("  poll:", ok(c.post(f"/api/live/{S}/confirmed", headers=H)))
ok(c.post(f"/api/tasks/{tid}/sessions/{S}/step", json={"step": 0, "result": "clean", "secs": 9, "verified": "teacher"}, headers=H))
ok(c.post(f"/api/tasks/{tid}/sessions/{S}/step", json={"step": 1, "result": "clean", "secs": 7, "verified": "camera"}, headers=H))
ok(c.post(f"/api/live/{S}/help", headers=H))
ok(c.post(f"/api/tasks/{tid}/sessions/{S}/end", headers=H))
p = ok(c.get(f"/api/tasks/{tid}/progress?student=672fd5", headers=H))
print("  grid col:", [row[0] for row in p["grid"][:3]])
print("  note:", p["sessions"][0]["note"])
ev = p["grid"][0][0].get("ev")
print("  evidence file:", ev, c.get(f"/api/tasks/{tid}/evidence/{ev}", headers=H).status_code if ev else None)

print("== voice upload")
r = ok(c.post(f"/api/tasks/{tid}/steps/0/voice", files={"audio": ("v.m4a", b"\x00" * 2000, "audio/mp4")}, headers=H))
print("  voice:", r.get("voice"), c.get(f"/api/tasks/{tid}/voice/{r['voice']}", headers=H).status_code)

print("== card check rubric now built from rules:\n ", safety.check_text()[:200], "…")
(app.DATA / tid).rename(app.DATA / ("_archived_" + tid))
print("archived test copy; DONE")
