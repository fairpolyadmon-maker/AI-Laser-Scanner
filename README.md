# AI Laser Scanner 🚀

A high-precision Binary Options & Forex trading analysis suite powered by Computer Vision, Gemini Vision AI, and 48 Master Candlestick Patterns.

---

## 📌 Versions Overview

| Version | Target / Edition | Key Features |
| :--- | :--- | :--- |
| **v1.0.0** | Android Mobile App (Online) | Cloud Gemini Vision AI, real-time screen overlay. |
| **v1.1.0** | Desktop App (Online) | Tkinter floating pill widget, 48-pattern cloud analysis, audio cues. |
| **v2.0.0** | Desktop App (Offline Edition) | **100% Offline (Zero API Key)**, Local OpenCV Candle Engine + 48 Patterns, HWID Licensing (1 PC = 1 Key), direct GUI launch (`--noconsole`), Standalone `.exe` build. |

---

## 🌟 Version 2.0.0 (Offline Edition) Highlights

- **Zero API Key Dependency**: Runs completely offline without internet or API quotas.
- **Ultra-Fast Local Computer Vision Engine**: Extracts candlesticks, bodies, wicks, and SNR levels in ~15-25ms.
- **48 Master Candlestick Patterns Engine**: Full technical confluence and pattern recognition based on The Candlestick Trading Bible.
- **Precise Timing Window**:
  - Auto-triggers scan at **:55s** of every candle.
  - Final signal committed between **:55s - :58s** for exact **:00s** entry.
  - Distinct audio sound cues for CALL, PUT, and entry ticks.
- **Hardware-Locked Licensing (1 PC = 1 Key)**:
  - Cryptographically signed HMAC-SHA256 license key bound to each machine's unique Hardware ID (HWID).
  - Admin key generator (`Generate_License.bat` / `license_generator.py`) supports 1 Month, 3 Months, 6 Months, 1 Year, or Lifetime keys.
- **Direct GUI Launch**:
  - Runs natively in Windows GUI subsystem with zero black CMD/terminal window.
- **Tkinter C-Heap Memory Leak Fix**:
  - Pre-rendered canvas items with zero allocation churn, preventing Tcl heap crashes.

---

## 🛠️ Quick Start

### 1. Running Desktop Offline App (v2.0.0)
Double-click:
```bat
Run_Desktop_Offline.bat
```
*(or run `AI Laser Scanner.exe` directly)*

### 2. Generating Client License Keys
Double-click:
```bat
Generate_License.bat
```
1. Input client's **Machine ID**.
2. Select desired duration (1-5).
3. Copy and provide the generated license key.

### 3. Building Standalone `.exe`
To compile from source into a single portable `.exe`:
```powershell
pyinstaller --noconsole --onefile --clean `
  --icon="icon.ico" `
  --name="AI Laser Scanner" `
  --add-data "call_alert.wav;." `
  --add-data "put_alert.wav;." `
  --add-data "icon.ico;." `
  --add-data "icon.png;." `
  --add-data "logo.png;." `
  --add-data "patterns;patterns" `
  floating_widget.py
```

---

## 📁 Repository Structure

```
AI-Laser-Scanner/
│
├── desktop_app/                  # v1.1.0: Online Desktop Floating Widget
│   ├── floating_widget.py
│   ├── signal_provider.py
│   ├── licensing.py
│   └── patterns/
│
├── desktop_offline_app/          # v2.0.0: Offline Desktop Engine
│   ├── cv_engine.py              # 100% Offline OpenCV Candlestick Engine
│   ├── floating_widget.py        # Optimized Tkinter Floating Pill Widget
│   ├── signal_provider.py        # 48 Candlestick Patterns Local Engine
│   ├── licensing.py              # HWID-bound License Validation
│   └── patterns/                 # Candlestick Knowledge Base (JSON)
│
├── license_generator.py          # Admin License Key Generator (CLI)
├── Generate_License.bat          # 1-Click License Generator Launcher
├── Run_Desktop_Offline.bat       # 1-Click Windowless Launcher (Offline v2.0)
├── Run_Desktop_App.bat           # 1-Click Launcher (Online v1.1)
├── icon.ico / icon.png           # Application Branding Assets
├── AI Laser Scanner apk          # v1.0.0 Mobile APK
├── AI Laser Scanner Offline.apk  # v2.0.0 Offline Mobile APK
└── README.md
```

---

## 📜 License
Proprietary trading tool. Hardware-locked activation required.
