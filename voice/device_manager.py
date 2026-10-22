# voice/device_manager.py
"""
Audio Device Manager for Jarvis V2.
Intelligently discovers, prioritizes, and dynamically routes audio input & output to
connected Bluetooth Earbuds / Headsets (e.g. CMF Buds, AirPods, Galaxy Buds, boAt, Sony, etc.)
with event-driven Windows COM hotplug notifications, physical headset pairing recognition,
honest capability feedback, thread-safe state machine, and automatic graceful fallback.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import os
import re
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.voice.device_manager")

# Popular Bluetooth earbud brands and generic keywords
BLUETOOTH_KEYWORDS = [
    # Generic Bluetooth terms
    "bluetooth", "bthhf", "hands-free", "handsfree", "headset", "earbuds", "earbud",
    "earphones", "earphone", "wireless", "tws", "audio gateway", "bt audio",
    # Specific Earbuds & Audio Brands
    "cmf", "boat", "airpod", "airpods", "galaxy buds", "buds", "oneplus", "realme",
    "noise", "boult", "sony", "jbl", "sennheiser", "anker", "soundcore", "bose",
    "jabra", "pixel buds", "oppo", "vivo", "redmi", "zebronics", "portronics",
    "skullcandy", "marshall", "edifier", "mivi", "truke"
]

USB_STUDIO_KEYWORDS = [
    "usb", "yeti", "fifine", "hyperx", "rode", "shure", "elgato", "samson", "audiotechnica", "focusrite"
]

EXCLUDED_INPUT_KEYWORDS = [
    "stereo mix", "sound mapper", "mapper - output", "primary sound driver",
    "speakers", "line out", "virtual", "cable output", "pc speaker", "2nd output"
]

EXCLUDED_OUTPUT_KEYWORDS = [
    "sound mapper", "mapper - output", "primary sound driver",
    "steam streaming", "virtual", "cable input"
]


class DeviceRole(str, Enum):
    """Functional role classification for discovered audio endpoints."""
    INPUT = "input"
    OUTPUT = "output"
    HEADSET = "headset"
    EARBUD = "earbud"
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    BLUETOOTH = "bluetooth"
    USB = "usb"
    DEFAULT = "default"


class AudioConnectionState(str, Enum):
    """Lifecycle state machine for audio connection & routing."""
    STABLE = "stable"
    SWITCHING = "switching"
    ACTIVE_HEADSET = "active_headset"
    FALLING_BACK = "falling_back"
    RECOVERED = "recovered"


@dataclass
class AudioDeviceInfo:
    """Represents a discovered and classified audio device (input or output)."""
    index: int
    name: str
    clean_name: str
    is_bluetooth: bool
    is_earbuds: bool
    is_usb: bool
    is_default: bool
    score: int
    hostapi_name: str
    max_input_channels: int = 0
    default_samplerate: float = 16000.0
    max_output_channels: int = 0
    is_output: bool = False
    roles: List[DeviceRole] = field(default_factory=list)


@dataclass
class PhysicalAudioHeadset:
    """
    Unified physical headset entity binding disparate input and output audio endpoints
    (e.g., Headset mic and Headphones speaker belonging to the same physical hardware).
    """
    hardware_id: str
    base_name: str
    display_name: str
    input_device: Optional[AudioDeviceInfo] = None
    output_device: Optional[AudioDeviceInfo] = None
    is_connected: bool = True
    has_microphone: bool = True
    has_speaker: bool = True
    battery_level: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "hardware_id": self.hardware_id,
            "base_name": self.base_name,
            "display_name": self.display_name,
            "has_microphone": self.has_microphone,
            "has_speaker": self.has_speaker,
            "is_connected": self.is_connected,
            "input_index": self.input_device.index if self.input_device else None,
            "output_index": self.output_device.index if self.output_device else None,
            "battery_level": self.battery_level,
        }


def extract_base_headset_identity(raw_name: str) -> str:
    """
    Extracts the canonical base hardware name of a headset/earbuds across input and output.
    Normalizes 'Headset (CMF Buds 2)' and 'Headphones (CMF Buds 2)' to 'CMF Buds 2'.
    """
    if not raw_name:
        return "Unknown"
    name = raw_name.strip()

    # 1. Driver string e.g. ';(CMF Buds 2)'
    m_driver = re.search(r";\s*\((.*?)\)", name)
    if m_driver and m_driver.group(1).strip():
        name = m_driver.group(1).strip()
    else:
        # 2. Endpoint pattern e.g. 'Headset (XYZ)' or 'Headphones (XYZ)'
        m_endpoint = re.match(
            r"^(?:Headset|Headphones|Microphone|Speakers|Hands-Free)\s*\((.*?)\)$",
            name,
            re.IGNORECASE
        )
        if m_endpoint and m_endpoint.group(1).strip():
            candidate = m_endpoint.group(1).strip()
            if candidate.lower() not in ("bluetooth", "audio", "default"):
                name = candidate

    # 3. Strip common decorators and audio profiles
    decorators = [
        r"\bHands-Free AG Audio\b", r"\bHands-Free Audio\b", r"\bHands-Free\b",
        r"\bStereo\b", r"\bAudio Gateway\b", r"\bHeadset\b", r"\bHeadphones\b",
        r"\(Bluetooth\)", r"\bBluetooth\b", r"\bWireless\b"
    ]
    for dec in decorators:
        name = re.sub(dec, "", name, flags=re.IGNORECASE)

    name = " ".join(name.replace("\ufffd", "").split())
    name = re.sub(r"^[\s\-\(\)]+|[\s\-\(\)]+$", "", name).strip()
    return name or "Unknown"


# Optional Windows CoreAudio COM callback client
COM_NOTIFICATION_AVAILABLE = False
WindowsAudioNotificationClient = None

try:
    if os.name == "nt":
        import comtypes
        from pycaw.pycaw import AudioUtilities, IMMNotificationClient
        from comtypes import COMObject

        class WindowsAudioNotificationClient(COMObject):
            _com_interfaces_ = [IMMNotificationClient]

            def __init__(self, callback: Callable[[str, Any], None]):
                super().__init__()
                self._callback = callback

            def OnDeviceStateChanged(self, pwstrDeviceId, dwNewState):
                self._callback("state_changed", (pwstrDeviceId, dwNewState))

            def OnDeviceAdded(self, pwstrDeviceId):
                self._callback("device_added", pwstrDeviceId)

            def OnDeviceRemoved(self, pwstrDeviceId):
                self._callback("device_removed", pwstrDeviceId)

            def OnDefaultDeviceChanged(self, flow, role, pwstrDeviceId):
                self._callback("default_changed", (flow, role, pwstrDeviceId))

            def OnPropertyValueChanged(self, pwstrDeviceId, key):
                pass

        COM_NOTIFICATION_AVAILABLE = True
except Exception as _com_err:
    COM_NOTIFICATION_AVAILABLE = False
    WindowsAudioNotificationClient = None


class AudioDeviceManager:
    """
    Intelligent hardware audio device orchestrator.
    Prioritizes Bluetooth Earbuds / Headsets over internal laptop microphones & speakers,
    providing seamless voice input/output routing and event-driven hot-plug connection detection.
    """

    _instance: Optional["AudioDeviceManager"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._cached_devices: List[AudioDeviceInfo] = []
        self._last_scan_time: float = 0.0
        self._cache_ttl: float = 2.0  # seconds

        # Cached output devices
        self._cached_output_devices: List[AudioDeviceInfo] = []
        self._last_output_scan_time: float = 0.0
        self._last_detected_output_identity: Optional[Tuple] = None
        self._last_detected_pygame_output: Optional[str] = None
        self._last_portaudio_reinit_time: float = 0.0

        # State machine & lifecycle management
        self._state_transition_lock = threading.RLock()
        self._connection_state = AudioConnectionState.STABLE
        self._active_headset: Optional[PhysicalAudioHeadset] = None
        self._fallback_input_device: Optional[AudioDeviceInfo] = None
        self._fallback_output_device: Optional[AudioDeviceInfo] = None
        self._active_input_device: Optional[AudioDeviceInfo] = None
        self._active_output_device: Optional[AudioDeviceInfo] = None

        # Configuration settings
        self.auto_switch_headset: bool = True
        self.preferred_headset: str = "auto"
        self.restore_previous_device: bool = True
        self.announce_device_changes: bool = True
        self._manual_preferred_device: Optional[str] = None

        # Proactive self-healing audio state
        self._suppressed_silent_devices: Dict[int, float] = {}
        self._last_unmute_check_time: float = 0.0

        self._load_config()

        # Injected TTS engine for announcements
        self._tts_engine: Optional[Any] = None

        # Hot-plug watcher state
        self._watcher_thread: Optional[threading.Thread] = None
        self._watcher_stop = threading.Event()
        self._last_detected_earbuds: Optional[str] = None
        self._last_detected_identity: Optional[Tuple] = None
        self._device_change_callbacks: List[Callable[[Optional[AudioDeviceInfo]], None]] = []
        self._output_device_change_callbacks: List[Callable[[Optional[AudioDeviceInfo], Optional[str]], None]] = []
        self._topology_change_callbacks: List[Callable[[Dict[str, Any]], None]] = []

        # COM notification registration
        self._com_enumerator = None
        self._com_client = None
        self._debounce_timer: Optional[threading.Timer] = None

    def _load_config(self) -> None:
        """Loads audio configuration options from config.yaml."""
        try:
            import yaml
            if os.path.exists("config.yaml"):
                with open("config.yaml", "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f) or {}
                    v_cfg = cfg.get("voice", {})
                    self.auto_switch_headset = bool(v_cfg.get("auto_switch_headset", True))
                    self.preferred_headset = str(v_cfg.get("preferred_headset", "auto")).strip()
                    self.restore_previous_device = bool(v_cfg.get("restore_previous_device", True))
                    self.announce_device_changes = bool(v_cfg.get("announce_device_changes", True))

                    pref = v_cfg.get("preferred_microphone", "auto")
                    if pref and str(pref).lower().strip() not in ("auto", "none"):
                        self._manual_preferred_device = str(pref).strip()
        except Exception as e:
            logger.debug(f"AudioDeviceManager: Config loading error: {e}")

    def set_tts_engine(self, tts_engine: Any) -> None:
        """Sets the TTS engine used for natural spoken audio route announcements."""
        self._tts_engine = tts_engine

    @staticmethod
    def clean_device_name(raw_name: str) -> str:
        """Cleans driver path metadata or system noise from Windows device names."""
        if not raw_name:
            return "Unknown Device"
        name = raw_name.strip()
        # Handle Windows driver strings like '@System32\\drivers\\bthhfenum.sys,#2;%1 Hands-Free%0 ;(CMF Buds 2)'
        match = re.search(r";\s*\((.*?)\)", name)
        if match:
            inner = match.group(1).strip()
            if inner:
                return f"{inner} (Bluetooth)"
        match_paren = re.search(r"Hands-Free.*?;\((.*?)\)", name, re.IGNORECASE)
        if match_paren:
            return f"{match_paren.group(1).strip()} (Bluetooth)"
        name = name.replace("\ufffd", "").replace("", "")
        name = " ".join(name.split())
        return name

    def is_bluetooth_device(self, name: str) -> bool:
        """Determines if a device name corresponds to Bluetooth Earbuds / Headsets."""
        name_lower = name.lower()
        return any(kw in name_lower for kw in BLUETOOTH_KEYWORDS)

    def is_usb_mic(self, name: str) -> bool:
        """Determines if a device is a dedicated external USB / Studio microphone."""
        name_lower = name.lower()
        return any(kw in name_lower for kw in USB_STUDIO_KEYWORDS)

    def is_excluded_input(self, name: str, hostapi_name: str = "") -> bool:
        """Checks if a device should be excluded from recording consideration."""
        name_lower = name.lower()
        if any(kw in name_lower for kw in EXCLUDED_INPUT_KEYWORDS):
            return True
        hapi_lower = hostapi_name.lower()
        if "wdm-ks" in hapi_lower or "kernel streaming" in hapi_lower:
            return True
        return False

    def classify_device_roles(self, dev: AudioDeviceInfo) -> List[DeviceRole]:
        """Classifies an audio device into functional roles."""
        roles: List[DeviceRole] = []
        if dev.is_output:
            roles.append(DeviceRole.OUTPUT)
            roles.append(DeviceRole.SPEAKER)
        else:
            roles.append(DeviceRole.INPUT)
            roles.append(DeviceRole.MICROPHONE)

        if dev.is_bluetooth or dev.is_earbuds:
            roles.append(DeviceRole.BLUETOOTH)
            roles.append(DeviceRole.HEADSET)
            roles.append(DeviceRole.EARBUD)

        if dev.is_usb:
            roles.append(DeviceRole.USB)

        if dev.is_default:
            roles.append(DeviceRole.DEFAULT)

        return roles

    def calculate_priority_score(self, name: str, is_default: bool, hostapi_name: str = "") -> int:
        """
        Calculates priority score for audio capture:
        - Bluetooth Earbuds / Headset: 100-110
        - USB Studio Mic: 70
        - Default System Input: 50
        - Built-in Internal Mic: 30
        - Excluded / Virtual / WDM-KS ghost: 0
        """
        if self.is_excluded_input(name, hostapi_name):
            return 0

        score = 20
        name_lower = name.lower()

        is_bt = self.is_bluetooth_device(name)
        if is_bt:
            score = 100
            if "wasapi" in hostapi_name.lower():
                score += 5
            elif "directsound" in hostapi_name.lower():
                score += 2
        elif self.is_usb_mic(name):
            score = 70
        elif is_default:
            score = 50
        elif "realtek" in name_lower or "microphone" in name_lower or "mic" in name_lower:
            score = 30

        return score

    def is_excluded_output(self, name: str, hostapi_name: str = "") -> bool:
        """Checks if an audio output device should be excluded from playback consideration."""
        name_lower = name.lower()
        if any(kw in name_lower for kw in EXCLUDED_OUTPUT_KEYWORDS):
            return True
        hapi_lower = hostapi_name.lower()
        if "wdm-ks" in hapi_lower or "kernel streaming" in hapi_lower:
            return True
        return False

    def calculate_output_priority_score(self, name: str, is_default: bool, hostapi_name: str = "") -> int:
        """
        Calculates priority score for audio output / TTS:
        - Bluetooth Earbuds / Headphones: 100-110
        - Default System Output: 50
        - Built-in Speakers / Realtek: 30
        - Excluded / Virtual / WDM-KS ghost: 0
        """
        if self.is_excluded_output(name, hostapi_name):
            return 0

        score = 20
        name_lower = name.lower()

        is_bt = self.is_bluetooth_device(name)
        if is_bt:
            score = 100
            if "wasapi" in hostapi_name.lower():
                score += 5
            elif "directsound" in hostapi_name.lower():
                score += 2
        elif is_default:
            score = 50
        elif "speakers" in name_lower or "realtek" in name_lower or "headphones" in name_lower:
            score = 30

        return score

    def _reinit_portaudio(self) -> None:
        """Forces PortAudio C-library device re-enumeration so hotplugged Bluetooth/USB devices are seen."""
        now = time.time()
        if now - self._last_portaudio_reinit_time < 0.5:
            return
        self._last_portaudio_reinit_time = now

        # CRITICAL SAFETY INVARIANT: Never terminate PortAudio if any audio stream is actively streaming!
        # Calling Pa_Terminate with open streams causes fatal C segmentation faults (0xC0000005 / exit code 3221225477).
        try:
            from voice.listener import PersistentAudioStream
            if PersistentAudioStream.has_active_streams():
                logger.debug("AudioDeviceManager: Skipping PortAudio reinit because audio stream is actively running.")
                return
        except Exception:
            pass

        try:
            import sounddevice as sd
            try:
                # Extra guard: check if default sounddevice stream is open and active
                stream = getattr(sd, "_last_callback", None)
                if stream and hasattr(stream, "active") and stream.active:
                    logger.debug("AudioDeviceManager: Skipping PortAudio reinit because sounddevice stream is active.")
                    return
            except Exception:
                pass

            if hasattr(sd, "_terminate") and hasattr(sd, "_initialize"):
                sd._terminate()
                sd._initialize()
        except Exception as e:
            logger.debug(f"AudioDeviceManager: PortAudio reinit note: {e}")

    def list_input_devices(self, force_refresh: bool = False) -> List[AudioDeviceInfo]:
        """
        Queries and ranks all available audio input devices from SoundDevice.
        Uses cached enumeration with short TTL to minimize latency.
        """
        now = time.time()
        if not force_refresh and self._cached_devices and (now - self._last_scan_time < self._cache_ttl):
            return self._cached_devices

        if force_refresh:
            self._reinit_portaudio()

        self.ensure_device_unmuted()

        devices: List[AudioDeviceInfo] = []
        try:
            import sounddevice as sd
            raw_devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            default_input_idx = sd.default.device[0] if sd.default.device else -1

            for idx, dev in enumerate(raw_devices):
                max_in = dev.get("max_input_channels", 0)
                if max_in <= 0:
                    continue

                raw_name = dev.get("name", f"Device {idx}")
                clean_name = self.clean_device_name(raw_name)
                hostapi_idx = dev.get("hostapi", 0)
                hostapi_name = hostapis[hostapi_idx]["name"] if hostapi_idx < len(hostapis) else ""

                is_def = (idx == default_input_idx)
                is_bt = self.is_bluetooth_device(raw_name) or self.is_bluetooth_device(clean_name)
                is_usb = self.is_usb_mic(raw_name) or self.is_usb_mic(clean_name)
                score = self.calculate_priority_score(raw_name, is_def, hostapi_name)

                info = AudioDeviceInfo(
                    index=idx,
                    name=raw_name,
                    clean_name=clean_name,
                    is_bluetooth=is_bt,
                    is_earbuds=is_bt,
                    is_usb=is_usb,
                    is_default=is_def,
                    score=score,
                    hostapi_name=hostapi_name,
                    max_input_channels=max_in,
                    default_samplerate=float(dev.get("default_samplerate", 16000.0)),
                    max_output_channels=0,
                    is_output=False
                )
                info.roles = self.classify_device_roles(info)
                devices.append(info)

            # Sort descending by priority score
            devices.sort(key=lambda d: d.score, reverse=True)

        except Exception as e:
            logger.debug(f"AudioDeviceManager: Error querying sounddevice: {e}")

        self._cached_devices = devices
        self._last_scan_time = now
        return devices

    def list_output_devices(self, force_refresh: bool = False) -> List[AudioDeviceInfo]:
        """
        Queries and ranks all available audio output devices from SoundDevice.
        Uses cached enumeration with short TTL to minimize latency.
        """
        now = time.time()
        if not force_refresh and self._cached_output_devices and (now - self._last_output_scan_time < self._cache_ttl):
            return self._cached_output_devices

        if force_refresh:
            self._reinit_portaudio()

        devices: List[AudioDeviceInfo] = []
        try:
            import sounddevice as sd
            raw_devices = sd.query_devices()
            hostapis = sd.query_hostapis()
            try:
                default_output_idx = sd.default.device[1] if sd.default.device is not None else -1
            except Exception:
                default_output_idx = -1

            for idx, dev in enumerate(raw_devices):
                max_out = dev.get("max_output_channels", 0)
                if max_out <= 0:
                    continue

                raw_name = dev.get("name", f"Output Device {idx}")
                clean_name = self.clean_device_name(raw_name)
                hostapi_idx = dev.get("hostapi", 0)
                hostapi_name = hostapis[hostapi_idx]["name"] if hostapi_idx < len(hostapis) else ""

                is_def = (idx == default_output_idx)
                is_bt = self.is_bluetooth_device(raw_name) or self.is_bluetooth_device(clean_name)
                is_usb = self.is_usb_mic(raw_name) or self.is_usb_mic(clean_name)
                score = self.calculate_output_priority_score(raw_name, is_def, hostapi_name)

                info = AudioDeviceInfo(
                    index=idx,
                    name=raw_name,
                    clean_name=clean_name,
                    is_bluetooth=is_bt,
                    is_earbuds=is_bt,
                    is_usb=is_usb,
                    is_default=is_def,
                    score=score,
                    hostapi_name=hostapi_name,
                    max_input_channels=0,
                    default_samplerate=float(dev.get("default_samplerate", 44100.0)),
                    max_output_channels=max_out,
                    is_output=True
                )
                info.roles = self.classify_device_roles(info)
                devices.append(info)

            # Sort descending by priority score
            devices.sort(key=lambda d: d.score, reverse=True)

        except Exception as e:
            logger.debug(f"AudioDeviceManager: Error querying sounddevice output devices: {e}")

        self._cached_output_devices = devices
        self._last_output_scan_time = now
        return devices

    def get_paired_physical_headsets(self, force_refresh: bool = False) -> List[PhysicalAudioHeadset]:
        """
        Discovers and pairs physical headsets by matching normalized base hardware identities
        across audio input and output endpoints.
        """
        in_devs = self.list_input_devices(force_refresh=force_refresh)
        out_devs = self.list_output_devices(force_refresh=force_refresh)

        headsets_map: Dict[str, PhysicalAudioHeadset] = {}

        # 1. Evaluate Bluetooth Outputs
        for dev in out_devs:
            if dev.is_bluetooth and dev.score > 0:
                base_name = extract_base_headset_identity(dev.name)
                key = base_name.lower().strip()
                if key not in headsets_map:
                    headsets_map[key] = PhysicalAudioHeadset(
                        hardware_id=key.replace(" ", "_"),
                        base_name=base_name,
                        display_name=base_name,
                        output_device=dev,
                        has_speaker=True,
                        has_microphone=False
                    )
                else:
                    if headsets_map[key].output_device is None or dev.score > headsets_map[key].output_device.score:
                        headsets_map[key].output_device = dev
                        headsets_map[key].has_speaker = True

        # 2. Evaluate Bluetooth Inputs
        for dev in in_devs:
            if dev.is_bluetooth and dev.score > 0:
                base_name = extract_base_headset_identity(dev.name)
                key = base_name.lower().strip()
                if key in headsets_map:
                    if headsets_map[key].input_device is None or dev.score > headsets_map[key].input_device.score:
                        headsets_map[key].input_device = dev
                        headsets_map[key].has_microphone = True
                else:
                    headsets_map[key] = PhysicalAudioHeadset(
                        hardware_id=key.replace(" ", "_"),
                        base_name=base_name,
                        display_name=base_name,
                        input_device=dev,
                        has_speaker=False,
                        has_microphone=True
                    )

        # Sort headsets so those with both mic + speaker rank highest
        headsets = list(headsets_map.values())
        headsets.sort(key=lambda h: (h.has_microphone and h.has_speaker, h.has_speaker), reverse=True)
        return headsets

    def get_best_output_device(self, preferred_api: Optional[str] = None, force_refresh: bool = False) -> Optional[AudioDeviceInfo]:
        """Returns the best audio output device (prioritizing Bluetooth earbuds/headphones)."""
        devices = self.list_output_devices(force_refresh=force_refresh)
        if not devices:
            return None

        valid_devices = [d for d in devices if d.score > 0]
        if not valid_devices:
            valid_devices = devices

        valid_devices.sort(key=lambda d: d.score, reverse=True)

        if preferred_api:
            api_lower = preferred_api.lower()
            filtered = [d for d in valid_devices if api_lower in d.hostapi_name.lower()]
            if filtered:
                return filtered[0]

        return valid_devices[0]

    def get_best_pygame_output_devicename(self, force_refresh: bool = False) -> Optional[str]:
        """
        Resolves the exact SDL2 audio output device name string suitable for pygame.mixer.init(devicename=...).
        Prioritizes connected Bluetooth earbuds/headphones.
        """
        try:
            import pygame
            import pygame._sdl2.audio as sdl_audio
            if not pygame.mixer.get_init():
                try:
                    pygame.mixer.init()
                except Exception:
                    pass
            sdl_devices = sdl_audio.get_audio_device_names(False)
            if not sdl_devices:
                return None

            # 1. Look for Bluetooth earbuds in SDL2 output devices
            for dev_name in sdl_devices:
                if self.is_bluetooth_device(dev_name) or self.is_bluetooth_device(self.clean_device_name(dev_name)):
                    return dev_name

            # 2. Check if best sounddevice matches an SDL device name
            best_sd = self.get_best_output_device(force_refresh=force_refresh)
            if best_sd:
                best_clean = best_sd.clean_name.lower()
                for dev_name in sdl_devices:
                    clean_sdl = self.clean_device_name(dev_name).lower()
                    if best_clean in clean_sdl or clean_sdl in best_clean or dev_name.lower() in best_sd.name.lower():
                        return dev_name

            return sdl_devices[0] if sdl_devices else None
        except Exception as e:
            logger.debug(f"AudioDeviceManager: Error querying pygame SDL2 output devices: {e}")
            return None

    def get_unique_output_devices(self, force_refresh: bool = False) -> List[AudioDeviceInfo]:
        """
        Returns a deduplicated list of real physical/logical output devices for GUI display.
        Deduplicates by clean name across host APIs (WASAPI, DirectSound, MME).
        """
        devices = self.list_output_devices(force_refresh=force_refresh)
        valid = [d for d in devices if d.score > 0]

        def _api_rank(hapi: str) -> int:
            h = hapi.lower()
            if "wasapi" in h:
                return 3
            if "directsound" in h:
                return 2
            if "mme" in h:
                return 1
            return 0

        unique_map: Dict[str, AudioDeviceInfo] = {}
        for dev in valid:
            key = dev.clean_name.lower().strip()
            if key not in unique_map:
                unique_map[key] = dev
            else:
                existing = unique_map[key]
                dev_rank = (dev.score, _api_rank(dev.hostapi_name))
                exist_rank = (existing.score, _api_rank(existing.hostapi_name))
                if dev_rank > exist_rank:
                    unique_map[key] = dev

        result = list(unique_map.values())
        result.sort(key=lambda d: (d.is_default, d.score), reverse=True)
        return result

    def get_unique_input_devices(self, force_refresh: bool = False) -> List[AudioDeviceInfo]:
        """
        Returns a deduplicated list of real physical/logical input devices for GUI display.
        Deduplicates by clean name across host APIs (WASAPI, DirectSound, MME).
        """
        devices = self.list_input_devices(force_refresh=force_refresh)
        valid = [d for d in devices if d.score > 0]

        def _api_rank(hapi: str) -> int:
            h = hapi.lower()
            if "wasapi" in h:
                return 3
            if "directsound" in h:
                return 2
            if "mme" in h:
                return 1
            return 0

        unique_map: Dict[str, AudioDeviceInfo] = {}
        for dev in valid:
            key = dev.clean_name.lower().strip()
            if key not in unique_map:
                unique_map[key] = dev
            else:
                existing = unique_map[key]
                dev_rank = (dev.score, _api_rank(dev.hostapi_name))
                exist_rank = (existing.score, _api_rank(existing.hostapi_name))
                if dev_rank > exist_rank:
                    unique_map[key] = dev

        result = list(unique_map.values())
        result.sort(key=lambda d: (d.is_default, d.score), reverse=True)
        return result

    def get_manual_device(self) -> Optional[str]:
        """Returns the currently configured manual preferred device identifier, or None if Auto-Detect."""
        return self._manual_preferred_device

    def set_manual_device(self, device_name_or_id: Optional[str]) -> None:
        """Sets manual microphone preference."""
        old_pref = self._manual_preferred_device
        if device_name_or_id is None or str(device_name_or_id).lower().strip() in ("auto", "none", ""):
            self._manual_preferred_device = None
        else:
            self._manual_preferred_device = str(device_name_or_id).strip()

        logger.info(f"AudioDeviceManager: Manual device preference set to: {self._manual_preferred_device or 'Auto-Detect'}")

        if self._manual_preferred_device != old_pref:
            new_best = self.get_best_input_device(force_refresh=True)
            new_id = (new_best.index, new_best.name, new_best.is_bluetooth) if new_best else None
            if new_id != self._last_detected_identity:
                self._last_detected_identity = new_id
                self._notify_device_changed(new_best)

    def get_best_input_device(
        self,
        preferred_api: Optional[str] = None,
        force_refresh: bool = False,
        allow_bluetooth: bool = True
    ) -> Optional[AudioDeviceInfo]:
        """
        Returns the single best audio input device.
        If manual preference is configured and matches, returns that.
        Otherwise returns highest-priority device (Bluetooth earbuds > USB > Default > Internal).
        """
        devices = self.list_input_devices(force_refresh=force_refresh)
        if not devices:
            return None

        # 1. If manual preferred device is set
        if self._manual_preferred_device:
            pref = self._manual_preferred_device.lower().strip()
            if pref not in ("auto", "none", ""):
                if pref.isdigit():
                    idx_target = int(pref)
                    for d in devices:
                        if d.index == idx_target:
                            return d
                matched = [
                    d for d in devices
                    if pref == d.clean_name.lower()
                    or pref in d.clean_name.lower()
                    or pref in d.name.lower()
                ]
                if matched:
                    matched.sort(key=lambda d: (d.score, "wasapi" in d.hostapi_name.lower()), reverse=True)
                    if preferred_api:
                        api_filtered = [d for d in matched if preferred_api.lower() in d.hostapi_name.lower()]
                        if api_filtered:
                            return api_filtered[0]
                    return matched[0]
                else:
                    logger.warning(
                        f"AudioDeviceManager: Preferred device '{self._manual_preferred_device}' not found. Falling back to auto-priority."
                    )

        # 2. Auto-priority logic
        now = time.time()
        self._suppressed_silent_devices = {
            idx: exp for idx, exp in self._suppressed_silent_devices.items() if exp > now
        }

        if not allow_bluetooth:
            valid_devices = [d for d in devices if d.score > 0 and not d.is_bluetooth]
        else:
            valid_devices = [d for d in devices if d.score > 0]

        if not valid_devices:
            valid_devices = devices

        # Filter out devices temporarily suppressed due to flatline silence
        unsuppressed = [d for d in valid_devices if d.index not in self._suppressed_silent_devices]
        if unsuppressed:
            valid_devices = unsuppressed

        valid_devices.sort(key=lambda d: d.score, reverse=True)

        if preferred_api:
            api_lower = preferred_api.lower()
            filtered = [d for d in valid_devices if api_lower in d.hostapi_name.lower()]
            if filtered:
                return filtered[0]

        return valid_devices[0]

    def get_fallback_or_internal_input_device(self, force_refresh: bool = False) -> Optional[AudioDeviceInfo]:
        """
        Returns the best reliable non-Bluetooth input device (e.g. system default or built-in Microphone Array).
        Guarantees fallback availability when Bluetooth headset microphones are dead, muted, or in A2DP-only mode.
        """
        return self.get_best_input_device(force_refresh=force_refresh, allow_bluetooth=False)

    def get_best_sounddevice_index(self, force_refresh: bool = False) -> Optional[int]:
        """Returns the best SoundDevice index (prioritizing manual preference or Bluetooth earbuds)."""
        best = self.get_best_input_device(force_refresh=force_refresh)
        return best.index if best else None

    def get_best_sr_device_index(self) -> Optional[int]:
        """Finds and returns the best PyAudio / SpeechRecognition microphone device index."""
        try:
            import speech_recognition as sr
            mic_names = sr.Microphone.list_microphone_names()
            if not mic_names:
                return None

            if self._manual_preferred_device:
                pref = self._manual_preferred_device.lower()
                if pref.isdigit():
                    idx = int(pref)
                    if 0 <= idx < len(mic_names):
                        return idx
                for idx, name in enumerate(mic_names):
                    clean = self.clean_device_name(name).lower()
                    if pref == clean or pref in clean or pref in name.lower():
                        return idx

            best_idx: Optional[int] = None
            best_score = -1

            for idx, name in enumerate(mic_names):
                if self.is_excluded_input(name):
                    continue

                clean = self.clean_device_name(name)
                is_bt = self.is_bluetooth_device(name) or self.is_bluetooth_device(clean)
                is_usb = self.is_usb_mic(name)

                score = 20
                if is_bt:
                    score = 100
                elif is_usb:
                    score = 70
                elif "realtek" in name.lower() or "mic" in name.lower():
                    score = 30

                if score > best_score:
                    best_score = score
                    best_idx = idx

            return best_idx
        except Exception as e:
            logger.debug(f"AudioDeviceManager: Error evaluating SpeechRecognition mic list: {e}")
            return None

    # Public active routing queries
    def get_active_input_device(self) -> Optional[AudioDeviceInfo]:
        """Returns currently active audio input endpoint."""
        with self._state_transition_lock:
            if self._active_input_device:
                return self._active_input_device
            return self.get_best_input_device()

    def get_active_output_device(self) -> Optional[AudioDeviceInfo]:
        """Returns currently active audio output endpoint."""
        with self._state_transition_lock:
            if self._active_output_device:
                return self._active_output_device
            return self.get_best_output_device()

    def get_active_headset(self) -> Optional[PhysicalAudioHeadset]:
        """Returns active physical headset if connected, otherwise None."""
        with self._state_transition_lock:
            return self._active_headset

    def get_audio_state(self) -> AudioConnectionState:
        """Returns current lifecycle state machine status."""
        with self._state_transition_lock:
            return self._connection_state

    def validate_input_device(self, device_index: int) -> bool:
        """Verifies if an audio input device index is operational."""
        try:
            import sounddevice as sd
            dev = sd.query_devices(device_index)
            if dev.get("max_input_channels", 0) <= 0:
                return False
            sr = int(dev.get("default_samplerate", 16000))
            for test_sr in [sr, 16000, 44100, 48000]:
                try:
                    sd.check_input_settings(device=device_index, channels=1, dtype="float32", samplerate=test_sr)
                    return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def validate_output_device(self, device_index: int) -> bool:
        """Verifies if an audio output device index is operational."""
        try:
            import sounddevice as sd
            dev = sd.query_devices(device_index)
            channels = min(2, dev.get("max_output_channels", 0))
            if channels <= 0:
                return False
            sr = int(dev.get("default_samplerate", 44100))
            for test_sr in [sr, 48000, 44100, 24000, 16000]:
                try:
                    sd.check_output_settings(device=device_index, channels=channels, dtype="float32", samplerate=test_sr)
                    return True
                except Exception:
                    continue
            return False
        except Exception:
            return False

    def test_device_audio(self, device_index: Optional[int] = None, duration: float = 1.5) -> Dict[str, Any]:
        """
        Records a short audio sample from the specified device (or best device)
        to verify audio capture functionality and signal level (RMS).
        """
        try:
            import sounddevice as sd
            import numpy as np

            if device_index is None:
                best = self.get_best_input_device()
                if not best:
                    return {"success": False, "rms": 0.0, "peak": 0.0, "message": "No input device available", "device_name": "None"}
                device_index = best.index
                device_name = best.clean_name
            else:
                all_devs = self.list_input_devices()
                matching = [d for d in all_devs if d.index == device_index]
                device_name = matching[0].clean_name if matching else f"Device #{device_index}"

            samplerate = 16000
            channels = 1
            audio_data = sd.rec(
                int(duration * samplerate),
                samplerate=samplerate,
                channels=channels,
                device=device_index,
                dtype="float32",
                blocking=True
            )
            sd.wait()

            if audio_data is None or len(audio_data) == 0:
                return {"success": False, "rms": 0.0, "peak": 0.0, "message": "No audio data recorded", "device_name": device_name}

            audio_f64 = audio_data.astype(np.float64)
            rms = float(np.sqrt(np.mean(np.square(audio_f64))))
            peak = float(np.max(np.abs(audio_f64)))

            if peak < 0.001:
                status_msg = "Audio captured, but signal is very faint or silent. Check microphone mute switch."
            elif peak < 0.02:
                status_msg = f"Audio captured! Signal level is moderate (Peak: {peak:.2f}, RMS: {rms:.4f})."
            else:
                status_msg = f"Audio captured successfully! Signal level is strong (Peak: {peak:.2f}, RMS: {rms:.4f})."

            return {
                "success": True,
                "rms": round(rms, 4),
                "peak": round(peak, 4),
                "message": status_msg,
                "device_name": device_name
            }
        except Exception as e:
            logger.error(f"AudioDeviceManager: Error testing audio device {device_index}: {e}")
            return {
                "success": False,
                "rms": 0.0,
                "peak": 0.0,
                "message": f"Error accessing device: {str(e)}",
                "device_name": str(device_index)
            }

    def ensure_device_unmuted(self, force: bool = False) -> bool:
        """
        Proactively audits Windows CoreAudio capture endpoints.
        If any microphone is muted (Mute == 1) or volume is < 0.25 (25%),
        unmutes it and restores volume to 0.85 (85%) automatically.
        """
        if os.name != "nt":
            return False
        now = time.time()
        if not force and (now - self._last_unmute_check_time < 3.0):
            return False
        self._last_unmute_check_time = now

        try:
            import comtypes
            try:
                comtypes.CoInitialize()
            except Exception:
                pass

            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            from ctypes import cast, POINTER
            from comtypes import CLSCTX_ALL

            enumerator = AudioUtilities.GetDeviceEnumerator()
            if not enumerator:
                return False
            endpoints = enumerator.EnumAudioEndpoints(1, 1)  # eCapture = 1, DEVICE_STATE_ACTIVE = 1
            if not endpoints:
                return False
            count = endpoints.GetCount()
            unmuted_any = False

            for i in range(count):
                try:
                    dev = endpoints.Item(i)
                    dev_id = dev.GetId()
                    interface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                    vol = cast(interface, POINTER(IAudioEndpointVolume))
                    is_muted = vol.GetMute()
                    level = vol.GetMasterVolumeLevelScalar()

                    if is_muted or level < 0.25:
                        logger.info(
                            f"AudioDeviceManager: Auto-healing microphone (ID: {dev_id}). "
                            f"Previous: Mute={is_muted}, Vol={level:.2f} -> Unmuting & Setting Vol=0.85"
                        )
                        vol.SetMute(0, None)
                        if level < 0.50:
                            vol.SetMasterVolumeLevelScalar(0.85, None)
                        unmuted_any = True
                except Exception as endpoint_err:
                    logger.debug(f"AudioDeviceManager endpoint un-mute check error: {endpoint_err}")

            # Explicitly release COM objects before uninitializing apartment
            try:
                del endpoints
            except Exception:
                pass
            try:
                del enumerator
            except Exception:
                pass

            return unmuted_any
        except Exception as e:
            logger.debug(f"AudioDeviceManager: ensure_device_unmuted error: {e}")
            return False
        finally:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

    def report_silent_device(self, device_index: Optional[int]) -> None:
        """
        Called when an audio stream receives flatline silence from a device.
        Attempts Windows CoreAudio unmute, and suppresses the device from auto-selection
        for 60s to prevent ping-pong flapping.
        """
        if device_index is None:
            return
        self.ensure_device_unmuted(force=True)
        with self._state_transition_lock:
            self._suppressed_silent_devices[device_index] = time.time() + 60.0
            fb = self.get_fallback_or_internal_input_device(force_refresh=True)
            if fb:
                logger.warning(
                    f"AudioDeviceManager: Device #{device_index} reported silent. "
                    f"Switching active input to fallback: {fb.clean_name}"
                )
                self._active_input_device = fb
                self._update_runtime_context()
                self._notify_device_changed(fb)

    def generate_connection_announcement(self, headset: Optional[PhysicalAudioHeadset], is_connected: bool) -> str:
        """Generates natural, honest Hinglish feedback for device connection / disconnection."""
        if is_connected and headset:
            if headset.has_microphone and headset.has_speaker:
                return "Ji, earbuds connect ho gaye. Ab main earbuds se sununga aur wahi par bolunga."
            elif headset.has_speaker and not headset.has_microphone:
                return "Ji, earbuds connect ho gaye hain, lekin microphone available nahi hai. Main current microphone use kar raha hoon."
            elif headset.has_microphone and not headset.has_speaker:
                return "Ji, earbuds microphone connect ho gaya hai. Output current speaker par rahega."
        return "Ji, earbuds disconnect ho gaye. Main default microphone aur speaker par aa gaya hoon."

    def _speak_announcement(self, text: str) -> None:
        """Dispatches natural audio announcement asynchronously."""
        if not self.announce_device_changes or not text:
            return
        logger.info(f"📢 AudioDeviceManager Announcement: {text}")
        if self._tts_engine is not None:
            def _run():
                try:
                    if hasattr(self._tts_engine, "speak"):
                        self._tts_engine.speak(text)
                    elif hasattr(self._tts_engine, "speak_chunk"):
                        self._tts_engine.speak_chunk(text)
                except Exception as spk_err:
                    logger.debug(f"AudioDeviceManager speak announcement error: {spk_err}")

            t = threading.Thread(target=_run, daemon=True, name="JarvisAudioAnnouncement")
            t.start()

    def _update_runtime_context(self) -> None:
        """Synchronizes audio state with the centralized RuntimeContext."""
        try:
            from core.context import RuntimeContext, AudioStateContext
            ctx = RuntimeContext.get_instance()
            headset = self._active_headset
            ctx.audio = AudioStateContext(
                is_headset_connected=(headset is not None),
                headset_name=headset.display_name if headset else None,
                active_input_device=self._active_input_device.clean_name if self._active_input_device else None,
                active_output_device=self._active_output_device.clean_name if self._active_output_device else None,
                connection_state=self._connection_state.value,
                has_microphone=headset.has_microphone if headset else True,
                has_speaker=headset.has_speaker if headset else True,
                auto_switch_enabled=self.auto_switch_headset
            )
        except Exception as e:
            logger.debug(f"AudioDeviceManager: Could not update RuntimeContext: {e}")

    def set_event_bus(self, event_bus: Any) -> None:
        """Sets the system EventBus for domain event dispatch."""
        self._event_bus = event_bus

    def get_event_bus(self) -> Any:
        """Returns the configured or default EventBus instance."""
        if getattr(self, "_event_bus", None) is not None:
            return self._event_bus
        from core.event_bus import EventBus
        return EventBus.get_default()

    def _emit_eventbus_change(self, event_type: str, headset: Optional[PhysicalAudioHeadset] = None) -> None:
        """Publishes an AudioDeviceChanged event to the system EventBus."""
        try:
            from core.event_bus import AudioDeviceChanged
            dev_name = headset.display_name if headset else (
                self._active_input_device.clean_name if self._active_input_device else "Default Device"
            )
            event = AudioDeviceChanged(
                event_type=event_type,
                device_name=dev_name,
                is_bluetooth=(headset is not None or (self._active_input_device and self._active_input_device.is_bluetooth)),
                input_index=self._active_input_device.index if self._active_input_device else None,
                output_index=self._active_output_device.index if self._active_output_device else None,
                has_microphone=headset.has_microphone if headset else True,
                has_speaker=headset.has_speaker if headset else True,
                timestamp=time.time()
            )
            bus = self.get_event_bus()
            if hasattr(bus, "publish"):
                bus.publish(event)
        except Exception as e:
            logger.debug(f"AudioDeviceManager: Could not publish EventBus event: {e}")

    def _handle_headset_connected(self, headset: PhysicalAudioHeadset) -> None:
        """Processes headset connection with honest capability evaluation."""
        self._connection_state = AudioConnectionState.SWITCHING
        logger.info(f"🎧 Physical Headset Connected: {headset.display_name} (Mic: {headset.has_microphone}, Speaker: {headset.has_speaker})")

        # Save fallback devices if not previously recorded (fallback input must always be non-bluetooth)
        if self._fallback_input_device is None or self._fallback_input_device.is_bluetooth:
            self._fallback_input_device = self.get_fallback_or_internal_input_device(force_refresh=True)
        if self._fallback_output_device is None:
            self._fallback_output_device = self.get_best_output_device(force_refresh=True)

        # Route input and output
        if headset.has_microphone and headset.input_device:
            self._active_input_device = headset.input_device
        else:
            # Honest degradation: retain current input
            if self._fallback_input_device:
                self._active_input_device = self._fallback_input_device

        if headset.has_speaker and headset.output_device:
            self._active_output_device = headset.output_device

        self._active_headset = headset
        self._connection_state = AudioConnectionState.ACTIVE_HEADSET

        self._update_runtime_context()
        self._emit_eventbus_change("headset_connected", headset)

        announcement = self.generate_connection_announcement(headset, is_connected=True)
        self._speak_announcement(announcement)

        # Notify registered callbacks
        self._notify_device_changed(self._active_input_device)
        sdl_out = self.get_best_pygame_output_devicename(force_refresh=True)
        self._notify_output_device_changed(self._active_output_device, sdl_out)
        self._notify_topology_changed(self.get_status_summary())

    def _handle_headset_disconnected(self) -> None:
        """Restores fallback devices gracefully upon headset disconnect."""
        self._connection_state = AudioConnectionState.FALLING_BACK
        old_headset = self._active_headset
        headset_name = old_headset.display_name if old_headset else "Earbuds"
        logger.info(f"🔌 Physical Headset Disconnected: {headset_name}. Falling back to default audio devices.")

        self._active_headset = None

        # Re-query system defaults for fallback
        system_in = [d for d in self.list_input_devices(force_refresh=True) if not d.is_bluetooth and d.score > 0]
        system_out = [d for d in self.list_output_devices(force_refresh=True) if not d.is_bluetooth and d.score > 0]

        if system_in:
            system_in.sort(key=lambda d: (d.is_default, d.score), reverse=True)
            self._active_input_device = system_in[0]
        else:
            self._active_input_device = self._fallback_input_device

        if system_out:
            system_out.sort(key=lambda d: (d.is_default, d.score), reverse=True)
            self._active_output_device = system_out[0]
        else:
            self._active_output_device = self._fallback_output_device

        self._connection_state = AudioConnectionState.RECOVERED
        self._update_runtime_context()
        self._emit_eventbus_change("headset_disconnected", old_headset)

        announcement = self.generate_connection_announcement(None, is_connected=False)
        self._speak_announcement(announcement)

        # Notify registered callbacks
        self._notify_device_changed(self._active_input_device)
        sdl_out = self.get_best_pygame_output_devicename(force_refresh=True)
        self._notify_output_device_changed(self._active_output_device, sdl_out)
        self._notify_topology_changed(self.get_status_summary())

        self._connection_state = AudioConnectionState.STABLE

    def _evaluate_audio_topology(self, initial: bool = False, force_refresh: bool = False) -> None:
        """Evaluates hardware pairing topology and handles state transitions."""
        with self._state_transition_lock:
            headsets = self.get_paired_physical_headsets(force_refresh=force_refresh)

            target_headset: Optional[PhysicalAudioHeadset] = None
            if headsets:
                if self.preferred_headset and self.preferred_headset.lower() != "auto":
                    pref = self.preferred_headset.lower()
                    matched = [h for h in headsets if pref in h.base_name.lower()]
                    target_headset = matched[0] if matched else headsets[0]
                else:
                    target_headset = headsets[0]

            was_connected = (self._active_headset is not None)
            is_connected = (target_headset is not None)

            if initial:
                if is_connected and self.auto_switch_headset:
                    self._active_headset = target_headset
                    self._active_input_device = target_headset.input_device
                    self._active_output_device = target_headset.output_device
                    self._connection_state = AudioConnectionState.ACTIVE_HEADSET
                else:
                    self._active_headset = None
                    self._active_input_device = self.get_best_input_device(force_refresh=force_refresh)
                    self._active_output_device = self.get_best_output_device(force_refresh=force_refresh)
                    self._connection_state = AudioConnectionState.STABLE
                self._update_runtime_context()
                return

            if not was_connected and is_connected:
                if self.auto_switch_headset:
                    self._handle_headset_connected(target_headset)
            elif was_connected and not is_connected:
                self._handle_headset_disconnected()
            elif was_connected and is_connected:
                # Same or updated headset endpoint
                if target_headset.hardware_id != self._active_headset.hardware_id:
                    if self.auto_switch_headset:
                        self._handle_headset_connected(target_headset)

    def _on_windows_endpoint_event(self, event_type: str, details: Any) -> None:
        """
        Coalesces and debounces rapid Windows CoreAudio COM notifications
        (A2DP, Hands-Free AG, endpoint arrivals/departures).
        """
        logger.debug(f"AudioDeviceManager: Windows CoreAudio event: {event_type}")
        with self._lock:
            if self._debounce_timer is not None:
                try:
                    self._debounce_timer.cancel()
                except Exception:
                    pass
            self._debounce_timer = threading.Timer(0.3, self._trigger_device_refresh)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _trigger_device_refresh(self) -> None:
        """Background callback after COM debounce settling."""
        try:
            self._evaluate_audio_topology(initial=False, force_refresh=True)
        except Exception as err:
            logger.debug(f"AudioDeviceManager: Error refreshing device topology: {err}")

    def get_status_summary(self) -> Dict[str, Any]:
        """Returns a user-friendly overview of current audio input and output topology."""
        best = self.get_active_input_device()
        all_in_devs = self.list_input_devices()
        earbuds_in = [d for d in all_in_devs if d.is_bluetooth and d.score > 50]

        best_out = self.get_active_output_device()
        all_out_devs = self.list_output_devices()
        earbuds_out = [d for d in all_out_devs if d.is_bluetooth and d.score > 50]

        sdl_out = self.get_best_pygame_output_devicename()
        headsets = self.get_paired_physical_headsets()
        is_eb_connected = (self._active_headset is not None) or len(earbuds_in) > 0 or len(earbuds_out) > 0

        active_eb_name = None
        if self._active_headset:
            active_eb_name = self._active_headset.display_name
        elif earbuds_in:
            active_eb_name = earbuds_in[0].clean_name
        elif earbuds_out:
            active_eb_name = earbuds_out[0].clean_name

        return {
            "earbuds_connected": is_eb_connected,
            "earbuds_name": active_eb_name,
            "earbuds_input_name": earbuds_in[0].clean_name if earbuds_in else None,
            "earbuds_output_name": earbuds_out[0].clean_name if earbuds_out else None,
            "active_device_index": best.index if best else None,
            "active_device_name": best.clean_name if best else "Default System Microphone",
            "active_is_bluetooth": best.is_bluetooth if best else False,
            "host_api": best.hostapi_name if best else "Default",
            "total_input_devices": len(all_in_devs),
            "active_output_index": best_out.index if best_out else None,
            "active_output_name": best_out.clean_name if best_out else "Default Speakers",
            "active_output_is_bluetooth": best_out.is_bluetooth if best_out else False,
            "pygame_output_name": sdl_out,
            "total_output_devices": len(all_out_devs),
            "connection_state": self._connection_state.value,
            "paired_headsets": [h.to_dict() for h in headsets]
        }

    def _notify_device_changed(self, device: Optional[AudioDeviceInfo]) -> None:
        """Notifies all registered listeners of an active device switch."""
        with self._lock:
            callbacks = list(self._device_change_callbacks)
        for cb in callbacks:
            try:
                cb(device)
            except Exception as cb_err:
                logger.debug(f"Error in device change callback: {cb_err}")

    def _notify_output_device_changed(self, device: Optional[AudioDeviceInfo], pygame_name: Optional[str]) -> None:
        """Notifies all registered listeners of an active audio output switch."""
        with self._lock:
            callbacks = list(self._output_device_change_callbacks)
        for cb in callbacks:
            try:
                cb(device, pygame_name)
            except Exception as cb_err:
                logger.debug(f"Error in output device change callback: {cb_err}")

    def _notify_topology_changed(self, summary: Dict[str, Any]) -> None:
        """Notifies all registered listeners of a unified audio topology change."""
        with self._lock:
            callbacks = list(self._topology_change_callbacks)
        for cb in callbacks:
            try:
                cb(summary)
            except Exception as cb_err:
                logger.debug(f"Error in topology change callback: {cb_err}")

    def register_device_change_listener(self, callback: Callable[[Optional[AudioDeviceInfo]], None], notify_immediate: bool = False) -> None:
        with self._lock:
            if callback not in self._device_change_callbacks:
                self._device_change_callbacks.append(callback)
        if notify_immediate:
            try:
                callback(self.get_active_input_device())
            except Exception as e:
                logger.debug(f"register_device_change_listener immediate error: {e}")

    def unregister_device_change_listener(self, callback: Callable[[Optional[AudioDeviceInfo]], None]) -> None:
        with self._lock:
            if callback in self._device_change_callbacks:
                self._device_change_callbacks.remove(callback)

    def register_output_device_change_listener(self, callback: Callable[[Optional[AudioDeviceInfo], Optional[str]], None]) -> None:
        with self._lock:
            if callback not in self._output_device_change_callbacks:
                self._output_device_change_callbacks.append(callback)

    def unregister_output_device_change_listener(self, callback: Callable[[Optional[AudioDeviceInfo], Optional[str]], None]) -> None:
        with self._lock:
            if callback in self._output_device_change_callbacks:
                self._output_device_change_callbacks.remove(callback)

    def register_topology_change_listener(self, callback: Callable[[Dict[str, Any]], None], notify_immediate: bool = False) -> None:
        with self._lock:
            if callback not in self._topology_change_callbacks:
                self._topology_change_callbacks.append(callback)
        if notify_immediate:
            try:
                callback(self.get_status_summary())
            except Exception as e:
                logger.debug(f"register_topology_change_listener immediate error: {e}")

    def unregister_topology_change_listener(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        with self._lock:
            if callback in self._topology_change_callbacks:
                self._topology_change_callbacks.remove(callback)

    def start_hotplug_watcher(self, poll_interval: float = 1.0) -> None:
        """
        Starts the event-driven hotplug monitor. Uses Windows CoreAudio COM callbacks
        when available, avoiding continuous CPU-heavy polling loops.
        """
        if self._watcher_thread and self._watcher_thread.is_alive():
            return

        self._watcher_stop.clear()
        self._evaluate_audio_topology(initial=True)

        best = self.get_active_input_device()
        self._last_detected_identity = (best.index, best.name, best.is_bluetooth) if best else None

        best_out = self.get_active_output_device()
        self._last_detected_output_identity = (best_out.index, best_out.name, best_out.is_bluetooth) if best_out else None
        self._last_detected_pygame_output = self.get_best_pygame_output_devicename()

        # Attempt to register Windows COM endpoint callback
        if COM_NOTIFICATION_AVAILABLE and WindowsAudioNotificationClient is not None:
            try:
                self._com_enumerator = AudioUtilities.GetDeviceEnumerator()
                self._com_client = WindowsAudioNotificationClient(self._on_windows_endpoint_event)
                self._com_enumerator.RegisterEndpointNotificationCallback(self._com_client)
                logger.info("AudioDeviceManager: Registered Windows CoreAudio IMMNotificationClient callback.")
            except Exception as com_err:
                logger.debug(f"AudioDeviceManager: Could not register COM callback: {com_err}")
                self._com_client = None
                self._com_enumerator = None

        def _watch_loop():
            # Heartbeat interval of 2.0s ensures rapid detection of newly paired/connected Bluetooth devices
            interval = 2.0 if self._com_client is not None else min(poll_interval, 2.0)

            while not self._watcher_stop.is_set():
                if self._watcher_stop.wait(interval):
                    break
                try:
                    # In heartbeat, evaluate topology to detect changes in environments without COM
                    self._evaluate_audio_topology(initial=False)

                    # Backward compatibility checks for input/output identity
                    current_best = self.get_active_input_device()
                    current_id = (current_best.index, current_best.name, current_best.is_bluetooth) if current_best else None
                    if current_id != self._last_detected_identity:
                        self._last_detected_identity = current_id
                        self._notify_device_changed(current_best)

                    current_best_out = self.get_active_output_device()
                    current_out_id = (current_best_out.index, current_best_out.name, current_best_out.is_bluetooth) if current_best_out else None
                    current_sdl_out = self.get_best_pygame_output_devicename()

                    if (current_out_id != self._last_detected_output_identity) or (current_sdl_out != self._last_detected_pygame_output):
                        self._last_detected_output_identity = current_out_id
                        self._last_detected_pygame_output = current_sdl_out
                        self._notify_output_device_changed(current_best_out, current_sdl_out)

                except Exception as loop_err:
                    logger.debug(f"Watcher loop error: {loop_err}")

        self._watcher_thread = threading.Thread(target=_watch_loop, daemon=True, name="JarvisAudioDeviceWatcher")
        self._watcher_thread.start()
        logger.info("AudioDeviceManager: Bluetooth Earbuds live hot-plug watcher active.")

    def stop_hotplug_watcher(self) -> None:
        """Stops the hot-plug monitoring thread and unregisters COM callbacks."""
        self._watcher_stop.set()
        if self._debounce_timer is not None:
            try:
                self._debounce_timer.cancel()
            except Exception:
                pass

        if self._com_enumerator and self._com_client:
            try:
                self._com_enumerator.UnregisterEndpointNotificationCallback(self._com_client)
            except Exception:
                pass
            self._com_client = None
            self._com_enumerator = None

        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=1.0)
        self._watcher_thread = None
