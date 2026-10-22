# gui/views/chat_view.py
"""Chat View: Interactive conversational stream with selectable text area, voice input, mute/clear controls, and copy actions."""

import datetime
import html
import logging
import math
import queue
import re
import struct
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from PySide6.QtCore import QObject, QThread, QTimer, Qt, Signal, QUrl
from PySide6.QtGui import QCursor, QTextCursor, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
    QPushButton, QTextBrowser, QVBoxLayout, QWidget
)

logger = logging.getLogger("jarvis.gui.chat_view")


class VoiceListenThread(QThread):
    """Background worker thread for capturing speech using PersistentAudioStream without blocking the GUI."""
    transcription_ready = Signal(str)
    status_updated = Signal(str)
    listening_finished = Signal()
    audio_level_updated = Signal(float, bool)  # (normalized_level 0..1, is_speech)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_cancelled = False
        self._stream = None
        self._local_stt = None
        self._audio_queue = queue.Queue()
        self._consecutive_silent_chunks = 0
        self._has_auto_fallen_back = False
        self._preferred_language = "en-IN"

    def cancel(self) -> None:
        self._is_cancelled = True
        self.requestInterruption()
        if self._stream:
            try:
                self._stream.stop()
            except Exception:
                pass

    @property
    def is_cancelled(self) -> bool:
        """Return whether the capture worker has been asked to stop."""
        return self._is_cancelled or self.isInterruptionRequested()

    @staticmethod
    def _sensitivity_profile(is_bluetooth: bool) -> dict:
        """
        Return sensitivity and noise gate thresholds tuned for different mic types.
        - Inbuilt Laptop Mic: High-gain calibrated profile (minimum 18.0, initial 24.0, ratio 1.20, max_floor 45.0, gain 2.2x)
          prevents laptop fan/ambient noise floor trapping while effortlessly capturing voice.
        - Bluetooth Earbuds: Ultra-responsive profile (minimum 8.0, initial 14.0, ratio 1.10, max_floor 28.0, gain 3.0x)
          so speech and soft wake-words into earbuds are reliably captured from across the room and boosted with 3.0x pre-amp.
        """
        if is_bluetooth:
            return {"initial": 14.0, "minimum": 8.0, "maximum": 260.0, "max_floor": 28.0, "ratio": 1.10, "gain": 3.0}
        return {"initial": 24.0, "minimum": 18.0, "maximum": 260.0, "max_floor": 45.0, "ratio": 1.20, "gain": 2.2}

    @staticmethod
    def _amplify_pcm(raw_pcm: bytes, gain: float = 1.0) -> bytes:
        """Applies clean software pre-amplification to quiet microphone input with soft-clipping guard."""
        if gain <= 1.01 or not raw_pcm:
            return raw_pcm
        try:
            count = len(raw_pcm) // 2
            if count == 0:
                return raw_pcm
            samples = struct.unpack(f"{count}h", raw_pcm[:count * 2])
            boosted = [max(-32768, min(32767, int(s * gain))) for s in samples]
            return struct.pack(f"{count}h", *boosted)
        except Exception:
            return raw_pcm

    def _transcribe_audio(self, r, audio) -> str:
        """Fast concurrent transcription with Google Speech API (en-IN, hi-IN in parallel) with local fallback."""
        import socket
        old_timeout = socket.getdefaulttimeout()
        text = ""
        try:
            socket.setdefaulttimeout(2.5)  # Fast 2.5-second socket timeout to prevent network hangs
            preferred = getattr(self, "_preferred_language", "en-IN")
            secondary = "hi-IN" if preferred != "hi-IN" else "en-IN"
            langs = [preferred, secondary]

            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                future_to_lang = {
                    executor.submit(r.recognize_google, audio, language=lang): lang
                    for lang in langs
                }
                for fut in concurrent.futures.as_completed(future_to_lang, timeout=2.5):
                    try:
                        res = fut.result()
                        if res and res.strip():
                            text = res.strip()
                            self._preferred_language = future_to_lang[fut]
                            break
                    except Exception:
                        continue
        except Exception as e:
            logger.debug(f"Remote STT error/timeout: {e}")
        finally:
            try:
                socket.setdefaulttimeout(old_timeout)
            except Exception:
                pass

        # Offline fallback via local SpeechToText if available
        if not text:
            try:
                if self._local_stt is None:
                    from voice.stt import SpeechToText
                    self._local_stt = SpeechToText()
                raw_bytes = audio.get_raw_data()
                res_obj = self._local_stt.transcribe(raw_bytes)
                if res_obj and res_obj.raw_text:
                    text = res_obj.raw_text
            except Exception as e:
                logger.debug(f"Local speech fallback error: {e}")

        return text

    def _on_audio_frame(self, raw_pcm_bytes: bytes) -> None:
        if not self.is_cancelled:
            self._audio_queue.put(raw_pcm_bytes)

    def _on_device_changed(self, new_dev_info) -> None:
        """Invoked live when Bluetooth earbuds connect or disconnect."""
        if self.is_cancelled:
            return
        try:
            is_earbuds = bool(new_dev_info and new_dev_info.is_bluetooth)
            sensitivity = self._sensitivity_profile(is_earbuds)
            if hasattr(self, "_noise_gate") and self._noise_gate:
                self._noise_gate.minimum_threshold = float(sensitivity["minimum"])
                self._noise_gate.noise_ratio = float(sensitivity["ratio"])
                self._noise_gate.maximum_threshold = float(sensitivity["maximum"])
                self._noise_gate.max_noise_floor = float(sensitivity.get("max_floor", 45.0))
                self._noise_gate.noise_floor = min(self._noise_gate.max_noise_floor, float(sensitivity["initial"]) / float(sensitivity["ratio"]))

            new_idx = new_dev_info.index if new_dev_info else None
            dev_name = new_dev_info.clean_name if new_dev_info else "Inbuilt Mic"

            if is_earbuds and self._has_auto_fallen_back:
                from voice.device_manager import AudioDeviceManager
                adm_inst = AudioDeviceManager()
                if new_idx in getattr(adm_inst, "_suppressed_silent_devices", {}):
                    logger.debug(f"VoiceListenThread: Ignoring switch back to suppressed silent device #{new_idx}")
                    return

            self._consecutive_silent_chunks = 0
            self._has_auto_fallen_back = False

            if self._stream:
                self._stream.switch_device(new_idx)

            if is_earbuds:
                self.status_updated.emit(f"🎧 Earbuds Mic Active ({dev_name})... Speak freely!")
            else:
                self.status_updated.emit(f"🎙️ Switched to Inbuilt Mic ({dev_name})... Speak freely!")
        except Exception as e:
            logger.debug(f"VoiceListenThread _on_device_changed error: {e}")

    def run(self) -> None:
        adm = None
        try:
            self.status_updated.emit("🎙️ Initializing microphone...")
            try:
                import speech_recognition as sr
            except ImportError:
                import subprocess, sys
                try:
                    self.status_updated.emit("🎙️ Installing speech recognition...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "SpeechRecognition", "pyaudio", "sounddevice"])
                    import speech_recognition as sr
                except Exception:
                    self.status_updated.emit("⚠️ speech_recognition library not installed. Run: pip install SpeechRecognition pyaudio")
                    return

            from voice.device_manager import AudioDeviceManager
            from voice.listener import PersistentAudioStream
            from voice.stt import AdaptiveNoiseGate, SpeechToText

            adm = AudioDeviceManager()
            best_dev = adm.get_best_input_device(force_refresh=False)
            sd_dev_idx = best_dev.index if best_dev else None
            is_earbuds = bool(best_dev and best_dev.is_bluetooth)
            sensitivity = self._sensitivity_profile(is_earbuds)

            r = sr.Recognizer()
            self._local_stt = SpeechToText()

            # Initialize adaptive noise gate based on profile with hard ceiling
            self._noise_gate = AdaptiveNoiseGate(
                minimum_threshold=float(sensitivity["minimum"]),
                noise_ratio=float(sensitivity["ratio"]),
                initial_noise_floor=float(sensitivity["initial"]) / float(sensitivity["ratio"]),
                maximum_threshold=float(sensitivity["maximum"]),
                max_noise_floor=float(sensitivity.get("max_floor", 45.0))
            )

            # Register live hot-plug listener for dynamic auto-switching between Earbuds and Inbuilt Mic
            adm.register_device_change_listener(self._on_device_changed)
            adm.start_hotplug_watcher(poll_interval=1.5)

            # Start persistent non-blocking hardware audio stream
            self._stream = PersistentAudioStream(
                sample_rate=16000,
                chunk_size=1024,
                on_frame=self._on_audio_frame,
                device=sd_dev_idx
            )
            started = self._stream.start()
            if not started:
                self.status_updated.emit("⚠️ Failed to open microphone stream.")
                return

            if best_dev and best_dev.is_bluetooth:
                self.status_updated.emit(f"🎧 Earbuds Mic Active ({best_dev.clean_name})... Speak freely!")
            else:
                active_name = best_dev.clean_name if best_dev else "Inbuilt Mic"
                self.status_updated.emit(f"🔴 Listening Active ({active_name})... Speak freely!")

            speech_buffer = []
            speech_active = False
            silence_start = 0.0
            speech_start_time = 0.0
            max_phrase_duration = 12.0
            silence_threshold = 0.40
            last_frame_time = time.time()
            self._consecutive_silent_chunks = 0
            self._has_auto_fallen_back = False
            cur_is_bluetooth = is_earbuds

            while not self.is_cancelled:
                try:
                    chunk = self._audio_queue.get(timeout=0.15)
                    last_frame_time = time.time()
                except queue.Empty:
                    # Audio stream watchdog: If no chunks received for > 5.0 seconds, refresh stream with current best device
                    if time.time() - last_frame_time > 5.0 and not self.is_cancelled:
                        logger.debug("VoiceListenThread: Audio stream silent/stalled for > 5s, refreshing stream...")
                        try:
                            # Cleanly stop old stream FIRST before querying or recreating
                            if self._stream:
                                try:
                                    self._stream.stop()
                                except Exception:
                                    pass
                                self._stream = None

                            current_best = (
                                adm.get_fallback_or_internal_input_device(force_refresh=True)
                                if self._has_auto_fallen_back
                                else adm.get_best_input_device(force_refresh=True)
                            ) if adm else None
                            current_idx = current_best.index if current_best else None
                            self._stream = PersistentAudioStream(
                                sample_rate=16000,
                                chunk_size=1024,
                                on_frame=self._on_audio_frame,
                                device=current_idx
                            )
                            self._stream.start()
                            last_frame_time = time.time()
                        except Exception as e_stream:
                            logger.debug(f"Audio stream watchdog restart error: {e_stream}")
                    continue

                try:
                    now = time.time()

                    # Dead-signal / flatline silence guard
                    if len(chunk) >= 4:
                        sample_count = len(chunk) // 2
                        samples = struct.unpack(f"{sample_count}h", chunk[:sample_count * 2])
                        peak_val = max(abs(s) for s in samples) if sample_count > 0 else 0
                        if peak_val <= 3:
                            self._consecutive_silent_chunks += 1
                        else:
                            self._consecutive_silent_chunks = 0

                    # Flatline silence guard: ONLY apply to internal laptop mic, NOT Bluetooth earbuds!
                    # Bluetooth earbuds have hardware ENC that outputs digital zeros when user is quiet.
                    # Never auto-switch away from Bluetooth earbuds just because of quiet background.
                    if not cur_is_bluetooth and self._consecutive_silent_chunks >= 15 and not self._has_auto_fallen_back and not speech_active:
                        self._consecutive_silent_chunks = 0
                        self._has_auto_fallen_back = True
                        cur_device_info = adm.get_best_input_device(force_refresh=False) if adm else None
                        is_cur_bt = bool(cur_device_info and cur_device_info.is_bluetooth) or cur_is_bluetooth

                        logger.warning(
                            f"VoiceListenThread: Audio input signal is flatline/dead (peak <= 3 for 0.96s). "
                            f"Auto-switching to system internal microphone..."
                        )

                        if adm and cur_device_info:
                            adm.report_silent_device(cur_device_info.index)

                        # Cleanly stop the dead stream first so PortAudio reinit is safe
                        if self._stream:
                            try:
                                self._stream.stop()
                            except Exception:
                                pass
                            self._stream = None

                        fallback_dev = adm.get_fallback_or_internal_input_device(force_refresh=True) if adm else None
                        if fallback_dev:
                            target_idx = fallback_dev.index
                            target_name = fallback_dev.clean_name
                            cur_is_bluetooth = False

                            # Reconfigure noise gate for internal microphone profile
                            sensitivity = self._sensitivity_profile(is_bluetooth=False)
                            self._noise_gate = AdaptiveNoiseGate(
                                minimum_threshold=float(sensitivity["minimum"]),
                                noise_ratio=float(sensitivity["ratio"]),
                                initial_noise_floor=float(sensitivity["initial"]) / float(sensitivity["ratio"]),
                                maximum_threshold=float(sensitivity["maximum"]),
                                max_noise_floor=float(sensitivity.get("max_floor", 45.0))
                            )

                            self._stream = PersistentAudioStream(
                                sample_rate=16000,
                                chunk_size=1024,
                                on_frame=self._on_audio_frame,
                                device=target_idx
                            )
                            self._stream.start()
                            reason = "earbuds mic silent" if is_cur_bt else "mic silent"
                            self.status_updated.emit(f"🎙️ Switched to {target_name} ({reason})... Speak freely!")
                            continue

                    is_speech = self._noise_gate.is_speech(chunk)
                    rms_val = getattr(self._noise_gate, "last_rms", 0.0)
                    noise_fl = getattr(self._noise_gate, "noise_floor", 18.0)
                    norm_level = min(1.0, max(0.0, (rms_val - noise_fl) / 100.0))
                    self.audio_level_updated.emit(norm_level, is_speech)
                    should_transcribe = False

                    if is_speech:
                        if not speech_active:
                            speech_active = True
                            speech_start_time = now
                            silence_start = now
                            speech_buffer.clear()
                            # INSTANT MEDIA DUCKING: Duck YouTube/Spotify/Browser so user voice is captured cleanly
                            try:
                                from voice.media_ducker import MediaDucker
                                MediaDucker.get_instance().duck(attenuation=0.15)
                            except Exception:
                                pass
                            self.status_updated.emit("⚡ Voice detected! Transcribing...")
                        speech_buffer.append(chunk)
                        silence_start = now

                        # Check max phrase duration: force flush if speaking longer than max duration
                        if now - speech_start_time >= max_phrase_duration:
                            should_transcribe = True

                    elif speech_active:
                        speech_buffer.append(chunk)
                        if now - silence_start >= silence_threshold or now - speech_start_time >= max_phrase_duration:
                            should_transcribe = True

                    if should_transcribe:
                        full_pcm = b"".join(speech_buffer)
                        speech_buffer.clear()
                        speech_active = False

                        if len(full_pcm) >= 3200:
                            cur_dev = adm.get_best_input_device() if adm else None
                            is_eb = bool(cur_dev and cur_dev.is_bluetooth)
                            boost_gain = 3.0 if is_eb else 2.2
                            processed_pcm = self._amplify_pcm(full_pcm, gain=boost_gain)
                            audio_data = sr.AudioData(processed_pcm, 16000, 2)
                            text = self._transcribe_audio(r, audio_data)
                            if text and not self.is_cancelled:
                                self.status_updated.emit(f"✓ Heard: \"{text}\"")
                                self.transcription_ready.emit(text)
                                if not self.is_cancelled:
                                    cur_dev = adm.get_best_input_device()
                                    if cur_dev and cur_dev.is_bluetooth:
                                        self.status_updated.emit(f"🎧 Earbuds Mic Active ({cur_dev.clean_name})... Speak next command!")
                                    else:
                                        self.status_updated.emit("🔴 Continuous Listening Active... Speak next command!")
                            elif not self.is_cancelled:
                                self.status_updated.emit("🔴 Listening... Speak clearly into mic.")
                except Exception as e_loop:
                    logger.debug(f"VoiceListenThread inner loop error: {e_loop}")
                    speech_buffer.clear()
                    speech_active = False

        except Exception as e:
            logger.error(f"VoiceListenThread error: {e}", exc_info=True)
            self.status_updated.emit(f"⚠️ Voice error: {e}")
        finally:
            if adm:
                try:
                    adm.unregister_device_change_listener(self._on_device_changed)
                except Exception:
                    pass
            if self._stream:
                try:
                    self._stream.stop()
                except Exception:
                    pass
                self._stream = None
            self.listening_finished.emit()


def parse_markdown_code_blocks(text: str) -> List[dict]:
    """
    Parses conversational text into sequential markdown text and fenced code blocks.
    Returns list of dicts: {"type": "text"|"code", "lang": str, "content": str}
    """
    pattern = re.compile(r"```([a-zA-Z0-9_\-\+]*)\r?\n?(.*?)```", re.DOTALL)
    segments = []
    last_idx = 0
    for match in pattern.finditer(text):
        start, end = match.span()
        if start > last_idx:
            pre_text = text[last_idx:start]
            if pre_text:
                segments.append({"type": "text", "lang": "", "content": pre_text})
        lang = match.group(1).strip() or "code"
        code_content = match.group(2)
        segments.append({"type": "code", "lang": lang, "content": code_content})
        last_idx = end

    if last_idx < len(text):
        post_text = text[last_idx:]
        if post_text:
            segments.append({"type": "text", "lang": "", "content": post_text})

    if not segments:
        segments.append({"type": "text", "lang": "", "content": text})

    return segments


class LiveChatBrowser(QTextBrowser):
    """Selectable rich text chat browser with Coucou visual simplicity, mouse dragging, Ctrl+C, context menu, and ChatGPT-style copy UX."""

    def __init__(self, on_action=None, parent=None):
        super().__init__(parent)
        self.on_action = on_action
        self._auto_scroll_to_bottom = True
        self._raw_messages: List[str] = []
        self._raw_code_blocks: List[str] = []

        self.setReadOnly(True)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._on_anchor_clicked)
        self.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        self.setTextInteractionFlags(
            Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard | Qt.LinksAccessibleByMouse
        )
        self.setCursor(Qt.IBeamCursor)
        self.setStyleSheet("""
            QTextBrowser {
                background-color: #141518;
                color: #f5f6f8;
                border: 1px solid rgba(255, 255, 255, 0.065);
                border-radius: 12px;
                padding: 12px 14px;
                font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", -apple-system, sans-serif;
                font-size: 13px;
                selection-background-color: #22d3ee;
                selection-color: #0b0c0e;
            }
            QScrollBar:vertical {
                background: #090a0d;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #1d1f23;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: #2a2d33;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        # Connect vertical scrollbar signals for rock-solid auto-scrolling
        vsb = self.verticalScrollBar()
        vsb.rangeChanged.connect(self._on_scroll_range_changed)
        vsb.valueChanged.connect(self._on_scroll_value_changed)

    def _on_scroll_range_changed(self, min_val: int, max_val: int):
        """Automatically keeps scroll position pinned to the bottom when new content expands layout."""
        if self._auto_scroll_to_bottom and not self.textCursor().hasSelection():
            self.verticalScrollBar().setValue(max_val)

    def _on_scroll_value_changed(self, value: int):
        """Tracks whether user has manually scrolled up to inspect history or is at the bottom."""
        if self.textCursor().hasSelection():
            self._auto_scroll_to_bottom = False
            return
        vsb = self.verticalScrollBar()
        # If user is within 40 pixels of the bottom, keep auto-scroll active.
        # If user scrolled further up, pause auto-scroll so view doesn't jump while reading.
        if vsb.maximum() - value <= 40:
            self._auto_scroll_to_bottom = True
        else:
            self._auto_scroll_to_bottom = False

    def showEvent(self, event):
        super().showEvent(event)
        self.scroll_to_bottom(force=True)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_scroll_to_bottom:
            self.scroll_to_bottom(force=False)

    def scroll_to_bottom(self, force: bool = True):
        """Forces the scrollbar and cursor to the absolute bottom of the document."""
        if self.textCursor().hasSelection():
            return
        if force:
            self._auto_scroll_to_bottom = True

        vsb = self.verticalScrollBar()
        vsb.setValue(vsb.maximum())

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

        # Handle asynchronous QTextDocument layout / font metric passes in Qt event loop
        QTimer.singleShot(0, self._deferred_scroll_to_bottom)
        QTimer.singleShot(40, self._deferred_scroll_to_bottom)
        QTimer.singleShot(160, self._deferred_scroll_to_bottom)
        QTimer.singleShot(300, self._deferred_scroll_to_bottom)

    def _deferred_scroll_to_bottom(self):
        if self._auto_scroll_to_bottom and not self.textCursor().hasSelection():
            vsb = self.verticalScrollBar()
            vsb.setValue(vsb.maximum())
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.setTextCursor(cursor)
            self.ensureCursorVisible()
    def _on_anchor_clicked(self, url: QUrl):
        """ChatGPT-style copy action dispatcher for message bubbles and code blocks."""
        scheme = url.scheme()
        url_str = url.toString() if hasattr(url, "toString") else str(url)
        if scheme in ("copy-msg", "copy_msg") or url_str.startswith(("copy-msg:", "copy_msg:")):
            try:
                val_str = url.path() if url.path() else url_str.split(":", 1)[1]
                idx = int(val_str)
                if 0 <= idx < len(self._raw_messages):
                    self._copy_to_clipboard(self._raw_messages[idx])
                    if self.on_action:
                        self.on_action("feedback", "✓ Message copied to clipboard!")
            except Exception as e:
                logger.debug(f"copy_msg error: {e}")
        elif scheme in ("copy-code", "copy_code") or url_str.startswith(("copy-code:", "copy_code:")):
            try:
                val_str = url.path() if url.path() else url_str.split(":", 1)[1]
                idx = int(val_str)
                if 0 <= idx < len(self._raw_code_blocks):
                    self._copy_to_clipboard(self._raw_code_blocks[idx])
                    if self.on_action:
                        self.on_action("feedback", "✓ Code block copied to clipboard!")
            except Exception as e:
                logger.debug(f"copy_code error: {e}")
        elif scheme in ("http", "https") or url_str.startswith(("http://", "https://")):
            QDesktopServices.openUrl(url)

    def clear(self):
        self._raw_messages.clear()
        self._raw_code_blocks.clear()
        super().clear()

    def contextMenuEvent(self, event):
        """Right-click context menu supporting selected text copy, line copy, resend, and memory."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #141518;
                color: #f5f6f8;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 10px;
                padding: 4px;
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 20px;
                border-radius: 6px;
            }
            QMenu::item:selected {
                background-color: #1d1f23;
                color: #22d3ee;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 0.06);
                margin: 4px 8px;
            }
        """)

        cursor = self.textCursor()
        selected_text = cursor.selectedText().replace("\u2029", "\n").strip()

        # Find block/line under mouse position
        pos_cursor = self.cursorForPosition(event.pos())
        pos_cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
        block_text = pos_cursor.selectedText().replace("\u2029", "\n").strip()

        target_text = selected_text if selected_text else block_text

        copy_sel_act = None
        if selected_text:
            copy_sel_act = menu.addAction("Copy")

        copy_line_act = menu.addAction("Copy Current Line")
        select_all_act = menu.addAction("Select All")
        menu.addSeparator()

        resend_act = None
        remember_act = None
        if target_text:
            resend_act = menu.addAction("Resend / Fill Input")
            remember_act = menu.addAction("Remember in Memory")
            menu.addSeparator()

        clear_act = menu.addAction("Clear Chat")

        action = menu.exec(event.globalPos())
        if copy_sel_act and action == copy_sel_act:
            self._copy_to_clipboard(selected_text)
        elif action == copy_line_act:
            if block_text:
                self._copy_to_clipboard(block_text)
            elif selected_text:
                self._copy_to_clipboard(selected_text)
        elif action == copy_all_act:
            if self.on_action:
                self.on_action("copy_all", "")
        elif action == select_all_act:
            self.selectAll()
        elif resend_act and action == resend_act:
            clean_text = self._strip_speaker_prefix(target_text)
            if self.on_action:
                self.on_action("resend", clean_text)
        elif remember_act and action == remember_act:
            clean_text = self._strip_speaker_prefix(target_text)
            if self.on_action:
                self.on_action("remember", clean_text)
        elif action == clear_act:
            if self.on_action:
                self.on_action("clear", "")

    def _strip_speaker_prefix(self, text: str) -> str:
        """Removes [HH:MM] and Sender: prefixes for resending/remembering clean text."""
        text = re.sub(r"^\[\d{1,2}:\d{2}\]\s*", "", text)
        text = re.sub(r"^(You|Jarvis|Assistant|System):\s*", "", text, flags=re.IGNORECASE)
        return text.strip()

    def _copy_to_clipboard(self, text: str):
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)
            if self.on_action:
                disp_t = text[:35] + ("..." if len(text) > 35 else "")
                self.on_action("feedback", f"✓ Copied: \"{disp_t}\"")


class MessageBubble(QFrame):
    """Backwards-compatible message bubble placeholder."""
    def __init__(self, sender: str, text: str, timestamp: Optional[str] = None, on_action=None):
        super().__init__()
        self.sender = sender
        self.raw_text = text
        self.timestamp = timestamp or datetime.datetime.now().strftime("%H:%M")
        self.on_action = on_action


class CommandHistoryLineEdit(QLineEdit):
    """
    Enhanced QLineEdit with command history navigation via Up and Down Arrow keys.
    Records previously typed and spoken commands, allowing instant recall and re-execution.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.history: List[str] = []
        self.history_index: int = -1
        self._temp_text: str = ""

    def add_history(self, text: str) -> None:
        """Add a command to history and reset navigation index."""
        cleaned = text.strip()
        if not cleaned:
            return
        # Avoid immediate duplicate consecutive entries
        if not self.history or self.history[-1] != cleaned:
            self.history.append(cleaned)
        self.history_index = -1
        self._temp_text = ""

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Up, Qt.Key_Up):
            if self._navigate_history(direction=-1):
                event.accept()
                return
        elif key in (Qt.Key.Key_Down, Qt.Key_Down):
            if self._navigate_history(direction=1):
                event.accept()
                return
        elif key in (Qt.Key.Key_Escape, Qt.Key_Escape) and self.history_index != -1:
            self.setText(self._temp_text)
            self.history_index = -1
            self.setCursorPosition(len(self.text()))
            event.accept()
            return

        super().keyPressEvent(event)

    def _navigate_history(self, direction: int) -> bool:
        if not self.history:
            return False

        if self.history_index == -1:
            if direction == 1:
                return False
            self._temp_text = self.text()
            new_index = len(self.history) - 1
        else:
            new_index = self.history_index + direction

        if new_index < 0:
            new_index = 0
        elif new_index >= len(self.history):
            new_index = -1

        self.history_index = new_index

        if self.history_index == -1:
            self.setText(self._temp_text)
        else:
            self.setText(self.history[self.history_index])

        self.setCursorPosition(len(self.text()))
        return True


class ChatView(QWidget):
    """Main Chat Tab with selectable rich text chat area, context chips, voice input, mute, and clear controls."""

    message_submitted = Signal(str)
    voice_message_submitted = Signal(str)
    mute_toggled = Signal(bool)
    chat_cleared = Signal()
    voice_listening_changed = Signal(bool)
    audio_level_updated = Signal(float, bool)  # (normalized_level, is_speech)
    remember_requested = Signal(str)
    open_news_requested = Signal()
    play_briefing_requested = Signal(str)

    def __init__(self, jarvis_core=None):
        super().__init__()
        self.core = jarvis_core
        self.is_muted = False
        self.conversation_history: List[Tuple[str, str, str]] = []
        self._voice_thread: Optional[VoiceListenThread] = None
        self._is_explicit_listening = False
        self._is_executing_command = False
        self._active_chip_buttons: List[QPushButton] = []
        self._current_chips: List[Any] = []
        self._news_card_briefing: Optional[Dict[str, Any]] = None

        self._init_ui()

        # Seed command history from active conversation manager if available
        if self.core and hasattr(self.core, "conversation_manager") and self.core.conversation_manager:
            try:
                for turn in self.core.conversation_manager.get_history(limit=50):
                    raw = getattr(turn, "raw_input", "") or getattr(turn, "normalized_input", "")
                    if raw and raw.strip():
                        self.input_field.add_history(raw.strip())
            except Exception:
                pass

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(6)

        # 1. Top Control Bar (Title, Message Count, Copy All, Mute Toggle, Clear Chat)
        toolbar = QFrame()
        toolbar.setStyleSheet("background: transparent; margin-bottom: 2px;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)

        title_lbl = QLabel("💬 Live Conversation")
        title_lbl.setStyleSheet("color: #94a3b8; font-size: 13px; font-weight: 700; letter-spacing: 0.5px;")
        toolbar_layout.addWidget(title_lbl)

        self.msg_count_lbl = QLabel("1 message")
        self.msg_count_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 600; margin-left: 4px;")
        toolbar_layout.addWidget(self.msg_count_lbl)

        toolbar_layout.addStretch()

        # Copy All Button
        self.copy_all_btn = QPushButton("📋 Copy All")
        self.copy_all_btn.setProperty("class", "toolbar-btn")
        self.copy_all_btn.setCursor(Qt.PointingHandCursor)
        self.copy_all_btn.setToolTip("Copy entire chat history to clipboard")
        self.copy_all_btn.clicked.connect(self.copy_all_messages)
        toolbar_layout.addWidget(self.copy_all_btn)

        # Mute / Unmute Button
        self.mute_btn = QPushButton("🔊 Voice: ON")
        self.mute_btn.setProperty("class", "toolbar-btn-mute-on")
        self.mute_btn.setCursor(Qt.PointingHandCursor)
        self.mute_btn.setToolTip("Toggle Jarvis voice output (Mute / Unmute)")
        self.mute_btn.clicked.connect(self.toggle_mute)
        toolbar_layout.addWidget(self.mute_btn)

        # Clear Chat Button
        self.clear_btn = QPushButton("🗑️ Clear Chat")
        self.clear_btn.setProperty("class", "toolbar-btn-danger")
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setToolTip("Clear all conversation history")
        self.clear_btn.clicked.connect(self.clear_chat)
        toolbar_layout.addWidget(self.clear_btn)

        main_layout.addWidget(toolbar)

        # 2. Selectable Live Conversation Chat Browser
        self.chat_display = LiveChatBrowser(on_action=self._handle_bubble_action)
        main_layout.addWidget(self.chat_display, stretch=1)

        # 3. Dynamic Quick action chips container
        self.chips_container = QWidget()
        self.chips_layout = QHBoxLayout(self.chips_container)
        self.chips_layout.setContentsMargins(0, 0, 0, 0)
        self.chips_layout.setSpacing(8)
        self.chips_layout.addStretch()
        main_layout.addWidget(self.chips_container)
        self.chips_container.setVisible(False)
        self.refresh_suggestion_chips()

        # 3b. Compact News Briefing card (visual only; data comes from the
        # structured news-briefing contract, never parsed from chat text).
        self.news_card = QFrame()
        self.news_card.setStyleSheet(
            "QFrame { background-color: #0E1626; border: 1px solid rgba(0,210,255,0.4);"
            " border-radius: 10px; }"
        )
        news_layout = QVBoxLayout(self.news_card)
        news_layout.setContentsMargins(14, 10, 14, 10)
        news_layout.setSpacing(4)
        self.news_title_lbl = QLabel("📰 TODAY'S NEWS")
        self.news_title_lbl.setStyleSheet(
            "color: #00D2FF; font-size: 12px; font-weight: 800; letter-spacing: 1px;"
            " background: transparent; border: none;"
        )
        news_layout.addWidget(self.news_title_lbl)
        self.news_date_lbl = QLabel("")
        self.news_date_lbl.setStyleSheet(
            "color: #8B98AD; font-size: 11px; background: transparent; border: none;"
        )
        news_layout.addWidget(self.news_date_lbl)
        self.news_top_lbl = QLabel("")
        self.news_top_lbl.setWordWrap(True)
        self.news_top_lbl.setStyleSheet(
            "color: #EDF2F7; font-size: 13px; font-weight: 700;"
            " background: transparent; border: none;"
        )
        news_layout.addWidget(self.news_top_lbl)
        self.news_meta_lbl = QLabel("")
        self.news_meta_lbl.setWordWrap(True)
        self.news_meta_lbl.setStyleSheet(
            "color: #5B6B82; font-size: 11px; background: transparent; border: none;"
        )
        news_layout.addWidget(self.news_meta_lbl)
        news_btn_row = QHBoxLayout()
        news_btn_row.setSpacing(8)
        self.news_open_btn = QPushButton("Open News")
        self.news_open_btn.setProperty("class", "primary-btn")
        self.news_open_btn.setCursor(Qt.PointingHandCursor)
        self.news_open_btn.clicked.connect(lambda: self.open_news_requested.emit())
        news_btn_row.addWidget(self.news_open_btn)
        self.news_play_btn = QPushButton("🔊 Play Briefing")
        self.news_play_btn.setProperty("class", "chip-btn")
        self.news_play_btn.setCursor(Qt.PointingHandCursor)
        self.news_play_btn.clicked.connect(self._on_play_briefing_clicked)
        news_btn_row.addWidget(self.news_play_btn)
        news_btn_row.addStretch()
        news_layout.addLayout(news_btn_row)
        main_layout.addWidget(self.news_card)
        self.news_card.setVisible(False)

        # 4. Input Area (Fixed at bottom)
        input_layout = QHBoxLayout()
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(10)

        self.input_field = CommandHistoryLineEdit()
        self.input_field.setPlaceholderText("Type a command or question for Jarvis... (Press Enter to Send)")
        self.input_field.returnPressed.connect(self._send_message)
        input_layout.addWidget(self.input_field, stretch=1)

        # Voice Listen Button
        self.listen_btn = QPushButton("🎙 Listen")
        self.listen_btn.setProperty("class", "chip-btn")
        self.listen_btn.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: 700; padding: 10px 16px;")
        self.listen_btn.setCursor(Qt.PointingHandCursor)
        self.listen_btn.setToolTip("Click to speak your command via microphone")
        self.listen_btn.clicked.connect(self._toggle_voice_listen)
        input_layout.addWidget(self.listen_btn)

        # Send Button
        self.send_btn = QPushButton("Send")
        self.send_btn.setProperty("class", "primary-btn")
        self.send_btn.setCursor(Qt.PointingHandCursor)
        self.send_btn.clicked.connect(self._send_message)
        input_layout.addWidget(self.send_btn)

        main_layout.addLayout(input_layout)

        # 5. Voice Status / Feedback Label
        self.voice_feedback_lbl = QLabel("")
        self.voice_feedback_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600; padding: 0 4px;")
        self.voice_feedback_lbl.setFixedHeight(18)
        main_layout.addWidget(self.voice_feedback_lbl)

        # Welcome message
        self.add_message("Jarvis", "Online and ready. Say 'Jarvis' when you need me.")

    def set_suggestion_chips(self, chips: Optional[List[Any]] = None):
        """Dynamically populates intelligent context-aware suggestion chips."""
        self._is_executing_command = False
        self._active_chip_buttons.clear()

        # Clear existing buttons
        while self.chips_layout.count() > 0:
            item = self.chips_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        chip_list = chips or []
        self._current_chips = list(chip_list)

        if not chip_list:
            if hasattr(self, "chips_container"):
                self.chips_container.setVisible(False)
            return

        if hasattr(self, "chips_container"):
            self.chips_container.setVisible(True)

        for c in chip_list:
            lbl = getattr(c, "label", str(c))
            cmd = getattr(c, "command", str(c))
            btn = QPushButton(lbl)
            btn.setProperty("class", "suggestion-chip")
            btn.setStyleSheet(
                "QPushButton { background-color: #1e293b; color: #94a3b8; border: 1px solid #334155; "
                "border-radius: 12px; padding: 5px 12px; font-size: 11px; font-weight: 600; } "
                "QPushButton:hover { background-color: #334155; color: #38bdf8; border: 1px solid #38bdf8; } "
                "QPushButton:pressed { background-color: #0f172a; color: #0284c7; border: 1px solid #0284c7; } "
                "QPushButton:disabled { background-color: #1e293b; color: #64748b; border: 1px solid #1e293b; }"
            )
            btn.setCursor(Qt.PointingHandCursor)
            btn.setToolTip(f"Suggests: {cmd}")
            btn.clicked.connect(lambda checked=False, chip_obj=c, b=btn: self._on_chip_clicked(chip_obj, b))
            self._active_chip_buttons.append(btn)
            self.chips_layout.addWidget(btn)

        self.chips_layout.addStretch()

    def refresh_suggestion_chips(
        self,
        last_input: str = "",
        last_response: str = "",
        active_app: Optional[str] = None
    ):
        """Generates and updates suggestion chips using the authoritative SuggestionManager."""
        try:
            mgr = None
            if self.core and hasattr(self.core, "suggestion_manager") and self.core.suggestion_manager:
                mgr = self.core.suggestion_manager
            else:
                from core.intelligence.suggestion_manager import get_suggestion_manager
                mgr = get_suggestion_manager()

            act_ctx = getattr(self.core, "active_context", None) if self.core else None
            diag_mgr = getattr(self.core, "dialog_manager", None) if self.core else None

            sys_state = {}
            if active_app:
                sys_state["active_app"] = active_app

            chips = mgr.generate_contextual_chips(
                active_context=act_ctx,
                dialog_manager=diag_mgr,
                last_user_input=last_input,
                last_assistant_response=last_response,
                system_state=sys_state,
                limit=5
            )
            self.set_suggestion_chips(chips)
        except Exception as e:
            import logging
            logging.getLogger("jarvis.gui.chat").error(f"Error refreshing suggestion chips: {e}")

    def update_context_chips(self, context_hint: Optional[str] = None):
        """Legacy compatibility adapter: routes into intelligent suggestion manager."""
        self.refresh_suggestion_chips(last_input=context_hint or "")

    def set_speaking_state(self, speaking: bool):
        """Updates voice button label based on active TTS speaking state."""
        if self.is_muted:
            self.mute_btn.setText("🔇 Voice: Muted")
        elif speaking:
            self.mute_btn.setText("🔊 Speaking...")
        else:
            self.mute_btn.setText("🔊 Voice: ON")

    def toggle_mute(self) -> bool:
        """Toggles the mute state for TTS voice output."""
        self.is_muted = not self.is_muted
        if self.is_muted:
            self.mute_btn.setText("🔇 Voice: Muted")
            self.mute_btn.setProperty("class", "toolbar-btn-muted")
        else:
            self.mute_btn.setText("🔊 Voice: ON")
            self.mute_btn.setProperty("class", "toolbar-btn-mute-on")

        self.mute_btn.style().unpolish(self.mute_btn)
        self.mute_btn.style().polish(self.mute_btn)
        self.mute_toggled.emit(self.is_muted)
        return self.is_muted

    def clear_chat(self) -> None:
        """Clears all conversation messages and resets message history."""
        from gui.sound_effects import Sound
        Sound.play("close")
        self.conversation_history.clear()
        self.chat_display.clear()
        self.add_message("Jarvis", "Chat cleared. Ready for your command, Boss.")
        self.chat_cleared.emit()

    def copy_all_messages(self) -> str:
        """Copies all messages in the conversation to the clipboard."""
        if not self.conversation_history:
            return ""

        formatted_lines = []
        for item in self.conversation_history:
            if len(item) == 3:
                sender, text, ts = item
                formatted_lines.append(f"[{ts}] {sender}: {text}")
            else:
                sender, text = item
                formatted_lines.append(f"{sender}: {text}")

        full_text = "\n".join(formatted_lines).strip()
        clipboard = QApplication.clipboard()
        if clipboard:
            from gui.sound_effects import Sound
            Sound.play("pop")
            clipboard.setText(full_text)
            self.copy_all_btn.setText("✓ All Copied!")
            self.copy_all_btn.setStyleSheet("color: #10b981; border-color: #10b981;")
            QTimer.singleShot(1500, self._reset_copy_all_btn)

        return full_text

    def _reset_copy_all_btn(self):
        self.copy_all_btn.setText("📋 Copy All")
        self.copy_all_btn.setStyleSheet("")

    def _toggle_voice_listen(self):
        """Starts or stops microphone speech recognition."""
        from gui.sound_effects import Sound
        Sound.play("peek")
        if self._voice_thread and self._voice_thread.isRunning():
            self.stop_voice_listening()
            return
        self.start_voice_listening(play_chime=True)

    def start_voice_listening(self, play_chime: bool = True):
        """Starts background voice listening thread if not already running."""
        if self._voice_thread and self._voice_thread.isRunning():
            return

        # Keep the hardware stream open, but do not treat every nearby voice as
        # a command. The wake word opens a short, one-command interaction.
        self._is_explicit_listening = False
        gate = getattr(self.core, "interaction_gate", None)
        if gate:
            gate.activate_explicit_listening()

        if play_chime:
            try:
                from voice.chime import play_wake_chime_async
                play_wake_chime_async()
            except Exception:
                pass

        self.listen_btn.setText("🔴 Stop Listening")
        self.listen_btn.setProperty("class", "listen-btn-active")
        self.listen_btn.style().unpolish(self.listen_btn)
        self.listen_btn.style().polish(self.listen_btn)
        self.input_field.setPlaceholderText("Listening for 'Jarvis'... Speak freely.")
        self.voice_feedback_lbl.setText("● Standby (Listening for 'Jarvis')...")
        self.voice_feedback_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600; padding: 0 4px;")

        self.voice_listening_changed.emit(True)

        self._voice_thread = VoiceListenThread(self)
        self._voice_thread.transcription_ready.connect(self._on_voice_transcribed)
        self._voice_thread.status_updated.connect(self._on_voice_status)
        self._voice_thread.listening_finished.connect(self._on_voice_finished)
        self._voice_thread.audio_level_updated.connect(self.audio_level_updated)
        self._voice_thread.start()

    def _on_voice_status(self, status: str):
        self.input_field.setPlaceholderText(status)
        self.voice_feedback_lbl.setText(status)
        if "⚠️" in status or "error" in status.lower():
            self.voice_feedback_lbl.setStyleSheet("color: #f59e0b; font-size: 11px; font-weight: 600; padding: 0 4px;")
        elif "✓" in status or "heard" in status.lower():
            self.voice_feedback_lbl.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600; padding: 0 4px;")
        elif "🔴" in status or "listening" in status.lower():
            self.voice_feedback_lbl.setStyleSheet("color: #ef4444; font-size: 11px; font-weight: 600; padding: 0 4px;")
        else:
            self.voice_feedback_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600; padding: 0 4px;")

    def _on_voice_transcribed(self, text: str):
        if not text or not text.strip():
            return

        gate = getattr(self.core, "interaction_gate", None)
        if gate:
            decision = gate.evaluate(text, is_explicit_listen=False)
            if not decision.accepted:
                # Discarded background speech (e.g. "Sagar hospital", "murshida", "chalo khana kha kar aata hun")
                # Restore any ducked media volume
                try:
                    from voice.media_ducker import MediaDucker
                    MediaDucker.get_instance().unduck()
                except Exception:
                    pass
                self.voice_feedback_lbl.setText("● Standby (Listening for 'Jarvis')...")
                self.voice_feedback_lbl.setStyleSheet("color: #64748b; font-size: 11px; font-weight: 500; padding: 0 4px;")
                return

            if decision.is_barge_in and hasattr(self.core, "interrupt_active_speech"):
                self.core.interrupt_active_speech(reason=decision.reason or "voice_barge_in", interrupting_text=text)

            if decision.reason in ("stop_command", "interruption_phrase"):
                self.stop_voice_listening()
                self.voice_feedback_lbl.setText("Continuous listening stopped.")
                return

            if decision.is_standalone_wake:
                try:
                    from voice.chime import play_wake_chime_async
                    play_wake_chime_async()
                except Exception:
                    pass
                self.voice_feedback_lbl.setText("● Active Listening... Speak your command!")
                self.voice_feedback_lbl.setStyleSheet("color: #10b981; font-size: 11px; font-weight: 600; padding: 0 4px;")
                self.add_message("You", "Jarvis")
                self.voice_message_submitted.emit("Jarvis")
                return

            # Accepted command with wake word removed or from explicit listening
            cmd = decision.command if decision.command else text
            try:
                from voice.chime import play_wake_chime_async
                play_wake_chime_async()
            except Exception:
                pass
            self.input_field.add_history(cmd)
            self.input_field.setText(cmd)
            self.input_field.clear()
            self.add_message("You", cmd)
            self.voice_message_submitted.emit(cmd)
        else:
            try:
                from voice.chime import play_wake_chime_async
                play_wake_chime_async()
            except Exception:
                pass
            self.input_field.setText(text)
            self._send_message()

    def stop_voice_listening(self):
        """Cleanly cancels and terminates the background voice listening thread."""
        self._is_explicit_listening = False
        gate = getattr(self.core, "interaction_gate", None)
        if gate:
            gate.deactivate_listening()

        if self._voice_thread:
            try:
                self._voice_thread.cancel()
                if self._voice_thread.isRunning():
                    self._voice_thread.wait(3500)
            except Exception:
                pass
            self._voice_thread = None
        self._on_voice_finished()

    def _on_voice_finished(self):
        self._is_explicit_listening = False
        gate = getattr(self.core, "interaction_gate", None)
        if gate:
            gate.deactivate_listening()

        self.listen_btn.setText("🎙 Listen")
        self._voice_thread = None
        self.listen_btn.setEnabled(True)
        self.listen_btn.setProperty("class", "chip-btn")
        self.listen_btn.setStyleSheet("background-color: #1e293b; color: #38bdf8; font-weight: 700; padding: 10px 16px;")
        self.listen_btn.style().unpolish(self.listen_btn)
        self.listen_btn.style().polish(self.listen_btn)
        self.input_field.setPlaceholderText("Type a command or question for Jarvis... (Press Enter to Send)")
        self.voice_listening_changed.emit(False)
        # Auto-clear status banner after 4.5 seconds
        QTimer.singleShot(4500, lambda: self._clear_voice_feedback_if_idle())

    def _clear_voice_feedback_if_idle(self):
        if not (self._voice_thread and self._voice_thread.isRunning()):
            self.voice_feedback_lbl.setText("")

    def add_message(self, sender: str, text: str, timestamp: Optional[str] = None):
        """Appends a timestamped line to the selectable rich text chat area."""
        if not timestamp:
            timestamp = datetime.datetime.now().strftime("%H:%M")

        self.conversation_history.append((sender, text, timestamp))

        # Format rich HTML line with selectable text
        is_user = (sender.lower() in ("you", "user"))
        if is_user and hasattr(self, "input_field") and hasattr(self.input_field, "add_history") and text:
            self.input_field.add_history(text)
        is_jarvis = (sender.lower() in ("jarvis", "assistant"))

        # Register message for instant ChatGPT-style copy
        self.chat_display._raw_messages.append(text)
        msg_idx = len(self.chat_display._raw_messages) - 1

        if is_user:
            escaped_body = html.escape(text).replace("\n", "<br/>")
            html_line = f"""
            <div style="text-align: right; margin-top: 6px; margin-bottom: 10px; user-select: text; -webkit-user-select: text;">
                <div style="display: inline-block; text-align: left; max-width: 82%; background-color: #1a1e26; border: 1px solid rgba(34, 211, 238, 0.25); border-radius: 14px; padding: 8px 14px; user-select: text; -webkit-user-select: text;">
                    <div style="margin-bottom: 3px; user-select: none; -webkit-user-select: none;">
                        <span style="color: #22d3ee; font-weight: 700; font-size: 11px;">You</span>
                        <span style="color: #64748b; font-size: 10px; margin-left: 6px;">[{timestamp}]</span>
                    </div>
                    <div style="color: #f5f6f8; font-size: 13px; line-height: 1.45; user-select: text; -webkit-user-select: text;">{escaped_body}</div>
                </div>
            </div>
            """
        elif is_jarvis:
            segments = parse_markdown_code_blocks(text)
            body_html_parts = []
            for seg in segments:
                if seg["type"] == "text":
                    t_clean = seg["content"]
                    if t_clean.strip():
                        t_escaped = html.escape(t_clean).replace("\n", "<br/>")
                        body_html_parts.append(f'<div style="color: #f5f6f8; font-size: 13px; line-height: 1.45; margin-bottom: 4px; user-select: text; -webkit-user-select: text;">{t_escaped}</div>')
                elif seg["type"] == "code":
                    code_raw = seg["content"]
                    self.chat_display._raw_code_blocks.append(code_raw)
                    code_escaped = html.escape(code_raw)
                    lang_name = seg["lang"].upper() if seg["lang"] else "CODE"
                    code_block_html = f"""
                    <div style="margin-top: 6px; margin-bottom: 6px; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; overflow: hidden; user-select: text; -webkit-user-select: text;">
                        <div style="background-color: #161b22; padding: 4px 10px; font-size: 11px; color: #8b949e; border-bottom: 1px solid rgba(255, 255, 255, 0.06); user-select: none; -webkit-user-select: none;">
                            <span style="font-weight: 700; color: #8b949e;">{lang_name}</span>
                        </div>
                        <pre style="background-color: #0d1117; color: #e6edf3; font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; padding: 10px; margin: 0; white-space: pre-wrap; word-wrap: break-word; user-select: text; -webkit-user-select: text;">{code_escaped}</pre>
                    </div>
                    """
                    body_html_parts.append(code_block_html)

            body_content_html = "".join(body_html_parts)
            if not body_content_html.strip():
                escaped_fallback = html.escape(text).replace("\n", "<br/>")
                body_content_html = f'<div style="color: #f5f6f8; font-size: 13px; line-height: 1.45; user-select: text; -webkit-user-select: text;">{escaped_fallback}</div>'

            html_line = f"""
            <div style="text-align: left; margin-top: 6px; margin-bottom: 12px; user-select: text; -webkit-user-select: text;">
                <div style="display: inline-block; text-align: left; max-width: 88%; background-color: #121418; border: 1px solid rgba(255, 255, 255, 0.06); border-radius: 14px; padding: 10px 14px; user-select: text; -webkit-user-select: text;">
                    <div style="margin-bottom: 6px; user-select: none; -webkit-user-select: none;">
                        <span style="background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #22d3ee, stop:1 #0369a1); color: #06121a; font-weight: 800; font-size: 10px; border-radius: 8px; padding: 2px 6px; user-select: none;">JARVIS</span>
                        <span style="color: #64748b; font-size: 10px; margin-left: 6px;">[{timestamp}]</span>
                    </div>
                    {body_content_html}
                </div>
            </div>
            """
        else:
            escaped_body = html.escape(text).replace("\n", "<br/>")
            html_line = f"""
            <div style="text-align: left; margin-top: 6px; margin-bottom: 10px; user-select: text; -webkit-user-select: text;">
                <div style="display: inline-block; text-align: left; max-width: 85%; background-color: #121418; border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 14px; padding: 8px 14px; user-select: text; -webkit-user-select: text;">
                    <div style="margin-bottom: 3px; user-select: none; -webkit-user-select: none;">
                        <span style="color: #f59e0b; font-weight: 700; font-size: 11px;">{html.escape(sender)}</span>
                        <span style="color: #64748b; font-size: 10px; margin-left: 6px;">[{timestamp}]</span>
                    </div>
                    <div style="color: #f5f6f8; font-size: 13px; line-height: 1.45; user-select: text; -webkit-user-select: text;">{escaped_body}</div>
                </div>
            </div>
            """

        self.chat_display.append(html_line)

        # Update dynamic context chips based on message text and speaker
        if is_user:
            self.refresh_suggestion_chips(last_input=text)
        else:
            self._is_executing_command = False
            last_user_inp = ""
            for s, m, _ in reversed(self.conversation_history):
                if s.lower() in ("you", "user"):
                    last_user_inp = m
                    break
            self.refresh_suggestion_chips(last_input=last_user_inp, last_response=text)

        # Update count
        count = len(self.conversation_history)
        self.msg_count_lbl.setText(f"{count} {'messages' if count != 1 else 'message'}")

        # Auto scroll to bottom
        self.chat_display.scroll_to_bottom(force=True)

    def keyPressEvent(self, event):
        """Dispatches Ctrl+A to input field if input has focus; otherwise selects chat conversation."""
        if event.matches(QKeySequence.StandardKey.SelectAll):
            if hasattr(self, "input_field") and self.input_field.hasFocus():
                self.input_field.selectAll()
            else:
                self.chat_display.selectAll()
            event.accept()
            return
        super().keyPressEvent(event)


    def _handle_bubble_action(self, action_type: str, text: str):
        """Handles actions from message context menu (copy, resend, remember, clear, feedback)."""
        if action_type == "feedback":
            self.voice_feedback_lbl.setText(text)
            self.voice_feedback_lbl.setStyleSheet("color: #38bdf8; font-size: 11px; font-weight: 600; padding: 0 4px;")
            QTimer.singleShot(2500, lambda: self._clear_voice_feedback_if_idle())
        elif action_type == "resend":
            self.input_field.setText(text)
            self.input_field.setFocus()
        elif action_type == "remember":
            self.remember_requested.emit(text)
            self.voice_feedback_lbl.setText(f"🧠 Remembered to cognitive memory: \"{text[:40]}...\"")
            self.voice_feedback_lbl.setStyleSheet("color: #a855f7; font-size: 11px; font-weight: 600; padding: 0 4px;")
            QTimer.singleShot(4000, lambda: self._clear_voice_feedback_if_idle())
        elif action_type == "copy_all":
            self.copy_all_messages()
        elif action_type == "clear":
            self.clear_chat()

    def show_news_briefing_card(self, briefing: Dict[str, Any]) -> None:
        """Shows the compact News Briefing card from structured briefing data."""
        try:
            articles = [a for a in briefing.get("articles", [])
                        if isinstance(a, dict) and a.get("headline")]
            if not articles:
                return
            self._news_card_briefing = briefing
            date_str = briefing.get("date") or ""
            self.news_title_lbl.setText("📰 TODAY'S NEWS")
            self.news_date_lbl.setText(str(date_str))
            top = articles[0]
            top_src = (top.get("source") or "").strip()
            top_pub = (top.get("published_at") or "").strip()
            attrib = top_src + (f" \u2022 {top_pub}" if top_pub else "")
            self.news_top_lbl.setText(f"🔴 Top Story\n{top.get('headline', '')}\n{attrib}")
            cats = []
            for a in articles:
                c = (a.get("category") or "").upper()
                if c and c not in cats:
                    cats.append(c)
            n = len(articles)
            self.news_meta_lbl.setText(
                f"{'  '.join(cats[:4])}\n{n} stor{'y' if n == 1 else 'ies'}"
            )
            # Keep a short textual trace in chat history alongside the card.
            self.add_message(
                "Jarvis",
                f"📰 Today's News ({n} stories, {date_str}). Top story: "
                f"{top.get('headline', '')} ({attrib}). Open the News tab to read, listen, or open sources."
            )
            self.news_card.setVisible(True)
        except Exception as exc:
            import logging as _log
            _log.getLogger("jarvis.gui.chat_view").debug(f"show_news_briefing_card failed: {exc}")

    def _on_play_briefing_clicked(self) -> None:
        try:
            b = self._news_card_briefing or {}
            text = b.get("spoken_text") or ""
            if not text:
                arts = [a for a in b.get("articles", []) if isinstance(a, dict) and a.get("headline")]
                text = ". ".join(a.get("headline", "") for a in arts[:3])
            if text:
                self.play_briefing_requested.emit(text)
        except Exception:
            pass

    def hide_news_briefing_card(self) -> None:
        try:
            self.news_card.setVisible(False)
            self._news_card_briefing = None
        except Exception:
            pass

    def _send_message(self):
        text = self.input_field.text().strip()
        if not text:
            return
        from gui.sound_effects import Sound
        Sound.play("send")
        self.input_field.add_history(text)
        self.input_field.clear()
        self.add_message("You", text)
        self.message_submitted.emit(text)

    def _on_chip_clicked(self, chip: Any, btn: Optional[QPushButton] = None):
        """
        Executes a suggestion chip via the standard semantic input pipeline.
        Enforces Section 2, 18, and 19 requirements:
        - Same execution pipeline as typed and voice input.
        - Execution state feedback ("⏳ Executing...") with double-click guard.
        - Stale chip protection: uses chip's explicit command/target.
        """
        from gui.sound_effects import Sound
        Sound.play("blip")
        if self._is_executing_command:
            return  # Prevent double-click duplicate execution
        self._is_executing_command = True

        cmd_text = getattr(chip, "command", str(chip))

        # Show temporary executing feedback
        if btn:
            btn.setText("⏳ Executing...")
            btn.setEnabled(False)
        for b in self._active_chip_buttons:
            if b is not btn:
                b.setEnabled(False)

        # Route through same authoritative semantic pipeline via message_submitted
        self.input_field.setText(cmd_text)
        self._send_message()
