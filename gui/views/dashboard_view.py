# gui/views/dashboard_view.py
"""Dashboard View: Real-time telemetry, resource metrics and active status."""

import psutil
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QVBoxLayout, QWidget
)



class MetricCard(QFrame):
    """Reusable visual glassmorphic telemetry card."""

    def __init__(self, title: str, initial_value: str = "--", subtitle: str = ""):
        super().__init__()
        self.setProperty("class", "card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(18, 14, 18, 14)
        self.layout.setSpacing(4)

        self.title_lbl = QLabel(title)
        self.title_lbl.setProperty("class", "card-title")

        self.value_lbl = QLabel(initial_value)
        self.value_lbl.setProperty("class", "card-value")
        self.value_lbl.setMinimumHeight(28)

        self.sub_lbl = QLabel(subtitle)
        self.sub_lbl.setProperty("class", "card-sub")

        self.layout.addWidget(self.title_lbl)
        self.layout.addWidget(self.value_lbl)
        self.layout.addWidget(self.sub_lbl)

    def update_data(self, value: str, subtitle: str = ""):
        self.value_lbl.setText(value)
        if subtitle:
            self.sub_lbl.setText(subtitle)


class DashboardView(QWidget):
    """Main Telemetry Dashboard for CPU, RAM, Mic, Speaker, LLM, Plugin, and Task."""

    def __init__(self, jarvis_core=None):
        super().__init__()
        self.core = jarvis_core
        self._refresh_count = 0
        self._init_ui()
        self._init_timer()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # Title
        hdr_layout = QHBoxLayout()
        title = QLabel("SYSTEM DASHBOARD")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #f8fafc; letter-spacing: 1px;")
        hdr_layout.addWidget(title)
        hdr_layout.addStretch()
        main_layout.addLayout(hdr_layout)

        # Grid of Cards
        grid = QGridLayout()
        grid.setSpacing(16)

        self.card_cpu = MetricCard("CPU USAGE", "0%", "Multi-core processor")
        self.card_ram = MetricCard("RAM USAGE", "0.0 / 0.0 GB", "Physical memory")
        self.card_battery = MetricCard("BATTERY", "--", "Checking power status")
        self.card_mic = MetricCard("MICROPHONE", "● READY", "Default input stream")
        self.card_speaker = MetricCard("SPEAKER", "● READY", "Default audio output")
        self.card_llm = MetricCard("LLM ENGINE", "Mock (Offline)", "Reasoning Provider")
        self.card_plugin = MetricCard("ACTIVE PLUGINS", "0 / 0 Enabled", "0 implementations loaded")
        self.card_task = MetricCard("CURRENT TASK", "IDLE", "No active plan")
        self.card_state = MetricCard("SYSTEM STATE", "ONLINE", "Nominal operation")
        self.card_active_app = MetricCard("ACTIVE APPLICATION", "DESKTOP", "Target context")
        self.card_proactive = MetricCard("PROACTIVE AI", "STANDBY", "Habit learner & observer")
        self.card_memory_store = MetricCard("COGNITIVE MEMORY", "0 Facts", "Long-term knowledge")

        grid.addWidget(self.card_cpu, 0, 0)
        grid.addWidget(self.card_ram, 0, 1)
        grid.addWidget(self.card_battery, 0, 2)

        grid.addWidget(self.card_mic, 1, 0)
        grid.addWidget(self.card_speaker, 1, 1)
        grid.addWidget(self.card_llm, 1, 2)

        grid.addWidget(self.card_plugin, 2, 0)
        grid.addWidget(self.card_task, 2, 1)
        grid.addWidget(self.card_state, 2, 2)

        grid.addWidget(self.card_active_app, 3, 0)
        grid.addWidget(self.card_proactive, 3, 1)
        grid.addWidget(self.card_memory_store, 3, 2)

        main_layout.addLayout(grid)
        main_layout.addStretch()

    def _init_timer(self):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_metrics)
        self.timer.start(1000)
        self.refresh_metrics()

    def refresh_metrics(self):
        """Fetches live CPU, RAM, and core state."""
        cpu = psutil.cpu_percent()
        mem = psutil.virtual_memory()
        used_gb = round(mem.used / (1024 ** 3), 1)
        total_gb = round(mem.total / (1024 ** 3), 1)

        self.card_cpu.update_data(f"{cpu}%", f"Current load")
        self.card_ram.update_data(f"{used_gb} / {total_gb} GB", f"{mem.percent}% utilized")
        self._refresh_count += 1
        if self._refresh_count == 1 or self._refresh_count % 10 == 0:
            self._refresh_audio_devices()

        battery = psutil.sensors_battery()
        if battery is None:
            self.card_battery.update_data("N/A", "Battery not detected")
        else:
            percent = round(battery.percent)
            if battery.power_plugged:
                power_state = "Charging" if percent < 100 else "Fully charged"
            else:
                power_state = "On battery"
            self.card_battery.update_data(f"{percent}%", power_state)

        if self.core:
            # Update core state
            state_str = str(self.core.state_machine.current_state.value).upper()
            self.card_state.update_data(state_str, "Core state")

            # Update loaded plugins count
            if self.core.plugin_manager:
                catalog = self.core.plugin_manager.get_catalog()
                enabled_cnt = sum(1 for manifest in catalog.values() if manifest.enabled)
                loaded_cnt = len(self.core.plugin_manager.get_all_plugins())
                self.card_plugin.update_data(
                    f"{enabled_cnt} / {len(catalog)} Enabled",
                    f"{loaded_cnt} implementations loaded"
                )

            brain_cfg = self.core.config.get("brain", {})
            provider = str(brain_cfg.get("llm_provider", "mock")).lower()
            model = str(brain_cfg.get("model", "")).strip()
            if provider == "mock":
                self.card_llm.update_data("Mock (Offline)", "No external model")
            else:
                self.card_llm.update_data(model or provider.title(), f"{provider.title()} provider")

            # Update working memory active task
            if self.core.memory_manager and self.core.memory_manager.working.active_task_id:
                self.card_task.update_data("IN_PROGRESS", f"Task: {self.core.memory_manager.working.active_task_id[:8]}")
            else:
                self.card_task.update_data("IDLE", "Listening for input")

            # Update active application and target context
            active_app = "Desktop"
            active_title = "Nominal foreground"
            if hasattr(self.core, "active_context") and self.core.active_context:
                target_app = getattr(self.core.active_context, "application", "") or getattr(self.core.active_context, "website", "")
                target_title = getattr(self.core.active_context, "window", "") or getattr(self.core.active_context, "page_title", "")
                if target_app:
                    active_app = target_app.title()
                if target_title:
                    active_title = target_title[:28]
            elif hasattr(self.core, "proactive_coordinator") and self.core.proactive_coordinator:
                ev = getattr(self.core.proactive_coordinator.memory, "active_event", None)
                if ev:
                    active_app = (ev.application or "Desktop").title()
                    active_title = (ev.window_title or ev.website or "Active")[:28]
            self.card_active_app.update_data(active_app, active_title)

            # Update proactive intelligence status
            if hasattr(self.core, "proactive_coordinator") and self.core.proactive_coordinator and self.core.proactive_coordinator.is_running:
                p_engine = getattr(self.core.proactive_coordinator, "pattern_engine", None)
                if p_engine and hasattr(p_engine, "get_all_patterns"):
                    pats = p_engine.get_all_patterns()
                elif p_engine and hasattr(p_engine, "get_strong_patterns"):
                    pats = p_engine.get_strong_patterns(min_confidence=0.0)
                else:
                    pats = []
                self.card_proactive.update_data("● ACTIVE", f"{len(pats)} habits tracked")
            else:
                self.card_proactive.update_data("STANDBY", "Observer ready")

            # Update cognitive memory facts count
            if self.core.memory_manager and hasattr(self.core.memory_manager, "long_term"):
                facts = self.core.memory_manager.long_term.get_all_facts()
                self.card_memory_store.update_data(f"{len(facts)} Facts", "5 Cognitive tiers active")

    def _refresh_audio_devices(self):
        """Report real default input/output devices instead of fixed READY labels."""
        try:
            import sounddevice as sd
            defaults = sd.default.device
            input_index = defaults[0] if defaults else -1
            output_index = defaults[1] if defaults else -1
            devices = sd.query_devices()
            if input_index is not None and input_index >= 0:
                mic_name = str(devices[input_index].get("name", "Default input"))
                self.card_mic.update_data("● READY", mic_name)
            else:
                self.card_mic.update_data("NOT FOUND", "No default input device")
            if output_index is not None and output_index >= 0:
                speaker_name = str(devices[output_index].get("name", "Default output"))
                self.card_speaker.update_data("● READY", speaker_name)
            else:
                self.card_speaker.update_data("NOT FOUND", "No default output device")
        except Exception:
            self.card_mic.update_data("UNAVAILABLE", "Audio input could not be queried")
            self.card_speaker.update_data("UNAVAILABLE", "Audio output could not be queried")
