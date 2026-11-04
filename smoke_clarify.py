"""追问 + 电脑任务：真实模型。"""
import sys, json, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from fastapi.testclient import TestClient
import app
c = TestClient(app.app); H = {"x-k": app.TOKEN or ""}
for g in ["use the computer", "learn AI", "make a cup of tea", "fold a T-shirt", "cleaning"]:
    r = c.post("/api/tasks/clarify", data={"goal": g}, headers=H).json()
    print(f"clarify {g!r:22} ->", json.dumps(r, ensure_ascii=False))
t0 = time.time()
t = c.post("/api/tasks", data={"goal": "Ask ChatGPT a question on the laptop", "media": "live"}, headers=H).json()
print(f"\nplan 'Ask ChatGPT a question' ({time.time()-t0:.0f}s) refuse={t.get('refuse')}")
for i, s in enumerate(t["steps"]): print(f"  {i+1}. {s['text']:<42} done: {s['done_state']}")
(app.DATA / t["id"]).rename(app.DATA / ("_archived_" + t["id"]))
t = c.post("/api/tasks", data={"goal": "take my pills", "media": "live"}, headers=H).json()
print("\nplan 'take my pills' refuse =", t.get("refuse"))
(app.DATA / t["id"]).rename(app.DATA / ("_archived_" + t["id"]))
print("DONE")
