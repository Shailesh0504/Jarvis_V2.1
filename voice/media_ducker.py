# voice/media_ducker.py
"""
Intelligent System Media Volume Ducker and Audio Playback Coordinator for Jarvis V2.
Monitors Windows audio sessions in real-time, detecting active media (YouTube, Spotify, VLC, Netflix)
and automatically ducking background playback volume during voice interactions so user speech
is captured with maximum SNR and clarity, then gracefully restoring media volume upon turn completion.

Thread Safety Invariant:
Windows CoreAudio COM interfaces (pycaw / comtypes) must NEVER be created on arbitrary ephemeral
threads or dereferenced across COM apartments, which causes 0xC0000005 access violations during Release().
All CoreAudio interactions are strictly isolated within a single persistent _MediaDuckerWorker thread.
"""

import logging
import os
import queue
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("jarvis.voice.media_ducker")


class _MediaDuckerWorker(threading.Thread):
    """
    Dedicated worker thread maintaining a persistent COM apartment for CoreAudio operations.
    Eliminates cross-apartment COM reference releases and prevent STATUS_ACCESS_VIOLATION crashes.
    """

    def __init__(self):
        super().__init__(daemon=True, name="JarvisMediaDuckerWorker")
        self._task_queue = queue.Queue()
        self._stop_event = threading.Event()
        self.start()

    def run(self):
        if os.name == "nt":
            import comtypes
            try:
                comtypes.CoInitialize()
            except Exception:
                pass

        try:
            while not self._stop_event.is_set():
                try:
                    item = self._task_queue.get(timeout=0.5)
                except queue.Empty:
                    continue

                if item is None:
                    break

                fn, args, done_event, result_box = item
                try:
                    result_box[0] = fn(*args)
                except Exception as exc:
                    result_box[1] = exc
                finally:
                    done_event.set()
                    self._task_queue.task_done()
        finally:
            if os.name == "nt":
                import comtypes
                try:
                    comtypes.CoUninitialize()
                except Exception:
                    pass

    def execute(self, fn: Callable, *args, timeout: float = 1.0) -> Any:
        """Executes a function inside the persistent COM apartment and returns the result."""
        if not self.is_alive():
            return fn(*args)
        done_event = threading.Event()
        result_box = [None, None]
        self._task_queue.put((fn, args, done_event, result_box))
        if done_event.wait(timeout=timeout):
            if result_box[1] is not None:
                raise result_box[1]
            return result_box[0]
        else:
            logger.debug(f"MediaDuckerWorker: Task {fn.__name__} timed out after {timeout}s")
            return None


class MediaDucker:
    """
    Thread-safe Windows CoreAudio Media Volume Ducker.
    Identifies browser tabs and media players producing sound and smoothly attenuates them
    during voice recognition and Jarvis spoken feedback.
    """

    _instance: Optional["MediaDucker"] = None
    _instance_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "MediaDucker":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lock = threading.RLock()
        self._is_ducked = False
        self._original_volumes: Dict[int, float] = {}
        self._last_duck_time = 0.0
        self._last_unduck_time = 0.0
        self._delayed_timer: Optional[threading.Timer] = None

        # Dedicated persistent COM thread
        self._worker: Optional[_MediaDuckerWorker] = None
        if os.name == "nt":
            try:
                self._worker = _MediaDuckerWorker()
            except Exception as e:
                logger.debug(f"MediaDuckerWorker initialization note: {e}")

        # Known web browsers and media players on Windows
        self._media_process_names: Set[str] = {
            "brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe",
            "spotify.exe", "vlc.exe", "wmplayer.exe", "music.ui.exe", "video.ui.exe",
            "itunes.exe", "foobar2000.exe", "aimp.exe", "kmplayer.exe", "potplayer.exe"
        }

    @property
    def is_ducked(self) -> bool:
        with self._lock:
            return self._is_ducked

    def is_media_playing(self) -> bool:
        """Returns True if any web browser or desktop media player is currently producing audio."""
        if os.name != "nt":
            return False

        if self._worker and self._worker.is_alive():
            try:
                res = self._worker.execute(self._sync_is_media_playing, timeout=0.5)
                return bool(res)
            except Exception:
                return False
        return self._sync_is_media_playing()

    def _sync_is_media_playing(self) -> bool:
        try:
            from pycaw.pycaw import AudioUtilities, IAudioMeterInformation
            sessions = AudioUtilities.GetAllSessions()
            has_sound = False
            for s in sessions:
                proc = s.Process
                if not proc:
                    continue
                name = proc.name().lower()
                if name in self._media_process_names:
                    try:
                        meter = s._ctl.QueryInterface(IAudioMeterInformation)
                        if meter and meter.GetPeakValue() > 0.01:
                            has_sound = True
                            del meter
                            break
                        del meter
                    except Exception:
                        continue
            del sessions
            return has_sound
        except Exception as e:
            logger.debug(f"MediaDucker is_media_playing check error: {e}")
            return False

    def duck(self, attenuation: float = 0.15) -> bool:
        """
        Ducks active media playback volume down to attenuation level (default 15%).
        Saves pre-ducking volume levels to ensure accurate restoration.
        """
        if os.name != "nt":
            return False

        with self._lock:
            if self._delayed_timer:
                self._delayed_timer.cancel()
                self._delayed_timer = None

            if self._is_ducked:
                return True

        if self._worker and self._worker.is_alive():
            try:
                res = self._worker.execute(self._sync_duck, attenuation, timeout=0.6)
                return bool(res)
            except Exception:
                return False
        return self._sync_duck(attenuation)

    def _sync_duck(self, attenuation: float = 0.15) -> bool:
        with self._lock:
            if self._is_ducked:
                return True

            try:
                from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume, IAudioMeterInformation
                sessions = AudioUtilities.GetAllSessions()
                ducked_any = False

                for s in sessions:
                    proc = s.Process
                    if not proc:
                        continue
                    name = proc.name().lower()
                    if name in self._media_process_names:
                        try:
                            meter = s._ctl.QueryInterface(IAudioMeterInformation)
                            peak = meter.GetPeakValue() if meter else 0.0
                            vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                            if vol:
                                cur_vol = vol.GetMasterVolume()
                                # Only duck if current volume is noticeably above attenuation level
                                if cur_vol > (attenuation + 0.05) and (peak > 0.005 or name in ("brave.exe", "chrome.exe", "msedge.exe")):
                                    if s.ProcessId not in self._original_volumes:
                                        self._original_volumes[s.ProcessId] = cur_vol
                                    vol.SetMasterVolume(attenuation, None)
                                    ducked_any = True
                                    logger.info(
                                        f"MediaDucker: Ducked {name} (PID: {s.ProcessId}) "
                                        f"from {cur_vol:.2f} -> {attenuation:.2f}"
                                    )
                                del vol
                            if meter:
                                del meter
                        except Exception as s_err:
                            logger.debug(f"MediaDucker session duck error for {name}: {s_err}")

                del sessions
                self._is_ducked = ducked_any
                self._last_duck_time = time.time()
                return ducked_any
            except Exception as e:
                logger.debug(f"MediaDucker duck error: {e}")
                return False

    def unduck(self) -> bool:
        """Restores previously ducked media playback sessions back to their original volumes."""
        if os.name != "nt":
            return False

        with self._lock:
            if self._delayed_timer:
                self._delayed_timer.cancel()
                self._delayed_timer = None

            if not self._is_ducked and not self._original_volumes:
                return False

        if self._worker and self._worker.is_alive():
            try:
                res = self._worker.execute(self._sync_unduck, timeout=0.6)
                return bool(res)
            except Exception:
                return False
        return self._sync_unduck()

    def unduck_delayed(self, delay: float = 0.4) -> None:
        """Schedules media restoration after delay seconds without creating ad-hoc COM threads."""
        with self._lock:
            if self._delayed_timer:
                self._delayed_timer.cancel()
            self._delayed_timer = threading.Timer(delay, self._on_delayed_unduck)
            self._delayed_timer.daemon = True
            self._delayed_timer.start()

    def _on_delayed_unduck(self) -> None:
        with self._lock:
            self._delayed_timer = None
        self.unduck()

    def _sync_unduck(self) -> bool:
        with self._lock:
            if not self._is_ducked and not self._original_volumes:
                return False

            try:
                from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
                sessions = AudioUtilities.GetAllSessions()
                restored_any = False

                for s in sessions:
                    if s.ProcessId in self._original_volumes:
                        try:
                            orig_vol = self._original_volumes[s.ProcessId]
                            # Safeguard against accidental near-zero restoration
                            if orig_vol <= 0.20:
                                orig_vol = 1.0
                            vol = s._ctl.QueryInterface(ISimpleAudioVolume)
                            if vol:
                                vol.SetMasterVolume(orig_vol, None)
                                restored_any = True
                                proc = s.Process
                                name = proc.name() if proc else f"PID {s.ProcessId}"
                                logger.info(f"MediaDucker: Restored {name} -> {orig_vol:.2f}")
                                del vol
                        except Exception as s_err:
                            logger.debug(f"MediaDucker session unduck error for PID {s.ProcessId}: {s_err}")

                del sessions
                self._original_volumes.clear()
                self._is_ducked = False
                self._last_unduck_time = time.time()
                return restored_any
            except Exception as e:
                logger.debug(f"MediaDucker unduck error: {e}")
                self._original_volumes.clear()
                self._is_ducked = False
                return False

