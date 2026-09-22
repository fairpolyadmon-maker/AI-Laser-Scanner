import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(BASE_DIR, "central_signal_server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

# Change directory to central_signal_server to ensure relative paths resolve cleanly
os.chdir(SERVER_DIR)

import server
from aiohttp import web

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    print("=" * 65)
    print(f"   AI LASER SCANNER - CENTRAL SIGNAL HUB (PORT {port})")
    print("   Deterministic AI (Temp=0.0) & Minute-Locked Single Source")
    print(f"   Web Dashboard: http://localhost:{port}")
    print("=" * 65)
    web.run_app(server.make_app(), host='0.0.0.0', port=port)
