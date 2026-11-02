"""Meta Model API 客户端（OpenAI SDK 兼容）。文档：https://dev.meta.ai/docs/quickstart"""
import base64
import json
import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_client = OpenAI(
    api_key=os.environ["MODEL_API_KEY"],
    base_url=os.getenv("META_BASE_URL", "https://api.meta.ai/v1"),
)
MODEL = os.getenv("META_MODEL", "muse-spark-1.3")
MAX_OUT = 8000  # Spark 是推理模型，推理也占输出预算，别设太小


def _parse(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(text)


def ask_json_images(prompt: str, images: list[bytes]) -> dict:
    """方式 A：抽帧后作为图片发送（Chat Completions）。"""
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}}
        for b in images
    ]
    resp = _client.chat.completions.create(
        model=MODEL, max_tokens=MAX_OUT,
        messages=[{"role": "user", "content": content}],
    )
    return _parse(resp.choices[0].message.content)


def to_mp4(video_path: str) -> str:
    """API 只收 mp4：把 iPhone 的 .mov 转成 1080p 的 mp4（保留声音）。"""
    src = Path(video_path)
    if src.suffix.lower() == ".mp4":
        return str(src)
    import imageio_ffmpeg
    dst = src.with_suffix(".mp4")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(src),
                    "-vf", "scale='min(1920,iw)':-2", "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "23", "-c:a", "aac", str(dst)], check=True, capture_output=True)
    return str(dst)


def ask_json_video(prompt: str, video_path: str) -> dict:
    """方式 B：整段视频上传给 Spark（Files API + Responses API）。"""
    mp4 = to_mp4(video_path)
    with open(mp4, "rb") as f:
        uploaded = _client.files.create(file=f, purpose="user_data")
    resp = _client.responses.create(
        model=MODEL, max_output_tokens=MAX_OUT,
        input=[{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt},
            {"type": "input_file", "file_id": uploaded.id},
        ]}],
    )
    return _parse(resp.output_text)
