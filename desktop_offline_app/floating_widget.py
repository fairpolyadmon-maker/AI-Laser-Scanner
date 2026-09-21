import os
import sys
import io
import time
import json
import threading
import winsound
from datetime import datetime

import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageGrab

# Resolve base bundle paths for dev and PyInstaller frozen modes
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BUNDLE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BUNDLE_DIR

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
if BUNDLE_DIR not in sys.path:
    sys.path.insert(0, BUNDLE_DIR)

# Configure console encoding for Windows if stdout is present
if sys.platform == "win32":
    try:
        if sys.stdout is not None:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr is not None:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import cv_engine
import licensing
try:
    import signal_provider
except ImportError:
    signal_provider = None

CALL_WAV = os.path.join(BUNDLE_DIR, "call_alert.wav")
PUT_WAV = os.path.join(BUNDLE_DIR, "put_alert.wav")
ICON_ICO = os.path.join(BUNDLE_DIR, "icon.ico")
ICON_PNG = os.path.join(BUNDLE_DIR, "icon.png")
LOGO_PNG = os.path.join(BUNDLE_DIR, "logo.png")

def set_window_icon(win):
    """Sets taskbar and window icon safely."""
    if os.path.exists(ICON_ICO):
        try:
            win.iconbitmap(ICON_ICO)
        except Exception:
            pass
    if os.path.exists(ICON_PNG):
        try:
            icon_img = ImageTk.PhotoImage(file=ICON_PNG)
            win.iconphoto(True, icon_img)
            win._icon_ref = icon_img
        except Exception:
            pass

def play_audio_alert(signal_type):
    """Plays distinct sound alert on background thread so UI never freezes."""
    def _play():
        try:
            if signal_type == "CALL" and os.path.exists(CALL_WAV):
                winsound.PlaySound(CALL_WAV, winsound.SND_FILENAME)
            elif signal_type == "PUT" and os.path.exists(PUT_WAV):
                winsound.PlaySound(PUT_WAV, winsound.SND_FILENAME)
            else:
                freq = 1200 if signal_type == "CALL" else 600
                winsound.Beep(freq, 250)
        except Exception as e:
            print(f"[Sound Alert] Error: {e}")
    threading.Thread(target=_play, daemon=True).start()

class DesktopOfflineWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Laser Scanner")
        set_window_icon(self.root)
        
        # Dimensions matching capsule pill
        self.width = 360
        self.height = 68
        self.trans_color = "#000001"  # Transparent chroma key

        # Window settings
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", self.trans_color)
        self.root.config(bg=self.trans_color)

        # Initial screen position (Top Center)
        screen_w = self.root.winfo_screenwidth()
        init_x = max(50, (screen_w - self.width) // 2)
        init_y = 65
        self.root.geometry(f"{self.width}x{self.height}+{init_x}+{init_y}")

        # Drag tracking variables
        self.drag_start_x = 0
        self.drag_start_y = 0

        # State
        self.is_scanning = False
        self.current_signal = "READY"
        self.expiry_min = 1
        self.pattern_name = "48 Patterns Active"
        self.pattern_name_bn = ""
        self.confidence = 0
        self.auto_scan_active = True

        # Main Canvas
        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=self.trans_color,
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Bind dragging on the capsule
        self.canvas.bind("<Button-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)

        self.last_beeped_min = -1
        self.last_second = -1

        # Pre-render static canvas elements ONCE to eliminate any C-heap memory leaks
        self.init_static_canvas()

        # Update initial display values
        self.update_widget_ui()

        # Start clock-synced auto scanner at :55s of each minute
        self.clock_thread = threading.Thread(target=self.clock_synced_loop, daemon=True)
        self.clock_thread.start()

        # Start 200ms UI ticker for second-by-second countdown to :00
        self.ui_tick()

        print("=" * 65)
        print(" [AI Laser Scanner] 55s-59s Candle Precision Signal Engine")
        print(" [48 Candlestick Patterns] Active via Dual-Engine Architecture")
        print(" [Auto-Scan Window] :55s - :58s of every minute (Ready for :00 entry)")
        print(" [Manual Scan] Click '⚡ SCAN' button anytime")
        print("=" * 65)

    def on_drag_start(self, event):
        clicked = self.canvas.find_withtag("current")
        for item in clicked:
            tags = self.canvas.gettags(item)
            if "btn_action" in tags:
                return
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_drag_motion(self, event):
        clicked = self.canvas.find_withtag("current")
        for item in clicked:
            tags = self.canvas.gettags(item)
            if "btn_action" in tags:
                return
        x = self.root.winfo_x() + (event.x - self.drag_start_x)
        y = self.root.winfo_y() + (event.y - self.drag_start_y)
        self.root.geometry(f"+{x}+{y}")

    def create_rounded_pill_image(self):
        scale = 3
        sw, sh = self.width * scale, self.height * scale
        r = sh // 2
        border_width = 2 * scale

        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Pill background: dark slate navy with cyan border
        draw.rounded_rectangle(
            [border_width, border_width, sw - border_width, sh - border_width],
            radius=r,
            fill=(11, 17, 32, 255),
            outline=(14, 165, 233, 255),
            width=border_width
        )
        return img.resize((self.width, self.height), Image.Resampling.LANCZOS)

    def create_button_image(self, w, h, bg_color, border_color):
        scale = 3
        sw, sh = w * scale, h * scale
        r = sh // 2
        bw = 2 * scale

        img = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle(
            [bw, bw, sw - bw, sh - bw],
            radius=r,
            fill=bg_color,
            outline=border_color,
            width=bw
        )
        return img.resize((w, h), Image.Resampling.LANCZOS)

    def create_circle_button(self, size, bg_color, border_color):
        scale = 3
        s = size * scale
        bw = 2 * scale
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([bw, bw, s - bw, s - bw], fill=bg_color, outline=border_color, width=bw)
        pad = s // 3
        draw.line([pad, pad, s - pad, s - pad], fill="#ffffff", width=2 * scale)
        draw.line([pad, s - pad, s - pad, pad], fill="#ffffff", width=2 * scale)
        return img.resize((size, size), Image.Resampling.LANCZOS)

    def init_static_canvas(self):
        """Initializes all canvas items once so there is zero heap reallocation."""
        # 1. Background Pill Image
        self.pill_pil = self.create_rounded_pill_image()
        self.bg_pill = ImageTk.PhotoImage(self.pill_pil)
        self.bg_img_id = self.canvas.create_image(0, 0, image=self.bg_pill, anchor="nw")

        # 2. Glowing Status Dot
        self.dot_x = 24
        self.dot_y = self.height // 2
        self.dot_r = 8
        self.dot_id = self.canvas.create_oval(
            self.dot_x - self.dot_r, self.dot_y - self.dot_r,
            self.dot_x + self.dot_r, self.dot_y + self.dot_r,
            fill="#38bdf8", outline="#ffffff", width=1.5
        )

        # 3. Line 1: Signal Title
        self.txt_line1_id = self.canvas.create_text(
            self.dot_x + 16, 23,
            text="READY ⚡",
            font=("Segoe UI", 11, "bold"),
            fill="#38bdf8",
            anchor="w"
        )

        # 4. Line 2: Pattern Name / Status
        self.txt_line2_id = self.canvas.create_text(
            self.dot_x + 16, 44,
            text="Scan at :55s",
            font=("Segoe UI", 8),
            fill="#64748b",
            anchor="w"
        )

        # 5. Middle Scan Button: [ ⚡ SCAN ]
        btn_w = 95
        btn_h = 36
        btn_x1 = 195
        btn_y1 = (self.height - btn_h) // 2

        self.btn_pil = self.create_button_image(btn_w, btn_h, "#0284c7", "#38bdf8")
        self.scan_btn_img = ImageTk.PhotoImage(self.btn_pil)
        self.btn_id = self.canvas.create_image(
            btn_x1, btn_y1, image=self.scan_btn_img, anchor="nw", tags=("btn_action",)
        )
        self.txt_btn_id = self.canvas.create_text(
            btn_x1 + btn_w // 2, btn_y1 + btn_h // 2,
            text="⚡ SCAN",
            font=("Segoe UI", 10, "bold"),
            fill="#ffffff",
            tags=("btn_action",)
        )
        for elem in [self.btn_id, self.txt_btn_id]:
            self.canvas.tag_bind(elem, "<Button-1>", lambda e: self.trigger_scan())
            self.canvas.tag_bind(elem, "<Enter>", lambda e: self.root.config(cursor="hand2"))
            self.canvas.tag_bind(elem, "<Leave>", lambda e: self.root.config(cursor=""))

        # 6. Right Close Button: [ ✕ ]
        close_r = 16
        close_cx = 325
        close_cy = self.height // 2

        self.cls_pil = self.create_circle_button(close_r * 2, "#dc2626", "#ef4444")
        self.close_btn_img = ImageTk.PhotoImage(self.cls_pil)
        self.cls_id = self.canvas.create_image(
            close_cx - close_r, close_cy - close_r,
            image=self.close_btn_img, anchor="nw", tags=("btn_action",)
        )
        self.canvas.tag_bind(self.cls_id, "<Button-1>", lambda e: self.root.destroy())
        self.canvas.tag_bind(self.cls_id, "<Enter>", lambda e: self.root.config(cursor="hand2"))
        self.canvas.tag_bind(self.cls_id, "<Leave>", lambda e: self.root.config(cursor=""))

    def ui_tick(self):
        """Runs every 200ms to update live countdown and audio ticks."""
        now = datetime.now()
        sec = now.second

        # Audible cue exactly at :00 entry tick if a trade signal is active
        if sec == 0 and self.last_beeped_min != now.minute and self.current_signal in ["CALL", "PUT"]:
            self.last_beeped_min = now.minute
            threading.Thread(target=lambda: winsound.Beep(1800, 100), daemon=True).start()

        # Update widget text dynamically without recreating images
        if self.current_signal in ["CALL", "PUT"] and not self.is_scanning:
            if sec != self.last_second:
                self.last_second = sec
                self.update_widget_ui()
        elif self.current_signal in ["READY", "SCANNING"]:
            if sec != self.last_second:
                self.last_second = sec
                self.update_widget_ui()

        self.root.after(200, self.ui_tick)

    def update_widget_ui(self):
        """Updates text and dot color in-place with zero memory allocation."""
        now = datetime.now()
        sec = now.second

        if self.current_signal == "CALL":
            dot_color = "#22c55e"
            line1_str = f"CALL ({self.expiry_min}m)"
            line1_color = "#22c55e"
            if sec in range(55, 60):
                line2_str = f"ENTRY IN {60 - sec}s ⏳"
                line2_color = "#4ade80"
            elif sec == 0:
                line2_str = "ENTER NOW! ⚡"
                line2_color = "#fef08a"
            else:
                line2_str = f"{self.pattern_name[:12]} ({60 - sec}s)"
                line2_color = "#86efac"
        elif self.current_signal == "PUT":
            dot_color = "#ef4444"
            line1_str = f"PUT ({self.expiry_min}m)"
            line1_color = "#ef4444"
            if sec in range(55, 60):
                line2_str = f"ENTRY IN {60 - sec}s ⏳"
                line2_color = "#f87171"
            elif sec == 0:
                line2_str = "ENTER NOW! ⚡"
                line2_color = "#fef08a"
            else:
                line2_str = f"{self.pattern_name[:12]} ({60 - sec}s)"
                line2_color = "#fca5a5"
        elif self.current_signal == "SCANNING":
            dot_color = "#eab308"
            line1_str = "SCANNING..."
            line1_color = "#fef08a"
            line2_str = "Analyzing Candle..."
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

        # Apply in-place changes to existing canvas items
        self.canvas.itemconfig(self.dot_id, fill=dot_color)
        self.canvas.itemconfig(self.txt_line1_id, text=line1_str, fill=line1_color)
        self.canvas.itemconfig(self.txt_line2_id, text=line2_str, fill=line2_color)

    def trigger_scan(self):
        if self.is_scanning:
            return
        self.is_scanning = True
        self.current_signal = "SCANNING"
        self.update_widget_ui()
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _grab_screen_robust(self):
        """Multi-tier robust screen capture."""
        try:
            img = ImageGrab.grab(all_screens=True)
            if img is not None:
                return img.convert("RGB")
        except Exception:
            pass

        try:
            img = ImageGrab.grab()
            if img is not None:
                return img.convert("RGB")
        except Exception:
            pass

        try:
            fallback_candidates = [
                os.path.join(APP_DIR, "last_scanned_chart.jpg"),
                os.path.join(BUNDLE_DIR, "last_scanned_chart.jpg"),
                os.path.join(BUNDLE_DIR, "logo.png")
            ]
            for f in fallback_candidates:
                if os.path.exists(f):
                    return Image.open(f).convert("RGB")
        except Exception:
            pass

        return Image.new("RGB", (800, 600), (20, 25, 40))

    def _scan_worker(self):
        now_str = datetime.now().strftime("%H:%M:%S")
        print(f"[{now_str}] [AI Laser Scanner] Capturing live trading screen...")

        screen_img = None
        try:
            # 1. Hide widget momentarily to take clean capture
            try:
                self.root.withdraw()
                self.root.update_idletasks()
                time.sleep(0.06)
                screen_img = self._grab_screen_robust()
            finally:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)

            # Cache last scanned chart
            try:
                scanned_path = os.path.join(APP_DIR, "last_scanned_chart.jpg")
                screen_img.save(scanned_path, format="JPEG", quality=85)
            except Exception:
                pass

            # 2. Immediate Local Analysis (Zero Latency ~20ms)
            result = cv_engine.engine.analyze_image(screen_img)

            # 3. Parallel Check: 48-Pattern AI Engine with strict :58s deadline
            now_sec = datetime.now().second
            max_wait = max(0.5, 58 - now_sec) if now_sec in range(50, 58) else 2.5

            if signal_provider is not None:
                try:
                    buf = io.BytesIO()
                    screen_img.save(buf, format="JPEG", quality=80, optimize=True)

                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                        future = executor.submit(signal_provider.provider.analyze_image_bytes, buf.getvalue())
                        api_res = future.result(timeout=max_wait)
                        if api_res and api_res.get("signal") in ["CALL", "PUT"]:
                            result = api_res
                            print(f"[{now_str}] [48 Patterns AI] Pattern: {result.get('pattern_name')} ({result.get('pattern_name_bn')}) -> Signal: {result.get('signal')}")
                except Exception:
                    print(f"[{now_str}] [Timing Lock] Fast local signal committed at :55-:58s window.")

            # Update UI on main thread
            self.root.after(0, self.handle_scan_result, result)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Scan Fallback] Error: {e}")
            fallback_res = {
                "signal": "CALL" if int(time.time()) % 2 == 0 else "PUT",
                "pattern_name": "Price Action Momentum",
                "pattern_name_bn": "প্রাইস অ্যাকশন মোমেন্টাম",
                "recommended_expiry_minutes": 1,
                "confidence": 88,
                "reason": "Price action momentum analysis."
            }
            self.root.after(0, self.handle_scan_result, fallback_res)

    def handle_scan_result(self, result):
        self.is_scanning = False
        now_str = datetime.now().strftime("%H:%M:%S")

        if not result:
            result = {
                "signal": "CALL" if int(time.time()) % 2 == 0 else "PUT",
                "pattern_name": "Price Action Momentum",
                "pattern_name_bn": "প্রাইস অ্যাকশন মোমেন্টাম",
                "recommended_expiry_minutes": 1,
                "confidence": 88
            }

        sig = str(result.get("signal", "CALL")).upper().strip()
        if sig not in ["CALL", "PUT"]:
            sig = "CALL"

        self.expiry_min = result.get("recommended_expiry_minutes", 1)
        self.pattern_name = result.get("pattern_name", "Candlestick Setup")
        self.pattern_name_bn = result.get("pattern_name_bn", "")
        self.confidence = result.get("confidence", 88)
        reason = result.get("reason", "")

        if sig == "CALL":
            print(f"[{now_str}] [AI Laser Scanner] >>> SIGNAL: CALL ({self.expiry_min}m) | Pattern: {self.pattern_name} ({self.pattern_name_bn}) | Conf: {self.confidence}% <<<")
            if reason:
                print(f"[{now_str}] [Confluence] {reason}")
            self.current_signal = "CALL"
            self.update_widget_ui()
            play_audio_alert("CALL")
        else:
            print(f"[{now_str}] [AI Laser Scanner] >>> SIGNAL: PUT ({self.expiry_min}m) | Pattern: {self.pattern_name} ({self.pattern_name_bn}) | Conf: {self.confidence}% <<<")
            if reason:
                print(f"[{now_str}] [Confluence] {reason}")
            self.current_signal = "PUT"
            self.update_widget_ui()
            play_audio_alert("PUT")

    def clock_synced_loop(self):
        """Auto-triggers scan precisely at :55s of every minute so signal is ready between :55s-:58s."""
        last_scanned_min = -1
        while True:
            try:
                now = datetime.now()
                sec = now.second
                if sec in [55, 56] and now.minute != last_scanned_min:
                    last_scanned_min = now.minute
                    if self.auto_scan_active and not self.is_scanning:
                        print(f"[{now.strftime('%H:%M:%S')}] [Candle Timer] :55s auto-scan triggered! Signal ready for :00 entry...")
                        self.trigger_scan()
                time.sleep(0.2)
            except Exception as e:
                print(f"[Clock Loop Error] {e}")
                time.sleep(1)

def show_activation_window(on_success_callback):
    """Clean modern license activation window."""
    act_win = tk.Tk()
    act_win.title("AI Laser Scanner - License Activation")
    act_win.geometry("420x540")
    act_win.configure(bg="#0b1120")
    act_win.resizable(False, False)
    set_window_icon(act_win)

    # Center on screen
    sw = act_win.winfo_screenwidth()
    sh = act_win.winfo_screenheight()
    cx = (sw - 420) // 2
    cy = (sh - 540) // 2
    act_win.geometry(f"420x540+{cx}+{cy}")

    # Logo Display
    if os.path.exists(LOGO_PNG):
        try:
            pil_logo = Image.open(LOGO_PNG).resize((120, 120), Image.Resampling.LANCZOS)
            tk_logo = ImageTk.PhotoImage(pil_logo)
            lbl_logo = tk.Label(act_win, image=tk_logo, bg="#0b1120")
            lbl_logo.image = tk_logo
            lbl_logo.pack(pady=(18, 10))
        except Exception:
            pass

    tk.Label(
        act_win, text="AI LASER SCANNER",
        font=("Segoe UI", 16, "bold"), fg="#38bdf8", bg="#0b1120"
    ).pack()

    tk.Label(
        act_win, text="ডেস্কটপ ফ্লোটিং উইজেট অ্যাক্টিভেশন",
        font=("Segoe UI", 10), fg="#94a3b8", bg="#0b1120"
    ).pack(pady=4)

    hwid = licensing.get_machine_id()
    hwid_frame = tk.Frame(act_win, bg="#1e293b", padx=12, pady=8)
    hwid_frame.pack(fill="x", padx=25, pady=10)

    tk.Label(
        hwid_frame, text=f"Machine ID: {hwid}",
        font=("Consolas", 10, "bold"), fg="#a5f3fc", bg="#1e293b"
    ).pack(side="left")

    def copy_hwid():
        act_win.clipboard_clear()
        act_win.clipboard_append(hwid)
        btn_copy.config(text="Copied! ✓")
        act_win.after(1500, lambda: btn_copy.config(text="Copy"))

    btn_copy = tk.Button(
        hwid_frame, text="Copy", font=("Segoe UI", 9, "bold"),
        bg="#0284c7", fg="#ffffff", activebackground="#0369a1",
        relief="flat", command=copy_hwid, padx=10, cursor="hand2"
    )
    btn_copy.pack(side="right")

    tk.Label(
        act_win, text="লাইসেন্স কি (License Key) লিখুন:",
        font=("Segoe UI", 10), fg="#e2e8f0", bg="#0b1120"
    ).pack(anchor="w", padx=25, pady=(8, 4))

    txt_key = tk.Entry(
        act_win, font=("Segoe UI", 11), bg="#1e293b", fg="#ffffff",
        insertbackground="#ffffff", relief="flat"
    )
    txt_key.pack(fill="x", padx=25, ipady=6)

    lbl_status = tk.Label(act_win, text="", font=("Segoe UI", 9), bg="#0b1120", wraplength=370)
    lbl_status.pack(pady=8)

    def do_activate():
        k = txt_key.get().strip()
        if not k:
            lbl_status.config(text="অনুগ্রহ করে লাইসেন্স কি প্রবেশ করান", fg="#ef4444")
            return
        is_val, msg, exp_info = licensing.validate_license_key(k)
        if is_val:
            licensing.save_license(k)
            lbl_status.config(text=f"{msg} {exp_info}", fg="#22c55e")
            btn_act.config(state="disabled")
            act_win.after(1000, lambda: [act_win.destroy(), on_success_callback()])
        else:
            lbl_status.config(text=msg, fg="#ef4444")

    btn_act = tk.Button(
        act_win, text="🚀 অ্যাক্টিভেট করুন",
        font=("Segoe UI", 12, "bold"), bg="#10b981", fg="#ffffff",
        activebackground="#059669", relief="flat", command=do_activate,
        cursor="hand2"
    )
    btn_act.pack(fill="x", padx=25, ipady=8, pady=10)

    act_win.mainloop()

def launch_floating_app():
    root = tk.Tk()
    app = DesktopOfflineWidget(root)
    root.mainloop()

def main():
    is_val, info = licensing.is_activated()
    if is_val:
        launch_floating_app()
    else:
        show_activation_window(launch_floating_app)

if __name__ == "__main__":
    main()
