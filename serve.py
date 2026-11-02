"""Start the app plus a temporary HTTPS tunnel (phones need HTTPS for camera and microphone).
python serve.py start   -> prints the link to open on the phone (includes a random access token)
python serve.py stop
Only people with the token can use the API. Stop it when you are done so nobody else uses your API credits.
"""
import os
import secrets
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
(ROOT / "jobs").mkdir(exist_ok=True)
PIDS, LOG, URLF = ROOT / "jobs/serve.pids", ROOT / "jobs/serve.log", ROOT / "jobs/serve.url"


def start():
    stop()
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pycloudflared"], check=False)
    token = secrets.token_urlsafe(8)
    env = {**os.environ, "APP_TOKEN": token}
    log = LOG.open("w")
    api = subprocess.Popen([sys.executable, "-m", "uvicorn", "app:app", "--port", "8000"], cwd=ROOT, env=env,
                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    tun = subprocess.Popen([sys.executable, "-c",
                            "from pycloudflared import try_cloudflare; import time;"
                            "u=try_cloudflare(port=8000, verbose=False); print('URL', u.tunnel, flush=True);"
                            "time.sleep(10**9)"],
                           cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)
    PIDS.write_text(f"{api.pid} {tun.pid}")
    t0 = time.time()
    for line in tun.stdout:
        if line.startswith("URL"):
            url = line.split()[1] + f"/?k={token}"
            URLF.write_text(url)
            print("Open on your phone:", url)
            print("Student view: add #learn   Teacher view: add #care")
            return
        if time.time() - t0 > 90:
            break
    print("Tunnel did not start; see jobs/serve.log")


def stop():
    if PIDS.exists():
        for pid in PIDS.read_text().split():
            try:
                os.killpg(int(pid), signal.SIGTERM)
            except Exception:  # noqa
                pass
        PIDS.unlink()
        print("stopped")


if __name__ == "__main__":
    {"start": start, "stop": stop}[sys.argv[1] if len(sys.argv) > 1 else "start"]()
