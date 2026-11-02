"""冒烟测试（10/28 中午）：对话式教练——听意图、开始前查桌面、练习中回答问题、无图任务。真实 Spark 调用。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "src"))
from fastapi.testclient import TestClient  # noqa: E402

import app  # noqa: E402

c = TestClient(app.app)
H = {"x-k": app.TOKEN or ""}
ok = lambda r: (r.raise_for_status(), r.json())[1]  # noqa: E731
MAYA = "672fd5"
print("assigned+approved for Maya:", [t["title"] for t in ok(c.get(f"/api/tasks?student={MAYA}", headers=H)) if t["approved"]])
for said in ["um I want tea", "can I make some tea please", "I want to fold my laundry", "cut an apple"]:
    print(f"intent {said!r:35} ->", ok(c.post("/api/intent", json={"student": MAYA, "said": said}, headers=H)))
print("requests:", [(r["name"], r["said"]) for r in ok(c.get("/api/requests", headers=H))])

cards = app.DATA / "ac801abc93" / "cards"
for f in ["0a.jpg", "5.jpg"]:
    r = ok(c.post("/api/tasks/ac801abc93/ready", files=[("frames", (f, (cards / f).read_bytes(), "image/jpeg"))], headers=H))
    print("ready", f, "->", r)
r = ok(c.post("/api/tasks/ac801abc93/ask", data={"step": 0, "q": "where is the tea bag"},
              files={"frame": ("f.jpg", (cards / "0a.jpg").read_bytes(), "image/jpeg")}, headers=H))
print("ask step1 'where is the tea bag' ->", r)
r = ok(c.post("/api/tasks/ac801abc93/ask", data={"step": 5, "q": "can I skip this one"}, headers=H))
print("ask step6 'can I skip this one' ->", r)
# 清掉本测试产生的请求
p = ROOT / "data/coach/requests.json"
if p.exists():
    reqs = json.loads(p.read_text())
    for x in reqs:
        x["done"] = True
    p.write_text(json.dumps(reqs, indent=1))
print("DONE")
