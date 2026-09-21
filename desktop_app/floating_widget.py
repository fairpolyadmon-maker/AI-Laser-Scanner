import os
import sys
import io
import time
import json
import base64
import threading
import urllib.request
import winsound
from datetime import datetime, timedelta
from dotenv import load_dotenv

import tkinter as tk
from PIL import Image, ImageTk, ImageDraw, ImageFont, ImageGrab

# Add current dir to sys.path
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Configure console encoding for Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import licensing
import signal_provider

# Load .env
env_path = os.path.join(APP_DIR, ".env")
load_dotenv(env_path)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
CALL_WAV = os.path.join(APP_DIR, "call_alert.wav")
PUT_WAV = os.path.join(APP_DIR, "put_alert.wav")
ICON_ICO = os.path.join(APP_DIR, "icon.ico")
LOGO_PNG = os.path.join(APP_DIR, "logo.png")

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
            print(f"[AI Sound] Error playing sound: {e}")
    threading.Thread(target=_play, daemon=True).start()

class DesktopFloatingWidget:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Laser Scanner Widget")
        
        # Dimensions matching user's image (Pill capsule)
        self.width = 360
        self.height = 68
        self.trans_color = "#000001" # Transparent chroma key

        # Window settings
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", self.trans_color)
        self.root.config(bg=self.trans_color)

        # Initial screen position (Top Center)
        screen_w = self.root.winfo_screenwidth()
        init_x = max(50, (screen_w - self.width) // 2)
        init_y = 70
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

        # Main Canvas for drawing the rounded pill
        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=self.trans_color,
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # Bind dragging to canvas
        self.canvas.bind("<Button-1>", self.on_drag_start)
        self.canvas.bind("<B1-Motion>", self.on_drag_motion)

        # Render initial pill graphics
        self.render_widget()

        print("=" * 65)
        print(" [AI Laser Scanner] Desktop Floating Widget Initialized")
        print(" [AI Laser Scanner] Memory: 48 Master Candlestick Patterns Active")
        print(" [AI Laser Scanner] Auto-Scan: Armed at :57s of each minute")
        print(" [AI Laser Scanner] Manual Scan: Click 'SCAN' button anytime")
        print("=" * 65)

        # Start clock-synchronized loop in background
        threading.Thread(target=self.clock_synced_loop, daemon=True).start()

    def on_drag_start(self, event):
        # Don't drag if clicking action buttons
        clicked = self.canvas.find_withtag("current")
        for item in clicked:
            tags = self.canvas.gettags(item)
            if "btn_action" in tags:
                return
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_drag_motion(self, event):
        new_x = self.root.winfo_x() + (event.x - self.drag_start_x)
        new_y = self.root.winfo_y() + (event.y - self.drag_start_y)
        self.root.geometry(f"+{new_x}+{new_y}")

    def create_rounded_pill_image(self):
        """Draws crisp antialiased capsule pill matching original design."""
        scale = 2 # 2x supersampling for smooth rounded corners
        w = self.width * scale
        h = self.height * scale
        r = h // 2

        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Outer border: Glowing cyan / blue (#0ea5e9)
        border_width = 3 * scale
        draw.rounded_rectangle(
            [0, 0, w, h],
            radius=r,
            fill=(11, 17, 32, 255),
            outline=(14, 165, 233, 255),
            width=border_width
        )
        return img.resize((self.width, self.height), Image.Resampling.LANCZOS)

    def render_widget(self):
        self.canvas.delete("all")

        # 1. Background Pill Image
        self.bg_pill = ImageTk.PhotoImage(self.create_rounded_pill_image())
        self.canvas.create_image(0, 0, image=self.bg_pill, anchor="nw")

        # 2. Left Indicator (Circle dot + 2-Line Signal & Pattern Text)
        dot_x = 24
        dot_y = self.height // 2
        dot_r = 8

        # Colors and Text based on state
        if self.current_signal == "CALL":
            dot_color = "#22c55e" # Green
            line1_str = f"CALL ({self.expiry_min}m)"
            line1_color = "#22c55e"
            line2_str = self.pattern_name[:18]
            line2_color = "#86efac"
        elif self.current_signal == "PUT":
            dot_color = "#ef4444" # Red
            line1_str = f"PUT ({self.expiry_min}m)"
            line1_color = "#ef4444"
            line2_str = self.pattern_name[:18]
            line2_color = "#fca5a5"
        elif self.current_signal == "SCANNING":
            dot_color = "#eab308" # Yellow
            line1_str = "SCANNING..."
            line1_color = "#fef08a"
            line2_str = "48 Patterns AI"
            line2_color = "#94a3b8"
        else:
            dot_color = "#38bdf8" # Cyan blue
            line1_str = "READY"
            line1_color = "#38bdf8"
            line2_str = "48 Patterns Active"
            line2_color = "#64748b"

        # Draw glowing status dot
        self.canvas.create_oval(
            dot_x - dot_r, dot_y - dot_r,
            dot_x + dot_r, dot_y + dot_r,
            fill=dot_color, outline="#ffffff", width=1.5
        )

        # Line 1: Signal Title (bold 11pt)
        self.canvas.create_text(
            dot_x + 16, 23,
            text=line1_str,
            font=("Segoe UI", 11, "bold"),
            fill=line1_color,
            anchor="w"
        )

        # Line 2: Candlestick Pattern Name (8pt)
        self.canvas.create_text(
            dot_x + 16, 44,
            text=line2_str,
            font=("Segoe UI", 8),
            fill=line2_color,
            anchor="w"
        )

        # 3. Middle Scan Button: [ ⚡ SCAN ] (Pill shape)
        btn_w = 95
        btn_h = 36
        btn_x1 = 200
        btn_y1 = (self.height - btn_h) // 2

        btn_img = self.create_button_image(btn_w, btn_h, "#0284c7", "#38bdf8")
        self.scan_btn_img = ImageTk.PhotoImage(btn_img)
        btn_id = self.canvas.create_image(btn_x1, btn_y1, image=self.scan_btn_img, anchor="nw", tags=("btn_action",))
        
        # Button Text
        txt_id = self.canvas.create_text(
            btn_x1 + btn_w // 2, btn_y1 + btn_h // 2,
            text="⚡ SCAN",
            font=("Segoe UI", 10, "bold"),
            fill="#ffffff",
            tags=("btn_action",)
        )
        for elem in [btn_id, txt_id]:
            self.canvas.tag_bind(elem, "<Button-1>", lambda e: self.trigger_scan())
            self.canvas.tag_bind(elem, "<Enter>", lambda e: self.root.config(cursor="hand2"))
            self.canvas.tag_bind(elem, "<Leave>", lambda e: self.root.config(cursor=""))

        # 4. Right Close Button: [ ✕ ] (Red circle)
        close_r = 16
        close_cx = 328
        close_cy = self.height // 2

        close_img = self.create_circle_button(close_r * 2, "#dc2626", "#ef4444")
        self.close_btn_img = ImageTk.PhotoImage(close_img)
        cls_id = self.canvas.create_image(close_cx - close_r, close_cy - close_r, image=self.close_btn_img, anchor="nw", tags=("btn_action",))

        cross_id = self.canvas.create_text(
            close_cx, close_cy,
            text="✕",
            font=("Segoe UI", 11, "bold"),
            fill="#ffffff",
            tags=("btn_action",)
        )
        for elem in [cls_id, cross_id]:
            self.canvas.tag_bind(elem, "<Button-1>", lambda e: self.root.destroy())
            self.canvas.tag_bind(elem, "<Enter>", lambda e: self.root.config(cursor="hand2"))
            self.canvas.tag_bind(elem, "<Leave>", lambda e: self.root.config(cursor=""))

    def create_button_image(self, width, height, fill_color, border_color):
        scale = 2
        w = width * scale
        h = height * scale
        r = h // 2
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rounded_rectangle([0, 0, w, h], radius=r, fill=fill_color, outline=border_color, width=2*scale)
        return img.resize((width, height), Image.Resampling.LANCZOS)

    def create_circle_button(self, size, fill_color, border_color):
        scale = 2
        s = size * scale
        img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([0, 0, s, s], fill=fill_color, outline=border_color, width=2*scale)
        return img.resize((size, size), Image.Resampling.LANCZOS)

    def trigger_scan(self):
        if self.is_scanning:
            return
        self.is_scanning = True
        self.current_signal = "SCANNING"
        self.render_widget()
        threading.Thread(target=self._perform_scan, daemon=True).start()

    def _perform_scan(self):
        screen_img = None
        now_str = datetime.now().strftime("%H:%M:%S")
        print(f"[{now_str}] [AI Engine] Capturing live trading screen...")

        try:
            # 1. Hide widget momentarily to take clean screen capture of chart
            try:
                self.root.withdraw()
                self.root.update_idletasks()
                time.sleep(0.08)
                try:
                    screen_img = ImageGrab.grab(all_screens=True)
                except Exception:
                    screen_img = ImageGrab.grab()
            finally:
                # Always restore widget window
                self.root.deiconify()
                self.root.lift()
                self.root.attributes("-topmost", True)

            if screen_img is None:
                print(f"[{now_str}] [AI Engine] Warning: Screen grab returned empty image")
                self.root.after(0, self.handle_scan_result, None)
                return

            # Compress for fast upload (<150KB) while keeping candlesticks sharp
            w, h = screen_img.size
            target_w = 960
            if w > target_w:
                target_h = int(h * (target_w / w))
                screen_img = screen_img.resize((target_w, target_h), Image.Resampling.LANCZOS)

            buf = io.BytesIO()
            screen_img.save(buf, format="JPEG", quality=80, optimize=True)

            # Save scanned chart for visual inspection
            try:
                scanned_path = os.path.join(APP_DIR, "last_scanned_chart.jpg")
                with open(scanned_path, "wb") as f:
                    f.write(buf.getvalue())
            except Exception:
                pass

            # 2. Call Master Signal Provider with 48 Candlestick Patterns
            result = signal_provider.provider.analyze_image_bytes(buf.getvalue())

            # Update UI on main thread
            self.root.after(0, self.handle_scan_result, result)

        except Exception as e:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [AI Engine] Scan error: {e}")
            self.root.after(0, self.handle_scan_result, None)

    def handle_scan_result(self, result):
        self.is_scanning = False
        now_str = datetime.now().strftime("%H:%M:%S")

        if not result or not result.get("is_trading_chart", False):
            print(f"[{now_str}] [AI Engine] READY - No active chart or setup detected")
            self.current_signal = "READY"
            self.pattern_name = "48 Patterns Active"
            self.render_widget()
            return

        sig = str(result.get("signal", "NONE")).upper().strip()
        self.expiry_min = result.get("recommended_expiry_minutes", 1)
        self.pattern_name = result.get("pattern_name", "Candlestick Setup")
        self.pattern_name_bn = result.get("pattern_name_bn", "")
        self.confidence = result.get("confidence", 85)
        reason = result.get("reason", "")
        elapsed = result.get("elapsed_sec", 0)

        if sig == "CALL":
            print(f"[{now_str}] [AI Engine] >>> SIGNAL: CALL ({self.expiry_min}m) | Pattern: {self.pattern_name} ({self.pattern_name_bn}) | Conf: {self.confidence}% | Time: {elapsed}s <<<")
            if reason:
                print(f"[{now_str}] [AI Analysis] Confluence: {reason}")
            self.current_signal = "CALL"
            self.render_widget()
            play_audio_alert("CALL")
        elif sig == "PUT":
            print(f"[{now_str}] [AI Engine] >>> SIGNAL: PUT ({self.expiry_min}m) | Pattern: {self.pattern_name} ({self.pattern_name_bn}) | Conf: {self.confidence}% | Time: {elapsed}s <<<")
            if reason:
                print(f"[{now_str}] [AI Analysis] Confluence: {reason}")
            self.current_signal = "PUT"
            self.render_widget()
            play_audio_alert("PUT")
        else:
            print(f"[{now_str}] [AI Engine] Market neutral (Signal: NONE) - Awaiting 48-pattern setup")
            self.current_signal = "READY"
            self.pattern_name = "Neutral Market"
            self.render_widget()

    def clock_synced_loop(self):
        """Auto-triggers scan at 57s-58s of every minute with high precision."""
        last_scanned_min = -1
        while True:
            try:
                now = datetime.now()
                sec = now.second
                if sec in [57, 58] and now.minute != last_scanned_min:
                    last_scanned_min = now.minute
                    if self.auto_scan_active and not self.is_scanning:
                        print(f"[{now.strftime('%H:%M:%S')}] [AI Engine] 57s candle auto-scan triggered...")
                        self.trigger_scan()
                time.sleep(0.5)
            except Exception as e:
                print(f"[AI Engine] Clock loop error: {e}")
                time.sleep(1)

def show_activation_window(on_success_callback):
    act_win = tk.Tk()
    act_win.title("AI Laser Scanner - Activation")
    act_win.geometry("400x520")
    act_win.configure(bg="#0b1120")
    act_win.resizable(False, False)

    # Logo
    if os.path.exists(LOGO_PNG):
        try:
            pil_logo = Image.open(LOGO_PNG).resize((130, 130), Image.Resampling.LANCZOS)
            tk_logo = ImageTk.PhotoImage(pil_logo)
            lbl_logo = tk.Label(act_win, image=tk_logo, bg="#0b1120")
            lbl_logo.image = tk_logo
            lbl_logo.pack(pady=15)
        except Exception:
            pass

    tk.Label(
        act_win, text="AI LASER SCANNER",
        font=("Segoe UI", 16, "bold"), fg="#38bdf8", bg="#0b1120"
    ).pack()

    tk.Label(
        act_win, text="ডেস্কটপ ফ্লোটিং উইজেট অ্যাক্টিভেশন",
        font=("Segoe UI", 10), fg="#94a3b8", bg="#0b1120"
    ).pack(pady=5)

    hwid = licensing.get_machine_id()
    hwid_frame = tk.Frame(act_win, bg="#1e293b", padx=10, pady=8)
    hwid_frame.pack(fill="x", padx=25, pady=10)

    tk.Label(
        hwid_frame, text=f"Machine ID: {hwid}",
        font=("Consolas", 10, "bold"), fg="#a5f3fc", bg="#1e293b"
    ).pack(side="left")

    def copy_hwid():
        act_win.clipboard_clear()
        act_win.clipboard_append(hwid)
        btn_copy.config(text="Copied!")
        act_win.after(1500, lambda: btn_copy.config(text="Copy"))

    btn_copy = tk.Button(
        hwid_frame, text="Copy", font=("Segoe UI", 9, "bold"),
        bg="#0284c7", fg="#ffffff", activebackground="#0369a1",
        relief="flat", command=copy_hwid, padx=8
    )
    btn_copy.pack(side="right")

    tk.Label(
        act_win, text="লাইসেন্স কি (License Key) লিখুন:",
        font=("Segoe UI", 10), fg="#e2e8f0", bg="#0b1120"
    ).pack(anchor="w", padx=25, pady=(10, 2))

    txt_key = tk.Entry(
        act_win, font=("Segoe UI", 11), bg="#1e293b", fg="#ffffff",
        insertbackground="#ffffff", relief="flat"
    )
    txt_key.pack(fill="x", padx=25, ipady=6)

    lbl_status = tk.Label(act_win, text="", font=("Segoe UI", 9), bg="#0b1120")
    lbl_status.pack(pady=8)

    def do_activate():
        k = txt_key.get().strip()
        if not k:
            lbl_status.config(text="অনুগ্রহ করে লাইসেন্স কি প্রবেশ করান", fg="#ef4444")
            return
        is_val, msg, exp_info = licensing.validate_license_key(k)
        if is_val:
            licensing.save_license(k)
            lbl_status.config(text="সফলভাবে অ্যাক্টিভেট হয়েছে!", fg="#22c55e")
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
    app = DesktopFloatingWidget(root)
    root.mainloop()

def main():
    is_val, info = licensing.is_activated()
    if is_val:
        launch_floating_app()
    else:
        show_activation_window(launch_floating_app)

if __name__ == "__main__":
    main()
