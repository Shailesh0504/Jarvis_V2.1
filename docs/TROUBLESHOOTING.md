# JARVIS — Diagnostic & Troubleshooting Guide

This guide covers common runtime issues, debugging procedures, and diagnostic steps for Jarvis.

---

## 1. Window & Application Resolution Issues

### Symptom: *"Application open nahi hai"* when window is visible
- **Cause**: The application might run under an unexpected process name or window title.
- **Diagnostic Check**:
  Inspect debug logs in `logs/jarvis.log` to see the candidate scoring breakdown:
  ```text
  [WINDOW_RESOLVER] Target='chrome' | Scored 12 running windows
  Window HWND=131234 Title='Google Chrome' Exe='chrome.exe' Score=95.0
  ```
- **Resolution**:
  - The `UniversalWindowResolver` automatically handles compound prefixes (*"anti gravity"* $\rightarrow$ *"antigravity"*), noise suffixes (*"ID"*, *"App"*, *"Browser"*), and deictic references (*"yah window"*).
  - If the application runs elevated (as Administrator), Windows UIPI blocks standard user processes from sending Win32 messages. Run Jarvis in matching privilege level if necessary.

---

## 2. Audio & Microphone Issues

### Symptom: Voice input not responding or wake-word not detected
- **Diagnostic Step**: Run Jarvis with CLI test:
  ```powershell
  python main.py --cli --no-auth
  ```
- **Microphone Selection**:
  - Open GUI $\rightarrow$ **Settings** $\rightarrow$ **Audio Devices**.
  - Click **"Test Mic"** to capture a 1.2-second sample and inspect live RMS volume levels.
  - If using Bluetooth earbuds (e.g. CMF Buds, Galaxy Buds), `AudioDeviceManager` dynamically detects device connection and routes input/output without requiring a system restart.

### Symptom: Text-to-Speech (TTS) silent or freezing
- **Cause**: Pygame Mixer or SAPI5 COM initialization conflict.
- **Resolution**:
  - In `config.yaml`, verify `voice.tts.engine` is set to `"edge-tts"` (with `"pyttsx3"` fallback).
  - All TTS audio is synthesized in-memory (`io.BytesIO`). If an underlying driver creates a temporary file, check that permissions allow creating files in `%TEMP%`.

---

## 3. SQLite Database Concurrency & Locks

### Symptom: `sqlite3.OperationalError: database is locked`
- **Cause**: Concurrent multi-threaded access while a heavy transaction is open.
- **Resolution**:
  - `DatabaseManager` runs in **WAL mode** (`PRAGMA journal_mode=WAL;`), which allows concurrent readers while a writer commits.
  - To force-checkpoint the WAL journal:
    ```powershell
    python -c "import sqlite3; conn = sqlite3.connect('data/jarvis.db'); conn.execute('PRAGMA wal_checkpoint(TRUNCATE);'); conn.close(); print('WAL Checkpointed!')"
    ```

---

## 4. Headless & PySide6 Offscreen Testing

### Symptom: `qt.qpa.plugin: Could not load the Qt platform plugin "windows"` in CI or remote terminal
- **Resolution**:
  - Set the environment variable before running tests:
    ```powershell
    $env:QT_QPA_PLATFORM = "offscreen"
    pytest tests/test_gui.py
    ```
  - This is already pre-configured in `conftest.py`.
