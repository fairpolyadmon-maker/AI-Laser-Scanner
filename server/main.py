import os
import io
import sys
import json
import time
import base64
import asyncio
import urllib.request
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="AI Laser Trading Central Signal Server",
    description="Centralized AI Trading Screen Assistant Server powered by Google Gemini and 48 Candlestick Patterns.",
    version="3.0.0"
)

# Enable CORS for all clients worldwide
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "laser_admin_secure_2026")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PATTERNS_JSON_PATH = os.path.join(BASE_DIR, "patterns", "candlestick_memory_48.json")

# Build Master Candlestick Prompt from 48 patterns
MASTER_PATTERNS = []
if os.path.exists(PATTERNS_JSON_PATH):
    try:
        with open(PATTERNS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            MASTER_PATTERNS = data.get("patterns", [])
    except Exception as e:
        print(f"Error loading patterns: {e}")

call_list = []
put_list = []
for p in MASTER_PATTERNS:
    p_id = p.get('id', '')
    p_name = p.get('name', '')
    p_bn = p.get('name_bn', '')
    p_rule = p.get('rule', '')
    desc = f"- {p_id}: {p_name} ({p_bn}) -> {p_rule}"
    if p.get("signal") == "CALL":
        call_list.append(desc)
    else:
        put_list.append(desc)

CALL_PATTERNS_TEXT = "\n".join(call_list[:24])
PUT_PATTERNS_TEXT = "\n".join(put_list[:24])

SYSTEM_VISION_PROMPT = f"""
You are the world's most elite Binary Options & Candlestick Pattern Recognition AI Analyst.
You analyze live candlestick trading charts from Quotex, Pocket Option, TradingView, IQ Option, Binomo, etc.

YOUR OBJECTIVE:
1. Check if the image contains an active Japanese Candlestick trading chart (green and red candles with bodies and wicks).
2. Read the asset/currency pair name from the top or left of the screen (e.g. "EUR/USD OTC", "GBP/USD", "BTC/USDT", or "OTC").
3. Determine the market direction for the NEXT 1-MINUTE CANDLE:
   - "CALL" (UP / BUY / Green Candle)
   - "PUT" (DOWN / SELL / Red Candle)
   - "WAIT" (If choppy, doji, noise, or no clear confluence)

MASTER 48 CANDLESTICK PATTERNS KNOWLEDGE:
[CALL PATTERNS (UP / BUY)]:
{CALL_PATTERNS_TEXT}

[PUT PATTERNS (DOWN / SELL)]:
{PUT_PATTERNS_TEXT}

PRICE ACTION & CANDLESTICK PSYCHOLOGY CONFLUENCE:
- Support & Resistance Levels (S/R bounce or breakout)
- Wick Rejection (Long wick showing buying/selling pressure)
- 21 EMA Trend Direction & Dynamic Bounce
- Inside Bar / False Breakout Trap

RETURN VALID JSON ONLY:
{{
  "is_trading_chart": true,
  "pair": "EUR/USD OTC",
  "signal": "CALL" | "PUT" | "WAIT",
  "pattern_id": "<pattern_id>",
  "pattern_name": "<Pattern Name>",
  "pattern_name_bn": "<প্যাটার্নের বাংলা নাম>",
  "recommended_expiry_minutes": 1,
  "confidence": 95,
  "confluence_factors": ["Support Level Rejection", "21 EMA Bounce"]
}}
"""

class MinuteSignalCache:
    """
    Single Source of Truth:
    Locks each currency pair's signal per candle minute.
    Guarantees 100% deterministic, identical signals for all clients worldwide!
    """
    def __init__(self):
        self.cache = {}
        self.active_signals = {}
        self.history = []

    def get_candle_key(self, pair_name):
        now = datetime.now(timezone.utc)
        if now.second >= 50:
            target_dt = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
        else:
            target_dt = now.replace(second=0, microsecond=0)
        norm_pair = pair_name.upper().replace("/", "").replace(" ", "").replace("-", "")
        return f"{norm_pair}_{target_dt.strftime('%Y%m%d_%H%M')}", target_dt

    def get(self, pair_name):
        key, _ = self.get_candle_key(pair_name)
        return self.cache.get(key, None)

    def set(self, pair_name, signal_dict):
        key, target_dt = self.get_candle_key(pair_name)
        signal_dict["candle_minute"] = target_dt.strftime("%H:%M:00")
        signal_dict["locked_key"] = key
        signal_dict["server_timestamp"] = datetime.now(timezone.utc).isoformat()
        self.cache[key] = signal_dict
        self.active_signals[pair_name.upper()] = signal_dict
        self.history.append(signal_dict)
        if len(self.history) > 100:
            self.history.pop(0)
        return signal_dict

signal_cache = MinuteSignalCache()

def evaluate_chart_with_gemini(image_bytes: bytes) -> dict:
    """
    Sends the user's mobile screen capture to Google Gemini AI deterministically.
    """
    if not GEMINI_API_KEY:
        return {"is_trading_chart": False, "signal": "WAIT", "pattern_name_bn": "API Key Not Configured on Server"}

    # Resize image for maximum speed (sub-second response)
    try:
        pil_img = Image.open(io.BytesIO(image_bytes))
        if pil_img.mode != "RGB":
            pil_img = pil_img.convert("RGB")
        w, h = pil_img.size
        max_dim = 1000
        if w > max_dim or h > max_dim:
            if w >= h:
                new_w = max_dim
                new_h = int(h * (max_dim / w))
            else:
                new_h = max_dim
                new_w = int(w * (max_dim / h))
            pil_img = pil_img.resize((new_w, new_h), Image.Resampling.BILINEAR)
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=75, optimize=True)
        image_bytes = buf.getvalue()
    except Exception as e:
        print(f"Image resize error: {e}")

    b64_data = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "contents": [{
            "parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": b64_data}},
                {"text": SYSTEM_VISION_PROMPT}
            ]
        }],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.0,
            "topK": 1
        }
    }
    req_bytes = json.dumps(payload).encode("utf-8")
    models = ["gemini-3.6-flash", "gemini-3.1-flash-lite", "gemini-flash-lite-latest"]
    raw_result = None

    for m in models:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={GEMINI_API_KEY}"
            req = urllib.request.Request(url, data=req_bytes, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                res_json = json.loads(resp.read().decode("utf-8"))
                text_val = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                if text_val.startswith("```"):
                    text_val = text_val.strip("`")
                    if text_val.startswith("json"):
                        text_val = text_val[4:].strip()
                raw_result = json.loads(text_val)
                if raw_result:
                    break
        except Exception as ex:
            print(f"[Gemini Model {m} Error] {ex}")
            continue

    if not raw_result:
        return {
            "is_trading_chart": False,
            "pair": "UNKNOWN",
            "signal": "WAIT",
            "pattern_name": "Scanner Ready",
            "pattern_name_bn": "স্ক্যানার প্রস্তুত (ক্লিয়ার চার্ট প্রয়োজন)",
            "recommended_expiry_minutes": 1,
            "confidence": 0,
            "confluence_factors": []
        }

    is_chart = raw_result.get("is_trading_chart", True)
    pair = raw_result.get("pair", "UNKNOWN").upper().strip()
    sig = str(raw_result.get("signal", "WAIT")).upper().strip()
    if sig not in ["CALL", "PUT"]:
        sig = "WAIT"

    return {
        "is_trading_chart": is_chart,
        "pair": pair if is_chart else "UNKNOWN",
        "signal": sig if is_chart else "WAIT",
        "pattern_id": raw_result.get("pattern_id", "candlestick_setup"),
        "pattern_name": raw_result.get("pattern_name", "Candlestick Setup"),
        "pattern_name_bn": raw_result.get("pattern_name_bn", "ক্যান্ডেলস্টিক সেটআপ"),
        "recommended_expiry_minutes": raw_result.get("recommended_expiry_minutes", 1),
        "confidence": raw_result.get("confidence", 95),
        "confluence_factors": raw_result.get("confluence_factors", ["Price Action Reaction"])
    }

# Latest Global Signal State (For WebSocket & fallback poll)
current_global_signal = {
    "status": "READY",
    "pair": "WAITING_FOR_SCREEN",
    "signal": "WAIT",
    "pattern_name_bn": "স্ক্রিন স্ক্যানের জন্য প্রস্তুত",
    "pattern_name_en": "Ready to scan live mobile screen",
    "recommended_expiry_minutes": 1,
    "confidence": 0,
    "confluence_factors": [],
    "server_timestamp": None
}

# WebSocket Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

@app.get("/")
def root():
    return {
        "service": "AI Laser Trading Central Signal Server",
        "status": "ONLINE",
        "active_clients": len(manager.active_connections),
        "docs_url": "/docs"
    }

@app.get("/health")
def health():
    return {"status": "healthy", "server_time_utc": datetime.now(timezone.utc).isoformat()}

@app.get("/api/signal/current")
def get_current_signal(pair: Optional[str] = None):
    now_utc = datetime.now(timezone.utc).isoformat()
    if pair:
        cached = signal_cache.get(pair)
        if cached:
            cached["server_timestamp"] = now_utc
            return cached
    current_global_signal["server_timestamp"] = now_utc
    return current_global_signal

@app.post("/api/scan")
async def handle_mobile_chart_scan(
    request: Request,
    file: Optional[UploadFile] = File(None)
):
    """
    🔥 CORE MOBILE SCANNER ENDPOINT 🔥
    Any mobile app across the world captures Quotex / Pocket Option screen
    and sends it here.
    1. Checks if another user already scanned this exact pair for this candle minute.
       If yes -> Returns the locked signal instantly (100% synchronized!).
    2. If no -> Calls Gemini AI with 48 Candlestick Patterns, locks the result,
       and returns it to this user and all subsequent users!
    """
    image_bytes = None

    if file:
        image_bytes = await file.read()
    else:
        # Check multipart or base64 JSON
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type:
            form = await request.form()
            upload = form.get("image") or form.get("file")
            if upload and hasattr(upload, "read"):
                image_bytes = await upload.read()
        elif "application/json" in content_type:
            body = await request.json()
            b64_str = body.get("image_base64") or body.get("image", "")
            if b64_str:
                if "," in b64_str:
                    b64_str = b64_str.split(",")[1]
                image_bytes = base64.b64decode(b64_str)

    if not image_bytes:
        raise HTTPException(status_code=400, detail="No screenshot image provided")

    # Evaluate with Gemini Vision AI
    result = evaluate_chart_with_gemini(image_bytes)

    if not result.get("is_trading_chart", False):
        return result

    pair_name = result.get("pair", "GLOBAL_CHART")

    # Check Minute-Lock Cache for this pair
    cached = signal_cache.get(pair_name)
    if cached is not None:
        return cached

    # Lock this new signal for this candle minute
    sig = result.get("signal", "WAIT")
    if sig in ["CALL", "PUT"]:
        locked = signal_cache.set(pair_name, result)
        global current_global_signal
        current_global_signal = dict(locked)
        await manager.broadcast(locked)
        return locked
    else:
        return result

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        await websocket.send_json(current_global_signal)
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
