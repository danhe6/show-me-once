"""语音合成：Kokoro（开放权重，本机 CPU 跑）。生成的音频按文本缓存，同一句话只生成一次。
模型没装时 available() 返回 False，前端会退回手机自带的声音。"""
import hashlib
import io
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL = ROOT / "data/tts_model/kokoro-v1.0.onnx"
VOICES = ROOT / "data/tts_model/voices-v1.0.bin"
CACHE = ROOT / "data/coach/tts_cache"
VOICE = os.getenv("TTS_VOICE", "af_heart")
VOICE_ZH = os.getenv("TTS_VOICE_ZH", "zf_xiaoxiao")
LANG_CODE = {"en": "en-us", "zh": "cmn"}
SPEED = 0.95
_k = None
_lock = threading.RLock()


def available() -> bool:
    return MODEL.exists() and VOICES.exists()


def _engine():
    global _k
    with _lock:
        if _k is None:
            from kokoro_onnx import Kokoro
            _k = Kokoro(str(MODEL), str(VOICES))
    return _k


def warmup():
    if available():
        threading.Thread(target=lambda: speak("Hello."), daemon=True).start()


def speak(text: str, voice: str | None = None, speed: float | None = None, lang: str = "en") -> bytes:
    """返回 WAV 字节。"""
    import soundfile as sf
    voice = voice or (VOICE_ZH if lang == "zh" else VOICE)
    speed = speed or SPEED
    code = LANG_CODE.get(lang, "en-us")
    text = " ".join(text.split())[:400]
    key = hashlib.sha1(f"{voice}|{speed}|{code}|{text}".encode()).hexdigest()[:20]
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / f"{key}.wav"
    if p.exists():
        return p.read_bytes()
    eng = _engine()
    with _lock:   # onnx 会话不要并发
        samples, sr = eng.create(text, voice=voice, speed=speed, lang=code)
    buf = io.BytesIO()
    sf.write(buf, samples, sr, format="WAV", subtype="PCM_16")
    data = buf.getvalue()
    p.write_bytes(data)
    return data
