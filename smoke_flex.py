"""冒烟测试（10/28 14:10）：灵活顺序。泡茶副本：推断依赖 → 先做第 2 步（装水）应被接受 → 没烧水就倒水应判 too_early。"""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

tid = "smokefx" + time.strftime("%H%M%S")
shutil.copytree(app.DATA / "ac801abc93", app.DATA / tid, ignore=shutil.ignore_patterns("evidence"))
t = json.loads((app.DATA / tid / "task.json").read_text())
t["id"] = tid
for s in t["steps"]:
    s.pop("needs", None)
(app.DATA / tid / "task.json").write_text(json.dumps(t))
c = TestClient(app.app)
H = {"x-k": app.TOKEN or ""}
ok = lambda r: (r.raise_for_status(), r.json())[1]  # noqa: E731
t = ok(c.get(f"/api/tasks/{tid}", headers=H))
print("order:", t["order"])
for i, s in enumerate(t["steps"]):
    print(f"  {i + 1}. {s['text']:<38} needs {[j + 1 for j in s['needs']]}")
S = ok(c.post(f"/api/tasks/{tid}/sessions", json={"student": "672fd5"}, headers=H))["session"]
cards = app.DATA / tid / "cards"
cases = [("nothing done; frames show step 2 (fill kettle)", "", ["1a.jpg", "1.jpg", "1.jpg"]),
         ("nothing done; frames show step 6 (pour hot water)", "", ["5a.jpg", "5.jpg", "5.jpg"]),
         ("steps 1-5 done; frames show step 6 (pour)", "0,1,2,3,4", ["5a.jpg", "5.jpg", "5.jpg"])]
for name, done, fs in cases:
    files = [("frames", (f, (cards / f).read_bytes(), "image/jpeg")) for f in fs]
    r = ok(c.post(f"/api/tasks/{tid}/judge", data={"step": 0, "session": S, "done": done}, files=files, headers=H))
    print(f"== {name}\n  step={None if r.get('step') is None else r['step'] + 1} status={r['status']} seeing={r.get('seeing')!r} hint={r.get('hint')!r} available={[i + 1 for i in r.get('available', [])]} ms={r['ms']}")
(app.DATA / tid).rename(app.DATA / ("_archived_" + tid))
print("DONE")
