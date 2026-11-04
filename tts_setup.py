"""一次性安装 Kokoro（开放权重的语音模型，Apache-2.0），下载模型文件，生成几句试听并测速度。
在 runner 的环境里运行一次：  conda activate meta; python tts_setup.py

会做的事：
1. pip install kokoro-onnx soundfile
2. 从 kokoro-onnx 的 GitHub release 下载 kokoro-v1.0.onnx（约 310 MB）和 voices-v1.0.bin（约 27 MB）到 data/tts_model/
3. 用 4 个声音各生成一句话到 data/out/tts_<voice>.wav，打印每句的生成时间
"""
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "kokoro-onnx", "soundfile"], check=True)
D = ROOT / "data/tts_model"
D.mkdir(parents=True, exist_ok=True)
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
for f in ["kokoro-v1.0.onnx", "voices-v1.0.bin"]:
    if not (D / f).exists():
        t0 = time.time()
        urllib.request.urlretrieve(BASE + f, D / f)
        print(f, (D / f).stat().st_size // 1_000_000, "MB", f"{time.time() - t0:.0f}s")

import soundfile as sf  # noqa: E402
from kokoro_onnx import Kokoro  # noqa: E402

k = Kokoro(str(D / "kokoro-v1.0.onnx"), str(D / "voices-v1.0.bin"))
LINE = "Nice, the kettle's full. Now let's put it on its base."
for v in ["af_heart", "af_bella", "af_nicole", "bf_emma"]:
    t0 = time.time()
    s, sr = k.create(LINE, voice=v, speed=0.95, lang="en-us")
    sf.write(ROOT / f"data/out/tts_{v}.wav", s, sr)
    print(v, f"{time.time() - t0:.2f}s to make {len(s) / sr:.1f}s of audio")
print("OK: listen to data/out/tts_*.wav")
