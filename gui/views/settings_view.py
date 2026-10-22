# gui/views/settings_view.py
"""Settings View: LLM Provider, Language Style, Voice preferences, and Biometric Security."""

import logging
import os
import yaml

logger = logging.getLogger("jarvis.gui.settings")

from typing import Optional
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class MicTestWorker(QThread):
    """Runs a non-blocking audio capture test to prevent freezing the PySide6 UI."""
    test_finished = Signal(dict)

    def __init__(self, device_index: Optional[int] = None, duration: float = 1.2, parent=None):
        super().__init__(parent)
        self.device_index = device_index
        self.duration = duration

    def run(self):
        try:
            from voice.device_manager import AudioDeviceManager
            adm = AudioDeviceManager()
            result = adm.test_device_audio(device_index=self.device_index, duration=self.duration)
            self.test_finished.emit(result)
        except Exception as e:
            self.test_finished.emit({
                "success": False,
                "rms": 0.0,
                "peak": 0.0,
                "message": f"Test failed: {str(e)}",
                "device_name": "Unknown"
            })


class SoftwareUpdateWorker(QThread):
    """Executes update discovery and installation asynchronously to prevent freezing the PySide6 UI."""
    status_updated = Signal(str, str)  # summary, detail
    check_finished = Signal(object, str)  # UpdatePlan, message
    update_finished = Signal(bool, str, dict)  # success, message, status_dict
    error_occurred = Signal(str)

    def __init__(self, action: str = "check_all", parent=None):
        super().__init__(parent)
        self.action = action  # "check_all", "check_windows", "update_all"

    def run(self):
        try:
            from core.software_update.manager import SoftwareUpdateManager
            from core.software_update.models import UpdateScope
            mgr = SoftwareUpdateManager.get_instance()

            if self.action == "check_all":
                self.status_updated.emit("Checking for updates...", "Scanning WinGet packages and Windows Update in background...")
                plan, msg = mgr.check_updates(scope=UpdateScope.ALL_SUPPORTED)
                self.check_finished.emit(plan, msg)

            elif self.action == "check_windows":
                self.status_updated.emit("Checking Windows updates...", "Querying native Windows Update service via PowerShell COM...")
                plan, msg = mgr.check_updates(scope=UpdateScope.OS)
                self.check_finished.emit(plan, msg)

            elif self.action == "update_all":
                self.status_updated.emit("Installing updates...", "Executing upgrade sequence in background...")
                success, msg = mgr.execute_updates()
                st_dict = mgr.get_status()
                self.update_finished.emit(success, msg, st_dict)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class LayaDownloadWorker(QThread):
    """Downloads Laya System-1 checkpoint in background; never blocks GUI thread."""
    progress_updated = Signal(str, str)  # stage, detail
    download_finished = Signal(bool, str, dict)  # success, message, status_dict
    error_occurred = Signal(str)

    def __init__(self, checkpoint: str = "multilingual", parent=None):
        super().__init__(parent)
        self.checkpoint = checkpoint

    def run(self):
        try:
            from core.laya import get_laya_manager
            mgr = get_laya_manager()
            self.progress_updated.emit("Starting...", f"Laya '{self.checkpoint}' download shuru ho raha hai...")

            def _cb(stage: str, detail: str):
                try:
                    self.progress_updated.emit(str(stage), str(detail))
                except Exception:
                    pass

            success, msg = mgr.download(checkpoint=self.checkpoint, progress_cb=_cb)
            try:
                st = mgr.get_status()
            except Exception:
                st = {}
            self.download_finished.emit(bool(success), str(msg), dict(st))
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class SettingsView(QWidget):
    """Configuration & Customization View for System & Security Biometrics."""

    topology_updated = Signal(dict)

    VOICES = {
        "Swara — Young Female, Hinglish (Recommended)": "hi-IN-SwaraNeural",
        "Neerja — Female, Indian English": "en-IN-NeerjaNeural",
        "Madhur — Male, Hindi/Hinglish": "hi-IN-MadhurNeural",
        "Prabhat — Male, Indian English": "en-IN-PrabhatNeural",
    }

    def __init__(self, jarvis_core=None, tts_engine=None):
        super().__init__()
        self.core = jarvis_core
        self.tts_engine = tts_engine
        self._update_worker: Optional[SoftwareUpdateWorker] = None
        self._laya_worker: Optional[LayaDownloadWorker] = None
        self._adm_listener = None
        self._init_ui()
        self._setup_live_audio_listener()

    def _init_ui(self):
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Scroll Area Container for consistent layout across all screen resolutions
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background-color: transparent;")

        container = QWidget()
        container.setStyleSheet("background-color: transparent;")
        main_layout = QVBoxLayout(container)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(20)

        # =====================================================================
        # 1. SYSTEM SETTINGS CARD
        # =====================================================================
        sys_hdr = QLabel("SYSTEM SETTINGS")
        sys_hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc; letter-spacing: 1.5px;")
        main_layout.addWidget(sys_hdr)

        card_sys = QFrame()
        card_sys.setProperty("class", "card")
        form_sys = QGridLayout(card_sys)
        form_sys.setContentsMargins(24, 22, 24, 22)
        form_sys.setHorizontalSpacing(24)
        form_sys.setVerticalSpacing(16)
        form_sys.setColumnMinimumWidth(0, 180)
        form_sys.setColumnStretch(1, 1)

        # 1. LLM Provider
        lbl_llm = QLabel("LLM Provider:")
        lbl_llm.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        self.combo_llm = QComboBox()
        self.combo_llm.setFixedHeight(36)
        self.combo_llm.addItems(["Mock (Offline)", "Ollama (Local)", "OpenAI Compatible"])
        form_sys.addWidget(lbl_llm, 0, 0)
        form_sys.addWidget(self.combo_llm, 0, 1)

        # 2. Language Preference
        lbl_lang = QLabel("Language Style:")
        lbl_lang.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        self.combo_lang = QComboBox()
        self.combo_lang.setFixedHeight(36)
        self.combo_lang.addItems(["Hinglish", "Hindi", "English"])
        form_sys.addWidget(lbl_lang, 1, 0)
        form_sys.addWidget(self.combo_lang, 1, 1)

        # 3. Conciseness
        lbl_tone = QLabel("Response Conciseness:")
        lbl_tone.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        self.combo_tone = QComboBox()
        self.combo_tone.setFixedHeight(36)
        self.combo_tone.addItems(["Concise (Default)", "Detailed", "Technical"])
        form_sys.addWidget(lbl_tone, 2, 0)
        form_sys.addWidget(self.combo_tone, 2, 1)

        # 4. User Title
        lbl_user = QLabel("User Title:")
        lbl_user.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        self.input_user = QLineEdit("Boss")
        self.input_user.setFixedHeight(36)
        form_sys.addWidget(lbl_user, 3, 0)
        form_sys.addWidget(self.input_user, 3, 1)

        # 5. Neural Voice Persona
        lbl_voice = QLabel("Jarvis Voice:")
        lbl_voice.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        voice_row = QHBoxLayout()
        voice_row.setSpacing(12)
        self.combo_voice = QComboBox()
        self.combo_voice.setFixedHeight(36)
        self.combo_voice.addItems(list(self.VOICES))
        configured_voice = "hi-IN-SwaraNeural"
        if self.core:
            configured_voice = self.core.config.get("voice", {}).get("voice_name", configured_voice)
        for label, voice_id in self.VOICES.items():
            if voice_id == configured_voice:
                self.combo_voice.setCurrentText(label)
                break

        preview_btn = QPushButton("🔊 Preview Voice")
        preview_btn.setProperty("class", "secondary-btn")
        preview_btn.setFixedHeight(36)
        preview_btn.setMinimumWidth(140)
        preview_btn.clicked.connect(self._preview_voice)
        voice_row.addWidget(self.combo_voice, stretch=1)
        voice_row.addWidget(preview_btn)
        form_sys.addWidget(lbl_voice, 4, 0)
        form_sys.addLayout(voice_row, 4, 1)

        self.voice_status = QLabel("")
        self.voice_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form_sys.addWidget(self.voice_status, 5, 1)

        # 6. Audio Device & Bluetooth Routing Card
        bt_card = QFrame()
        bt_card.setStyleSheet("""
            QFrame {
                background-color: #0b1329;
                border: 1px solid #1e293b;
                border-radius: 8px;
                padding: 12px;
            }
        """)
        bt_layout = QVBoxLayout(bt_card)
        bt_layout.setSpacing(10)

        # Status Header Row
        bt_header = QHBoxLayout()
        lbl_bt_title = QLabel("🎧 Bluetooth Earbuds & Mic Routing")
        lbl_bt_title.setStyleSheet("font-weight: 700; font-size: 13px; color: #f8fafc;")
        bt_header.addWidget(lbl_bt_title)
        bt_header.addStretch()

        self.lbl_bt_badge = QLabel("○ Bluetooth: Standby")
        self.lbl_bt_badge.setStyleSheet("""
            color: #94a3b8;
            font-weight: 600;
            font-size: 11px;
            background-color: rgba(148, 163, 184, 0.12);
            border: 1px solid rgba(148, 163, 184, 0.25);
            border-radius: 6px;
            padding: 3px 8px;
        """)
        bt_header.addWidget(self.lbl_bt_badge)
        bt_layout.addLayout(bt_header)

        self.lbl_bt_device = QLabel("Active Hardware: Scanning audio endpoints...")
        self.lbl_bt_device.setStyleSheet("color: #e2e8f0; font-size: 12px; font-weight: 500;")
        bt_layout.addWidget(self.lbl_bt_device)

        self.lbl_bt_details = QLabel("Live Route: Initializing...")
        self.lbl_bt_details.setStyleSheet("color: #64748b; font-size: 11px;")
        bt_layout.addWidget(self.lbl_bt_details)

        # Checkboxes for auto-switch & announcements
        chk_layout = QVBoxLayout()
        chk_layout.setSpacing(6)

        self.chk_auto_switch = QCheckBox("⚡ Auto-switch mic & speaker to Bluetooth earbuds when connected (Recommended)")
        self.chk_auto_switch.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 500;")
        auto_sw_val = True
        if self.core and hasattr(self.core, "config"):
            auto_sw_val = bool(self.core.config.get("voice", {}).get("auto_switch_headset", True))
        self.chk_auto_switch.setChecked(auto_sw_val)
        chk_layout.addWidget(self.chk_auto_switch)

        self.chk_announce_bt = QCheckBox("📢 Natural voice announcement when Bluetooth earbuds connect or disconnect")
        self.chk_announce_bt.setStyleSheet("color: #cbd5e1; font-size: 12px; font-weight: 500;")
        ann_val = True
        if self.core and hasattr(self.core, "config"):
            ann_val = bool(self.core.config.get("voice", {}).get("announce_device_changes", True))
        self.chk_announce_bt.setChecked(ann_val)
        chk_layout.addWidget(self.chk_announce_bt)

        bt_layout.addLayout(chk_layout)

        # Input Microphone Dropdown Row inside card
        lbl_mic_select = QLabel("Select Active Microphone Device:")
        lbl_mic_select.setStyleSheet("font-weight: 600; font-size: 12px; color: #94a3b8; margin-top: 4px;")
        bt_layout.addWidget(lbl_mic_select)

        mic_row = QHBoxLayout()
        mic_row.setSpacing(10)
        self.combo_mic = QComboBox()
        self.combo_mic.setFixedHeight(36)
        self.combo_mic.currentIndexChanged.connect(self._on_mic_changed)

        self.btn_refresh_mic = QPushButton("🔄 Refresh")
        self.btn_refresh_mic.setProperty("class", "secondary-btn")
        self.btn_refresh_mic.setFixedHeight(36)
        self.btn_refresh_mic.setMinimumWidth(100)
        self.btn_refresh_mic.setToolTip("Scan for newly connected microphones or Bluetooth earbuds")
        self.btn_refresh_mic.clicked.connect(self._refresh_microphones)

        self.btn_test_mic = QPushButton("🎤 Test Mic")
        self.btn_test_mic.setProperty("class", "secondary-btn")
        self.btn_test_mic.setFixedHeight(36)
        self.btn_test_mic.setMinimumWidth(110)
        self.btn_test_mic.setToolTip("Record a 1.2s diagnostic sample to verify microphone signal level")
        self.btn_test_mic.clicked.connect(self._test_microphone)

        mic_row.addWidget(self.combo_mic, stretch=1)
        mic_row.addWidget(self.btn_refresh_mic)
        mic_row.addWidget(self.btn_test_mic)
        bt_layout.addLayout(mic_row)

        self.mic_status = QLabel("")
        self.mic_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        bt_layout.addWidget(self.mic_status)

        form_sys.addWidget(QLabel("Audio & Bluetooth:"), 6, 0)
        form_sys.addWidget(bt_card, 6, 1)

        # Save System Settings Button Row
        btn_save_row = QHBoxLayout()
        save_btn = QPushButton("💾 Save Preferences")
        save_btn.setProperty("class", "primary-btn")
        save_btn.setFixedHeight(38)
        save_btn.setMinimumWidth(180)
        save_btn.clicked.connect(self._save_settings)
        btn_save_row.addWidget(save_btn)

        self.btn_reset_pos = QPushButton("📍 Reset JARVIS Position")
        self.btn_reset_pos.setProperty("class", "secondary-btn")
        self.btn_reset_pos.setFixedHeight(38)
        self.btn_reset_pos.setMinimumWidth(180)
        self.btn_reset_pos.setToolTip("Restore the floating JARVIS anchor to default top-center desktop position")
        self.btn_reset_pos.clicked.connect(self._reset_jarvis_anchor_position)
        btn_save_row.addWidget(self.btn_reset_pos)

        btn_save_row.addStretch()
        form_sys.addLayout(btn_save_row, 8, 1)

        main_layout.addWidget(card_sys)

        # =====================================================================
        # 2. BIOMETRIC FACE AUTHENTICATION & SECURITY CARD
        # =====================================================================
        sec_hdr = QLabel("SECURITY & BIOMETRICS")
        sec_hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc; letter-spacing: 1.5px; margin-top: 10px;")
        main_layout.addWidget(sec_hdr)

        card_sec = QFrame()
        card_sec.setProperty("class", "card")
        form_sec = QGridLayout(card_sec)
        form_sec.setContentsMargins(24, 22, 24, 22)
        form_sec.setHorizontalSpacing(24)
        form_sec.setVerticalSpacing(16)
        form_sec.setColumnMinimumWidth(0, 180)
        form_sec.setColumnStretch(1, 1)

        # 1. Face Auth Status
        lbl_face_status = QLabel("Biometric Face Lock:")
        lbl_face_status.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        from security.face_authenticator import FaceAuthenticator
        self.authenticator = FaceAuthenticator(getattr(self.core, "config", {}))

        self.combo_face_auth = QComboBox()
        self.combo_face_auth.setFixedHeight(36)
        self.combo_face_auth.addItems(["Enabled (Active)", "Disabled (Bypassed)"])
        self.combo_face_auth.setCurrentIndex(0 if self.authenticator.enabled else 1)

        form_sec.addWidget(lbl_face_status, 0, 0)
        form_sec.addWidget(self.combo_face_auth, 0, 1)

        # 2. Registered Profile Status
        lbl_profile = QLabel("Enrolled Profile:")
        lbl_profile.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")

        profile_row = QHBoxLayout()
        profile_row.setSpacing(14)
        enrolled = self.authenticator.has_enrolled_profile()
        user_display = self.authenticator.user_name if enrolled else "None"
        status_text = f"✓ Registered ({user_display})" if enrolled else "⚠ Not Enrolled"
        status_color = "#10b981" if enrolled else "#f59e0b"

        self.lbl_profile_status = QLabel(status_text)
        self.lbl_profile_status.setFixedHeight(36)
        self.lbl_profile_status.setStyleSheet(f"""
            QLabel {{
                color: {status_color};
                font-weight: bold;
                font-size: 13px;
                background-color: rgba(15, 23, 42, 0.6);
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0 14px;
            }}
        """)

        self.btn_register_face = QPushButton("📷 Register / Update Face")
        self.btn_register_face.setFixedHeight(36)
        self.btn_register_face.setMinimumWidth(200)
        self.btn_register_face.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00c6ff, stop:1 #0072ff);
                color: #ffffff;
                font-weight: bold;
                font-size: 12px;
                border-radius: 8px;
                padding: 0 16px;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00f2fe, stop:1 #4facfe);
            }
        """)
        self.btn_register_face.clicked.connect(self._open_face_registration)

        profile_row.addWidget(self.lbl_profile_status, stretch=1)
        profile_row.addWidget(self.btn_register_face)
        form_sec.addWidget(lbl_profile, 1, 0)
        form_sec.addLayout(profile_row, 1, 1)

        # 3. Master PIN
        lbl_pin = QLabel("Master Passcode (PIN):")
        lbl_pin.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        self.input_pin = QLineEdit(self.authenticator.master_pin)
        self.input_pin.setFixedHeight(36)
        self.input_pin.setPlaceholderText("4-digit fallback PIN (e.g. 1234)")
        form_sec.addWidget(lbl_pin, 2, 0)
        form_sec.addWidget(self.input_pin, 2, 1)

        # Save Security Settings Button Row
        btn_sec_save_row = QHBoxLayout()
        save_sec_btn = QPushButton("🔒 Save Security Settings")
        save_sec_btn.setProperty("class", "primary-btn")
        save_sec_btn.setFixedHeight(38)
        save_sec_btn.setMinimumWidth(210)
        save_sec_btn.clicked.connect(self._save_security_settings)
        btn_sec_save_row.addWidget(save_sec_btn)
        btn_sec_save_row.addStretch()
        form_sec.addLayout(btn_sec_save_row, 3, 1)

        self.sec_status = QLabel("")
        self.sec_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form_sec.addWidget(self.sec_status, 4, 1)

        main_layout.addWidget(card_sec)

        # =====================================================================
        # 3. PROACTIVE INTELLIGENCE & PRIVACY CARD
        # =====================================================================
        pro_hdr = QLabel("PROACTIVE INTELLIGENCE & PRIVACY")
        pro_hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc; letter-spacing: 1.5px; margin-top: 10px;")
        main_layout.addWidget(pro_hdr)

        card_pro = QFrame()
        card_pro.setProperty("class", "card")
        form_pro = QGridLayout(card_pro)
        form_pro.setContentsMargins(24, 22, 24, 22)
        form_pro.setHorizontalSpacing(24)
        form_pro.setVerticalSpacing(16)
        form_pro.setColumnMinimumWidth(0, 180)
        form_pro.setColumnStretch(1, 1)

        # 1. Proactive Suggestions
        lbl_pro_enable = QLabel("Proactive Suggestions:")
        lbl_pro_enable.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        self.combo_pro_enable = QComboBox()
        self.combo_pro_enable.setFixedHeight(36)
        self.combo_pro_enable.addItems(["Enabled (Active)", "Disabled (Silent Mode)"])
        pro_cfg = self.core.config.get("proactive_intelligence", {}) if self.core else {}
        self.combo_pro_enable.setCurrentIndex(0 if pro_cfg.get("enabled", True) else 1)
        form_pro.addWidget(lbl_pro_enable, 0, 0)
        form_pro.addWidget(self.combo_pro_enable, 0, 1)

        # 2. Suggestion Confidence Threshold
        lbl_conf = QLabel("Confidence Threshold:")
        lbl_conf.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        self.combo_conf = QComboBox()
        self.combo_conf.setFixedHeight(36)
        self.combo_conf.addItems(["70% (Responsive)", "80% (Balanced - Default)", "90% (Strict)"])
        self.combo_conf.setCurrentIndex(1)
        form_pro.addWidget(lbl_conf, 1, 0)
        form_pro.addWidget(self.combo_conf, 1, 1)

        # 3. Distraction Guard
        lbl_guard = QLabel("Distraction Guard:")
        lbl_guard.setStyleSheet("font-weight: 600; font-size: 13px; color: #cbd5e1;")
        self.combo_guard = QComboBox()
        self.combo_guard.setFixedHeight(36)
        self.combo_guard.addItems(["Enabled (Focus Protection)", "Disabled"])
        form_pro.addWidget(lbl_guard, 2, 0)
        form_pro.addWidget(self.combo_guard, 2, 1)

        # Save Proactive Settings Button Row
        btn_pro_save_row = QHBoxLayout()
        save_pro_btn = QPushButton("⚡ Save Proactive Settings")
        save_pro_btn.setProperty("class", "primary-btn")
        save_pro_btn.setFixedHeight(38)
        save_pro_btn.setMinimumWidth(210)
        save_pro_btn.clicked.connect(self._save_proactive_settings)
        btn_pro_save_row.addWidget(save_pro_btn)
        btn_pro_save_row.addStretch()
        form_pro.addLayout(btn_pro_save_row, 3, 1)

        self.pro_status = QLabel("")
        self.pro_status.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form_pro.addWidget(self.pro_status, 4, 1)

        main_layout.addWidget(card_pro)

        # =====================================================================
        # 4. SOFTWARE & SYSTEM UPDATES CARD
        # =====================================================================
        upd_hdr = QLabel("SOFTWARE & SYSTEM UPDATES")
        upd_hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc; letter-spacing: 1.5px; margin-top: 10px;")
        main_layout.addWidget(upd_hdr)

        card_upd = QFrame()
        card_upd.setProperty("class", "card")
        form_upd = QVBoxLayout(card_upd)
        form_upd.setContentsMargins(24, 22, 24, 22)
        form_upd.setSpacing(14)

        # Reboot Banner
        self.reboot_banner = QLabel("⚠ A system restart is required to finish installing updates.")
        self.reboot_banner.setFixedHeight(34)
        self.reboot_banner.setStyleSheet("""
            QLabel {
                color: #f59e0b;
                font-weight: bold;
                font-size: 12px;
                background-color: rgba(245, 158, 11, 0.15);
                border: 1px solid #f59e0b;
                border-radius: 6px;
                padding: 0 12px;
            }
        """)
        self.reboot_banner.setVisible(False)
        form_upd.addWidget(self.reboot_banner)

        # Status row
        upd_status_row = QHBoxLayout()
        self.lbl_upd_summary = QLabel("Status: Ready to check for updates")
        self.lbl_upd_summary.setStyleSheet("color: #cbd5e1; font-size: 13px; font-weight: 600;")
        upd_status_row.addWidget(self.lbl_upd_summary)
        upd_status_row.addStretch()
        form_upd.addLayout(upd_status_row)

        # Action Buttons Row
        btn_upd_row = QHBoxLayout()
        btn_upd_row.setSpacing(12)

        self.btn_check_upd = QPushButton("🔍 Check for Updates")
        self.btn_check_upd.setFixedHeight(36)
        self.btn_check_upd.clicked.connect(self._gui_check_updates)
        btn_upd_row.addWidget(self.btn_check_upd)

        self.btn_run_upd = QPushButton("🚀 Update All")
        self.btn_run_upd.setProperty("class", "primary-btn")
        self.btn_run_upd.setFixedHeight(36)
        self.btn_run_upd.clicked.connect(self._gui_update_all)
        btn_upd_row.addWidget(self.btn_run_upd)

        self.btn_win_upd = QPushButton("🪟 Windows Update")
        self.btn_win_upd.setFixedHeight(36)
        self.btn_win_upd.clicked.connect(self._gui_windows_update)
        btn_upd_row.addWidget(self.btn_win_upd)

        btn_upd_row.addStretch()
        form_upd.addLayout(btn_upd_row)

        # Output / History Label
        self.lbl_upd_detail = QLabel("Providers: WinGet, Windows Update, Microsoft Store")
        self.lbl_upd_detail.setWordWrap(True)
        self.lbl_upd_detail.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form_upd.addWidget(self.lbl_upd_detail)

        main_layout.addWidget(card_upd)

        # =====================================================================
        # 5. LAYA SYSTEM-1 DECISION ENGINE CARD
        # =====================================================================
        laya_hdr = QLabel("LAYA SYSTEM-1 DECISION ENGINE")
        laya_hdr.setStyleSheet("font-size: 15px; font-weight: 800; color: #f8fafc; letter-spacing: 1.5px; margin-top: 10px;")
        main_layout.addWidget(laya_hdr)

        card_laya = QFrame()
        card_laya.setProperty("class", "card")
        form_laya = QVBoxLayout(card_laya)
        form_laya.setContentsMargins(24, 22, 24, 22)
        form_laya.setSpacing(12)

        laya_info = QLabel("HF Laya optional enhancement hai (dependency nahi): download se pehle rule-based mode 100% functional; download ke baad Rule + Laya Assist automatic on — better ambiguity resolution. Advisory only, kabhi auto-execute nahi.")
        laya_info.setWordWrap(True)
        laya_info.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form_laya.addWidget(laya_info)

        self.lbl_laya_status = QLabel("Status: Checking Laya...")
        self.lbl_laya_status.setStyleSheet("color: #cbd5e1; font-size: 13px; font-weight: 600;")
        form_laya.addWidget(self.lbl_laya_status)

        laya_row = QHBoxLayout()
        laya_row.setSpacing(12)

        self.combo_laya_checkpoint = QComboBox()
        self.combo_laya_checkpoint.setFixedHeight(36)
        self.combo_laya_checkpoint.addItems(["multilingual (Hinglish/Hindi - Recommended)", "english (English/Guardrails)", "typed-decisions (Workflows)"])
        laya_row.addWidget(self.combo_laya_checkpoint, stretch=1)

        self.btn_laya_download = QPushButton("⬇ Download Laya")
        self.btn_laya_download.setProperty("class", "primary-btn")
        self.btn_laya_download.setFixedHeight(36)
        self.btn_laya_download.clicked.connect(self._gui_laya_download)
        laya_row.addWidget(self.btn_laya_download)

        self.btn_laya_test = QPushButton("🧪 Test")
        self.btn_laya_test.setFixedHeight(36)
        self.btn_laya_test.clicked.connect(self._gui_laya_test)
        laya_row.addWidget(self.btn_laya_test)

        form_laya.addLayout(laya_row)

        laya_opt_row = QHBoxLayout()
        laya_opt_row.setSpacing(16)
        self.chk_laya_enable = QCheckBox("Enable Laya advisory engine")
        self.chk_laya_enable.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.chk_laya_enable.setChecked(True)
        laya_opt_row.addWidget(self.chk_laya_enable)

        self.chk_laya_routing = QCheckBox("Use for intent routing (advisory, auto-on after download)")
        self.chk_laya_routing.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.chk_laya_routing.setChecked(True)
        self.chk_laya_routing.setToolTip("Download ke baad automatic on: low-confidence turns par Rule + Laya Assist. HF optional hai — rules 100% functional rehte hain.")
        laya_opt_row.addWidget(self.chk_laya_routing)

        self.chk_laya_guard = QCheckBox("Use for guardrails (advisory, auto-on after download)")
        self.chk_laya_guard.setStyleSheet("color: #cbd5e1; font-size: 12px;")
        self.chk_laya_guard.setChecked(True)
        laya_opt_row.addWidget(self.chk_laya_guard)
        laya_opt_row.addStretch()
        form_laya.addLayout(laya_opt_row)

        self.lbl_laya_detail = QLabel("Repo: convaiinnovations/laya | pip: laya | Weights: data/models/laya")
        self.lbl_laya_detail.setWordWrap(True)
        self.lbl_laya_detail.setStyleSheet("color: #94a3b8; font-size: 11px;")
        form_laya.addWidget(self.lbl_laya_detail)

        btn_laya_save_row = QHBoxLayout()
        save_laya_btn = QPushButton("💾 Save Laya Settings")
        save_laya_btn.setProperty("class", "primary-btn")
        save_laya_btn.setFixedHeight(38)
        save_laya_btn.setMinimumWidth(200)
        save_laya_btn.clicked.connect(self._save_laya_settings)
        btn_laya_save_row.addWidget(save_laya_btn)
        btn_laya_save_row.addStretch()
        form_laya.addLayout(btn_laya_save_row)

        main_layout.addWidget(card_laya)
        main_layout.addStretch()

        scroll.setWidget(container)
        root_layout.addWidget(scroll)

        # Initialize microphone device list
        self._populate_microphones(force_refresh=False)
        try:
            self._refresh_laya_ui()
        except Exception:
            pass

    def _open_face_registration(self):
        """Opens the interactive Face Registration Dialog."""
        from gui.dialogs.face_register_dialog import FaceRegisterDialog
        dialog = FaceRegisterDialog(authenticator=self.authenticator, parent=self)
        dialog.enrolled.connect(self._on_face_enrolled)
        dialog.exec()

    def _on_face_enrolled(self, success: bool, user_name: str):
        if success:
            self.lbl_profile_status.setText(f"✓ Registered ({user_name})")
            self.lbl_profile_status.setStyleSheet("""
                QLabel {
                    color: #10b981;
                    font-weight: bold;
                    font-size: 13px;
                    background-color: rgba(15, 23, 42, 0.6);
                    border: 1px solid #10b981;
                    border-radius: 8px;
                    padding: 0 14px;
                }
            """)
            self.sec_status.setText(f"Face biometric profile updated for {user_name}!")
            self.sec_status.setStyleSheet("color: #10b981; font-size: 11px;")

    def _save_security_settings(self):
        enabled = self.combo_face_auth.currentIndex() == 0
        pin = self.input_pin.text().strip() or "1234"

        if self.core:
            sec_cfg = self.core.config.setdefault("security", {}).setdefault("face_auth", {})
            sec_cfg["enabled"] = enabled
            sec_cfg["master_pin"] = pin
            try:
                with open(self.core.config_path, "w", encoding="utf-8") as config_file:
                    yaml.safe_dump(self.core.config, config_file, sort_keys=False, allow_unicode=True)
                self.sec_status.setText("✓ Security & Face Lock settings saved successfully.")
                self.sec_status.setStyleSheet("color: #10b981; font-size: 11px;")
            except Exception as exc:
                self.sec_status.setText(f"Could not save security settings: {exc}")
                self.sec_status.setStyleSheet("color: #ef4444; font-size: 11px;")

    def _setup_live_audio_listener(self) -> None:
        """Connects live hardware hotplug notifications to GUI slots thread-safely."""
        try:
            self.topology_updated.connect(self._on_topology_changed_slot)
            from voice.device_manager import AudioDeviceManager
            self._adm = AudioDeviceManager()
            self._adm_listener = lambda summary: self.topology_updated.emit(summary)
            self._adm.register_topology_change_listener(self._adm_listener, notify_immediate=True)
        except Exception as e:
            logger.debug(f"Audio topology listener setup note: {e}")

    def _on_topology_changed_slot(self, summary: dict) -> None:
        """Cross-thread safe slot triggered when Bluetooth earbuds connect or disconnect."""
        if not summary:
            return
        is_eb = bool(summary.get("earbuds_connected", False)) or bool(summary.get("is_input_bluetooth", False)) or bool(summary.get("is_output_bluetooth", False)) or bool(summary.get("earbuds_paired", False))
        eb_name = summary.get("earbuds_name") or summary.get("active_input_name") or summary.get("active_device_name")
        active_in = summary.get("active_device_name") or summary.get("active_input_name") or "Default Microphone"
        active_out = summary.get("active_output_name") or "Default Speakers"

        if is_eb and eb_name:
            self.lbl_bt_badge.setText(f"● Connected: {eb_name}")
            self.lbl_bt_badge.setStyleSheet("""
                color: #38bdf8;
                font-weight: 700;
                font-size: 11px;
                background-color: rgba(56, 189, 248, 0.15);
                border: 1px solid rgba(56, 189, 248, 0.35);
                border-radius: 6px;
                padding: 3px 8px;
            """)
            self.lbl_bt_device.setText(f"🎧 Active Headset: {eb_name} (Microphone & Audio Output Connected)")
            self.lbl_bt_details.setText(f"Live Route: Mic -> {active_in} | Audio -> {active_out}")
        else:
            self.lbl_bt_badge.setText("○ Bluetooth: Standby")
            self.lbl_bt_badge.setStyleSheet("""
                color: #94a3b8;
                font-weight: 600;
                font-size: 11px;
                background-color: rgba(148, 163, 184, 0.12);
                border: 1px solid rgba(148, 163, 184, 0.25);
                border-radius: 6px;
                padding: 3px 8px;
            """)
            self.lbl_bt_device.setText(f"💻 System Audio Active ({active_in})")
            self.lbl_bt_details.setText(f"Waiting for Bluetooth Earbuds to connect. Route: {active_in} / {active_out}")

        # If on Auto-Detect, refresh dropdown options dynamically
        if hasattr(self, "combo_mic"):
            curr_data = self.combo_mic.currentData()
            if curr_data == "auto" or curr_data is None:
                self._populate_microphones(force_refresh=False)

    def _populate_microphones(self, force_refresh: bool = False) -> None:
        """Populates the microphone combo box with Auto-Detect and unique hardware devices."""
        self.combo_mic.blockSignals(True)
        self.combo_mic.clear()

        # Item 0: Auto-Detect
        self.combo_mic.addItem("⚡ Auto-Detect (Bluetooth Earbuds > USB Mic > Default)", "auto")

        preferred = "auto"
        if self.core and hasattr(self.core, "config"):
            preferred = self.core.config.get("voice", {}).get("preferred_microphone", "auto")

        try:
            from voice.device_manager import AudioDeviceManager
            adm = AudioDeviceManager()
            devices = adm.get_unique_input_devices(force_refresh=force_refresh)

            selected_idx = 0
            for idx, dev in enumerate(devices, start=1):
                if dev.is_bluetooth:
                    badge = "🎧 [Bluetooth]"
                elif dev.is_usb:
                    badge = "🎙️ [USB]"
                elif dev.is_default:
                    badge = "⭐ [Default]"
                else:
                    badge = "💻 [Internal/Analog]"

                label = f"{badge} {dev.clean_name} ({dev.hostapi_name})"
                data_val = dev.clean_name
                self.combo_mic.addItem(label, data_val)

                if preferred and str(preferred).lower().strip() != "auto":
                    pref_str = str(preferred).lower().strip()
                    if (pref_str == dev.clean_name.lower() or
                        pref_str in dev.clean_name.lower() or
                        (pref_str.isdigit() and int(pref_str) == dev.index)):
                        selected_idx = idx

            self.combo_mic.setCurrentIndex(selected_idx)
        except Exception as e:
            logging.getLogger("jarvis.gui.settings").warning(f"Error enumerating audio devices: {e}")
        finally:
            self.combo_mic.blockSignals(False)

    def _refresh_microphones(self) -> None:
        """Scans for newly connected microphones or Bluetooth earbuds and updates the dropdown."""
        self.mic_status.setText("Scanning audio devices...")
        self.mic_status.setStyleSheet("color: #38bdf8; font-size: 11px;")
        self._populate_microphones(force_refresh=True)
        self.mic_status.setText("✓ Audio devices refreshed.")
        self.mic_status.setStyleSheet("color: #10b981; font-size: 11px;")

    def _test_microphone(self) -> None:
        """Runs a 1.2s audio capture test on the selected microphone via a background worker thread."""
        self.btn_test_mic.setEnabled(False)
        self.btn_test_mic.setText("⏳ Listening...")
        self.mic_status.setText("Listening for 1.2s to test signal strength... (Please speak)")
        self.mic_status.setStyleSheet("color: #38bdf8; font-size: 11px;")

        selected_data = self.combo_mic.currentData()
        target_index = None

        if selected_data and str(selected_data).lower().strip() != "auto":
            try:
                from voice.device_manager import AudioDeviceManager
                adm = AudioDeviceManager()
                devices = adm.list_input_devices()
                data_str = str(selected_data).lower().strip()
                for dev in devices:
                    if (data_str == dev.clean_name.lower() or
                        data_str in dev.clean_name.lower() or
                        (data_str.isdigit() and int(data_str) == dev.index)):
                        target_index = dev.index
                        break
            except Exception:
                target_index = None

        self._mic_worker = MicTestWorker(device_index=target_index, duration=1.2, parent=self)
        self._mic_worker.test_finished.connect(self._on_mic_test_done)
        self._mic_worker.start()

    def _on_mic_test_done(self, result: dict) -> None:
        """Handles completion of the audio capture diagnostic."""
        self.btn_test_mic.setEnabled(True)
        self.btn_test_mic.setText("🎤 Test Mic")

        if result.get("success"):
            peak = result.get("peak", 0.0)
            rms = result.get("rms", 0.0)
            dev_name = result.get("device_name", "Microphone")
            if peak < 0.005:
                self.mic_status.setText(f"⚠️ {dev_name}: Very faint signal (Peak: {peak:.2f}, RMS: {rms:.4f}). Check mic mute switch/level.")
                self.mic_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
            else:
                self.mic_status.setText(f"✓ {dev_name}: Signal strong (Peak: {peak:.2f}, RMS: {rms:.4f}). Hardware active.")
                self.mic_status.setStyleSheet("color: #10b981; font-size: 11px;")
        else:
            self.mic_status.setText(f"❌ Mic test error: {result.get('message', 'Unknown error')}")
            self.mic_status.setStyleSheet("color: #ef4444; font-size: 11px;")

    def _on_mic_changed(self, index: int) -> None:
        """Provides immediate user feedback when changing microphone dropdown selection."""
        if index == 0:
            self.mic_status.setText("Auto-detect: Bluetooth Earbuds & USB mics prioritized automatically when connected.")
        else:
            self.mic_status.setText("Click 'Save Preferences' to persist, or 'Test Mic' to verify signal.")
        self.mic_status.setStyleSheet("color: #94a3b8; font-size: 11px;")

    def _save_settings(self):
        if not self.core:
            return

        lang = self.combo_lang.currentText().lower()
        tone = self.combo_tone.currentText().lower().split()[0]
        title = self.input_user.text().strip() or "Boss"

        if self.core.learning_manager:
            self.core.learning_manager.preferences.set("language_style", lang)
            self.core.learning_manager.preferences.set("conciseness", tone)
            self.core.learning_manager.preferences.set("user_title", title)

        voice_name = self.VOICES[self.combo_voice.currentText()]
        self._apply_voice(voice_name)
        self.core.config.setdefault("voice", {})["voice_name"] = voice_name

        # Microphone preference & Bluetooth auto-switch settings
        selected_mic = self.combo_mic.currentData() or "auto"
        auto_sw = self.chk_auto_switch.isChecked() if hasattr(self, "chk_auto_switch") else True
        ann_bt = self.chk_announce_bt.isChecked() if hasattr(self, "chk_announce_bt") else True

        self.core.config.setdefault("voice", {})["preferred_microphone"] = selected_mic
        self.core.config.setdefault("voice", {})["auto_switch_headset"] = auto_sw
        self.core.config.setdefault("voice", {})["announce_device_changes"] = ann_bt

        try:
            from voice.device_manager import AudioDeviceManager
            adm = AudioDeviceManager()
            adm.auto_switch_headset = auto_sw
            adm.announce_device_changes = ann_bt
            adm.set_manual_device(selected_mic)
        except Exception as adm_err:
            logging.getLogger("jarvis.gui.settings").warning(f"Could not apply audio settings: {adm_err}")

        try:
            with open(self.core.config_path, "w", encoding="utf-8") as config_file:
                yaml.safe_dump(self.core.config, config_file, sort_keys=False, allow_unicode=True)
            self.voice_status.setText("✓ Preferences saved and applied.")
            self.voice_status.setStyleSheet("color: #10b981; font-size: 11px;")
            if selected_mic == "auto":
                self.mic_status.setText("✓ Active mic: Auto-Detect (Bluetooth Earbuds > USB > Default).")
            else:
                self.mic_status.setText(f"✓ Active mic locked to: {selected_mic}")
            self.mic_status.setStyleSheet("color: #10b981; font-size: 11px;")
        except Exception as exc:
            logging.getLogger("jarvis.gui.settings").error("Could not save settings: %s", exc)
            self.voice_status.setText("Could not save preferences.")
            self.voice_status.setStyleSheet("color: #ef4444; font-size: 11px;")

    def _reset_jarvis_anchor_position(self) -> None:
        """Restores default top-center floating anchor position across application."""
        try:
            from gui.island.position_manager import AnchorPositionManager
            from PySide6.QtGui import QGuiApplication
            from PySide6.QtWidgets import QApplication
            pos_mgr = AnchorPositionManager()
            screen = self.screen() or QGuiApplication.primaryScreen()
            if screen:
                screen_geo = screen.availableGeometry()
                pos = pos_mgr.default_position(screen_geo, 64)
                pos_mgr.save_position(pos, screen_geo, 64)
            app = QApplication.instance()
            if app:
                for widget in app.topLevelWidgets():
                    if hasattr(widget, "reset_anchor_position"):
                        widget.reset_anchor_position()
                        break
            self.voice_status.setText("✓ JARVIS floating anchor position reset to default top-center.")
            self.voice_status.setStyleSheet("color: #10b981; font-size: 11px;")
        except Exception as e:
            logger.warning(f"Failed to reset JARVIS anchor position: {e}")

    def _apply_voice(self, voice_name: str) -> None:
        if self.tts_engine:
            target = getattr(self.tts_engine, "tts", self.tts_engine)
            target.set_prosody(voice_name=voice_name)

    def _preview_voice(self) -> None:
        voice_name = self.VOICES[self.combo_voice.currentText()]
        self._apply_voice(voice_name)
        self.voice_status.setText("Playing voice preview...")
        if self.tts_engine:
            preview_text = "Hello Boss! Main Jarvis hoon. Bataiye, aaj main aapki kya help kar sakti hoon?"
            try:
                self.tts_engine.speak(preview_text, priority=True)
            except TypeError:
                self.tts_engine.speak(preview_text)
        self.voice_status.setText("Preview queued. Click Save Preferences to keep this voice.")

    def _save_proactive_settings(self):
        if not self.core:
            return
        enabled = self.combo_pro_enable.currentIndex() == 0
        conf_map = {"70% (Responsive)": 0.70, "80% (Balanced - Default)": 0.80, "90% (Strict)": 0.90}
        conf = conf_map.get(self.combo_conf.currentText(), 0.80)
        guard = self.combo_guard.currentIndex() == 0

        pro_cfg = self.core.config.setdefault("proactive_intelligence", {})
        pro_cfg["enabled"] = enabled
        pro_cfg.setdefault("intelligence", {})["suggestion_confidence_threshold"] = conf
        pro_cfg["enable_distraction_guard"] = guard
        try:
            with open(self.core.config_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.core.config, f, sort_keys=False, allow_unicode=True)
            self.pro_status.setText("✓ Proactive Intelligence settings saved successfully.")
            self.pro_status.setStyleSheet("color: #10b981; font-size: 11px;")
        except Exception as exc:
            self.pro_status.setText(f"Could not save proactive settings: {exc}")
            self.pro_status.setStyleSheet("color: #ef4444; font-size: 11px;")

    def refresh_settings(self):
        """Reloads settings from core.config and preferences."""
        if not self.core:
            return
        if self.core.learning_manager:
            user_title = self.core.learning_manager.preferences.get("user_title", "Boss")
            self.input_user.setText(str(user_title))
        pro_cfg = self.core.config.get("proactive_intelligence", {})
        is_enabled = pro_cfg.get("enabled", True)
        self.combo_pro_enable.setCurrentIndex(0 if is_enabled else 1)
        self._populate_microphones(force_refresh=False)
        self._refresh_update_ui()

    def _set_update_buttons_enabled(self, enabled: bool) -> None:
        self.btn_check_upd.setEnabled(enabled)
        self.btn_run_upd.setEnabled(enabled)
        self.btn_win_upd.setEnabled(enabled)

    def _gui_check_updates(self):
        """Discovers updates asynchronously without blocking the UI thread."""
        if self._update_worker and self._update_worker.isRunning():
            return
        self._set_update_buttons_enabled(False)
        self.lbl_upd_summary.setText("⏳ Checking for updates...")
        self.lbl_upd_detail.setText("Scanning WinGet and Windows Update in background...")
        self._update_worker = SoftwareUpdateWorker(action="check_all", parent=self)
        self._update_worker.status_updated.connect(self._on_update_status)
        self._update_worker.check_finished.connect(self._on_check_updates_done)
        self._update_worker.error_occurred.connect(self._on_update_error)
        self._update_worker.start()

    def _gui_update_all(self):
        """Executes all available updates asynchronously without blocking the UI thread."""
        if self._update_worker and self._update_worker.isRunning():
            return
        self._set_update_buttons_enabled(False)
        self.lbl_upd_summary.setText("⏳ Installing updates...")
        self.lbl_upd_detail.setText("Applying package upgrades in background. Please wait...")
        self._update_worker = SoftwareUpdateWorker(action="update_all", parent=self)
        self._update_worker.status_updated.connect(self._on_update_status)
        self._update_worker.update_finished.connect(self._on_update_all_done)
        self._update_worker.error_occurred.connect(self._on_update_error)
        self._update_worker.start()

    def _gui_windows_update(self):
        """Opens native Windows Update Settings and queries updates asynchronously."""
        # Non-blocking OS launch of native Windows Update settings for instant feedback
        try:
            import platform
            if platform.system() == "Windows":
                os.startfile("ms-settings:windowsupdate")
        except Exception as exc:
            logger.debug("Could not launch ms-settings:windowsupdate: %s", exc)

        if self._update_worker and self._update_worker.isRunning():
            return
        self._set_update_buttons_enabled(False)
        self.lbl_upd_summary.setText("⏳ Checking Windows updates...")
        self.lbl_upd_detail.setText("Opening Windows Settings and querying pending patches in background...")
        self._update_worker = SoftwareUpdateWorker(action="check_windows", parent=self)
        self._update_worker.status_updated.connect(self._on_update_status)
        self._update_worker.check_finished.connect(self._on_windows_check_done)
        self._update_worker.error_occurred.connect(self._on_update_error)
        self._update_worker.start()

    def _on_update_status(self, summary: str, detail: str) -> None:
        self.lbl_upd_summary.setText(summary)
        self.lbl_upd_detail.setText(detail)

    def _on_check_updates_done(self, plan, msg: str) -> None:
        self._set_update_buttons_enabled(True)
        if plan:
            self.lbl_upd_summary.setText(f"Available: {plan.total_available} updates ({len(plan.winget_updates)} apps, {len(plan.windows_updates)} OS)")
            self.lbl_upd_detail.setText(msg)
            self.reboot_banner.setVisible(bool(plan.reboot_required))
        else:
            self.lbl_upd_summary.setText("Update check completed")
            self.lbl_upd_detail.setText(msg)

    def _on_windows_check_done(self, plan, msg: str) -> None:
        self._set_update_buttons_enabled(True)
        if plan:
            self.lbl_upd_summary.setText(f"Windows updates: {len(plan.windows_updates)} available")
            self.lbl_upd_detail.setText(msg)
            self.reboot_banner.setVisible(bool(plan.reboot_required))
        else:
            self.lbl_upd_summary.setText("Windows update check completed")
            self.lbl_upd_detail.setText(msg)

    def _on_update_all_done(self, success: bool, msg: str, st_dict: dict) -> None:
        self._set_update_buttons_enabled(True)
        st = "Completed" if success else "Failed"
        self.lbl_upd_summary.setText(f"Status: {st}")
        self.lbl_upd_detail.setText(msg)
        self.reboot_banner.setVisible(bool(st_dict.get("reboot_pending", False)))

    def _on_update_error(self, err: str) -> None:
        self._set_update_buttons_enabled(True)
        self.lbl_upd_summary.setText("Operation failed")
        self.lbl_upd_detail.setText(err)

    def _refresh_update_ui(self):
        """Refreshes status and reboot pending banner."""
        try:
            from core.software_update.manager import SoftwareUpdateManager
            mgr = SoftwareUpdateManager.get_instance()
            st = mgr.get_status()
            self.reboot_banner.setVisible(bool(st.get("reboot_pending", False)))
        except Exception:
            pass
        self._refresh_laya_ui()

    # =====================================================================
    # LAYA SYSTEM-1 ENGINE UI
    # =====================================================================
    def _laya_selected_checkpoint(self) -> str:
        txt = self.combo_laya_checkpoint.currentText() if hasattr(self, "combo_laya_checkpoint") else "multilingual"
        low = txt.lower()
        if "english" in low:
            return "english"
        if "typed" in low:
            return "typed-decisions"
        return "multilingual"

    def _set_laya_buttons_enabled(self, enabled: bool) -> None:
        try:
            self.btn_laya_download.setEnabled(enabled)
            self.btn_laya_test.setEnabled(enabled)
        except Exception:
            pass

    def _gui_laya_download(self):
        if self._laya_worker and self._laya_worker.isRunning():
            return
        cp = self._laya_selected_checkpoint()
        self._set_laya_buttons_enabled(False)
        self.lbl_laya_status.setText(f"⏳ Laya '{cp}' download ho raha hai...")
        self.lbl_laya_detail.setText("pip package + weights background me download ho rahe hain. Jarvis responsive rahega.")
        self._laya_worker = LayaDownloadWorker(checkpoint=cp, parent=self)
        self._laya_worker.progress_updated.connect(self._on_laya_progress)
        self._laya_worker.download_finished.connect(self._on_laya_done)
        self._laya_worker.error_occurred.connect(self._on_laya_error)
        self._laya_worker.start()

    def _on_laya_progress(self, stage: str, detail: str) -> None:
        self.lbl_laya_status.setText(f"⏳ [{stage}] {detail}"[:220])
        self.lbl_laya_detail.setText(detail[:500])

    def _on_laya_done(self, success: bool, msg: str, st_dict: dict) -> None:
        self._set_laya_buttons_enabled(True)
        # Download success => Rule + Laya Assist auto-on: reflect in checkboxes.
        if success:
            try:
                if hasattr(self, "chk_laya_routing"):
                    self.chk_laya_routing.setChecked(True)
                if hasattr(self, "chk_laya_guard"):
                    self.chk_laya_guard.setChecked(True)
            except Exception:
                pass
        self.lbl_laya_status.setText(f"{'✓' if success else '❌'} {msg}"[:220])
        self.lbl_laya_status.setStyleSheet(
            "color: #10b981; font-size: 13px; font-weight: 600;" if success
            else "color: #ef4444; font-size: 13px; font-weight: 600;"
        )
        try:
            ready = st_dict.get("ready", success)
            cp = st_dict.get("checkpoint", self._laya_selected_checkpoint())
            self.lbl_laya_detail.setText(f"Checkpoint: {cp} | Ready: {ready} | {msg}"[:500])
        except Exception:
            self.lbl_laya_detail.setText(msg[:500])

    def _on_laya_error(self, err: str) -> None:
        self._set_laya_buttons_enabled(True)
        self.lbl_laya_status.setText("❌ Laya download failed")
        self.lbl_laya_status.setStyleSheet("color: #ef4444; font-size: 13px; font-weight: 600;")
        self.lbl_laya_detail.setText(err[:500])

    def _gui_laya_test(self):
        try:
            from core.laya import get_laya_manager
            mgr = get_laya_manager()
            st = mgr.get_status()
            if not st.get("ready"):
                self.lbl_laya_status.setText("⚠ " + mgr.status_message())
                self.lbl_laya_detail.setText("Pehle Download kijiye, phir Test.")
                return
            res = mgr.predict(
                {"text": "chrome kholo"},
                {"intent": {"type": "choice", "instructions": "Which intent matches?", "criteria": {"open_app": "open/launch/kholo app", "other": "everything else"}}},
            )
            if res is None:
                self.lbl_laya_status.setText("○ Rule-based mode (100% functional) — Laya inference unavailable, HF optional hai.")
                self.lbl_laya_detail.setText(f"Mode: RULE_ONLY | Checkpoint: {st.get('checkpoint')} | Loaded: {st.get('loaded')}")
            else:
                self.lbl_laya_status.setText("✓ Laya test success — advisory decision mil gaya.")
                self.lbl_laya_detail.setText(str(res)[:500])
        except Exception as exc:
            self.lbl_laya_detail.setText(f"Test note: {exc}"[:500])

    def _save_laya_settings(self):
        try:
            cp = self._laya_selected_checkpoint()
            enabled = self.chk_laya_enable.isChecked() if hasattr(self, "chk_laya_enable") else True
            routing = self.chk_laya_routing.isChecked() if hasattr(self, "chk_laya_routing") else True
            guard = self.chk_laya_guard.isChecked() if hasattr(self, "chk_laya_guard") else True
            from core.laya import get_laya_manager
            mgr = get_laya_manager()
            mgr.config["checkpoint"] = cp
            mgr.config["enabled"] = enabled
            mgr.config["use_for_intent_routing"] = routing
            mgr.config["use_for_guardrails"] = guard
            if self.core:
                laya_cfg = self.core.config.setdefault("laya", {})
                laya_cfg.update(mgr.config)
                with open(self.core.config_path, "w", encoding="utf-8") as f:
                    yaml.safe_dump(self.core.config, f, sort_keys=False, allow_unicode=True)
            self.lbl_laya_detail.setText(f"✓ Saved: checkpoint={cp}, enabled={enabled}, routing={routing}, guardrails={guard}")
            self._refresh_laya_ui()
        except Exception as exc:
            try:
                self.lbl_laya_detail.setText(f"Save note: {exc}"[:500])
            except Exception:
                pass

    def _refresh_laya_ui(self):
        try:
            from core.laya import get_laya_manager
            mgr = get_laya_manager(config=(self.core.config.get("laya", {}) if self.core else None))
            st = mgr.get_status()
            cp = st.get("checkpoint", "multilingual")
            if hasattr(self, "combo_laya_checkpoint"):
                for i in range(self.combo_laya_checkpoint.count()):
                    if cp in self.combo_laya_checkpoint.itemText(i).lower():
                        self.combo_laya_checkpoint.setCurrentIndex(i)
                        break
            if hasattr(self, "chk_laya_enable"):
                self.chk_laya_enable.setChecked(bool(st.get("enabled", True)))
            if hasattr(self, "chk_laya_routing"):
                self.chk_laya_routing.setChecked(bool(st.get("use_for_intent_routing", True)))
            if hasattr(self, "chk_laya_guard"):
                self.chk_laya_guard.setChecked(bool(st.get("use_for_guardrails", True)))
            if hasattr(self, "lbl_laya_status"):
                mode = st.get("mode", "RULE_ONLY")
                if st.get("busy"):
                    self.lbl_laya_status.setText("⏳ Laya download in progress... (tab tak rule-based mode, 100% functional)")
                elif st.get("ready"):
                    self.lbl_laya_status.setText(f"✓ Rule + Laya Assist active [{mode}] '{cp}' ({st.get('checkpoint_desc','')})")
                elif not st.get("pip_installed"):
                    self.lbl_laya_status.setText("○ Rule-based mode (100% functional) — Download se Rule + Laya Assist auto-on.")
                else:
                    self.lbl_laya_status.setText(f"○ Rule-based mode (100% functional) — '{cp}' download par assist auto-on.")
        except Exception as exc:
            logger.debug("Laya UI refresh note: %s", exc)


