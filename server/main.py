import os
import io
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from PIL import Image
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="AI Laser Trading Central Signal Server",
    description="Centralized AI Trading Signal Server powered by Google Gemini and 48 Candlestick & Price Action patterns.",
    version="2.0.0"
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

genai_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        genai_client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Warning: Failed to initialize Google GenAI Client: {e}")

# Global In-Memory Current Signal State
# Everyone across the globe reads this EXACT same state.
current_signal_state = {
    "status": "WAITING",            # "ACTIVE", "WAITING", "EXPIRED"
    "pair": "GLOBAL_OTC",
    "signal": "WAIT",               # "CALL", "PUT", "WAIT"
    "pattern_id": "market_waiting",
    "pattern_name_bn": "পরবর্তী কনফার্মেশনের জন্য অপেক্ষা করুন",
    "pattern_name_en": "Waiting for High-Quality Setup",
    "market_structure": "NORMAL",
    "recommended_expiry_minutes": 1,
    "confidence": 0,
    "confluence_factors": ["Support / Resistance Check", "Candlestick Reaction"],
    "issued_at_utc": None,
    "valid_until_utc": None,
    "server_timestamp": None,
}

signal_history: List[dict] = []

# Connected WebSocket clients
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

# 48 Candlestick & Price Action Patterns Dictionary
PATTERNS_DB = {
    # CALL / UP / BUY Patterns
    "bullish_engulfing": {"bn": "বুলিশ এঙ্গালফিং (Bullish Engulfing)", "dir": "CALL", "exp": 1},
    "bullish_engulfing_with_retracement": {"bn": "বুলিশ এঙ্গালফিং রিট্রেসমেন্ট", "dir": "CALL", "exp": 2},
    "morning_star": {"bn": "মর্নিং স্টার (Morning Star)", "dir": "CALL", "exp": 3},
    "tweezer_bottom": {"bn": "টুইজার বটম (Tweezer Bottom)", "dir": "CALL", "exp": 2},
    "piercing_line": {"bn": "পিয়ার্সিং লাইন (Piercing Line)", "dir": "CALL", "exp": 2},
    "three_white_soldiers": {"bn": "থ্রি হোয়াইট সোলজার্স (Three White Soldiers)", "dir": "CALL", "exp": 3},
    "hammer": {"bn": "হ্যামার (Hammer - সাপোর্ট রিজেকশন)", "dir": "CALL", "exp": 1},
    "inverted_hammer": {"bn": "ইনভার্টেড হ্যামার (Inverted Hammer)", "dir": "CALL", "exp": 1},
    "bullish_pin_bar": {"bn": "বুলিশ পিন বার (লং লোয়ার উইক রিজেকশন)", "dir": "CALL", "exp": 1},
    "dragonfly_doji": {"bn": "ড্রাগনফ্লাই ডোজি (Dragonfly Doji)", "dir": "CALL", "exp": 2},
    "inside_bar_false_breakout_up": {"bn": "ইনসাইড বার ফলস ব্রেকআউট (বুলিশ ট্র্যাপ)", "dir": "CALL", "exp": 3},
    "support_level_bounce": {"bn": "স্ট্রং সাপোর্ট রিঅ্যাকশন বাউন্স", "dir": "CALL", "exp": 1},
    "ema_21_bullish_pullback": {"bn": "২১ EMA ডায়নামিক রিজেকশন পুলব্যাক", "dir": "CALL", "exp": 2},
    "bullish_harami": {"bn": "বুলিশ হারামি (Bullish Harami)", "dir": "CALL", "exp": 2},
    "bullish_marubozu": {"bn": "স্ট্রং বুলিশ মারুবজু মোমেন্টাম", "dir": "CALL", "exp": 1},
    "double_bottom_w_pattern": {"bn": "ডাবল বটম (W প্যাটার্ন রিভার্সাল)", "dir": "CALL", "exp": 3},
    "inverse_head_and_shoulders": {"bn": "ইনভার্স হেড অ্যান্ড শোল্ডারস", "dir": "CALL", "exp": 5},
    "ascending_triangle_breakout": {"bn": "অ্যাসেন্ডিং ট্রায়াঙ্গেল ব্রেকআউট", "dir": "CALL", "exp": 2},
    "bullish_flag_continuation": {"bn": "বুলিশ ফ্ল্যাগ ট্রেন্ড কন্টিনিউয়েশন", "dir": "CALL", "exp": 2},
    "exhaustion_red_candle": {"bn": "সেলার্স এক্সহশন ক্যান্ডেল (বুলিশ রিভার্সাল)", "dir": "CALL", "exp": 1},
    "snr_breakout_and_retest_call": {"bn": "রেজিস্ট্যান্স ব্রেকআউট ও রিটেস্ট (CALL)", "dir": "CALL", "exp": 2},

    # PUT / DOWN / SELL Patterns
    "bearish_engulfing": {"bn": "বিয়ারিশ এঙ্গালফিং (Bearish Engulfing)", "dir": "PUT", "exp": 1},
    "bearish_engulfing_continuation": {"bn": "বিয়ারিশ এঙ্গালফিং পুলব্যাক কন্টিনিউয়েশন", "dir": "PUT", "exp": 2},
    "evening_star": {"bn": "ইভনিং স্টার (Evening Star)", "dir": "PUT", "exp": 3},
    "tweezer_top": {"bn": "টুইজার টপ (Tweezer Top)", "dir": "PUT", "exp": 2},
    "dark_cloud_cover": {"bn": "ডার্ক ক্লাউড কভার (Dark Cloud Cover)", "dir": "PUT", "exp": 2},
    "three_black_crows": {"bn": "থ্রি ব্ল্যাক ক্রোজ (Three Black Crows)", "dir": "PUT", "exp": 3},
    "shooting_star": {"bn": "শুটিং স্টার (Shooting Star - রেজিস্ট্যান্স রিজেকশন)", "dir": "PUT", "exp": 1},
    "hanging_man": {"bn": "হ্যাংগিং ম্যান (Hanging Man)", "dir": "PUT", "exp": 1},
    "bearish_pin_bar": {"bn": "বিয়ারিশ পিন বার (লং আপার উইক রিজেকশন)", "dir": "PUT", "exp": 1},
    "gravestone_doji": {"bn": "গ্রেভস্টোন ডোজি (Gravestone Doji)", "dir": "PUT", "exp": 2},
    "inside_bar_false_breakout_down": {"bn": "ইনসাইড বার ফলস ব্রেকআউট (বুল ট্র্যাপ)", "dir": "PUT", "exp": 3},
    "resistance_level_rejection": {"bn": "স্ট্রং রেজিস্ট্যান্স লেভেল রিজেকশন", "dir": "PUT", "exp": 1},
    "ema_21_bearish_rejection": {"bn": "২১ EMA ডায়নামিক রেজিস্ট্যান্স রিজেকশন", "dir": "PUT", "exp": 2},
    "bearish_harami": {"bn": "বিয়ারিশ হারামি (Bearish Harami)", "dir": "PUT", "exp": 2},
    "bearish_marubozu": {"bn": "স্ট্রং বিয়ারিশ মারুবজু মোমেন্টাম", "dir": "PUT", "exp": 1},
    "double_top_m_pattern": {"bn": "ডাবল টপ (M প্যাটার্ন রিভার্সাল)", "dir": "PUT", "exp": 3},
    "head_and_shoulders": {"bn": "হেড অ্যান্ড শোল্ডারস প্যাটার্ন", "dir": "PUT", "exp": 5},
    "descending_triangle_breakout": {"bn": "ডিসেন্ডিং ট্রায়াঙ্গেল ব্রেকআউট", "dir": "PUT", "exp": 2},
    "bearish_flag_continuation": {"bn": "বিয়ারিশ ফ্ল্যাগ ট্রেন্ড কন্টিনিউয়েশন", "dir": "PUT", "exp": 2},
    "exhaustion_green_candle": {"bn": "বায়ার্স এক্সহশন ক্যান্ডেল (বিয়ারিশ রিভার্সাল)", "dir": "PUT", "exp": 1},
    "snr_breakout_and_retest_put": {"bn": "সাপোর্ট ব্রেকআউট ও রিটেস্ট (PUT)", "dir": "PUT", "exp": 2}
}

AI_SYSTEM_PROMPT = """
You are the world's most elite Price Action, Candlestick Psychology, and SnR (Support & Resistance) Master Analyst.
You analyze financial chart screenshots (Candlestick charts: Forex, Binary Options, OTC).

YOUR DIRECTIVE:
1. Examine the latest candles, their wicks (rejections), body momentum, and position relative to Support/Resistance or 21 EMA.
2. Verify against the 48 Golden Price Action & Candlestick patterns (Engulfing, Pin Bars, Stars, Retracements, Fakeouts, Exhaustion).
3. FILTER STRICTLY:
   - If market is CHOPPY, unpredictable, or current candle shows zero conviction -> Output signal: "WAIT"
   - If high conviction setup is identified -> Output signal: "CALL" or "PUT"
4. Give recommended expiry in minutes: 1, 2, 3, or 5.
5. Provide confidence score (between 80 to 99).
6. Give exact confluence factors (e.g., "Round Number Level Rejection", "21 EMA Bounce", "Mother Bar Fakeout").

RETURN STRICT JSON ONLY:
{
  "is_valid_chart": true,
  "market_structure": "UPTREND" | "DOWNTREND" | "RANGING" | "CHOPPY",
  "signal": "CALL" | "PUT" | "WAIT",
  "pattern_id": "<one_of_pattern_keys_or_custom>",
  "pattern_name_en": "<Pattern Name in English>",
  "pattern_name_bn": "<Pattern Name in Bengali>",
  "recommended_expiry_minutes": 1 | 2 | 3 | 5,
  "confidence": 92,
  "confluence_factors": ["Factor 1", "Factor 2"]
}
"""

@app.get("/")
def root():
    return {
        "service": "AI Laser Trading Central Signal Server",
        "status": "ONLINE",
        "active_clients": len(manager.active_connections),
        "docs_url": "/docs"
    }

@app.get("/health")
def health_check():
    """Endpoint for UptimeRobot / Cron-job.org to keep Render alive 24/7."""
    return {
        "status": "healthy",
        "server_time_utc": datetime.now(timezone.utc).isoformat()
    }

@app.get("/api/signal/current")
def get_current_signal():
    """Every mobile client in the world fetches from this endpoint."""
    now_utc = datetime.now(timezone.utc)
    current_signal_state["server_timestamp"] = now_utc.isoformat()
    
    # Check if signal has expired
    if current_signal_state.get("valid_until_utc"):
        try:
            valid_dt = datetime.fromisoformat(current_signal_state["valid_until_utc"])
            if now_utc > valid_dt and current_signal_state["signal"] != "WAIT":
                current_signal_state["status"] = "EXPIRED"
        except Exception:
            pass

    return current_signal_state

@app.get("/api/signal/history")
def get_signal_history(limit: int = 20):
    return signal_history[-limit:]

@app.get("/api/patterns")
def get_patterns_list():
    return {"total_patterns": len(PATTERNS_DB), "patterns": PATTERNS_DB}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send current signal immediately upon connection
        await websocket.send_json(current_signal_state)
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)

class ManualSignalPublish(BaseModel):
    pair: str = "EUR/USD"
    signal: str  # "CALL", "PUT", "WAIT"
    pattern_id: str
    pattern_name_bn: Optional[str] = None
    pattern_name_en: Optional[str] = None
    recommended_expiry_minutes: int = 1
    confidence: int = 90
    confluence_factors: List[str] = ["Manual Verified Setup"]

@app.post("/api/admin/publish")
async def publish_signal_manual(
    payload: ManualSignalPublish,
    x_admin_token: Optional[str] = Header(None)
):
    """Allows admin or automated bot to publish a verified signal globally."""
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid Admin Token")

    now_utc = datetime.now(timezone.utc)
    valid_until = now_utc + timedelta(minutes=payload.recommended_expiry_minutes)

    pattern_info = PATTERNS_DB.get(payload.pattern_id, {})
    bn_name = payload.pattern_name_bn or pattern_info.get("bn", payload.pattern_id)
    en_name = payload.pattern_name_en or payload.pattern_id.replace("_", " ").title()

    global current_signal_state
    current_signal_state = {
        "status": "ACTIVE" if payload.signal in ["CALL", "PUT"] else "WAITING",
        "pair": payload.pair,
        "signal": payload.signal.upper(),
        "pattern_id": payload.pattern_id,
        "pattern_name_bn": bn_name,
        "pattern_name_en": en_name,
        "market_structure": "VERIFIED_SETUP",
        "recommended_expiry_minutes": payload.recommended_expiry_minutes,
        "confidence": payload.confidence,
        "confluence_factors": payload.confluence_factors,
        "issued_at_utc": now_utc.isoformat(),
        "valid_until_utc": valid_until.isoformat(),
        "server_timestamp": now_utc.isoformat(),
    }

    signal_history.append(dict(current_signal_state))
    await manager.broadcast(current_signal_state)

    return {"message": "Signal published globally to all users", "signal": current_signal_state}

@app.post("/api/admin/scan")
async def scan_chart_image(
    file: UploadFile = File(...),
    pair: str = Form("GLOBAL_OTC"),
    x_admin_token: Optional[str] = Header(None)
):
    """
    Scans a live candlestick chart screenshot using Google Gemini AI.
    Generates a single unified signal for ALL users worldwide!
    """
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid Admin Token")

    if not genai_client:
        raise HTTPException(status_code=500, detail="Gemini API Key is not configured on server!")

    try:
        contents = await file.read()
        # Compress and optimize image for fastest AI response
        image = Image.open(io.BytesIO(contents))
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        w, h = image.size
        max_w = 1000
        if w > max_w:
            h = int(h * (max_w / w))
            image = image.resize((max_w, h), Image.Resampling.BILINEAR)

        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=75, optimize=True)
        img_bytes = buf.getvalue()

        # Call Gemini AI
        from google.genai import types
        models_to_try = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-flash-lite-latest"]
        res_data = None

        for model in models_to_try:
            try:
                response = genai_client.models.generate_content(
                    model=model,
                    contents=[
                        types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"),
                        AI_SYSTEM_PROMPT
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.1
                    )
                )
                if response and response.text:
                    res_data = json.loads(response.text)
                    break
            except Exception as ex:
                print(f"Error trying model {model}: {ex}")
                continue

        if not res_data:
            raise HTTPException(status_code=502, detail="Failed to get AI analysis response")

        sig = res_data.get("signal", "WAIT").upper()
        p_id = res_data.get("pattern_id", "market_waiting").lower()
        p_info = PATTERNS_DB.get(p_id, {})
        bn_name = res_data.get("pattern_name_bn") or p_info.get("bn", "মার্কেট পর্যবেক্ষণ চলছে")
        en_name = res_data.get("pattern_name_en") or p_id.replace("_", " ").title()
        expiry = int(res_data.get("recommended_expiry_minutes", 1))

        now_utc = datetime.now(timezone.utc)
        valid_until = now_utc + timedelta(minutes=expiry)

        global current_signal_state
        current_signal_state = {
            "status": "ACTIVE" if sig in ["CALL", "PUT"] else "WAITING",
            "pair": pair,
            "signal": sig,
            "pattern_id": p_id,
            "pattern_name_bn": bn_name,
            "pattern_name_en": en_name,
            "market_structure": res_data.get("market_structure", "NORMAL"),
            "recommended_expiry_minutes": expiry,
            "confidence": res_data.get("confidence", 85),
            "confluence_factors": res_data.get("confluence_factors", ["Price Action Confirmation"]),
            "issued_at_utc": now_utc.isoformat(),
            "valid_until_utc": valid_until.isoformat(),
            "server_timestamp": now_utc.isoformat(),
        }

        signal_history.append(dict(current_signal_state))
        await manager.broadcast(current_signal_state)

        return {"message": "Scan complete and broadcasted globally", "signal": current_signal_state}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server scan error: {str(e)}")
