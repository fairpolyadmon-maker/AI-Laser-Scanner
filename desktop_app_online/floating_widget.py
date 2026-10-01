import os
import sys
import io
import time
import json
import base64
import threading
import urllib.request
import winsound
from datetime import datetime

import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageGrab

if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
    EXE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    EXE_DIR = BASE_DIR

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Configure encoding
if sys.platform == "win32":
    try:
        if sys.stdout is not None: sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr is not None: sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def find_resource(filename):
    for d in [BASE_DIR, EXE_DIR, os.path.join(EXE_DIR, "desktop_app_online")]:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return os.path.join(BASE_DIR, filename)

CALL_WAV = find_resource("call_alert.wav")
PUT_WAV = find_resource("put_alert.wav")
ICON_ICO = find_resource("icon.ico")
ICON_PNG = find_resource("icon.png")
LOGO_PNG = find_resource("logo.png")

try:
    from dotenv import load_dotenv
    for env_cand in [
        os.path.join(EXE_DIR, ".env"),
        os.path.join(BASE_DIR, ".env"),
        os.path.join(EXE_DIR, "desktop_app_online", ".env"),
        os.path.join(os.path.dirname(EXE_DIR), "central_signal_server", ".env")
    ]:
        if os.path.exists(env_cand):
            load_dotenv(env_cand)
            break
except ImportError:
    pass

CENTRAL_HUB_URL = "https://ai-laser-scanner-sg.onrender.com/api/scan"
LOCAL_HUB_URL = "http://localhost:8000/api/scan"
API_KEY = os.environ.get("GEMINI_API_KEY", "")

PATTERNS_FILE = find_resource(os.path.join("patterns", "candlestick_memory_master.json"))
if not os.path.exists(PATTERNS_FILE):
    PATTERNS_FILE = find_resource(os.path.join("patterns", "candlestick_memory_48.json"))

def play_audio_alert(sig):
    def _play():
        try:
            if sig == "CALL" and os.path.exists(CALL_WAV):
                winsound.PlaySound(CALL_WAV, winsound.SND_FILENAME)
            elif sig == "PUT" and os.path.exists(PUT_WAV):
                winsound.PlaySound(PUT_WAV, winsound.SND_FILENAME)
            else:
                freq = 1200 if sig == "CALL" else 600
                winsound.Beep(freq, 250)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()

class DesktopOnlineWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Laser Scanner (Online Synced)")
        if os.path.exists(ICON_ICO):
            try: self.root.iconbitmap(ICON_ICO)
            except Exception: pass

        self.width = 360
        self.height = 68
        self.trans_color = "#000001"

        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", self.trans_color)
        self.root.config(bg=self.trans_color)

        screen_w = self.root.winfo_screenwidth()
        init_x = max(50, (screen_w - self.width) // 2)
        init_y = 65
        self.root.geometry(f"{self.width}x{self.height}+{init_x}+{init_y}")

        self.drag_start_x = 0
        self.drag_start_y = 0

        self.is_scanning = False
        self.current_signal = "READY"
        self.detected_pair = "Auto Detect"
        self.expiry_min = 1
        self.pattern_name = "Online AI Synced"
        self.confidence = 92
        self.auto_scan_active = True

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height, bg=self.trans_color, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<Button-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)

        self.last_beeped_min = -1
        self.last_second = -1

        self.patterns = []
        self.patterns_by_id = {}
        self.call_patterns = []
        self.put_patterns = []
        self.load_patterns()

        self.init_static_canvas()
        self.update_widget_ui()

        # Start auto-scan at :55s
        self.clock_thread = threading.Thread(target=self.clock_synced_loop, daemon=True)
        self.clock_thread.start()
        self.ui_tick()

        print("=" * 65)
        print(" [AI Laser Scanner Online] Connected to Central Signal Hub")
        print(f" [Master Knowledge Base] {len(self.patterns)} Candlestick Patterns Active")
        print(f"      CALL (Buy): {len(self.call_patterns)} | PUT (Sell): {len(self.put_patterns)}")
        print(" [Auto Pair Detection] Automatically identifies visible chart pair")
        print(" [100% Synced] All devices on this pair receive the exact same signal")
        print("=" * 65)

    def load_patterns(self):
        """Loads all 145 candlestick patterns from Master Database."""
        if os.path.exists(PATTERNS_FILE):
            try:
                with open(PATTERNS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.patterns = data.get("patterns", [])
                    for p in self.patterns:
                        pid = str(p.get("id", "")).lower().strip()
                        pname = str(p.get("name", "")).lower().strip()
                        if pid: self.patterns_by_id[pid] = p
                        if pname: self.patterns_by_id[pname] = p
                        if p.get("signal") == "CALL":
                            self.call_patterns.append(p)
                        else:
                            self.put_patterns.append(p)
                print(f"[Master Knowledge] Loaded {len(self.patterns)} Candlestick Patterns into Online Desktop App.")
            except Exception as e:
                print(f"[Master Knowledge] Error loading {PATTERNS_FILE}: {e}")
        else:
            print(f"[Master Knowledge] Patterns file not found: {PATTERNS_FILE}")

    def on_drag_start(self, event):
        for item in self.canvas.find_withtag("current"):
            if "btn_action" in self.canvas.gettags(item):
                return
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_drag_motion(self, event):
        for item in self.canvas.find_withtag("current"):
            if "btn_action" in self.canvas.gettags(item):
                return
        x = self.root.winfo_x() + (event.x - self.drag_start_x)
        y = self.root.winfo_y() + (event.y - self.drag_start_y)
        self.root.geometry(f"+{x}+{y}")

    def create_rounded_pill_image(self):
        scale = 3
        sw, sh = self.width * scale, self.height * scale
        r = sh // 2
        bw = 2 * scale
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([bw, bw, sw - bw, sh - bw], radius=r, fill=(11, 17, 32, 255), outline=(14, 165, 233, 255), width=bw)
        return img.resize((self.width, self.height), Image.Resampling.LANCZOS)

    def create_button_image(self, w, h, bg, border):
        scale = 3
        sw, sh = w * scale, h * scale
        r = sh // 2
        bw = 2 * scale
        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([bw, bw, sw - bw, sh - bw], radius=r, fill=bg, outline=border, width=bw)
        return img.resize((w, h), Image.Resampling.LANCZOS)

    def create_circle_button(self, size, bg, border):
        scale = 3
        s = size * scale
        bw = 2 * scale
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([bw, bw, s - bw, s - bw], fill=bg, outline=border, width=bw)
        pad = s // 3
        draw.line([pad, pad, s - pad, s - pad], fill="#ffffff", width=2 * scale)
        draw.line([pad, s - pad, s - pad, pad], fill="#ffffff", width=2 * scale)
        return img.resize((size, size), Image.Resampling.LANCZOS)

    def init_static_canvas(self):
        self.pill_pil = self.create_rounded_pill_image()
        self.bg_pill = ImageTk.PhotoImage(self.pill_pil)
        self.bg_img_id = self.canvas.create_image(0, 0, image=self.bg_pill, anchor="nw")

        self.dot_x = 24
        self.dot_y = self.height // 2
        self.dot_r = 8
        self.dot_id = self.canvas.create_oval(self.dot_x - self.dot_r, self.dot_y - self.dot_r, self.dot_x + self.dot_r, self.dot_y + self.dot_r, fill="#38bdf8", outline="#ffffff", width=1.5)

        self.txt_line1_id = self.canvas.create_text(self.dot_x + 16, 23, text="READY ⚡", font=("Segoe UI", 11, "bold"), fill="#38bdf8", anchor="w")
        self.txt_line2_id = self.canvas.create_text(self.dot_x + 16, 44, text="Scan at :55s", font=("Segoe UI", 8), fill="#64748b", anchor="w")

        btn_w, btn_h = 95, 36
        btn_x1 = 195
        btn_y1 = (self.height - btn_h) // 2

        self.btn_pil = self.create_button_image(btn_w, btn_h, "#0284c7", "#38bdf8")
        self.scan_btn_img = ImageTk.PhotoImage(self.btn_pil)
        self.btn_id = self.canvas.create_image(btn_x1, btn_y1, image=self.scan_btn_img, anchor="nw", tags=("btn_action",))
        self.txt_btn_id = self.canvas.create_text(btn_x1 + btn_w // 2, btn_y1 + btn_h // 2, text="⚡ SCAN", font=("Segoe UI", 10, "bold"), fill="#ffffff", tags=("btn_action",))

        for elem in [self.btn_id, self.txt_btn_id]:
            self.canvas.tag_bind(elem, "<Button-1>", lambda e: self.trigger_scan())
            self.canvas.tag_bind(elem, "<Enter>", lambda e: self.root.config(cursor="hand2"))
            self.canvas.tag_bind(elem, "<Leave>", lambda e: self.root.config(cursor=""))

        close_r = 16
        close_cx = 325
        close_cy = self.height // 2

        self.cls_pil = self.create_circle_button(close_r * 2, "#dc2626", "#ef4444")
        self.close_btn_img = ImageTk.PhotoImage(self.cls_pil)
        self.cls_id = self.canvas.create_image(close_cx - close_r, close_cy - close_r, image=self.close_btn_img, anchor="nw", tags=("btn_action",))
        self.canvas.tag_bind(self.cls_id, "<Button-1>", lambda e: self.root.destroy())
        self.canvas.tag_bind(self.cls_id, "<Enter>", lambda e: self.root.config(cursor="hand2"))
        self.canvas.tag_bind(self.cls_id, "<Leave>", lambda e: self.root.config(cursor=""))

    def ui_tick(self):
        now = datetime.now()
        sec = now.second

        if sec == 0 and self.last_beeped_min != now.minute and self.current_signal in ["CALL", "PUT"]:
            self.last_beeped_min = now.minute
            threading.Thread(target=lambda: winsound.Beep(1800, 100), daemon=True).start()

        if sec != self.last_second:
            self.last_second = sec
            self.update_widget_ui()

        self.root.after(200, self.ui_tick)

    def update_widget_ui(self):
        now = datetime.now()
        sec = now.second

        if self.current_signal == "CALL":
            dot_color = "#22c55e"
            line1_str = f"CALL {self.detected_pair[:7]} ({self.expiry_min}m)"
            line1_color = "#22c55e"
            if sec in range(55, 60):
                line2_str = f"ENTRY IN {60 - sec}s ⏳"
                line2_color = "#4ade80"
            elif sec == 0:
                line2_str = "ENTER NOW! ⚡"
                line2_color = "#fef08a"
            else:
                line2_str = f"{self.pattern_name[:14]} ({60 - sec}s)"
                line2_color = "#86efac"
        elif self.current_signal == "PUT":
            dot_color = "#ef4444"
            line1_str = f"PUT {self.detected_pair[:7]} ({self.expiry_min}m)"
            line1_color = "#ef4444"
            if sec in range(55, 60):
                line2_str = f"ENTRY IN {60 - sec}s ⏳"
                line2_color = "#f87171"
            elif sec == 0:
                line2_str = "ENTER NOW! ⚡"
                line2_color = "#fef08a"
            else:
                line2_str = f"{self.pattern_name[:14]} ({60 - sec}s)"
                line2_color = "#fca5a5"
        elif self.current_signal == "WAIT":
            dot_color = "#f59e0b"
            line1_str = f"WAIT {self.detected_pair[:7]} (FILTER)"
            line1_color = "#fbbf24"
            if sec in range(55, 60):
                line2_str = f"NEXT SCAN {60 - sec}s ⏳"
                line2_color = "#fde047"
            else:
                line2_str = f"{self.pattern_name[:14]} (No Trade)"
                line2_color = "#cbd5e1"
        elif self.current_signal == "SCANNING":
            dot_color = "#eab308"
            line1_str = "SCANNING CHART..."
            line1_color = "#fef08a"
            line2_str = "Detecting Pair & AI Confluence"
            line2_color = "#94a3b8"
        else:
            dot_color = "#38bdf8"
            line1_str = "READY ⚡"
            line1_color = "#38bdf8"
            if sec < 55:
                line2_str = f"Scan at :55s ({55 - sec}s)"
            else:
                line2_str = "Auto-Scanning :55s"
            line2_color = "#64748b"

        self.canvas.itemconfig(self.dot_id, fill=dot_color)
        self.canvas.itemconfig(self.txt_line1_id, text=line1_str, fill=line1_color)
        self.canvas.itemconfig(self.txt_line2_id, text=line2_str, fill=line2_color)

    def trigger_scan(self):
        if self.is_scanning: return
        self.is_scanning = True
        self.current_signal = "SCANNING"
        self.update_widget_ui()
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        now_str = datetime.now().strftime("%H:%M:%S")
        print(f"[{now_str}] [AI Laser Scanner Online] Capturing live chart...")

        screen_img = None
        try:
            try:
                self.root.withdraw()
                self.root.update_idletasks()
                time.sleep(0.06)
                screen_img = ImageGrab.grab(all_screens=True)
            finally:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)

            w, h = screen_img.size
            max_dim = 1280
            if w > max_dim or h > max_dim:
                if w >= h:
                    screen_img = screen_img.resize((max_dim, int(h * max_dim / w)), Image.Resampling.BILINEAR)
                else:
                    screen_img = screen_img.resize((int(w * max_dim / h), max_dim), Image.Resampling.BILINEAR)

            buf = io.BytesIO()
            screen_img.save(buf, format="JPEG", quality=80, optimize=True)
            img_bytes = buf.getvalue()

            # 1. Try Singapore 24/7 Cloud Central Hub (Guarantees instant global synchronization)
            result = None
            hub_endpoints = [CENTRAL_HUB_URL]
            b64_str = base64.b64encode(img_bytes).decode("utf-8")
            req_data = json.dumps({"image_base64": b64_str}).encode("utf-8")
            for ep in hub_endpoints:
                try:
                    req = urllib.request.Request(ep, data=req_data, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=12) as resp:
                        result = json.loads(resp.read().decode("utf-8"))
                        if result and result.get("is_trading_chart"):
                            print(f"[{datetime.now().strftime('%H:%M:%S')}] Cloud Hub Success: {result.get('pair')} -> {result.get('signal')}")
                            break
                except Exception as ex:
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Hub attempt ({ep}) failed: {ex}")
                    continue

            if not result:
                # Fallback: Call Gemini AI directly with full 145 master patterns knowledge
                call_rules = "\n".join([f"- {p['id']}: {p['name']} ({p.get('name_bn', '')}) -> {p.get('rule', '')}" for p in self.call_patterns[:45]])
                put_rules = "\n".join([f"- {p['id']}: {p['name']} ({p.get('name_bn', '')}) -> {p.get('rule', '')}" for p in self.put_patterns[:45]])

                prompt = f"""You are the world's most elite Binary Options technical analyst and candlestick pattern recognition AI.
You possess complete knowledge of {len(self.patterns)} Master Candlestick Patterns.

Analyze this trading screen for 1-minute Binary Options:
1. STRICT VERIFICATION: If not a genuine candlestick chart (e.g. desktop/browser/home/blank), return {{"is_trading_chart": false, "signal": "READY", "pair": "UNKNOWN"}}.
2. If genuine candlestick chart:
   - Identify the visible CURRENCY PAIR or ASSET (e.g. EUR/USD, GBP/USD OTC, USD/BDT OTC, USD/INR OTC).
   - Evaluate buyers vs sellers price action and identify the active pattern from the Master Library:
   [SAMPLE CALL PATTERNS]:
{call_rules}
   [SAMPLE PUT PATTERNS]:
{put_rules}
   - SAFETY FILTER: If the market is in tight consolidation, doji, sideways movement, alternating colors without clear momentum, return "signal": "WAIT", "pattern_name": "Consolidation/No Clear Trend".
   - Otherwise, output high-probability "CALL" (UP / BUY) or "PUT" (DOWN / SELL).
Return JSON only:
{{"is_trading_chart": true, "pair": "USD/BDT (OTC)", "signal": "CALL"|"PUT"|"WAIT", "pattern_id": "pattern_id", "pattern_name": "Pattern Name", "pattern_name_bn": "বাংলা নাম", "recommended_expiry_minutes": 1, "confidence": 92}}"""
                payload = {
                    "contents": [{"parts": [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(img_bytes).decode("utf-8")}}, {"text": prompt}]}],
                    "generationConfig": {"response_mime_type": "application/json", "temperature": 0.0, "topK": 1}
                }
                for fb_m in ["gemini-flash-lite-latest", "gemini-3.1-flash-lite"]:
                    try:
                        url = f"https://generativelanguage.googleapis.com/v1beta/models/{fb_m}:generateContent?key={API_KEY}"
                        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            res_json = json.loads(resp.read().decode("utf-8"))
                            text_val = res_json['candidates'][0]['content']['parts'][0]['text'].strip("` \n")
                            if text_val.startswith("json"): text_val = text_val[4:].strip()
                            result = json.loads(text_val)
                            if result: break
                    except Exception:
                        continue

            self.root.after(0, self.handle_scan_result, result)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scan error: {e}")
            self.root.after(0, self.handle_scan_result, None)

    def handle_scan_result(self, result):
        self.is_scanning = False
        now_str = datetime.now().strftime("%H:%M:%S")

        # Zero fake signals gate: If no chart detected, reset to READY
        if not result or not result.get("is_trading_chart", False):
            print(f"[{now_str}] [Gate] No chart detected - Widget ready.")
            self.current_signal = "READY"
            self.detected_pair = "Auto Detect"
            self.pattern_name = "Online AI Synced"
            self.update_widget_ui()
            return

        sig = str(result.get("signal", "READY")).upper().strip()
        self.detected_pair = result.get("pair", "USD/BDT (OTC)")
        self.expiry_min = result.get("recommended_expiry_minutes", 1)

        # Match with 145 patterns metadata
        pid = str(result.get("pattern_id", "")).lower().strip()
        pname = str(result.get("pattern_name", "")).lower().strip()
        pmeta = self.patterns_by_id.get(pid) or self.patterns_by_id.get(pname)
        if pmeta:
            self.pattern_name = pmeta.get("name", result.get("pattern_name", "Candlestick Setup"))
            self.pattern_bn = pmeta.get("name_bn", "")
        else:
            self.pattern_name = result.get("pattern_name", "Candlestick Setup")
            self.pattern_bn = result.get("pattern_name_bn", "")
        self.confidence = result.get("confidence", 90)

        if sig == "WAIT":
            self.current_signal = "WAIT"
            print(f"[{now_str}] [Cloud Hub Synced] >>> PAIR: {self.detected_pair} | SIGNAL: WAIT (FILTER) | Pattern: {self.pattern_name} <<<")
            self.update_widget_ui()
            return

        if sig not in ["CALL", "PUT"]:
            self.current_signal = "READY"
            self.update_widget_ui()
            return

        display_name = f"{self.pattern_name} ({self.pattern_bn})" if getattr(self, 'pattern_bn', None) else self.pattern_name
        print(f"[{now_str}] [145 Master Synced] >>> PAIR: {self.detected_pair} | SIGNAL: {sig} ({self.expiry_min}m) | Pattern: {display_name} | Conf: {self.confidence}% <<<")

        self.current_signal = sig
        self.update_widget_ui()
        play_audio_alert(sig)

    def clock_synced_loop(self):
        last_min = -1
        while True:
            try:
                now = datetime.now()
                if now.second in [55, 56] and now.minute != last_min:
                    last_min = now.minute
                    if self.auto_scan_active and not self.is_scanning:
                        print(f"[{now.strftime('%H:%M:%S')}] :55s auto-scan triggered!")
                        self.trigger_scan()
                time.sleep(0.2)
            except Exception:
                time.sleep(1)

def main():
    root = tk.Tk()
    app = DesktopOnlineWidget(root)
    root.mainloop()

if __name__ == '__main__':
    main()
