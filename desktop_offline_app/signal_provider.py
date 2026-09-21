import os
import sys
import io
import time
import json
import base64
import urllib.request
from datetime import datetime

# Resolve base paths for both dev and PyInstaller frozen modes
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BUNDLE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BUNDLE_DIR

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Candlestick patterns path
PATTERNS_FILE = os.path.join(BUNDLE_DIR, "patterns", "candlestick_memory_48.json")
if not os.path.exists(PATTERNS_FILE):
    # Fallback to current directory or desktop_app directory
    alt_file = os.path.join(APP_DIR, "patterns", "candlestick_memory_48.json")
    if os.path.exists(alt_file):
        PATTERNS_FILE = alt_file

API_KEY = os.environ.get("GEMINI_API_KEY", "")

class SignalProvider:
    """
    48 Master Candlestick Patterns Engine for Desktop Offline Scanner.
    """
    def __init__(self, api_key=None):
        self.api_key = api_key or API_KEY
        self.patterns = []
        self.patterns_by_id = {}
        self.load_patterns()
        self.system_prompt = self._build_knowledge_prompt()

    def load_patterns(self):
        """Loads all 48 candlestick patterns into memory."""
        if os.path.exists(PATTERNS_FILE):
            try:
                with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.patterns = data.get("patterns", [])
                    self.patterns_by_id = {p["id"]: p for p in self.patterns}
            except Exception as e:
                print(f"[SignalProvider] Error loading patterns: {e}")
        else:
            print(f"[SignalProvider] Patterns file not found: {PATTERNS_FILE}")

    def get_pattern(self, pattern_id):
        return self.patterns_by_id.get(pattern_id.lower().strip(), None)

    def _build_knowledge_prompt(self):
        call_patterns_text = ""
        put_patterns_text = ""
        c_idx = 1
        p_idx = 1
        for p in self.patterns:
            line = f"  - ID: \"{p['id']}\" | {p['name']} ({p['name_bn']}): {p['rule']} [Expiry: {p.get('recommended_expiry_minutes', 1)}m]\n"
            if p.get("signal") == "CALL":
                call_patterns_text += f"  {c_idx}. " + line.lstrip()
                c_idx += 1
            else:
                put_patterns_text += f"  {p_idx}. " + line.lstrip()
                p_idx += 1

        prompt = f"""You are the world's most elite Binary Options technical analyst and candlestick recognition AI.
You have been trained on "THE CANDLESTICK TRADING BIBLE" and possess exact knowledge of 48 MASTER CANDLESTICK PATTERNS.

Your task is to analyze the attached live trading chart and provide a HIGH-ACCURACY signal for the VERY NEXT candle.

============================================================
KNOWLEDGE BASE: 48 MASTER CANDLESTICK PATTERNS
============================================================

A. 24 BULLISH (CALL / UP) PATTERNS & SETUPS:
{call_patterns_text}

B. 24 BEARISH (PUT / DOWN) PATTERNS & SETUPS:
{put_patterns_text}

============================================================
ANALYSIS RULES & CONFLUENCE:
============================================================
1. Examine the RIGHTMOST recent candles and current price action.
2. Identify support/resistance, key levels, or trendline interactions.
3. Match the current setup against the closest matching pattern among the 48 Master Patterns above.
4. If a bullish pattern or upward momentum/bounce is present -> Signal is "CALL".
5. If a bearish pattern or downward momentum/rejection is present -> Signal is "PUT".
6. If the image is NOT a trading chart -> Return "is_trading_chart": false, "signal": "NONE".

Return strict JSON only matching this schema:
{{
  "is_trading_chart": true,
  "signal": "CALL",
  "pattern_id": "bullish_engulfing",
  "pattern_name": "Bullish Engulfing",
  "pattern_name_bn": "বুলিশ এঙ্গালফিং",
  "recommended_expiry_minutes": 1,
  "confidence": 94,
  "reason": "Clear bullish engulfing at support with lower wick rejection"
}}"""
        return prompt

    def analyze_image_bytes(self, image_bytes):
        t0 = time.time()
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        kb_size = len(image_bytes) / 1024

        payload = {
            "contents": [{
                "parts": [
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64_data}},
                    {"text": self.system_prompt}
                ]
            }],
            "generationConfig": {"response_mime_type": "application/json"}
        }
        req_bytes = json.dumps(payload).encode("utf-8")

        models = ["gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.1-flash-lite-preview", "gemini-3.5-flash"]
        raw_result = None
        matched_model = None

        for m in models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={self.api_key}"
                req = urllib.request.Request(url, data=req_bytes, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=8) as resp:
                    res_json = json.loads(resp.read().decode("utf-8"))
                    text_val = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                    if text_val.startswith("```"):
                        text_val = text_val.strip("`")
                        if text_val.startswith("json"):
                            text_val = text_val[4:].strip()
                    raw_result = json.loads(text_val)
                    if raw_result:
                        matched_model = m
                        break
            except Exception:
                continue

        elapsed = time.time() - t0

        if not raw_result:
            return {
                "is_trading_chart": False,
                "signal": "NONE",
                "pattern_id": "none",
                "pattern_name": "No Signal",
                "pattern_name_bn": "কোনো সিগন্যাল মেলেনি",
                "recommended_expiry_minutes": 1,
                "confidence": 0,
                "reason": "API request failed or no response",
                "elapsed_sec": round(elapsed, 2)
            }

        is_chart = raw_result.get("is_trading_chart", False)
        signal = str(raw_result.get("signal", "NONE")).upper().strip()
        p_id = str(raw_result.get("pattern_id", "")).lower().strip()
        p_name = raw_result.get("pattern_name", "")
        p_name_bn = raw_result.get("pattern_name_bn", "")
        expiry = raw_result.get("recommended_expiry_minutes", 1)
        confidence = raw_result.get("confidence", 85)
        reason = raw_result.get("reason", "")

        if p_id in self.patterns_by_id:
            internal_p = self.patterns_by_id[p_id]
            if not p_name: p_name = internal_p["name"]
            if not p_name_bn: p_name_bn = internal_p["name_bn"]
            if not expiry: expiry = internal_p.get("recommended_expiry_minutes", 1)
        elif not p_name:
            p_name = "Price Action Setup"
            p_name_bn = "প্রাইস অ্যাকশন সেটআপ"

        return {
            "is_trading_chart": is_chart,
            "signal": signal if signal in ["CALL", "PUT"] else "NONE",
            "pattern_id": p_id,
            "pattern_name": p_name,
            "pattern_name_bn": p_name_bn,
            "recommended_expiry_minutes": expiry,
            "confidence": confidence,
            "reason": reason,
            "model_used": matched_model,
            "elapsed_sec": round(elapsed, 2),
            "payload_kb": round(kb_size, 1),
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }

# Singleton instance
provider = SignalProvider()
