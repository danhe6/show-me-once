"""标注坐标准不准：用泡茶图卡当镜头画面，把模型给的 mark 画到图上存成 png 看。"""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))
from fastapi.testclient import TestClient
import cv2, numpy as np
import app
c = TestClient(app.app); H = {"x-k": app.TOKEN or ""}
cards = app.DATA / "ac801abc93" / "cards"
S = c.post("/api/tasks/ac801abc93/sessions", json={"student": "672fd5"}, headers=H).json()["session"]
for step, f, done in [(0, "0a.jpg", ""), (2, "2a.jpg", "0,1"), (5, "5a.jpg", "0,1,2,3,4")]:
    b = (cards / f).read_bytes()
    j = c.post("/api/tasks/ac801abc93/judge", data={"step": step, "session": S, "done": done, "view": "back"},
               files=[("frames", (f, b, "image/jpeg"))] * 2, headers=H).json()
    m = j.get("mark"); print(f"step {step+1} {f}: status={j['status']} seeing={j.get('seeing')!r} mark={m}")
    im = cv2.imread(str(cards / f)); Hh, W = im.shape[:2]
    if m:
        x, y = int(m["x"] / 100 * W), int(m["y"] / 100 * Hh); r = int(W * 0.09)
        cv2.circle(im, (x, y), r, (143, 158, 63), 6)
        if m.get("to_x") is not None:
            tx, ty = int(m["to_x"] / 100 * W), int(m["to_y"] / 100 * Hh); cv2.arrowedLine(im, (x, y), (tx, ty), (143, 158, 63), 6, tipLength=0.2)
        cv2.putText(im, m.get("label", ""), (max(0, x - r), max(30, y - r - 15)), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (79, 97, 240), 3)
    cv2.imwrite(f"data/out/mark_{step+1}.png", im)
p = app.DATA / "ac801abc93" / "task.json"; t = json.loads(p.read_text()); t["sessions"] = [x for x in t["sessions"] if x["id"] != S]; p.write_text(json.dumps(t, ensure_ascii=False, indent=1))
print("saved data/out/mark_*.png")
