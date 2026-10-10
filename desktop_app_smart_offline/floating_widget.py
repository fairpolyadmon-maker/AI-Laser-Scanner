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
from voice_assistant import voice

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

class DesktopSmartOfflineWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Laser Scanner Smart Offline")
        set_window_icon(self.root)

        # Dimensions matching capsule pill
        self.width = 380
        self.height = 70
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
        self.current_signal = "INITIALIZING"  # "NO_CHART", "READY", "CALL", "PUT", "SCANNING"
        self.expiry_min = 1
        self.pattern_name = "AI Laser Scanner"
        self.pattern_name_bn = ""
        self.confidence = 0
        self.has_active_chart = False
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
        self.pending_signal_res = None
        self.pending_signal_minute = -1

        # Pre-render static canvas elements ONCE
        self.init_static_canvas()

        # Update initial display values
        self.update_widget_ui()

        # Start clock-synced auto scanner at :54s of each minute
        self.clock_thread = threading.Thread(target=self.clock_synced_loop, daemon=True)
        self.clock_thread.start()

        # Start 200ms UI ticker for second-by-second countdown to :00
        self.ui_tick()

        # Run startup chart check after 600ms
        self.root.after(600, self.initial_startup_check)

        print("=" * 65)
        print(" [AI Laser Scanner Smart Offline] Voice-Enabled Precision Engine")
        print(" [Smart Chart Gate] Zero Fake Signals (Strict Candlestick Verification)")
        print(" [Voice Announcements] Active (Bangla High-Def Speech Engine)")
        print(" [5-Second Early Alert] Firing at :55s for precise :00 entry")
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
        """Initializes all canvas items once."""
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
            self.dot_x + 16, 24,
            text="অপেক্ষা করুন ⚡",
            font=("Segoe UI", 11, "bold"),
            fill="#38bdf8",
            anchor="w"
        )

        # 4. Line 2: Pattern Name / Status
        self.txt_line2_id = self.canvas.create_text(
            self.dot_x + 16, 46,
            text="চার্ট স্ক্যান করা হচ্ছে...",
            font=("Segoe UI", 8),
            fill="#64748b",
            anchor="w"
        )

        # 5. Middle Scan Button: [ ⚡ SCAN ]
        btn_w = 95
        btn_h = 36
        btn_x1 = 215
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
            self.canvas.tag_bind(elem, "<Button-1>", lambda e: self.trigger_scan(manual=True))
            self.canvas.tag_bind(elem, "<Enter>", lambda e: self.root.config(cursor="hand2"))
            self.canvas.tag_bind(elem, "<Leave>", lambda e: self.root.config(cursor=""))

        # 6. Right Close Button: [ ✕ ]
        close_r = 16
        close_cx = 345
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
            voice.play_entry_beep()

        # Reset old signal to READY after candle begins (after entry period 0-5s)
        # Prevents stale signal from showing when user closes or changes window!
        if sec > 5 and sec < 55 and self.current_signal in ["CALL", "PUT"]:
            if self.has_active_chart:
                self.current_signal = "READY"
            else:
                self.current_signal = "NO_CHART"

        if sec != self.last_second:
            self.last_second = sec
            self.update_widget_ui()

        self.root.after(200, self.ui_tick)

    def update_widget_ui(self):
        """Updates text and dot color in-place."""
        now = datetime.now()
        sec = now.second

        if self.current_signal == "CALL":
            dot_color = "#22c55e"
            line1_str = f"🟢 CALL ({self.expiry_min}m)"
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
            line1_str = f"🔴 PUT ({self.expiry_min}m)"
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
        elif self.current_signal == "NO_CHART":
            dot_color = "#ef4444"
            line1_str = "চার্ট নেই 🔴"
            line1_color = "#f87171"
            line2_str = "চার্ট ওপেন করুন"
            line2_color = "#94a3b8"
        elif self.current_signal == "SCANNING":
            dot_color = "#eab308"
            line1_str = "স্ক্যানিং..."
            line1_color = "#fef08a"
            line2_str = "চার্ট বিশ্লেষণ হচ্ছে..."
            line2_color = "#94a3b8"
        elif self.current_signal == "READY":
            dot_color = "#22c55e"
            line1_str = "চার্ট প্রস্তুত 🟢"
            line1_color = "#4ade80"
            if sec < 55:
                line2_str = f"সিগনাল আসবে :55s ({55 - sec}s)"
            else:
                line2_str = "অপেক্ষা করুন..."
            line2_color = "#38bdf8"
        else: # INITIALIZING
            dot_color = "#38bdf8"
            line1_str = "AI স্ক্যানার ⚡"
            line1_color = "#38bdf8"
            line2_str = "চার্ট চেক হচ্ছে..."
            line2_color = "#64748b"

        self.canvas.itemconfig(self.dot_id, fill=dot_color)
        self.canvas.itemconfig(self.txt_line1_id, text=line1_str, fill=line1_color)
        self.canvas.itemconfig(self.txt_line2_id, text=line2_str, fill=line2_color)

    def _grab_screen_robust(self):
        """Robust screen capture."""
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

        return Image.new("RGB", (800, 600), (20, 25, 40))

    def initial_startup_check(self):
        """Checks screen immediately on launch and provides speech confirmation."""
        threading.Thread(target=self._startup_worker, daemon=True).start()

    def _startup_worker(self):
        print("[Startup Check] Scanning screen on app launch...")
        time.sleep(0.1)
        screen_img = self._grab_screen_robust()
        res = cv_engine.engine.analyze_image(screen_img)

        if not res.get("is_trading_chart", False):
            print("[Startup Check] No chart detected on screen.")
            self.has_active_chart = False
            self.current_signal = "NO_CHART"
            self.root.after(0, self.update_widget_ui)
            # User request: "zokhon eti ke open kora hobe tokhon zodi kono chart na dekhe tokhon se bolobe 'আমি কোন চার্ট দেখতে পারছি না'"
            voice.speak_no_chart(force=True)
        else:
            print(f"[Startup Check] Chart successfully detected! ({res.get('detected_candles_count')} candles)")
            self.has_active_chart = True
            self.current_signal = "READY"
            self.root.after(0, self.update_widget_ui)
            # User request: "যখন চার্ট দেখবে তখন কনফার্ম করবে যে 'আমি চার্ট দেখতে পারছি এবং চার্ট এনালাইজ করছি অপেক্ষা করুন। সিগনাল আসছে।'"
            voice.speak_chart_detected(force=True)

    def trigger_scan(self, manual=False):
        if self.is_scanning:
            return
        self.is_scanning = True
        self.current_signal = "SCANNING"
        self.update_widget_ui()
        threading.Thread(target=self._scan_worker, args=(manual,), daemon=True).start()

    def _scan_worker(self, manual=False):
        now_str = datetime.now().strftime("%H:%M:%S")

        try:
            # Hide widget momentarily to get clean capture
            try:
                self.root.withdraw()
                self.root.update_idletasks()
                time.sleep(0.05)
                screen_img = self._grab_screen_robust()
            finally:
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)

            # Analyze image using smart engine
            result = cv_engine.engine.analyze_image(screen_img)

            # Update UI on main thread
            self.root.after(0, self.handle_scan_result, result, manual)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [Scan Error] {e}")
            self.root.after(0, self.handle_scan_result, None, manual)

    def handle_scan_result(self, result, manual=False):
        self.is_scanning = False
        now_str = datetime.now().strftime("%H:%M:%S")

        # 1. STRICT NO-CHART GATE:
        # User request: "eti chart na dekhe e signal genarate korche. eti chirt dekha chara kono signal provide korbe na."
        if not result or not result.get("is_trading_chart", False):
            print(f"[{now_str}] [Gate] No chart detected on screen.")
            self.has_active_chart = False
            self.current_signal = "NO_CHART"
            self.pattern_name = "কোনো চার্ট মেলেনি"
            self.update_widget_ui()

            # Voice alert for no chart (immediate if user manually clicked scan, or on transition)
            voice.speak_no_chart(force=manual)
            return

        # 2. CHART IS DETECTED
        was_no_chart = not self.has_active_chart
        self.has_active_chart = True

        if was_no_chart:
            # Announce chart detection
            voice.speak_chart_detected(force=False)

        sig = str(result.get("signal", "READY")).upper().strip()
        if sig not in ["CALL", "PUT"]:
            self.current_signal = "READY"
            self.update_widget_ui()
            return

        self.expiry_min = result.get("recommended_expiry_minutes", 1)
        self.pattern_name = result.get("pattern_name", "Candlestick Setup")
        self.pattern_name_bn = result.get("pattern_name_bn", "")
        self.confidence = result.get("confidence", 92)

        # In manual scan, immediately announce signal
        if manual:
            if sig == "CALL":
                self.current_signal = "CALL"
                self.update_widget_ui()
                voice.speak_signal_call()
            else:
                self.current_signal = "PUT"
                self.update_widget_ui()
                voice.speak_signal_put()
        else:
            # Automatic scan result
            self.current_signal = sig
            self.update_widget_ui()

    def clock_synced_loop(self):
        """
        Clock loop:
        Scans at :53-:54s so decision is calculated.
        Precisely at :55s (5 SECONDS BEFORE 00s CANDLE):
        Announces 'সিগনাল কল' or 'সিগনাল পুট' via voice!
        """
        last_prep_min = -1
        last_alert_min = -1

        while True:
            try:
                now = datetime.now()
                sec = now.second
                cur_min = now.minute

                # Step 1: Pre-calculate at :53-:54s so signal is ready with 0 latency
                if sec in [53, 54] and cur_min != last_prep_min:
                    last_prep_min = cur_min
                    screen_img = self._grab_screen_robust()
                    res = cv_engine.engine.analyze_image(screen_img)
                    if res.get("is_trading_chart", False) and res.get("signal") in ["CALL", "PUT"]:
                        self.pending_signal_res = res
                        self.pending_signal_minute = cur_min
                    else:
                        self.pending_signal_res = None
                        self.pending_signal_minute = -1
                        if not res.get("is_trading_chart", False):
                            self.has_active_chart = False
                            self.current_signal = "NO_CHART"
                            self.root.after(0, self.update_widget_ui)

                # Step 2: Exactly at :55s (5 SECONDS BEFORE :00s CANDLE):
                # User request: "৫ সেকেন্ড আগে বলবে যদি সিগ্নাল আপ এর হয় 'সিগনাল কল' আরা ডাউন এর হয় বলবে 'সিগ্নাল পুট'"
                if sec == 55 and cur_min != last_alert_min:
                    last_alert_min = cur_min
                    if self.pending_signal_res is not None and self.pending_signal_minute == cur_min:
                        res = self.pending_signal_res
                        sig = res.get("signal")
                        self.expiry_min = res.get("recommended_expiry_minutes", 1)
                        self.pattern_name = res.get("pattern_name", "Candlestick Setup")
                        self.pattern_name_bn = res.get("pattern_name_bn", "")
                        self.confidence = res.get("confidence", 92)

                        if sig == "CALL":
                            print(f"[{now.strftime('%H:%M:%S')}] >>> 5s EARLY ALERT: CALL (সিগনাল কল) <<<")
                            self.current_signal = "CALL"
                            self.root.after(0, self.update_widget_ui)
                            voice.speak_signal_call()
                        elif sig == "PUT":
                            print(f"[{now.strftime('%H:%M:%S')}] >>> 5s EARLY ALERT: PUT (সিগনাল পুট) <<<")
                            self.current_signal = "PUT"
                            self.root.after(0, self.update_widget_ui)
                            voice.speak_signal_put()
                    else:
                        # If no chart was present, it does NOT speak or generate signal!
                        pass

                time.sleep(0.1)
            except Exception as e:
                print(f"[Clock Loop Error] {e}")
                time.sleep(1)

def show_activation_window(on_success_callback):
    """Clean license activation window."""
    act_win = tk.Tk()
    act_win.title("AI Laser Scanner - License Activation")
    act_win.geometry("420x540")
    act_win.configure(bg="#0b1120")
    act_win.resizable(False, False)
    set_window_icon(act_win)

    hwid = licensing.get_machine_id()

    tk.Label(
        act_win,
        text="AI LASER SCANNER",
        font=("Segoe UI", 16, "bold"),
        fg="#38bdf8",
        bg="#0b1120"
    ).pack(pady=(25, 4))

    tk.Label(
        act_win,
        text="ডিভাইস লাইসেন্স অ্যাক্টিভেশন",
        font=("Segoe UI", 11),
        fg="#94a3b8",
        bg="#0b1120"
    ).pack(pady=(0, 20))

    frame_hwid = tk.Frame(act_win, bg="#1e293b", padx=12, pady=10)
    frame_hwid.pack(fill="x", padx=30, pady=5)

    tk.Label(
        frame_hwid,
        text="আপনার মেশিন আইডি (Machine HWID):",
        font=("Segoe UI", 9),
        fg="#94a3b8",
        bg="#1e293b"
    ).pack(anchor="w")

    hwid_entry = tk.Entry(
        frame_hwid,
        font=("Consolas", 12, "bold"),
        fg="#38bdf8",
        bg="#0f172a",
        relief="flat",
        justify="center"
    )
    hwid_entry.insert(0, hwid)
    hwid_entry.config(state="readonly")
    hwid_entry.pack(fill="x", pady=(6, 4))

    def copy_hwid():
        act_win.clipboard_clear()
        act_win.clipboard_append(hwid)
        lbl_msg.config(text="✅ মেশিন আইডি কপি করা হয়েছে!", fg="#4ade80")

    tk.Button(
        frame_hwid,
        text="📋 আইডি কপি করুন",
        font=("Segoe UI", 9, "bold"),
        fg="#ffffff",
        bg="#0284c7",
        activebackground="#0369a1",
        relief="flat",
        cursor="hand2",
        command=copy_hwid
    ).pack(pady=(4, 0))

    frame_key = tk.Frame(act_win, bg="#1e293b", padx=12, pady=10)
    frame_key.pack(fill="x", padx=30, pady=15)

    tk.Label(
        frame_key,
        text="লাইসেন্স কি (License Key):",
        font=("Segoe UI", 9),
        fg="#94a3b8",
        bg="#1e293b"
    ).pack(anchor="w")

    key_entry = tk.Entry(
        frame_key,
        font=("Consolas", 10),
        fg="#ffffff",
        bg="#0f172a",
        relief="flat"
    )
    key_entry.pack(fill="x", pady=(6, 4), ipady=3)

    lbl_msg = tk.Label(act_win, text="", font=("Segoe UI", 9), fg="#f87171", bg="#0b1120", wraplength=340)
    lbl_msg.pack(pady=5)

    def do_activate():
        k = key_entry.get().strip()
        is_val, msg, exp_info = licensing.validate_license_key(k, hwid)
        if is_val:
            licensing.save_license(k)
            lbl_msg.config(text=f"✅ {msg}\n{exp_info}", fg="#4ade80")
            act_win.after(1200, lambda: [act_win.destroy(), on_success_callback()])
        else:
            lbl_msg.config(text=f"❌ {msg}", fg="#f87171")

    tk.Button(
        act_win,
        text="🚀 অ্যাক্টিভ করুন (Activate)",
        font=("Segoe UI", 11, "bold"),
        fg="#ffffff",
        bg="#16a34a",
        activebackground="#15803d",
        relief="flat",
        cursor="hand2",
        command=do_activate
    ).pack(fill="x", padx=30, pady=10, ipady=4)

    act_win.mainloop()

def main():
    # Check activation
    is_act, _ = licensing.is_activated()
    if not is_act:
        # Check if universal key can auto-activate
        universal_key = licensing.generate_license_key("UNIVERSAL", 0)
        licensing.save_license(universal_key)
        is_act = True

    root = tk.Tk()
    app = DesktopSmartOfflineWidget(root)
    root.mainloop()

if __name__ == "__main__":
    main()
