import os
import io
import sys
import time
import json
import base64
import threading
from datetime import datetime, timedelta

import kivy
from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.core.audio import SoundLoader
from kivy.graphics import Color, RoundedRectangle

import requests

# CONFIGURATION: Connected to your deployed Central Render Server
SERVER_URL = "https://ai-laser-trading-server.onrender.com"

CALL_WAV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "call_alert.wav")
PUT_WAV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "put_alert.wav")

MAJOR_PAIRS = [
    "EUR/USD OTC",
    "GBP/USD OTC",
    "USD/JPY OTC",
    "AUD/USD OTC",
    "USD/INR OTC",
    "USD/BRL OTC",
    "EUR/JPY OTC",
    "GBP/JPY OTC",
    "Crypto IDX",
    "BTC/USD OTC"
]

def play_signal_sound(signal_type):
    """Plays distinct notification sound for CALL and PUT signals."""
    try:
        if signal_type == "CALL" and os.path.exists(CALL_WAV_PATH):
            sound = SoundLoader.load(CALL_WAV_PATH)
            if sound: sound.play()
        elif signal_type == "PUT" and os.path.exists(PUT_WAV_PATH):
            sound = SoundLoader.load(PUT_WAV_PATH)
            if sound: sound.play()
    except Exception:
        pass

def capture_screen_safe():
    """
    Cross-platform safe screen capture:
    - On Desktop (PC): Uses Pillow ImageGrab.
    - On Mobile (Android): Looks for recent screenshot in DCIM/Pictures/Screenshots.
    """
    # 1. Try Desktop Screen Grab
    try:
        from PIL import Image, ImageGrab
        img = ImageGrab.grab()
        if img:
            w, h = img.size
            target_w = 640
            if w > target_w:
                target_h = int(h * (target_w / w))
                img = img.resize((target_w, target_h), Image.Resampling.BILINEAR)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60, optimize=True)
            return buf.getvalue()
    except Exception:
        pass

    # 2. Try Android Screenshots folder
    screenshot_dirs = [
        "/sdcard/DCIM/Screenshots",
        "/sdcard/Pictures/Screenshots",
        "/storage/emulated/0/DCIM/Screenshots",
        "/storage/emulated/0/Pictures/Screenshots",
        "/sdcard/Screenshots"
    ]
    for sdir in screenshot_dirs:
        try:
            if os.path.isdir(sdir):
                files = [os.path.join(sdir, f) for f in os.listdir(sdir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
                if files:
                    files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                    latest = files[0]
                    with open(latest, "rb") as f:
                        return f.read()
        except Exception:
            pass

    return None

class AILaserScreenAssistantApp(App):
    def build(self):
        self.title = "AI Laser Scanner - Mobile & Desktop Client"
        self.auto_monitoring = True
        self.is_evaluating = False
        self.selected_pair = "EUR/USD OTC"

        layout = BoxLayout(orientation='vertical', padding=12, spacing=10)

        # Header Title
        lbl_header = Label(
            text="⚡ AI Laser Scanner (Central Client)",
            font_size='18sp', bold=True, color=(0.2, 0.8, 1, 1),
            size_hint=(1, 0.12)
        )
        layout.add_widget(lbl_header)

        # Pair Selector Row
        pair_row = BoxLayout(orientation='horizontal', spacing=8, size_hint=(1, 0.12))
        lbl_p = Label(text="পেয়ার নির্বাচন:", font_size='13sp', bold=True, size_hint=(0.35, 1))
        self.spinner_pair = Spinner(
            text=self.selected_pair,
            values=MAJOR_PAIRS,
            font_size='14sp', bold=True,
            background_color=(0.1, 0.3, 0.5, 1),
            size_hint=(0.65, 1)
        )
        self.spinner_pair.bind(text=self.on_pair_change)
        pair_row.add_widget(lbl_p)
        pair_row.add_widget(self.spinner_pair)
        layout.add_widget(pair_row)

        # Status & Candle Countdown Box
        self.status_box = BoxLayout(orientation='vertical', padding=10, size_hint=(1, 0.40))
        with self.status_box.canvas.before:
            Color(0.08, 0.12, 0.20, 1)
            self.rect = RoundedRectangle(pos=self.status_box.pos, size=self.status_box.size, radius=[10])
        self.status_box.bind(pos=self._update_rect, size=self._update_rect)

        self.lbl_candle_time = Label(
            text="⏱️ ক্যান্ডেল শেষ হতে বাকি: --s",
            font_size='14sp', bold=True, color=(1, 0.85, 0.2, 1)
        )
        self.status_box.add_widget(self.lbl_candle_time)

        self.lbl_status = Label(
            text="অটো-স্ক্যান অন (:৫৫ সেকেন্ডে সিগন্যাল আসবে)",
            font_size='13sp', color=(1, 1, 1, 1)
        )
        self.status_box.add_widget(self.lbl_status)

        self.lbl_last_signal = Label(
            text="লাস্ট সিগন্যাল: স্ক্যানের অপেক্ষায়",
            font_size='14sp', bold=True, color=(0.2, 1, 0.5, 1)
        )
        self.status_box.add_widget(self.lbl_last_signal)

        layout.add_widget(self.status_box)

        # Action Buttons
        btn_scan = Button(
            text="⚡ এখনই স্ক্যান করুন (Scan Trade Now)",
            font_size='16sp', bold=True,
            background_color=(0.05, 0.65, 0.95, 1),
            size_hint=(1, 0.22)
        )
        btn_scan.bind(on_press=lambda instance: self.trigger_scan())
        layout.add_widget(btn_scan)

        # Footer Info
        lbl_footer = Label(
            text="🔒 100% Locked Central Architecture | Quotex, Pocket Option, IQ",
            font_size='10sp', color=(0.5, 0.5, 0.5, 1),
            size_hint=(1, 0.08)
        )
        layout.add_widget(lbl_footer)

        # Start 1-second clock sync loop
        threading.Thread(target=self.clock_synced_monitor_loop, daemon=True).start()

        return layout

    def on_pair_change(self, spinner, text):
        self.selected_pair = text
        self.lbl_status.text = f"নির্বাচিত পেয়ার: {text}"

    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

    def clock_synced_monitor_loop(self):
        """Monitors clock and triggers chart scan at :55 seconds before every minute."""
        while True:
            now = datetime.now()
            sec = now.second
            remaining = 60 - sec
            self.lbl_candle_time.text = f"⏱️ ক্যান্ডেল শেষ হতে বাকি: {remaining:02d}s"

            if sec == 55 and self.auto_monitoring and not self.is_evaluating:
                self.trigger_scan()

            time.sleep(1)

    def trigger_scan(self):
        if self.is_evaluating: return
        threading.Thread(target=self._capture_and_send_to_server, daemon=True).start()

    def _capture_and_send_to_server(self):
        self.is_evaluating = True
        Clock.schedule_once(lambda dt: self._set_eval_text("📸 সেন্ট্রাল সার্ভারে লাইভ সিগন্যাল যাচাই চলছে..."))

        img_bytes = capture_screen_safe()
        result_json = None

        try:
            url = f"{SERVER_URL}/api/scan"
            if img_bytes:
                files = {"image": ("chart.jpg", img_bytes, "image/jpeg")}
                data = {"pair": self.selected_pair}
                resp = requests.post(url, files=files, data=data, timeout=12)
            else:
                resp = requests.post(url + f"?pair={self.selected_pair}", timeout=12)

            if resp.status_code == 200:
                result_json = resp.json()
        except Exception as e:
            print(f"[Client Scan Error] {e}")

        Clock.schedule_once(lambda dt: self.update_ui(result_json))

    def _set_eval_text(self, text):
        self.lbl_status.text = text

    def update_ui(self, result_json):
        if not result_json:
            self.lbl_status.text = "⚠️ সার্ভার সংযোগ ত্রুটি (পুনরায় চেষ্টা করুন)"
            self.is_evaluating = False
            return

        signal = result_json.get("signal", "CALL")
        pair = result_json.get("pair", self.selected_pair)
        p_name = result_json.get("pattern_name", "Price Action Reaction")
        bn_name = result_json.get("pattern_name_bn", "ক্যান্ডেলস্টিক সেটআপ")
        expiry_min = result_json.get("recommended_expiry_minutes", 1)
        confluence = result_json.get("confluence_factors", [])
        candle_minute = result_json.get("candle_minute", "Next Minute")

        dir_txt = "🟢 CALL (UP / উপরে)" if signal == "CALL" else "🔴 PUT (DOWN / নিচে)"
        self.lbl_last_signal.text = f"{pair}: {dir_txt} ({expiry_min}m)"
        self.lbl_status.text = f"প্যাটার্ন: {bn_name}"

        # Play sound alert
        play_signal_sound(signal)

        # Show popup card
        self.show_popup_card(pair, signal, bn_name, expiry_min, candle_minute, confluence)
        self.is_evaluating = False

    def show_popup_card(self, pair, signal, bn_name, expiry_min, candle_minute, confluence):
        box = BoxLayout(orientation='vertical', padding=12, spacing=10)

        is_call = (signal == "CALL")
        color = (0.2, 0.9, 0.4, 1) if is_call else (1, 0.3, 0.3, 1)
        dir_txt = "🟢 CALL (UP / উপরে)" if is_call else "🔴 PUT (DOWN / নিচে)"

        lbl_pair = Label(text=f"📊 পেয়ার: {pair}", font_size='18sp', bold=True)
        box.add_widget(lbl_pair)

        lbl_dir = Label(
            text=f"ট্রেডের দিক:\n{dir_txt}",
            font_size='20sp', bold=True, color=color
        )
        box.add_widget(lbl_dir)

        lbl_exp = Label(text=f"⏱️ প্রস্তাবিত মেয়াদ: {expiry_min} মিনিট", font_size='14sp', bold=True, color=(1, 0.85, 0.2, 1))
        box.add_widget(lbl_exp)

        lbl_target = Label(text=f"🎯 টার্গেট ক্যান্ডেল: {candle_minute}", font_size='13sp')
        box.add_widget(lbl_target)

        lbl_pat = Label(text=f"💡 প্যাটার্ন: {bn_name}", font_size='13sp')
        box.add_widget(lbl_pat)

        popup = Popup(
            title=f"⚡ {pair} লাইভ সিগন্যাল",
            content=box,
            size_hint=(0.9, 0.65),
            auto_dismiss=True
        )
        popup.open()
        Clock.schedule_once(lambda dt: popup.dismiss(), 15)

if __name__ == '__main__':
    AILaserScreenAssistantApp().run()
