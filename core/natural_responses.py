# core/natural_responses.py
"""
Centralized Natural Response Synthesizer & Language Mirroring for Jarvis V2.1.
Enforces the invariant: SHORT, NATURAL, CONTEXT-AWARE, AND VARIED RESPONSES.

Bans robotic responses:
  - "Command executed successfully."
  - "Operation completed."
  - "Target application launched successfully."

Produces human-like, concise responses:
  - "Ji, Chrome khol diya."
  - "Excel open ho gaya."
  - "YouTube Chrome mein khol raha hoon."
  - "Bluetooth off kar diya."
  - "Ji, dono browsers open kar diye."

Mirrors conversational language:
  - Hinglish input -> Hinglish response
  - English input -> English response
  - Hindi input -> Hindi/Hinglish response
"""

import functools
import re
import threading
from typing import Dict, List, Optional


class NaturalResponseSynthesizer:
    """
    Synthesizes concise, natural, and context-aware responses with dynamic variation rotation.
    """

    _lock = threading.Lock()
    _counters: Dict[str, int] = {}

    HINDI_INDIC_RANGE = re.compile(r"[\u0900-\u097F]")
    _WORDS_RE = re.compile(r"[a-z]+")
    HINGLISH_MARKERS = {
        "karo", "kholo", "chalao", "band", "batao", "dikhao", "hai", "hain", "kya",
        "ka", "ki", "ke", "ko", "se", "aur", "ye", "yeh", "woh", "wahi", "usko",
        "isko", "nahi", "nahin", "haan", "dono", "sab", "saare", "sabhi", "bhai",
        "yaar", "kardo", "kar", "do", "bana", "banao", "chalu", "me", "mein", "par",
        "pe", "kitna", "kitne", "wala", "wali", "wale", "ji", "ek", "dusra", "dusri"
    }

    @classmethod
    @functools.lru_cache(maxsize=512)
    def detect_language(cls, text: str) -> str:
        """
        Detects if input is English, Hindi, or Hinglish using precompiled regex and LRU cache.
        Returns 'hi' for Hindi/Hinglish, 'en' for English.
        """
        if not text:
            return "hi"
        if cls.HINDI_INDIC_RANGE.search(text):
            return "hi"
        lowered = text.lower()
        words = set(cls._WORDS_RE.findall(lowered))
        overlap = words.intersection(cls.HINGLISH_MARKERS)
        if overlap:
            return "hi"  # Conversational Hinglish / Hindi
        return "en"

    @classmethod
    def _next_variation(cls, key: str, options: List[str]) -> str:
        """Picks the next variation in round-robin fashion for the given category."""
        if not options:
            return ""
        with cls._lock:
            idx = cls._counters.get(key, 0)
            cls._counters[key] = (idx + 1) % len(options)
        return options[idx]

    @classmethod
    def open_app(cls, app_name: str, language: str = "hi") -> str:
        """Short, natural response for opening an application."""
        display_name = (app_name or "").replace("_", " ").strip().title().replace("Ide", "IDE")
        if language == "en":
            options = [
                f"Opened {display_name}.",
                f"{display_name} is open.",
                f"Launched {display_name}.",
            ]
            return cls._next_variation(f"open_app_en_{display_name.lower()}", options)
        else:
            options = [
                f"Ji, {display_name} khol diya.",
                f"{display_name} open ho gaya.",
                f"Ji, {display_name} open kar diya.",
                f"{display_name} launch kar diya hai.",
            ]
            return cls._next_variation(f"open_app_hi_{display_name.lower()}", options)

    @classmethod
    def close_app(cls, app_name: str, language: str = "hi") -> str:
        """Short, natural response for closing an application."""
        display_name = (app_name or "").replace("_", " ").strip().title().replace("Ide", "IDE")
        if language == "en":
            options = [
                f"Closed {display_name}.",
                f"{display_name} has been closed.",
            ]
            return cls._next_variation(f"close_app_en_{display_name.lower()}", options)
        else:
            options = [
                f"{display_name} band kar diya.",
                f"{display_name} close ho gaya.",
                f"Ji, {display_name} band kar diya hai.",
            ]
            return cls._next_variation(f"close_app_hi_{display_name.lower()}", options)

    @classmethod
    def open_website(cls, site: str, container: str = "", language: str = "hi") -> str:
        """Short, natural response for opening a website (optionally inside a browser)."""
        disp_site = (site or "").strip().title()
        disp_container = (container or "").strip().title()

        if disp_container:
            if language == "en":
                options = [
                    f"Opening {disp_site} in {disp_container}.",
                    f"Opened {disp_site} in {disp_container}.",
                ]
                return cls._next_variation(f"open_web_cont_en_{disp_site.lower()}", options)
            else:
                options = [
                    f"{disp_site} {disp_container} mein khol raha hoon.",
                    f"Ji, {disp_site} {disp_container} mein open kar diya.",
                    f"{disp_container} mein {disp_site} open kar diya.",
                ]
                return cls._next_variation(f"open_web_cont_hi_{disp_site.lower()}", options)
        else:
            if language == "en":
                options = [
                    f"Opened {disp_site}.",
                    f"{disp_site} is open in your browser.",
                ]
                return cls._next_variation(f"open_web_en_{disp_site.lower()}", options)
            else:
                options = [
                    f"Ji, {disp_site} khol diya.",
                    f"{disp_site} open ho gaya.",
                    f"{disp_site} browser mein open kar diya.",
                ]
                return cls._next_variation(f"open_web_hi_{disp_site.lower()}", options)

    @classmethod
    def toggle_device(cls, device: str, state: bool, language: str = "hi") -> str:
        """Short, natural response for device toggles like Bluetooth or Wi-Fi."""
        disp_dev = (device or "Device").strip().title()
        state_str_en = "on" if state else "off"
        state_str_hi = "chalu" if state else "band"

        if language == "en":
            if state:
                options = [
                    f"{disp_dev} is turned on.",
                    f"Enabled {disp_dev}.",
                ]
            else:
                options = [
                    f"{disp_dev} is turned off.",
                    f"Disabled {disp_dev}.",
                ]
            return cls._next_variation(f"toggle_en_{disp_dev.lower()}_{state_str_en}", options)
        else:
            if state:
                options = [
                    f"{disp_dev} on kar diya.",
                    f"{disp_dev} chalu kar diya hai.",
                ]
            else:
                options = [
                    f"{disp_dev} off kar diya.",
                    f"{disp_dev} band kar diya.",
                ]
            return cls._next_variation(f"toggle_hi_{disp_dev.lower()}_{state_str_hi}", options)

    @classmethod
    def multi_entity_result(
        cls,
        action: str,
        succeeded: List[str],
        failed: List[str],
        entity_type: str = "applications",
        language: str = "hi",
    ) -> str:
        """Natural feedback for multi-entity executions (e.g. 'Ji, dono browsers open kar diye.')."""
        verb = (action or "open").lower().strip()

        # Helper to join list
        def _join_en(names: List[str]) -> str:
            if not names:
                return ""
            if len(names) == 1:
                return names[0]
            if len(names) == 2:
                return f"{names[0]} and {names[1]}"
            return f"{', '.join(names[:-1])} and {names[-1]}"

        def _join_hi(names: List[str]) -> str:
            if not names:
                return ""
            if len(names) == 1:
                return names[0]
            if len(names) == 2:
                return f"{names[0]} aur {names[1]}"
            return f"{', '.join(names[:-1])} aur {names[-1]}"

        # Detect if entities are browsers
        is_all_browsers = bool(
            succeeded and all(any(b in s.lower() for b in ("chrome", "brave", "edge", "firefox", "opera")) for s in succeeded)
        )
        cat_hi = "browsers" if is_all_browsers else "applications"
        cat_en = "browsers" if is_all_browsers else "applications"

        if verb in ("open", "launch", "start", "run"):
            if succeeded and not failed:
                if len(succeeded) == 2:
                    if language == "en":
                        options = [
                            f"Opened both {cat_en}.",
                            f"{_join_en(succeeded)} are now open.",
                        ]
                    else:
                        options = [
                            f"Ji, dono {cat_hi} open kar diye.",
                            f"{_join_hi(succeeded)} dono open ho gaye.",
                        ]
                    return cls._next_variation("multi_open_2", options)
                else:
                    if language == "en":
                        options = [
                            f"Opened all {len(succeeded)} {cat_en}.",
                            f"{_join_en(succeeded)} are all open.",
                        ]
                    else:
                        options = [
                            f"Ji, sabhi {cat_hi} open kar diye.",
                            f"{_join_hi(succeeded)} sab open ho gaye.",
                        ]
                    return cls._next_variation("multi_open_many", options)

            elif succeeded and failed:
                if language == "en":
                    return f"{_join_en(succeeded)} opened, but {_join_en(failed)} could not be opened."
                else:
                    return f"{_join_hi(succeeded)} open ho gaye, lekin {_join_hi(failed)} open nahi ho paaya."
            else:
                if language == "en":
                    return "None of the requested applications could be opened."
                else:
                    return "Koi bhi app open nahi ho paya."

        elif verb in ("close", "band"):
            if succeeded and not failed:
                if len(succeeded) == 2:
                    if language == "en":
                        return f"Closed both {cat_en}."
                    else:
                        return f"Ji, dono {cat_hi} band kar diye."
                else:
                    if language == "en":
                        return f"Closed all {len(succeeded)} {cat_en}."
                    else:
                        return f"{_join_hi(succeeded)} sab band ho gaye."
            elif succeeded and failed:
                if language == "en":
                    return f"{_join_en(succeeded)} closed, but {_join_en(failed)} could not be closed."
                else:
                    return f"{_join_hi(succeeded)} band ho gaye, lekin {_join_hi(failed)} band nahi ho paya."
            else:
                if language == "en":
                    return "Could not close the requested applications."
                else:
                    return "Target apps band nahi ho paaye."

        # Fallback generic
        if succeeded and not failed:
            if language == "en":
                return f"{_join_en(succeeded)} {verb} completed."
            else:
                return f"{_join_hi(succeeded)} {verb} ho gaye."
        elif succeeded and failed:
            if language == "en":
                return f"{_join_en(succeeded)} succeeded, {_join_en(failed)} failed."
            else:
                return f"{_join_hi(succeeded)} complete ho gaye, lekin {_join_hi(failed)} nahi hue."
        else:
            if language == "en":
                return f"Action {verb} failed."
            else:
                return f"Action {verb} complete nahi ho paya."

    @classmethod
    def generate_password(cls, length: int, password: str, language: str = "hi") -> str:
        """Natural response for generated password."""
        if language == "en":
            options = [
                f"Generated a {length}-character secure password and copied to clipboard: {password}",
                f"Here is your {length}-character secure password (copied to clipboard): {password}",
            ]
            return cls._next_variation("gen_pwd_en", options)
        else:
            options = [
                f"Ji, {length} characters ka secure password generate karke clipboard par copy kar diya hai: {password}",
                f"{length} digit ka secure password generate kar diya hai aur clipboard par copy kar diya: {password}",
            ]
            return cls._next_variation("gen_pwd_hi", options)

    @classmethod
    def system_maintenance(
        cls,
        action: str,
        target: str = "temp",
        is_repeat: bool = False,
        language: str = "hi",
        safety_reassurance: bool = False,
    ) -> str:
        """
        Short, natural response for system maintenance actions (temp cleanup, recycle bin).
        Rotates between natural variations.
        """
        is_temp = "temp" in action.lower() or "temp" in target.lower()
        if safety_reassurance:
            if is_temp:
                if language == "en":
                    options = [
                        "Done. Your personal files are safe, only temporary junk files were cleaned.",
                        "Done. Cleaned temporary files without touching your personal files.",
                    ]
                    return cls._next_variation("maint_temp_safe_en", options)
                else:
                    options = [
                        "Done. Aapki personal files safe hain, sirf temporary junk files clean kiye hain.",
                        "Ji, aapki personal files ko touch nahi kiya gaya hai, sirf temporary files clean kar diye hain.",
                    ]
                    return cls._next_variation("maint_temp_safe_hi", options)
            else:
                if language == "en":
                    options = [
                        "Done. Emptied Recycle Bin without touching your active personal files.",
                    ]
                    return cls._next_variation("maint_recycle_safe_en", options)
                else:
                    options = [
                        "Done. Recycle Bin clear kar diya hai, aapki personal files bilkul safe hain.",
                    ]
                    return cls._next_variation("maint_recycle_safe_hi", options)

        if is_temp:
            if is_repeat:
                if language == "en":
                    options = [
                        "Done, temp cleanup repeated.",
                        "Done. Temp files cleaned again.",
                    ]
                    return cls._next_variation("maint_temp_repeat_en", options)
                else:
                    options = [
                        "Done, temp cleanup dobara kar diya.",
                        "Ho gaya, temp cleanup phir se kar diya.",
                    ]
                    return cls._next_variation("maint_temp_repeat_hi", options)
            else:
                if language == "en":
                    options = [
                        "Done. Temp cleanup complete.",
                        "Done. Temp files cleaned.",
                    ]
                    return cls._next_variation("maint_temp_en", options)
                else:
                    options = [
                        "Done. Temp files clean kar diye.",
                        "Done. Temp cleanup complete.",
                    ]
                    return cls._next_variation("maint_temp_hi", options)
        else:
            # Recycle bin
            if is_repeat:
                if language == "en":
                    options = [
                        "Recycle Bin cleared again.",
                        "Done, recycle bin emptied once more.",
                    ]
                    return cls._next_variation("maint_recycle_repeat_en", options)
                else:
                    options = [
                        "Recycle Bin dobara clear kar diya hai.",
                        "Recycle Bin phir se khali kar diya hai.",
                    ]
                    return cls._next_variation("maint_recycle_repeat_hi", options)
            else:
                if language == "en":
                    options = [
                        "Recycle Bin clear kar diya hai.",
                        "Recycle Bin has been emptied.",
                    ]
                    return cls._next_variation("maint_recycle_en", options)
                else:
                    options = [
                        "Recycle Bin clear kar diya hai.",
                        "Recycle Bin khali kar diya hai.",
                    ]
                    return cls._next_variation("maint_recycle_hi", options)

