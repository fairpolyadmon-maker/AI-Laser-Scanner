import os
import sys
import time
import threading
import winsound

# Resolve base bundle paths
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    BUNDLE_DIR = sys._MEIPASS
    APP_DIR = os.path.dirname(sys.executable)
else:
    BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    APP_DIR = BUNDLE_DIR

VOICE_NO_CHART = os.path.join(BUNDLE_DIR, "voice_no_chart.wav")
VOICE_CHART_DETECTED = os.path.join(BUNDLE_DIR, "voice_chart_detected.wav")
VOICE_SIGNAL_CALL = os.path.join(BUNDLE_DIR, "voice_signal_call.wav")
VOICE_SIGNAL_PUT = os.path.join(BUNDLE_DIR, "voice_signal_put.wav")
CALL_WAV = os.path.join(BUNDLE_DIR, "call_alert.wav")
PUT_WAV = os.path.join(BUNDLE_DIR, "put_alert.wav")

class VoiceAssistant:
    """
    Manages all Bengali voice announcements and chimes offline via native Windows audio.
    """
    def __init__(self):
        self._lock = threading.Lock()
        self.last_no_chart_time = 0
        self.chart_detected_spoken = False
        self.last_spoken_signal_sec = -1

    def _play_wav_sync(self, path):
        """Plays a WAV file synchronously inside a worker thread."""
        try:
            if os.path.exists(path):
                winsound.PlaySound(path, winsound.SND_FILENAME)
        except Exception as e:
            print(f"[VoiceAssistant Error] {e}")

    def speak_no_chart(self, force=False):
        """
        Speaks: 'আমি কোন চার্ট দেখতে পারছি না'
        Plays immediately if forced (e.g. on manual scan or initial launch),
        or throttled to prevent spam.
        """
        now = time.time()
        if force or (now - self.last_no_chart_time >= 30.0):
            self.last_no_chart_time = now
            self.chart_detected_spoken = False
            def _worker():
                with self._lock:
                    print("[Voice] >>> আমি কোন চার্ট দেখতে পারছি না <<<")
                    self._play_wav_sync(VOICE_NO_CHART)
            threading.Thread(target=_worker, daemon=True).start()

    def speak_chart_detected(self, force=False):
        """
        Speaks: 'আমি চার্ট দেখতে পাচ্ছি এবং চার্ট এনালাইজ করছি অপেক্ষা করুন। সিগনাল আসছে।'
        Triggered when chart is recognized.
        """
        if force or not self.chart_detected_spoken:
            self.chart_detected_spoken = True
            def _worker():
                with self._lock:
                    print("[Voice] >>> আমি চার্ট দেখতে পাচ্ছি এবং চার্ট এনালাইজ করছি অপেক্ষা করুন। সিগনাল আসছে। <<<")
                    self._play_wav_sync(VOICE_CHART_DETECTED)
            threading.Thread(target=_worker, daemon=True).start()

    def speak_signal_call(self):
        """
        Speaks: 'সিগনাল কল' (5 seconds before candle end) + chime
        """
        def _worker():
            with self._lock:
                print("[Voice] >>> সিগনাল কল (৫ সেকেন্ড আগে) <<<")
                self._play_wav_sync(VOICE_SIGNAL_CALL)
                if os.path.exists(CALL_WAV):
                    time.sleep(0.05)
                    self._play_wav_sync(CALL_WAV)
        threading.Thread(target=_worker, daemon=True).start()

    def speak_signal_put(self):
        """
        Speaks: 'সিগনাল পুট' (5 seconds before candle end) + chime
        """
        def _worker():
            with self._lock:
                print("[Voice] >>> সিগনাল পুট (৫ সেকেন্ড আগে) <<<")
                self._play_wav_sync(VOICE_SIGNAL_PUT)
                if os.path.exists(PUT_WAV):
                    time.sleep(0.05)
                    self._play_wav_sync(PUT_WAV)
        threading.Thread(target=_worker, daemon=True).start()

    def play_entry_beep(self):
        """Audible beep at 00s entry tick."""
        def _beep():
            try:
                winsound.Beep(1800, 120)
            except Exception:
                pass
        threading.Thread(target=_beep, daemon=True).start()

# Global singleton
voice = VoiceAssistant()
