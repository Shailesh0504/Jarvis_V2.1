# plugins/sounds/plugin.py
"""Sounds plugin implementation for sound effects, alarms, frequency tones, and Windows system chimes."""

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import winsound
except ImportError:
    winsound = None

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.sounds")


class SoundsPlugin(BasePlugin):
    """Controls sound effects playback, alarms, and Windows system chimes."""

    def __init__(self, manifest: Optional[PluginManifest] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest=manifest, config=config)
        self.sounds_dir = os.path.dirname(os.path.abspath(__file__))
        self._volume = 0.8
        self._alarm_thread = None
        self._stop_alarm_event = threading.Event()
        self._init_audio()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="sounds",
            version="2.0.0",
            description="Sound effects, alarms, tone generators, and audio alerts controller.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def _init_audio(self) -> None:
        try:
            import pygame
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except Exception as e:
            logger.debug("Pygame mixer init note: %s", e)

    def _resolve_sound_path(self, name: str) -> Optional[str]:
        if os.path.isabs(name) and os.path.isfile(name):
            return name
        clean_name = os.path.basename(name).lower()
        if not clean_name.endswith((".mp3", ".wav")):
            clean_name = f"{clean_name}.mp3"
        candidate = os.path.join(self.sounds_dir, clean_name)
        if os.path.isfile(candidate):
            return candidate
        wav_candidate = candidate.replace(".mp3", ".wav")
        if os.path.isfile(wav_candidate):
            return wav_candidate
        return None

    def _play_audio_file_async(self, file_path: str) -> bool:
        """Plays audio in a background thread to prevent blocking caller."""
        def _worker():
            try:
                import pygame
                if pygame.mixer.get_init():
                    sound = pygame.mixer.Sound(file_path)
                    sound.set_volume(self._volume)
                    sound.play()
                    return
            except Exception:
                pass

            # Fallback to Windows native winsound or PowerShell
            try:
                if file_path.lower().endswith(".wav") and winsound:
                    winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                else:
                    import subprocess
                    ps_cmd = f"(New-Object Media.SoundPlayer '{file_path}').PlaySync()"
                    subprocess.Popen(["powershell", "-NoProfile", "-Command", ps_cmd], creationflags=0x08000000)
            except Exception as e:
                logger.debug("Playback fallback failed: %s", e)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return True

    def verify_state(self, action_name: str, parameters: Dict[str, Any], result_data: Any) -> Optional[Any]:
        from core.execution.models import VerificationResult, ExecutionState
        if action_name in ("play_sound", "play_custom_audio_file", "play_recycle_bin_sound"):
            path = (result_data or {}).get("path")
            if path and os.path.isfile(path) and os.path.getsize(path) > 0:
                return VerificationResult(
                    verified=True,
                    state=ExecutionState.SUCCESS,
                    check_type="file_exists",
                    expected=path,
                    actual=f"{os.path.getsize(path)} bytes",
                    message="Sound file asset verified on disk."
                )
            return VerificationResult(
                verified=False,
                state=ExecutionState.FAILED,
                check_type="file_exists",
                expected=path,
                actual=None,
                error="Sound file missing or unreadable."
            )
        return None

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        # 1. play_sound
        if action_name == "play_sound":
            sound_name = str(parameters.get("sound_name", "jarvis")).strip()
            path = self._resolve_sound_path(sound_name)
            if not path:
                return PluginResult(success=False, error=f"Sound effect '{sound_name}' not found in assets.")

            self._play_audio_file_async(path)
            return PluginResult(
                success=True,
                data={"name": sound_name, "path": path, "message": f"Playing sound effect '{sound_name}'."}
            )

        # 2. play_system_beep
        elif action_name == "play_system_beep":
            beep_type = str(parameters.get("beep_type", "ok")).strip().lower()
            if not winsound:
                return PluginResult(success=False, error="winsound is not available on this platform.")

            beep_map = {
                "ok": winsound.MB_OK,
                "asterisk": winsound.MB_ICONASTERISK,
                "exclamation": winsound.MB_ICONEXCLAMATION,
                "hand": winsound.MB_ICONHAND,
                "question": winsound.MB_ICONQUESTION
            }
            code = beep_map.get(beep_type, winsound.MB_OK)
            try:
                winsound.MessageBeep(code)
                return PluginResult(success=True, data={"beep_type": beep_type, "message": f"Played system beep '{beep_type}'."})
            except Exception as e:
                return PluginResult(success=False, error=f"MessageBeep failed: {e}")

        # 3. play_alarm
        elif action_name == "play_alarm":
            duration = int(parameters.get("duration_seconds", 5))
            path = self._resolve_sound_path("alarm") or self._resolve_sound_path("reminder")
            if not path:
                return PluginResult(success=False, error="Alarm sound asset not found.")

            self._stop_alarm_event.clear()

            def _alarm_worker():
                start = time.time()
                while not self._stop_alarm_event.is_set() and (time.time() - start) < duration:
                    self._play_audio_file_async(path)
                    time.sleep(1.2)

            self._alarm_thread = threading.Thread(target=_alarm_worker, daemon=True)
            self._alarm_thread.start()

            return PluginResult(
                success=True,
                data={"path": path, "duration_seconds": duration, "message": f"Alarm started for {duration} seconds."}
            )

        # 4. stop_all_sounds
        elif action_name == "stop_all_sounds":
            self._stop_alarm_event.set()
            try:
                import pygame
                if pygame.mixer.get_init():
                    pygame.mixer.stop()
            except Exception:
                pass
            return PluginResult(success=True, data={"stopped": True, "message": "Stopped all active sound playback."})

        # 5. list_available_sounds
        elif action_name == "list_available_sounds":
            valid_exts = (".mp3", ".wav")
            files = [f for f in sorted(os.listdir(self.sounds_dir)) if f.lower().endswith(valid_exts)]
            names = [os.path.splitext(f)[0] for f in files]
            return PluginResult(
                success=True,
                data={"count": len(files), "sounds": names, "files": files, "message": f"Available sound assets ({len(names)}): {', '.join(names)}"}
            )

        # 6. set_sound_volume
        elif action_name == "set_sound_volume":
            vol_pct = max(0, min(100, int(parameters.get("volume_percent", 80))))
            self._volume = vol_pct / 100.0
            return PluginResult(success=True, data={"volume_percent": vol_pct, "message": f"Sound effects volume set to {vol_pct}%."})

        # 7. play_custom_audio_file
        elif action_name == "play_custom_audio_file":
            fp = parameters.get("file_path", "").strip()
            if not fp or not os.path.isfile(fp):
                return PluginResult(success=False, error=f"Audio file not found: '{fp}'")

            self._play_audio_file_async(os.path.abspath(fp))
            return PluginResult(success=True, data={"path": fp, "message": f"Playing audio file '{os.path.basename(fp)}'."})

        # 8. generate_frequency_tone
        elif action_name == "generate_frequency_tone":
            if not winsound:
                return PluginResult(success=False, error="Tone generation requires winsound.")

            freq = max(37, min(32767, int(parameters.get("frequency", 1000))))
            dur = max(50, min(5000, int(parameters.get("duration_ms", 400))))
            try:
                # Play async in thread so caller is not blocked
                threading.Thread(target=lambda: winsound.Beep(freq, dur), daemon=True).start()
                return PluginResult(success=True, data={"frequency": freq, "duration_ms": dur, "message": f"Generated {freq} Hz tone for {dur} ms."})
            except Exception as e:
                return PluginResult(success=False, error=f"Frequency tone generation failed: {e}")

        # 9. get_audio_duration
        elif action_name == "get_audio_duration":
            target = str(parameters.get("sound_name_or_path", "")).strip()
            path = self._resolve_sound_path(target)
            if not path:
                return PluginResult(success=False, error=f"Audio asset '{target}' not found.")

            size = os.path.getsize(path)
            # Estimate duration based on standard MP3/WAV average bitrate
            est_seconds = round(size / (16000), 2)  # rough ~128kbps estimate
            return PluginResult(
                success=True,
                data={"path": path, "size_bytes": size, "estimated_duration_seconds": est_seconds, "message": f"Asset '{os.path.basename(path)}' size: {size} bytes (~{est_seconds}s)."}
            )

        # 10. verify_sound_file
        elif action_name == "verify_sound_file":
            target = str(parameters.get("sound_name_or_path", "")).strip()
            path = self._resolve_sound_path(target)
            is_valid = path is not None and os.path.isfile(path) and os.path.getsize(path) > 0
            return PluginResult(
                success=is_valid,
                data={"valid": is_valid, "path": path, "message": f"Sound asset '{target}' is {'valid' if is_valid else 'invalid / missing'}."},
                error=None if is_valid else f"Sound asset '{target}' not found or empty."
            )

        # 11. play_recycle_bin_sound
        elif action_name == "play_recycle_bin_sound":
            path = self._resolve_sound_path("recycle_bin")
            if not path:
                return PluginResult(success=False, error="Recycle bin sound asset not found.")

            self._play_audio_file_async(path)
            return PluginResult(success=True, data={"path": path, "message": "Played recycle bin sound effect."})

        return PluginResult(success=False, error=f"Unknown action '{action_name}' in Sounds plugin.")
