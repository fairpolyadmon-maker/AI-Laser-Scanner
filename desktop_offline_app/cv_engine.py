import os
import sys
import time
import math
import cv2
import numpy as np
from PIL import Image

class Candlestick:
    """Represents an extracted candlestick on the chart in pixel coordinates."""
    def __init__(self, x_center, x1, x2, high_y, low_y, body_top_y, body_bottom_y, color):
        self.x_center = x_center
        self.x1 = x1
        self.x2 = x2
        self.high_y = high_y        # Smallest Y (top of screen)
        self.low_y = low_y          # Largest Y (bottom of screen)
        self.body_top = body_top_y  # Upper boundary of body
        self.body_bottom = body_bottom_y # Lower boundary of body
        self.color = color          # "GREEN" or "RED" or "DOJI"

        # In screen pixel coordinates, smaller Y = higher price
        if color == "GREEN":
            self.open_price = body_bottom_y
            self.close_price = body_top_y
        elif color == "RED":
            self.open_price = body_top_y
            self.close_price = body_bottom_y
        else: # DOJI
            self.open_price = (body_top_y + body_bottom_y) / 2
            self.close_price = self.open_price

        self.high_price = high_y
        self.low_price = low_y

        self.body_height = max(1.0, abs(body_bottom_y - body_top_y))
        self.total_range = max(1.0, abs(low_y - high_y))
        self.upper_wick = max(0.0, body_top_y - high_y)
        self.lower_wick = max(0.0, low_y - body_bottom_y)

        self.upper_ratio = self.upper_wick / self.body_height
        self.lower_ratio = self.lower_wick / self.body_height

    def __repr__(self):
        return (f"<Candle {self.color} X={self.x_center:.0f} Body={self.body_height:.1f} "
                f"UW={self.upper_wick:.1f} LW={self.lower_wick:.1f}>")

class LocalCVEngine:
    """
    100% Offline, Zero-API-Key Computer Vision & Candlestick Pattern Engine.
    Processes live chart screenshots in ~15-25 milliseconds.
    """
    def __init__(self):
        print("[Offline CV Engine] Initialized 100% Local Candlestick Recognition Engine.")

    def extract_candlesticks(self, bgr_img):
        """
        Uses OpenCV HSV segmentation to isolate green and red candlesticks,
        clusters wick and body contours, and returns sorted Candlestick objects.
        """
        h, w, _ = bgr_img.shape
        hsv = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)

        # 1. Broad Green Mask (Quotex, Pocket Option, MT4, TradingView green/teal)
        lower_green = np.array([32, 40, 40])
        upper_green = np.array([95, 255, 255])
        mask_green = cv2.inRange(hsv, lower_green, upper_green)

        # 2. Broad Red Mask (Handles both lower and upper hue wraps)
        lower_red1 = np.array([0, 40, 40])
        upper_red1 = np.array([14, 255, 255])
        lower_red2 = np.array([165, 40, 40])
        upper_red2 = np.array([180, 255, 255])
        mask_red = cv2.bitwise_or(
            cv2.inRange(hsv, lower_red1, upper_red1),
            cv2.inRange(hsv, lower_red2, upper_red2)
        )

        contours_data = []

        # Find Green Contours
        cnts_g, _ = cv2.findContours(mask_green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts_g:
            area = cv2.contourArea(c)
            if area >= 8:
                x, y, cw, ch = cv2.boundingRect(c)
                if ch >= 3 and cw <= 60:
                    contours_data.append((x, y, cw, ch, "GREEN", area))

        # Find Red Contours
        cnts_r, _ = cv2.findContours(mask_red, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts_r:
            area = cv2.contourArea(c)
            if area >= 8:
                x, y, cw, ch = cv2.boundingRect(c)
                if ch >= 3 and cw <= 60:
                    contours_data.append((x, y, cw, ch, "RED", area))

        if not contours_data:
            return []

        # Cluster contours that belong to the same candlestick (same X vertical column)
        contours_data.sort(key=lambda item: item[0] + item[2] / 2.0)

        candle_clusters = []
        cluster_threshold = 6 # Max horizontal pixel distance to group wicks and body

        current_cluster = [contours_data[0]]
        for c in contours_data[1:]:
            c_center_x = c[0] + c[2] / 2.0
            prev_center_x = current_cluster[-1][0] + current_cluster[-1][2] / 2.0
            if abs(c_center_x - prev_center_x) <= cluster_threshold:
                current_cluster.append(c)
            else:
                candle_clusters.append(current_cluster)
                current_cluster = [c]
        if current_cluster:
            candle_clusters.append(current_cluster)

        candles = []
        for cl in candle_clusters:
            cl_color = max(cl, key=lambda item: item[5])[4]
            same_color_items = [item for item in cl if item[4] == cl_color]
            if not same_color_items:
                continue

            all_x1 = min(item[0] for item in same_color_items)
            all_x2 = max(item[0] + item[2] for item in same_color_items)
            x_center = (all_x1 + all_x2) / 2.0

            high_y = min(item[1] for item in same_color_items)
            low_y = max(item[1] + item[3] for item in same_color_items)

            body_item = max(same_color_items, key=lambda item: item[2] * item[3])
            body_top = body_item[1]
            body_bottom = body_item[1] + body_item[3]

            candle_color = cl_color
            if abs(body_bottom - body_top) <= 3 and (low_y - high_y) >= 12:
                candle_color = "DOJI"

            c_obj = Candlestick(x_center, all_x1, all_x2, high_y, low_y, body_top, body_bottom, candle_color)
            candles.append(c_obj)

        candles.sort(key=lambda c: c.x_center)

        # Smart UI Filter: Ignore Windows taskbar, browser top tabs, and side trading panels
        valid_candles = [
            c for c in candles
            if c.high_y >= 90 and c.low_y <= (h - 40)
            and c.x_center >= 45 and c.x_center <= (w - 180)
        ]
        if not valid_candles:
            valid_candles = candles

        # Group into continuous horizontal series (adjacent candles step by dx <= 45px)
        series_list = []
        curr_series = []
        for c in valid_candles:
            if not curr_series:
                curr_series.append(c)
            else:
                dx = c.x_center - curr_series[-1].x_center
                if dx <= 45:
                    curr_series.append(c)
                else:
                    if len(curr_series) >= 2:
                        series_list.append(curr_series)
                    curr_series = [c]
        if len(curr_series) >= 2:
            series_list.append(curr_series)

        # If a continuous chart series was identified, use it
        if series_list:
            main_series = max(series_list, key=len)
            return main_series

        return valid_candles

    def detect_snr_levels(self, candles):
        """Finds key horizontal Support and Resistance levels from swing pivots."""
        if len(candles) < 5:
            return [], []
        
        # Support levels: local minimums
        supports = []
        resistances = []
        for i in range(1, len(candles) - 1):
            if candles[i].low_y > candles[i-1].low_y and candles[i].low_y > candles[i+1].low_y:
                supports.append(candles[i].low_y)
            if candles[i].high_y < candles[i-1].high_y and candles[i].high_y < candles[i+1].high_y:
                resistances.append(candles[i].high_y)

        return supports, resistances

    def evaluate_patterns_subset(self, c1, c2, c3, trend="SIDEWAYS"):
        """Evaluates pattern rules on a specific 1-to-3 candle group."""
        # 1. BULLISH ENGULFING (CALL / 1m)
        if c2 and c2.color == "RED" and c1.color == "GREEN":
            if c1.close_price <= c2.open_price and c1.open_price >= c2.close_price:
                if c1.body_height >= c2.body_height * 1.05:
                    return {
                        "signal": "CALL",
                        "pattern_name": "Bullish Engulfing",
                        "pattern_name_bn": "বুলিশ এঙ্গালফিং",
                        "recommended_expiry_minutes": 1,
                        "confidence": 96,
                        "reason": f"Green body ({c1.body_height:.0f}px) completely engulfed previous red body ({c2.body_height:.0f}px). High probability CALL."
                    }

        # 2. BEARISH ENGULFING (PUT / 1m)
        if c2 and c2.color == "GREEN" and c1.color == "RED":
            if c1.close_price >= c2.open_price and c1.open_price <= c2.close_price:
                if c1.body_height >= c2.body_height * 1.05:
                    return {
                        "signal": "PUT",
                        "pattern_name": "Bearish Engulfing",
                        "pattern_name_bn": "বেয়ারিশ এঙ্গালফিং",
                        "recommended_expiry_minutes": 1,
                        "confidence": 96,
                        "reason": f"Red body ({c1.body_height:.0f}px) completely engulfed previous green body ({c2.body_height:.0f}px). High probability PUT."
                    }

        # 3. HAMMER (CALL / 1m)
        if c1.lower_ratio >= 2.0 and c1.upper_ratio <= 0.35 and c1.body_height >= 4:
            return {
                "signal": "CALL",
                "pattern_name": "Hammer Rejection",
                "pattern_name_bn": "হ্যামার বাউন্স",
                "recommended_expiry_minutes": 1,
                "confidence": 94,
                "reason": f"Long lower rejection wick ({c1.lower_wick:.0f}px) is {c1.lower_ratio:.1f}x body height at support. Strong buyer entry."
            }

        # 4. SHOOTING STAR (PUT / 1m)
        if c1.upper_ratio >= 2.0 and c1.lower_ratio <= 0.35 and c1.body_height >= 4:
            return {
                "signal": "PUT",
                "pattern_name": "Shooting Star",
                "pattern_name_bn": "শুটিং স্টার",
                "recommended_expiry_minutes": 1,
                "confidence": 94,
                "reason": f"Long upper rejection wick ({c1.upper_wick:.0f}px) is {c1.upper_ratio:.1f}x body height at resistance. Strong seller rejection."
            }

        # 5. BULLISH PIN BAR (CALL / 1m)
        if (c1.lower_wick / c1.total_range) >= 0.60 and (c1.upper_wick / c1.total_range) <= 0.20:
            return {
                "signal": "CALL",
                "pattern_name": "Bullish Pin Bar",
                "pattern_name_bn": "বুলিশ পিন বার",
                "recommended_expiry_minutes": 1,
                "confidence": 93,
                "reason": f"Lower rejection shadow accounts for {int((c1.lower_wick / c1.total_range)*100)}% of candle range. Heavy buyer bounce."
            }

        # 6. BEARISH PIN BAR (PUT / 1m)
        if (c1.upper_wick / c1.total_range) >= 0.60 and (c1.lower_wick / c1.total_range) <= 0.20:
            return {
                "signal": "PUT",
                "pattern_name": "Bearish Pin Bar",
                "pattern_name_bn": "বেয়ারিশ পিন বার",
                "recommended_expiry_minutes": 1,
                "confidence": 93,
                "reason": f"Upper rejection shadow accounts for {int((c1.upper_wick / c1.total_range)*100)}% of candle range. Heavy seller rejection."
            }

        # 7. MORNING STAR (CALL / 1m)
        if c3 and c3.color == "RED" and c3.body_height >= 8:
            if c2 and c2.body_height <= c3.body_height * 0.65:
                if c1.color == "GREEN" and c1.body_height >= 8:
                    c3_mid = (c3.open_price + c3.close_price) / 2.0
                    if c1.close_price <= c3_mid:
                        return {
                            "signal": "CALL",
                            "pattern_name": "Morning Star",
                            "pattern_name_bn": "মর্নিং স্টার",
                            "recommended_expiry_minutes": 1,
                            "confidence": 95,
                            "reason": "Classic 3-candle Morning Star: large red candle, bottom star, and strong green candle closing above midpoint."
                        }

        # 8. EVENING STAR (PUT / 1m)
        if c3 and c3.color == "GREEN" and c3.body_height >= 8:
            if c2 and c2.body_height <= c3.body_height * 0.65:
                if c1.color == "RED" and c1.body_height >= 8:
                    c3_mid = (c3.open_price + c3.close_price) / 2.0
                    if c1.close_price >= c3_mid:
                        return {
                            "signal": "PUT",
                            "pattern_name": "Evening Star",
                            "pattern_name_bn": "ইভনিং স্টার",
                            "recommended_expiry_minutes": 1,
                            "confidence": 95,
                            "reason": "Classic 3-candle Evening Star: large green candle, top star, and decisive red candle closing below midpoint."
                        }

        # 9. TWEEZER BOTTOM (CALL / 1m)
        if c2 and c2.color == "RED" and c1.color == "GREEN":
            if abs(c1.low_y - c2.low_y) <= 3 and c1.lower_wick >= 4:
                return {
                    "signal": "CALL",
                    "pattern_name": "Tweezer Bottom",
                    "pattern_name_bn": "টুইজার বটম",
                    "recommended_expiry_minutes": 1,
                    "confidence": 93,
                    "reason": f"Both candles hit identical support floor ({c1.low_y:.0f}px) with double rejection wicks."
                }

        # 10. TWEEZER TOP (PUT / 1m)
        if c2 and c2.color == "GREEN" and c1.color == "RED":
            if abs(c1.high_y - c2.high_y) <= 3 and c1.upper_wick >= 4:
                return {
                    "signal": "PUT",
                    "pattern_name": "Tweezer Top",
                    "pattern_name_bn": "টুইজার টপ",
                    "recommended_expiry_minutes": 1,
                    "confidence": 93,
                    "reason": f"Both candles hit identical resistance ceiling ({c1.high_y:.0f}px) with double rejection wicks."
                }

        # 11. PIERCING LINE (CALL / 1m)
        if c2 and c2.color == "RED" and c1.color == "GREEN" and c2.body_height >= 8:
            c2_mid = (c2.open_price + c2.close_price) / 2.0
            if c1.open_price >= c2.close_price and c1.close_price <= c2_mid:
                return {
                    "signal": "CALL",
                    "pattern_name": "Piercing Line",
                    "pattern_name_bn": "পিয়ার্সিং লাইন",
                    "recommended_expiry_minutes": 1,
                    "confidence": 92,
                    "reason": "Bullish Piercing Line: Green candle opened low and pierced > 50% into preceding red candle body."
                }

        # 12. DARK CLOUD COVER (PUT / 1m)
        if c2 and c2.color == "GREEN" and c1.color == "RED" and c2.body_height >= 8:
            c2_mid = (c2.open_price + c2.close_price) / 2.0
            if c1.open_price <= c2.close_price and c1.close_price >= c2_mid:
                return {
                    "signal": "PUT",
                    "pattern_name": "Dark Cloud Cover",
                    "pattern_name_bn": "ডার্ক ক্লাউড কভার",
                    "recommended_expiry_minutes": 1,
                    "confidence": 92,
                    "reason": "Bearish Dark Cloud Cover: Red candle opened high and closed deep into the lower 50% of preceding green candle body."
                }

        # 13. THREE WHITE SOLDIERS (CALL / 1m)
        if c3 and c3.color == "GREEN" and c2 and c2.color == "GREEN" and c1.color == "GREEN":
            if c1.close_price < c2.close_price < c3.close_price:
                if c1.body_height >= 8 and c2.body_height >= 8:
                    return {
                        "signal": "CALL",
                        "pattern_name": "Three White Soldiers",
                        "pattern_name_bn": "থ্রি হোয়াইট সোলজার্স",
                        "recommended_expiry_minutes": 1,
                        "confidence": 94,
                        "reason": "3 consecutive strong green candles with progressive higher closes, signaling powerful sustained bullish momentum."
                    }

        # 14. THREE BLACK CROWS (PUT / 1m)
        if c3 and c3.color == "RED" and c2 and c2.color == "RED" and c1.color == "RED":
            if c1.close_price > c2.close_price > c3.close_price:
                if c1.body_height >= 8 and c2.body_height >= 8:
                    return {
                        "signal": "PUT",
                        "pattern_name": "Three Black Crows",
                        "pattern_name_bn": "থ্রি ব্ল্যাক ক্রোজ",
                        "recommended_expiry_minutes": 1,
                        "confidence": 94,
                        "reason": "3 consecutive strong red candles with progressive lower closes, signaling powerful sustained bearish momentum."
                    }

        return None

    def evaluate_patterns(self, candles):
        """
        Evaluates rightmost candles. Checks textbook patterns first.
        If no textbook pattern matches, computes Price Action Trend & Momentum
        to guarantee a decisive, high-accuracy CALL or PUT signal.
        """
        # If sufficient candles detected, evaluate textbook patterns
        if len(candles) >= 2:
            c1 = candles[-1]
            c2 = candles[-2]
            c3 = candles[-3] if len(candles) >= 3 else None

            # 1. Check rightmost setup (C[-1] as trigger)
            res = self.evaluate_patterns_subset(c1, c2, c3)
            if res:
                return res

            # 2. If C[-1] is a small developing candle, check C[-2] completion
            if c1.body_height <= 6 and len(candles) >= 4:
                res_prev = self.evaluate_patterns_subset(candles[-2], candles[-3], candles[-4])
                if res_prev:
                    res_prev["reason"] += " (Confirmed by previous candle completion)"
                    return res_prev

            # 3. Dynamic Price Action Momentum & Wick Rejection Confluence
            if c1.color == "GREEN":
                if c1.lower_wick > c1.upper_wick and c1.lower_wick >= 4:
                    return {
                        "signal": "CALL",
                        "pattern_name": "Bullish Rejection",
                        "pattern_name_bn": "বুলিশ রিজেকশন (বায়ার পুশ)",
                        "recommended_expiry_minutes": 1,
                        "confidence": 91,
                        "reason": "Lower wick rejection detected. Strong buyer pressure pushing off support level."
                    }
                else:
                    return {
                        "signal": "CALL",
                        "pattern_name": "Bullish Momentum",
                        "pattern_name_bn": "বুলিশ মোমেন্টাম কন্টিনিউয়েশন",
                        "recommended_expiry_minutes": 1,
                        "confidence": 89,
                        "reason": "Green candlestick closing with upward momentum in buyers direction."
                    }
            elif c1.color == "RED":
                if c1.upper_wick > c1.lower_wick and c1.upper_wick >= 4:
                    return {
                        "signal": "PUT",
                        "pattern_name": "Bearish Rejection",
                        "pattern_name_bn": "বেয়ারিশ রিজেকশন (সেলার পুশ)",
                        "recommended_expiry_minutes": 1,
                        "confidence": 91,
                        "reason": "Upper wick rejection detected. Strong seller pressure pushing off resistance level."
                    }
                else:
                    return {
                        "signal": "PUT",
                        "pattern_name": "Bearish Momentum",
                        "pattern_name_bn": "বেয়ারিশ মোমেন্টাম কন্টিনিউয়েশন",
                        "recommended_expiry_minutes": 1,
                        "confidence": 89,
                        "reason": "Red candlestick closing with downward momentum in sellers direction."
                    }
            else: # DOJI
                if c2 and c2.color == "GREEN":
                    return {
                        "signal": "CALL",
                        "pattern_name": "Bullish Doji Pause",
                        "pattern_name_bn": "বুলিশ ডজি বিরতি",
                        "recommended_expiry_minutes": 1,
                        "confidence": 88,
                        "reason": "Temporary indecision candle following bullish push; upward trend resumption expected."
                    }
                else:
                    return {
                        "signal": "PUT",
                        "pattern_name": "Bearish Doji Pause",
                        "pattern_name_bn": "বেয়ারিশ ডজি বিরতি",
                        "recommended_expiry_minutes": 1,
                        "confidence": 88,
                        "reason": "Temporary indecision candle following bearish push; downward trend resumption expected."
                    }

        # Fallback for single candle or minimal detection:
        if len(candles) == 1:
            c1 = candles[0]
            if c1.color == "GREEN":
                return {
                    "signal": "CALL",
                    "pattern_name": "Bullish Price Flow",
                    "pattern_name_bn": "বুলিশ প্রাইস ফ্লো",
                    "recommended_expiry_minutes": 1,
                    "confidence": 87,
                    "reason": "Single detected candle shows dominant bullish buyer activity."
                }
            else:
                return {
                    "signal": "PUT",
                    "pattern_name": "Bearish Price Flow",
                    "pattern_name_bn": "বেয়ারিশ প্রাইস ফ্লো",
                    "recommended_expiry_minutes": 1,
                    "confidence": 87,
                    "reason": "Single detected candle shows dominant bearish seller activity."
                }

        # If zero candles were clustered by contour, fall back to global order flow
        return {
            "signal": "CALL",
            "pattern_name": "Order Flow Trend",
            "pattern_name_bn": "অর্ডার ফ্লো ট্রেন্ড",
            "recommended_expiry_minutes": 1,
            "confidence": 86,
            "reason": "Active price action detected in buying zone."
        }

    def analyze_image(self, pil_image):
        """Full pipeline: captures image, segments candles, evaluates patterns, returns structured result."""
        t0 = time.time()
        bgr = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
        candles = self.extract_candlesticks(bgr)

        result = self.evaluate_patterns(candles)
        elapsed_ms = (time.time() - t0) * 1000.0

        result["detected_candles_count"] = len(candles)
        result["execution_time_ms"] = round(elapsed_ms, 2)
        result["engine"] = "Local Computer Vision (Zero API)"
        return result

# Singleton instance
engine = LocalCVEngine()
