import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JSON_PATH = os.path.join(BASE_DIR, "patterns", "candlestick_memory_48.json")

def get_all_patterns():
    if os.path.exists(JSON_PATH):
        try:
            with open(JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("patterns", [])
        except Exception:
            pass
    return []

def load_patterns_prompt():
    patterns = get_all_patterns()

    call_patterns_list = []
    put_patterns_list = []

    for p in patterns:
        p_id = p.get('id', '')
        p_name = p.get('name', '')
        p_bn = p.get('name_bn', '')
        p_rule = p.get('rule', '')
        p_desc = f"{p_name} ({p_bn}): {p_rule}"
        if p.get("signal") == "CALL":
            call_patterns_list.append(f"- {p_id}: {p_desc}")
        else:
            put_patterns_list.append(f"- {p_id}: {p_desc}")

    call_text = "\n".join(call_patterns_list[:24])
    put_text = "\n".join(put_patterns_list[:24])

    prompt = f"""You are the world's most elite Binary Options and Candlestick Pattern Recognition AI Analyst.
You possess complete knowledge of 48 Master Candlestick Patterns and Price Action Confluence.

Analyze this trading screen:

1. STRICT CHART VERIFICATION:
   - Does this image contain a trading chart with green and red Japanese Candlesticks (bodies and wicks)?
   - Works on BOTH desktop PC charts AND mobile phone trading apps (Quotex, Pocket Option, Binomo, Olymp Trade, Deriv, TradingView, MetaTrader) in portrait or landscape!
   - As long as candlestick bars (red/green) are visible on the mobile or desktop screen, it IS a valid trading chart (is_trading_chart: true).
   - ONLY return is_trading_chart: false if this is a phone home screen, chat app, gallery, or has zero trading candlesticks:
     {{"is_trading_chart": false, "signal": "NONE", "pair": "UNKNOWN", "pattern_id": "none", "pattern_name": "No Chart Detected", "pattern_name_bn": "কোনো চার্ট মেলেনি", "confidence": 0, "recommended_expiry_minutes": 1, "reason": "Not a trading chart."}}

2. AUTO-DETECT CURRENCY PAIR / ASSET:
   - Read the CURRENCY PAIR or ASSET NAME from the chart header, tab, or title (e.g. EUR/USD, EUR/JPY, GBP/USD OTC, CAD/CHF OTC, USD/INR OTC, BTC/USD, etc.). If not visible, default to "EUR/USD".

3. DECISIVE BINARY OPTIONS 1-MINUTE PREDICTION:
   - For Binary Options 1-minute expiration, evaluate whether BUYERS (CALL) or SELLERS (PUT) have the statistical edge for the upcoming candle.
   - Examine the latest candle body, wick rejections (lower wick = buying pressure, upper wick = selling pressure), momentum, and support/resistance.
   - Match the primary price action pattern from the 48 Patterns below.
   - You MUST pick either "CALL" (Up) or "PUT" (Down). Binary options requires an actionable direction on live charts. Never return "NONE" if candles are visible!
   - Confidence: 88 to 98.
   - Recommended expiry: 1 minute.

============================================================
48 MASTER CANDLESTICK PATTERNS MEMORY:
============================================================
A. BULLISH (CALL / UP) PATTERNS:
{call_text}

B. BEARISH (PUT / DOWN) PATTERNS:
{put_text}

Return strict JSON format only:
{{
  "is_trading_chart": true,
  "pair": "EUR/USD",
  "signal": "CALL",
  "pattern_id": "bullish_engulfing",
  "pattern_name": "Bullish Engulfing",
  "pattern_name_bn": "বুলিশ এঙ্গালফিং",
  "recommended_expiry_minutes": 1,
  "confidence": 94,
  "reason": "Lower wick rejection at support with strong green candle body confirming buyer dominance."
}}"""
    return prompt
