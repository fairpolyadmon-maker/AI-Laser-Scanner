import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SERVER_DIR = os.path.join(BASE_DIR, "server")
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

os.chdir(SERVER_DIR)

import uvicorn
from main import app

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8000))
    print("=" * 65)
    print(f"   AI LASER SCANNER - CENTRAL SIGNAL HUB (PORT {port})")
    print("   Tracking 10 Major Pairs for Mobile & Cloud")
    print("=" * 65)
    uvicorn.run(app, host="0.0.0.0", port=port)
