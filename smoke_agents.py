"""冒烟测试（10/28 下午）：Monitor → Tuner → 老师 Apply → Analyst。在泡茶任务副本上跑，真实 Wonder 调用。
为了触发 Monitor，往副本写入模拟的镜头判断记录（只属于这个副本，跑完归档）。"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

tid = "smokeag" + time.strftime("%H%M%S")
shutil.copytree(app.DATA / "ac801abc93", app.DATA / tid, ignore=shutil.ignore_patterns("evidence"))
t = json.loads((app.DATA / tid / "task.json").read_text())
t["id"] = tid
(app.DATA / tid / "task.json").write_text(json.dumps(t))
# 模拟：第 1 步（放茶包）镜头 10 次里 6 次看不清
with open(app.WATCH_LOG, "a") as f:
    for k in range(10):
        st = "unclear" if k < 6 else "working"
        f.write(json.dumps({"ts": time.time(), "task": tid, "session": "sim", "step": 0, "status": st, "ms": 2100,
                            "seeing": "I can't see your hands" if st == "unclear" else "You are holding a small white packet near the mug"}) + "\n")
c = TestClient(app.app)
H = {"x-k": app.TOKEN or ""}
ok = lambda r: (r.raise_for_status(), r.json())[1]  # noqa: E731
t0 = time.time()
app._after_session(tid, "672fd5")
print(f"after_session took {time.time() - t0:.1f}s")
A = ok(c.get(f"/api/tasks/{tid}/agents?student=672fd5", headers=H))
print("flagged:", A["health"]["flagged"], [s["problems"] for s in A["health"]["steps"] if s["problems"]])
for p in A["proposals"]:
    print("PROPOSAL", json.dumps({k: p[k] for k in ("kind", "problem", "change", "new_steps")}, ensure_ascii=False, indent=1))
R = A["report"]
print("REPORT", json.dumps({k: R.get(k) for k in ("summary", "wins", "concerns", "next_week", "iep_line", "facts")}, ensure_ascii=False, indent=1) if R else None)
print("LOG:")
for l in A["log"]:
    print(f"  [{l['agent']}] {l['did']}")
if A["proposals"]:
    n0 = len(ok(c.get(f"/api/tasks/{tid}", headers=H))["steps"])
    t2 = ok(c.post(f"/api/tasks/{tid}/proposals/{A['proposals'][0]['id']}/apply", headers=H))
    print("applied: steps", n0, "->", len(t2["steps"]), "| step1 now:", t2["steps"][0]["text"], "/", t2["steps"][0]["done_state"])
    p = ok(c.get(f"/api/tasks/{tid}/progress?student=672fd5", headers=H))
    print("data sheet still loads:", len(p["grid"]), "rows,", len(p["sessions"]), "sessions")
(app.DATA / tid).rename(app.DATA / ("_archived_" + tid))
print("DONE")
