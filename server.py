import os
import sys

# Ensure immediate unbuffered output in Render and container environments
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass
os.environ["PYTHONUNBUFFERED"] = "1"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

os.chdir(SERVER_DIR)

import uvicorn
from main import app

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    print("=" * 70, flush=True)
    print(f"🚀 AI LASER SCANNER - CENTRAL SIGNAL HUB STARTING (PORT {port})", flush=True)
    print("📋 Real-time Unbuffered Logging: ENABLED", flush=True)
    print("🎯 Strict Active Pair Tracking: ENABLED", flush=True)
    print("=" * 70, flush=True)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

