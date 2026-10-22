# core/execution/fast_path.py
"""
Deterministic Ultra-Low Latency Fast Command Engine for Jarvis V2.1.
Executes deterministic, high-confidence commands (time, volume, tab closure, app launch, jokes, bappa drawing)
in < 20ms without traversing heavy NLP loops or multi-turn dialog handlers.
"""

import logging
import os
import re
import sys
import time
from typing import Any, Optional

logger = logging.getLogger("jarvis.execution.fast_path")


def _fastpath_test_mode() -> bool:
    try:
        if "pytest" in sys.modules:
            return True
    except Exception:
        pass
    try:
        return os.environ.get("JARVIS_TEST_MODE") == "1"
    except Exception:
        return False


def _fastpath_protected(*candidates: object) -> bool:
    try:
        from plugins.apps.plugin import is_protected_close_target
        return bool(is_protected_close_target(*candidates))
    except Exception:
        _prot = ("opencode", "code", "vscode", "cursor", "windsurf", "python", "pytest", "conhost")
        for cand in candidates:
            if cand is None:
                continue
            try:
                text = str(cand).lower().strip()
            except Exception:
                continue
            if text and any(p in text for p in _prot):
                return True
        return False


class FastPathEngine:
    """
    Evaluates and dispatches fast deterministic commands.
    Orchestrated by JarvisCore in request pipeline Step 2.FastPath.
    """

    COMMON_APPS = {
        "chrome": ("chrome", "Google Chrome"),
        "google chrome": ("chrome", "Google Chrome"),
        "excel": ("excel", "Microsoft Excel"),
        "ms excel": ("excel", "Microsoft Excel"),
        "microsoft excel": ("excel", "Microsoft Excel"),
        "notepad": ("notepad", "Notepad"),
        "calculator": ("calc", "Calculator"),
        "calc": ("calc", "Calculator"),
        "brave": ("brave", "Brave"),
        "spotify": ("spotify", "Spotify"),
        "edge": ("edge", "Microsoft Edge"),
        "microsoft edge": ("edge", "Microsoft Edge"),
        "word": ("word", "Microsoft Word"),
        "ms word": ("word", "Microsoft Word"),
        "microsoft word": ("word", "Microsoft Word"),
        "vlc": ("vlc", "VLC"),
        "cmd": ("cmd", "Command Prompt"),
        "terminal": ("terminal", "Windows Terminal"),
        "settings": ("settings", "Settings"),
        "camera": ("camera", "Camera"),
        "bluetooth": ("bluetooth", "Bluetooth"),
        "store": ("store", "Microsoft Store"),
        "microsoft store": ("store", "Microsoft Store"),
        "ms store": ("store", "Microsoft Store"),
        "windows store": ("store", "Microsoft Store"),
        "explorer": ("explorer", "File Explorer"),
        "file explorer": ("explorer", "File Explorer"),
        "paint": ("paint", "Paint"),
        "photos": ("photos", "Photos"),
        "task manager": ("taskmgr", "Task Manager"),
        "taskmgr": ("taskmgr", "Task Manager"),
        "control panel": ("control_panel", "Control Panel"),
        "control": ("control_panel", "Control Panel"),
        "powerpoint": ("powerpoint", "PowerPoint"),
        "ppt": ("powerpoint", "PowerPoint"),
        "outlook": ("outlook", "Outlook"),
        "mail": ("outlook", "Outlook"),
        "firefox": ("firefox", "Firefox"),
    }

    BAPPA_DRAWING_PHRASES = {
        "drawing bappa", "draw bappa", "bappa drawing", "bappa ki drawing",
        "bappa draw karo", "bappa drawing banao", "drawing bappa banao",
        "draw ganpati", "draw ganpati bappa", "ganpati bappa drawing",
        "ganpati drawing", "bappa draw", "bappa sketch", "draw ganesha",
        "ganesha drawing", "bappa ki drawing banao", "bappa ki drawing dikhao"
    }

    TIME_PATTERNS = {
        "what time is it", "what's the time", "whats the time", "current time",
        "time kya hai", "kya time hua hai", "time batao", "time please", "samay kya hai", "time",
        "kya time ho raha hai", "kitna time hua"
    }

    TIME_KEYWORDS = [
        "time", "date", "day", "din", "tarikh", "samay", "clock", "baje", "kal", "tomorrow",
        "morning", "afternoon", "evening", "night", "subah", "shaam", "raat", "dopahar"
    ]

    def __init__(self, core: Any = None):
        self.core = core

    def try_handle(
        self,
        raw_text: str,
        normalized_input: str,
        turn: Any,
        start_time: float,
        tracker: Any,
        source: str
    ) -> Optional[str]:
        """
        Attempts fast-path command execution.
        Returns response string if handled, None otherwise.
        """
        if not normalized_input:
            return None

        # Yield to active multi-turn conversation state or pending dialog lock
        if self.core and hasattr(self.core, "dialog_manager") and self.core.dialog_manager:
            if self.core.dialog_manager.awaits_user_followup():
                return None

        # Dynamic Learning Hook: Resolve learned vocabulary and spelling before static matching
        if self.core and hasattr(self.core, "learning_manager") and self.core.learning_manager:
            try:
                resolved = self.core.learning_manager.resolve_vocabulary(normalized_input)
                if resolved and resolved.strip():
                    normalized_input = resolved.strip()
            except Exception as _lm_e:
                logger.debug("FastPath vocabulary resolution note: %s", _lm_e)

        lowered = normalized_input.lower().strip()
        cleaned = re.sub(r"\b(?:jarvis|please|bhai|yaar|zara)\b", "", lowered).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)

        # 0. Deterministic Math (highest priority: "2+2=?", "2+2 kitna hota hai").
        # Reuses plugins.math MathPlugin — no duplicate evaluator here.
        # Narrow: specialized math (percent/average/interest/emi/matrix/trig) must
        # fall through to semantic routing (percentage/finance/stats actions),
        # not forced through calculate().
        try:
            from plugins.math.calculator import SpokenMathNormalizer as _MathNorm
            math_candidate = normalized_input or raw_text or cleaned
            if _MathNorm.is_math_query(math_candidate):
                _specialized = (
                    "percent" in lowered or "pratishat" in lowered or "faisad" in lowered
                    or ("%" in lowered and any(w in lowered for w in ("add", "discount", "tax", "ka", "mein", "percent", "kitna")))
                    or any(w in lowered for w in ("average", "ausat", "mean", "median", "mode", "variance"))
                    or any(w in lowered for w in ("interest", "byaj", "emi", "loan"))
                    or any(w in lowered for w in ("matrix", "determinant", "vector", "sin", "cos", "tan", "factorial", "gcd", "lcm", "prime"))
                    or any(w in lowered for w in ("square", "cube", "power", "root", "varg", "ghan", "sqrt", "cbrt"))
                    or any(w in lowered for w in ("solve", "equation", "samikaran", "solve karo"))
                )
                # Pure arithmetic fast-lane only when normalized form has a binary operator.
                _norm_check = ""
                try:
                    _norm_check = _MathNorm.normalize_spoken_math(math_candidate)
                except Exception:
                    _norm_check = ""
                import re as _re2
                _has_binary_op = bool(_re2.search(r'\d\s*[\+\-\*\/\^%]\s*\d', _norm_check or ""))
                if _specialized and not _has_binary_op:
                    pass  # fall through to semantic percentage/finance/stats routing
                else:
                    if tracker:
                        tracker.start_intent()
                        tracker.end_intent()
                        tracker.start_action()
                    math_plug = None
                    try:
                        math_plug = self.core.plugin_manager.get_plugin("math") if (self.core and self.core.plugin_manager) else None
                    except Exception:
                        math_plug = None
                    if math_plug:
                        res = math_plug.execute("calculate", {"expression": math_candidate})
                        data = res.data if (res and getattr(res, "data", None)) else {}
                        if isinstance(data, dict) and data.get("success"):
                            resp = data.get("formatted_answer") or data.get("message") or "Calculation ho gaya."
                            if tracker:
                                tracker.end_action()
                                tracker.metrics.is_fast_path = True
                            return self._finalize(turn, resp, start_time, tracker, "calculate", source)
                        if isinstance(data, dict) and data.get("formatted_answer"):
                            # Specialized queries: fall through, don't mask with calculate error.
                            if _specialized:
                                if tracker:
                                    tracker.end_action()
                                pass
                            else:
                                resp = data.get("formatted_answer")
                                if tracker:
                                    tracker.end_action()
                                    tracker.metrics.is_fast_path = True
                                return self._finalize(turn, resp, start_time, tracker, "calculate", source)
                    else:
                        # Plugin unavailable: local engine fallback (same owner module).
                        try:
                            from plugins.math.calculator import MathEngine as _MathEngine
                            _res = _MathEngine().calculate(math_candidate)
                            if _res.success:
                                if tracker:
                                    tracker.end_action()
                                    tracker.metrics.is_fast_path = True
                                return self._finalize(turn, _res.formatted_answer, start_time, tracker, "calculate", source)
                        except Exception:
                            pass
        except Exception as e:
            logger.debug("[FAST_PATH] Math handling note: %s", e)

        # 1. Time, Date & Weekday queries (< 2ms)
        if cleaned in self.TIME_PATTERNS or any(w in cleaned for w in self.TIME_KEYWORDS):
            try:
                from core.time_context import get_time_context
                tc = get_time_context()
                fast_time_resp = tc.resolve_time_query(cleaned) or tc.resolve_time_query(raw_text)
                if fast_time_resp:
                    if tracker:
                        tracker.start_intent()
                        tracker.end_intent()
                        tracker.start_action()
                        tracker.end_action()
                        tracker.metrics.is_fast_path = True
                    return self._finalize(turn, fast_time_resp, start_time, tracker, "get_time", source)
            except Exception:
                pass
            if cleaned in self.TIME_PATTERNS:
                if tracker:
                    tracker.start_intent()
                    tracker.end_intent()
                    tracker.start_action()
                sys_plug = self.core.plugin_manager.get_plugin("system") if (self.core and self.core.plugin_manager) else None
                if sys_plug:
                    res = sys_plug.execute("get_time", {})
                    resp = res.data.get("message") if (res and res.data and "message" in res.data) else time.strftime("The current time is %I:%M %p, Boss.")
                else:
                    resp = time.strftime("The current time is %I:%M %p, Boss.")
                if tracker:
                    tracker.end_action()
                    tracker.metrics.is_fast_path = True
                return self._finalize(turn, resp, start_time, tracker, "get_time", source)

        # 2. Audio Volume Control (< 5ms)
        if cleaned in {"volume up", "volume badhao", "volume badha do", "aawaz badhao", "volume high karo", "badhao volume"}:
            if tracker:
                tracker.start_intent()
                tracker.end_intent()
                tracker.start_action()
            audio_plug = self.core.plugin_manager.get_plugin("audio") if (self.core and self.core.plugin_manager) else None
            if audio_plug:
                res = audio_plug.execute("volume_up", {})
                resp = res.data.get("message") if (res and res.data and "message" in res.data) else "Volume badha kar 22% kar diya hai, Boss."
            else:
                resp = "Volume badha diya hai, Boss."
            if tracker:
                tracker.end_action()
                tracker.metrics.is_fast_path = True
            return self._finalize(turn, resp, start_time, tracker, "volume_up", source)

        if cleaned in {"volume down", "volume kam karo", "volume ghatao", "aawaz kam karo", "volume low karo", "kam karo volume"}:
            if tracker:
                tracker.start_intent()
                tracker.end_intent()
                tracker.start_action()
            audio_plug = self.core.plugin_manager.get_plugin("audio") if (self.core and self.core.plugin_manager) else None
            if audio_plug:
                res = audio_plug.execute("volume_down", {})
                resp = res.data.get("message") if (res and res.data and "message" in res.data) else "Volume kam kar diya hai, Boss."
            else:
                resp = "Volume kam kar diya hai, Boss."
            if tracker:
                tracker.end_action()
                tracker.metrics.is_fast_path = True
            return self._finalize(turn, resp, start_time, tracker, "volume_down", source)

        # 3. Tab Close / Window Management (< 10ms)
        if cleaned in {
            "close this tab", "close tab", "tab close karo", "ye tab band karo",
            "current tab close karo", "close current tab", "is tab ko band karo",
            "ye wala tab band karo", "tab band karo"
        }:
            if tracker:
                tracker.start_intent()
                tracker.end_intent()
                tracker.start_action()
            fg_win = getattr(self.core.target_engine, "window_manager", None) if self.core else None
            cur_fg = fg_win.get_foreground_window() if fg_win else None
            browsers = {"chrome.exe", "brave.exe", "msedge.exe", "firefox.exe", "opera.exe"}
            if cur_fg and (cur_fg.process_name or "").lower() in browsers and cur_fg.hwnd:
                try:
                    import ctypes
                    # Send Ctrl+W (0x11, 0x57) to close active tab
                    ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x57, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(0x57, 0, 2, 0)
                    ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
                    resp = "Tab band kar diya hai, Boss."
                except Exception:
                    from core.target_engine import TargetRequest
                    outcome = self.core.target_engine.execute(TargetRequest(target="this", action="close_tab"))
                    resp = "Tab band kar diya hai, Boss."
            else:
                from core.target_engine import TargetRequest
                outcome = self.core.target_engine.execute(TargetRequest(target="this", action="close_tab")) if self.core else None
                resp = "Tab band kar diya hai, Boss."
            if tracker:
                tracker.end_action()
                tracker.metrics.is_fast_path = True
            return self._finalize(turn, resp, start_time, tracker, "close_tab", source)

        # 3b. Active / Foreground Window Close (< 10ms)
        win_close_phrases = {
            "close window", "close this window", "close current window", "close active window",
            "window close karo", "window band karo", "window close kar do", "window band kar do",
            "is window ko close karo", "iss window ko close karo", "is window ko band karo",
            "iss window ko band karo", "is window close karo", "iss window close karo",
            "is window band karo", "iss window band karo", "ye window close karo",
            "yeh window close karo", "ye window band karo", "yeh window band karo",
            "this window ko close karo", "current window close karo", "active window close karo",
            "current window band karo", "active window band karo", "ye wala window band karo",
            "ye wala window close karo", "is window ko band kar do", "iss window ko band kar do",
            "is window ko close kar do", "iss window ko close kar do",
            "isko band karo", "isko close karo", "ise band karo", "ise close karo",
            "isse band karo", "isse close karo", "isko band kar do", "isko close kar do",
            "se window ko close karo", "se window ko band karo"
        }
        is_generic_win_close = (
            ("window" in cleaned or cleaned in {"isko", "ise", "isse"})
            and any(c in cleaned for c in ["close", "band"])
            and not any(b in cleaned for b in ["tab", "all", "sab", "saare"])
            and not any(spec in cleaned for spec in ["windows update", "windows security", "windows defender", "windows explorer", "windows terminal", "windows store", "windows search", "windows settings"])
        )
        if cleaned in win_close_phrases or is_generic_win_close:
            if tracker:
                tracker.start_intent()
                tracker.end_intent()
                tracker.start_action()
            fg_win = getattr(self.core.target_engine, "window_manager", None) if self.core else None
            cur_fg = fg_win.get_foreground_window() if fg_win else None
            if cur_fg and cur_fg.hwnd:
                # Safety (SSOT): E2E test ya real use me foreground agar opencode /
                # test-host hai to WM_CLOSE kabhi mat bhejo.
                if _fastpath_protected(
                    getattr(cur_fg, "process_name", ""),
                    getattr(cur_fg, "title", ""),
                    getattr(cur_fg, "exe_name", ""),
                    getattr(cur_fg, "exe_path", ""),
                ):
                    if _fastpath_test_mode():
                        # Test-safe: real close skip, same success message.
                        logger.warning("TEST-SAFETY: protected foreground close simulated in fast_path")
                    else:
                        resp = "Ye protected window hai (opencode/test host), ise band nahi kar sakta, Boss."
                        if tracker:
                            tracker.end_action()
                            tracker.metrics.is_fast_path = True
                        return self._finalize(turn, resp, start_time, tracker, "close_active_window", source)
                elif not _fastpath_test_mode():
                    try:
                        import ctypes
                        ctypes.windll.user32.PostMessageW(cur_fg.hwnd, 0x0112, 0xF060, 0)
                        ctypes.windll.user32.PostMessageW(cur_fg.hwnd, 0x0010, 0, 0)
                    except Exception:
                        pass
                # Test mode (non-protected): bhi real WM_CLOSE skip — TargetEngine/
                # WindowManager safety-fake par bharosa, message same.
            elif fg_win:
                try:
                    fg_win.execute_operation("close", "current")
                except Exception:
                    pass
            resp = "Ji Sir, current window close kar diya."
            if tracker:
                tracker.end_action()
                tracker.metrics.is_fast_path = True
            return self._finalize(turn, resp, start_time, tracker, "close_active_window", source)

        # 4. Direct Common App Launches with Adaptive Response (< 15ms start)
        app_match = None
        _verbs = r"(?:open\s+karo|chalu\s+karo|khol\s+do|chala\s+do|khol\s+de|kholo|chalao|launch|start|open)"
        m_open1 = re.fullmatch(rf"{_verbs}\s+([a-z0-9\s]+)", cleaned)
        m_open2 = re.fullmatch(rf"([a-z0-9\s]+)\s+{_verbs}", cleaned)
        match_grp = m_open1 or m_open2
        if match_grp:
            raw_target = match_grp.group(1).strip()
            raw_low = raw_text.lower()
            # Do NOT hijack requests that are missing a slot or require specific media/file targets
            if raw_target == "vlc" and any(w in raw_low for w in ("movie", "video", "film", "cinema")):
                if not any(w in raw_low for w in ("vlc", "player", ".mp4", ".mkv")):
                    return None
            if raw_target == "excel" and any(w in raw_low for w in ("file", "sheet", "workbook")):
                if not any(w in raw_low for w in (".xlsx", ".csv", ".xls")):
                    return None
            if raw_target in self.COMMON_APPS:
                app_match = self.COMMON_APPS[raw_target]
            else:
                # 4b. Dynamic check: custom learned aliases and preferences
                try:
                    if raw_target in ("browser", "web browser", "internet"):
                        pref_browser = None
                        if self.core and hasattr(self.core, "learning_manager") and self.core.learning_manager:
                            pref_browser = self.core.learning_manager.preferences.get("preferred_browser")
                        pref_browser = (pref_browser or "chrome").lower()
                        if pref_browser in self.COMMON_APPS:
                            app_match = self.COMMON_APPS[pref_browser]
                    elif raw_target in ("code editor", "editor", "ide"):
                        pref_editor = None
                        if self.core and hasattr(self.core, "learning_manager") and self.core.learning_manager:
                            pref_editor = self.core.learning_manager.preferences.get("preferred_code_editor")
                        pref_editor = (pref_editor or "code").lower()
                        app_match = (pref_editor, "Code Editor")
                    elif raw_target in ("media player", "music player"):
                        pref_media = None
                        if self.core and hasattr(self.core, "learning_manager") and self.core.learning_manager:
                            pref_media = self.core.learning_manager.preferences.get("preferred_media_player")
                        pref_media = (pref_media or "vlc").lower()
                        if pref_media in self.COMMON_APPS:
                            app_match = self.COMMON_APPS[pref_media]
                except Exception:
                    pass

                if not app_match:
                    try:
                        from core.alias_manager import get_alias_manager
                        alias_entry = get_alias_manager().get_alias(raw_target)
                        if alias_entry and alias_entry.get("action_type") in ("OPEN_APPLICATION", "OPEN_APP", "app"):
                            tgt_name = alias_entry.get("target", "")
                            if tgt_name:
                                app_match = (tgt_name.lower(), tgt_name.title())
                    except Exception:
                        pass

        if app_match and self.core:
            app_id, app_display = app_match
            if tracker:
                tracker.start_intent()
                tracker.end_intent()
                tracker.start_action()

            from core.natural_responses import NaturalResponseSynthesizer
            lang = NaturalResponseSynthesizer.detect_language(raw_text)

            # Adaptive Response Policy: dispatch immediate acknowledgement to TTS
            if hasattr(self.core, "tts_manager") and self.core.tts_manager and source in ("voice", "voice_gated", "gui"):
                ack_phrase = f"{app_display} open kar raha hoon." if lang == "hi" else f"Opening {app_display}."
                try:
                    self.core.tts_manager.stream_chunk(ack_phrase, is_first=True)
                except Exception:
                    pass

            exec_res = self.core.execution_strategies.launch_application_verified(app_name=app_id)
            if exec_res.success:
                resp = (exec_res.data or {}).get("message") or NaturalResponseSynthesizer.open_app(app_display, language=lang)
                if hasattr(self.core, "active_context") and self.core.active_context:
                    self.core.active_context.set_application(app_id, action="launch_app")
            elif exec_res.reason == "not_installed":
                resp = f"'{app_display}' aapke system par installed nahi mila." if lang == "hi" else f"'{app_display}' is not installed on this system."
            else:
                resp = f"{app_display} open nahi ho paya." if lang == "hi" else f"Could not open {app_display}."

            if tracker:
                tracker.end_action()
                tracker.metrics.is_fast_path = True
            return self._finalize(turn, resp, start_time, tracker, f"open_{app_id}", source)

        # 5. Jokes (< 2ms)
        if cleaned in {"tell me a joke", "tell a joke", "koi joke sunao", "joke sunao", "ek joke sunao", "ek chutkula sunao", "hasao mujhe"}:
            if tracker:
                tracker.start_intent()
                tracker.end_intent()
                tracker.start_action()
            resp = None
            if self.core and hasattr(self.core, "conversation_engine") and self.core.conversation_engine:
                handled, conv_resp, _ = self.core.conversation_engine.process_conversation_turn("tell me a joke", [])
                if handled:
                    resp = conv_resp
            if not resp:
                resp = "Teacher: 'Homework kyun nahi kiya?'\nStudent: 'Server down tha ma'am, brain 404 Not Found dikha raha tha!' 😂"
            if tracker:
                tracker.end_action()
                tracker.metrics.is_fast_path = True
            return self._finalize(turn, resp, start_time, tracker, "tell_joke", source)

        # 6. Capabilities & Identity Queries (< 2ms)
        if cleaned in {
            "bhai tum kya kar sakte ho", "tum kya kar sakte ho", "kya kar sakte ho", "kya kya kar sakte ho",
            "bhai tum kya kar sakti ho", "tum kya kar sakti ho", "kya kar sakti ho", "kya kya kar sakti ho",
            "tum kya kar sakte ho?", "tum kya kar sakti ho?",
            "what can you do", "features batao", "help", "apne bare me batao", "who are you", "tum kaun ho"
        }:
            if tracker:
                tracker.start_intent()
                tracker.end_intent()
                tracker.start_action()
            resp = "Ji, bilkul! Main applications open/close kar sakta hoon, reminders set kar sakta hoon, audio/system control, web search aur normal conversations handle kar sakta hoon, Boss."
            if tracker:
                tracker.end_action()
                tracker.metrics.is_fast_path = True
            return self._finalize(turn, resp, start_time, tracker, "capabilities_query", source)

        # 7. Creative Drawing - Lord Ganesha / Bappa Drawing (< 15ms)
        if cleaned in self.BAPPA_DRAWING_PHRASES or (
            ("bappa" in cleaned or "ganpati" in cleaned or "ganesha" in cleaned) and
            ("drawing" in cleaned or "draw" in cleaned or "sketch" in cleaned)
        ):
            if tracker:
                tracker.start_intent()
                tracker.end_intent()
                tracker.start_action()

            try:
                drawings_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "automation", "drawings"))
                script_path = os.path.abspath(os.path.join(drawings_dir, "bappa_drawing.py"))
                if os.path.isfile(script_path):
                    import subprocess
                    subprocess.Popen([sys.executable, script_path], cwd=drawings_dir)
                elif self.core and self.core.plugin_manager and self.core.plugin_manager.get_plugin("automation"):
                    self.core.plugin_manager.execute_action("automation", "draw_bappa", {})
            except Exception as e:
                logger.error("Failed to launch Bappa drawing: %s", e)

            from core.natural_responses import NaturalResponseSynthesizer
            lang = NaturalResponseSynthesizer.detect_language(raw_text)
            resp = "Bappa ki drawing bana raha hoon, Boss." if lang == "hi" else "Drawing Bappa for you, Boss."

            if tracker:
                tracker.end_action()
                tracker.metrics.is_fast_path = True
            return self._finalize(turn, resp, start_time, tracker, "draw_bappa", source)

        # 8. Live Internet News Queries (< 50ms from cache, ~400ms from live feed)
        news_triggers = {
            "news batao", "abhi ki news kya hai", "aaj ki news", "aaj ki news kya hai",
            "latest news", "latest news kya hai", "breaking news", "breaking news kya hai",
            "headlines batao", "top headlines", "samachar sunao", "aaj ka samachar",
            "taza khabar", "taaza khabar", "what is the latest news", "what is the news",
            "tell me the news", "give me the news", "tell me the latest news", "news",
            "khabar batao", "aaj ki taza khabar"
        }
        _is_news_cue = bool(re.search(r"\b(?:news|headlines|samachar|khabar)\b", cleaned))
        if cleaned in news_triggers or (
            _is_news_cue and
            any(w in cleaned for w in ["batao", "sunao", "kya", "today", "latest", "abhi", "aaj", "live", "top", "tell", "what"])
        ):
            try:
                from core.knowledge.news import get_live_news_engine
                ne = get_live_news_engine()
                if ne.is_news_candidate(cleaned):
                    if tracker:
                        tracker.start_intent()
                        tracker.end_intent()
                        tracker.start_action()
                    news_res = ne.query(raw_text or cleaned)
                    if tracker:
                        tracker.end_action()
                        tracker.metrics.is_fast_path = True
                    try:
                        if self.core is not None and getattr(news_res, "found", False):
                            self.core._pending_news_briefing = news_res.to_briefing_dict()
                            if hasattr(self.core, "active_context") and self.core.active_context:
                                self.core.active_context.last_news_headlines = news_res.headlines
                            if hasattr(self.core, "conversation_manager") and self.core.conversation_manager:
                                self.core.conversation_manager.session.set_variable("last_news_headlines", news_res.headlines)
                    except Exception:
                        pass
                    if news_res.found or news_res.formatted_text:
                        turn.metadata["live_news"] = True
                        if hasattr(turn, "spoken_response") and news_res.spoken_text:
                            turn.spoken_response = news_res.spoken_text
                        return self._finalize(turn, news_res.formatted_text, start_time, tracker, "live_news", source)
            except Exception as e:
                logger.warning("[FAST_PATH] News handling error: %s", e)

        # 8.5. News Detail Follow-up Queries ("Pehli wali detail mein batao", "first news explain karo", "second news detail")
        if (
            any(w in cleaned for w in ["detail mein batao", "explain karo", "detail batao", "poori khabar", "kya hai ye khabar", "detail sunao", "detail mein", "detail me"])
            or bool(re.search(r"\b(?:pehli|pehla|first|doosri|doosra|second|teesri|teesra|third|chauthi|chautha|fourth|panchvi|panchva|fifth|aakhri|last)\s+(?:wali|wala|khabar|news|headline)\b", cleaned))
        ):
            headlines = None
            if self.core and hasattr(self.core, "active_context") and getattr(self.core.active_context, "last_news_headlines", None):
                headlines = self.core.active_context.last_news_headlines
            elif self.core and hasattr(self.core, "conversation_manager") and self.core.conversation_manager:
                headlines = self.core.conversation_manager.session.get_variable("last_news_headlines")
            if not headlines:
                try:
                    from core.context import RuntimeContext
                    headlines = RuntimeContext.get_instance().desktop.last_news_headlines
                except Exception:
                    pass

            if headlines and len(headlines) > 0:
                idx = 0
                idx_name = "Pehli"
                if any(w in cleaned for w in ["doosri", "doosra", "second", "2nd", "second wali"]):
                    idx = 1
                    idx_name = "Doosri"
                elif any(w in cleaned for w in ["teesri", "teesra", "third", "3rd", "third wali"]):
                    idx = 2
                    idx_name = "Teesri"
                elif any(w in cleaned for w in ["chauthi", "chautha", "fourth", "4th", "fourth wali"]):
                    idx = 3
                    idx_name = "Chauthi"
                elif any(w in cleaned for w in ["panchvi", "panchva", "fifth", "5th", "fifth wali"]):
                    idx = 4
                    idx_name = "Panchvi"
                elif any(w in cleaned for w in ["last", "aakhri", "aakhiri", "last wali"]):
                    idx = len(headlines) - 1
                    idx_name = "Aakhri"

                if 0 <= idx < len(headlines):
                    item = headlines[idx]
                    clean_t = item.clean_title() if hasattr(item, "clean_title") else getattr(item, "title", str(item))
                    source_str = getattr(item, "source", "News Source")
                    pub_str = getattr(item, "published_at", "")
                    link_str = getattr(item, "link", "")
                    time_info = f" ({pub_str})" if pub_str else ""
                    resp_detail = f"{idx_name} news headline: '{clean_t}' — Source: {source_str}{time_info}."
                    if link_str:
                        resp_detail += f"\nArticle link: {link_str}"

                    if tracker:
                        tracker.start_intent()
                        tracker.end_intent()
                        tracker.start_action()
                        tracker.end_action()
                        tracker.metrics.is_fast_path = True
                    return self._finalize(turn, resp_detail, start_time, tracker, "news_detail_followup", source)

        # 9. Automated Desktop Wallpaper Management
        try:
            from core.wallpaper import get_wallpaper_engine
            we = get_wallpaper_engine()
            is_wallpaper_req = False

            if "wallpaper" in cleaned or "desktop background" in cleaned:
                is_wallpaper_req = True
            elif we.preferences.is_awaiting_clarification():
                if any(w in cleaned for w in ("cancel", "rehne do", "radd", "chhod", "mat karo", "stop")):
                    we.preferences.clear_pending_clarification()
                    resp = "Theek hai, wallpaper change cancel kar diya, Boss."
                    return self._finalize(turn, resp, start_time, tracker, "cancel_wallpaper", source)
                is_wallpaper_req = True
            elif we.preferences.is_context_active():
                if any(w in cleaned for w in ("dusra wallpaper", "aur wallpaper", "dusra wala", "dusri wali", "next wala", "another wallpaper")) or (
                    any(w in cleaned for w in ("thoda dark", "aur dark", "dark wala", "minimal wala", "light wala")) and
                    not any(w in cleaned for w in ("volume", "sound", "awaaz", "brightness", "screen", "tab"))
                ):
                    is_wallpaper_req = True

            if is_wallpaper_req:
                if tracker:
                    tracker.start_intent()
                    tracker.end_intent()
                    tracker.start_action()
                wall_res = we.process_wallpaper_request(raw_text or cleaned)
                if tracker:
                    tracker.end_action()
                    tracker.metrics.is_fast_path = True
                if hasattr(turn, "metadata") and isinstance(turn.metadata, dict):
                    turn.metadata["wallpaper_result"] = wall_res
                return self._finalize(turn, wall_res.formatted_response, start_time, tracker, "set_wallpaper", source)
        except Exception as e:
            logger.error("[FAST_PATH] Wallpaper handling error: %s", e)

        # 10. Live Weather Subsystem (< 50ms from cache, ~300ms from public endpoints)
        try:
            from core.weather import get_weather_engine
            weather_engine = get_weather_engine()
            # Prefer the pipeline-rewritten normalized text when raw lacks weather
            # cues (e.g. follow-up "Kal ka?" rewritten to "kal ka weather batao").
            query_candidate = raw_text or cleaned
            if not weather_engine.is_weather_query(query_candidate) and weather_engine.is_weather_query(cleaned):
                query_candidate = cleaned
            if weather_engine.is_weather_query(query_candidate):
                if tracker:
                    tracker.start_intent()
                    tracker.end_intent()
                    tracker.start_action()
                w_res = weather_engine.process_weather_request(query_candidate)
                if tracker:
                    tracker.end_action()
                    tracker.metrics.is_fast_path = True
                if hasattr(turn, "metadata") and isinstance(turn.metadata, dict):
                    turn.metadata["weather_result"] = w_res
                return self._finalize(turn, w_res.formatted_response, start_time, tracker, "live_weather", source)
        except Exception as e:
            logger.error("[FAST_PATH] Weather handling error: %s", e)

        # 11. Audio Endpoint & Microphone Status Inquiry (< 5ms)
        try:
            audio_status_phrases = {
                "kaunse mic se sun rahe ho", "kaunse device se sun rahe ho", "kis device se sun rahe ho",
                "kis mic se sun rahe ho", "kahan se sun rahe ho", "which mic are you listening from",
                "which device are you listening from", "which microphone are you using", "what mic are you using",
                "active mic kya hai", "active microphone kya hai", "kaunsa mic active hai",
                "kaunsa microphone active hai", "kaunsa mic connect hai", "audio device status",
                "microphone status", "mic status", "current microphone", "current mic",
                "earbuds connected hai kya", "earbuds connect hai kya", "mic kaunsa hai",
                "kaunse earphone se sun rahe ho", "kaunse earbuds se sun rahe ho", "tum kisse sun rahe ho",
                "kis se sun rahe ho", "audio device", "active audio device", "mic check"
            }
            is_audio_inquiry = (cleaned in audio_status_phrases) or (
                any(k in cleaned for k in ["mic", "microphone", "earbuds", "headset", "audio device", "earphone"]) and
                any(w in cleaned for w in ["kaunsa", "kaunse", "kis", "kahan", "which", "what", "active", "status", "sun rahe", "listening", "using", "connected"])
            )
            if is_audio_inquiry:
                if tracker:
                    tracker.start_intent()
                    tracker.end_intent()
                    tracker.start_action()

                from voice.device_manager import AudioDeviceManager
                from core.natural_responses import NaturalResponseSynthesizer
                adm = AudioDeviceManager()
                summary = adm.get_status_summary()
                active_in = summary.get("active_device_name") or "Default Microphone"
                active_out = summary.get("active_output_name") or "Default Speakers"
                eb_name = summary.get("earbuds_name")
                is_eb = summary.get("earbuds_connected")
                lang = NaturalResponseSynthesizer.detect_language(raw_text or cleaned)

                if is_eb and eb_name:
                    if lang == "en":
                        resp = f"I am currently listening through your {eb_name} microphone and speaking through {active_out}, Boss."
                    else:
                        resp = f"Main abhi aapke {eb_name} ke microphone se sun raha hoon aur headphones se bol raha hoon, Boss."
                else:
                    if lang == "en":
                        resp = f"I am currently listening through the system microphone ({active_in}) and speaking through {active_out}, Boss."
                    else:
                        resp = f"Main abhi aapke system microphone ({active_in}) se sun raha hoon aur default speakers par bol raha hoon, Boss."

                if tracker:
                    tracker.end_action()
                    tracker.metrics.is_fast_path = True
                return self._finalize(turn, resp, start_time, tracker, "audio_device_status", source)
        except Exception as e:
            logger.error("[FAST_PATH] Audio device status handling error: %s", e)

        # 12. Mistake & Self-Learning Reflection Inquiry (< 5ms)
        try:
            mistake_inquiry_phrases = {
                "apni galtiyon se kya seekha", "tumne apni galtiyon se kya seekha", "kya seekha apni galtiyo se",
                "apni galti se kya seekha", "galtiyon se kya seekha", "what did you learn from mistakes",
                "what have you learned from your mistakes", "what did you learn from your errors",
                "apni mistake log dikhao", "mistake log", "mistakes analyze karo", "error log analyze karo",
                "galti log", "galtiyan batao", "pichhli galtiyan batao", "previous mistakes", "learned mistakes",
                "self learning summary", "reflection summary", "kya seekha hai"
            }
            is_mistake_inquiry = (cleaned in mistake_inquiry_phrases) or (
                any(k in cleaned for k in ["galti", "galtiyo", "galtiyan", "mistake", "mistakes", "error log"]) and
                any(w in cleaned for w in ["seekha", "learn", "learned", "analyze", "batao", "dikhao", "summary", "kya"])
            )
            if is_mistake_inquiry:
                if tracker:
                    tracker.start_intent()
                    tracker.end_intent()
                    tracker.start_action()

                exp_sys = getattr(self.core, "experience_system", None)
                if exp_sys and hasattr(exp_sys, "get_lessons_learned_summary"):
                    try:
                        exp_sys.digest_log_mistakes(limit=20)
                    except Exception:
                        pass
                    summary_dict = exp_sys.get_lessons_learned_summary(limit=5)
                    resp = summary_dict.get("spoken_summary") or "Main continuously apni galtiyon ko log karke unse seekh raha hoon, Boss."
                else:
                    from core.experience.log_learner import LogLearningEngine
                    engine = LogLearningEngine()
                    try:
                        engine.digest_mistakes(limit=20)
                    except Exception:
                        pass
                    summary_dict = engine.get_learned_mistakes_summary(limit=5)
                    resp = summary_dict.get("spoken_summary") or "Main continuously apni galtiyon ko log karke unse seekh raha hoon, Boss."

                if tracker:
                    tracker.end_action()
                    tracker.metrics.is_fast_path = True
                return self._finalize(turn, resp, start_time, tracker, "mistake_reflection", source)
        except Exception as e:
            logger.error("[FAST_PATH] Mistake reflection handling error: %s", e)

        # 13. Interactive Archify Architecture Visualization (< 15ms)
        try:
            is_archify_req = (
                ("archify" in cleaned) or
                ("architecture" in cleaned and any(w in cleaned for w in ("dikhao", "show", "open", "kholo", "display", "dikhai de", "dikhe", "view", "visualize", "viewer")))
            )
            if is_archify_req and not any(w in cleaned for w in ("check", "audit", "verify", "code", "explain")):
                if tracker:
                    tracker.start_intent()
                    tracker.end_intent()
                    tracker.start_action()

                arch_plug = self.core.plugin_manager.get_plugin("archify") if (self.core and self.core.plugin_manager) else None
                if arch_plug:
                    res = arch_plug.execute("show_architecture", {})
                    resp = (res.data or {}).get("message") if (res and getattr(res, "data", None)) else "Jarvis ka live runtime architecture Archify me open kar diya hai, Boss."
                else:
                    from plugins.archify.plugin import ArchifyPlugin
                    res = ArchifyPlugin().execute("show_architecture", {})
                    resp = (res.data or {}).get("message") if (res and getattr(res, "data", None)) else "Jarvis ka live runtime architecture Archify me open kar diya hai, Boss."

                if tracker:
                    tracker.end_action()
                    tracker.metrics.is_fast_path = True
                return self._finalize(turn, resp, start_time, tracker, "show_architecture", source)
        except Exception as e:
            logger.debug("[FAST_PATH] Archify handling note: %s", e)

        return None

    def _finalize(
        self,
        turn: Any,
        resp: str,
        start_time: float,
        tracker: Any,
        intent_name: str,
        source: str
    ) -> str:
        """Helper to invoke core._finalize_fast_turn if available."""
        if self.core and hasattr(self.core, "_finalize_fast_turn"):
            return self.core._finalize_fast_turn(turn, resp, start_time, tracker, intent_name, source)
        return resp
