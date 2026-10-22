# core/response_policy.py
"""
Centralized Conversational Feedback & Response Policy Engine.
Enforces the response invariant:
    DIRECT ANSWER → OPTIONAL USEFUL DETAIL → STOP

Generates human-like, concise, context-aware, and relevance-driven responses
without exposing internal process names, window handles, technical metadata,
or debug bracketed text.
"""

import re
from typing import Any, Dict, List, Optional
from core.natural_responses import NaturalResponseSynthesizer


class ConversationalResponsePolicy:
    """
    Centralized policy engine formulating natural, human-grade conversational feedback.
    Adapts detail level strictly based on the user's explicit question and intent.
    """

    @staticmethod
    def clean_window_title(title: str, app_name: str = "") -> str:
        """
        Cleans technical suffixes, process labels, and raw brackets from window titles
        for natural spoken/chat delivery.
        """
        if not title:
            return ""

        cleaned = title.strip()
        # Remove surrounding quotes or brackets if present
        cleaned = re.sub(r"^['\"(\[]+|['\")\]]+$", "", cleaned).strip()

        # Remove repetitive application suffix like "- Google Chrome", "- Brave", "- Visual Studio Code"
        # only if a meaningful title remains before it
        patterns_to_strip = [
            r"\s*-\s*Google Chrome$",
            r"\s*-\s*Brave$",
            r"\s*-\s*Microsoft Edge$",
            r"\s*-\s*Mozilla Firefox$",
            r"\s*-\s*Visual Studio Code$",
            r"\s*-\s*Notepad$",
            r"\s*-\s*VLC media player$",
        ]
        for pat in patterns_to_strip:
            m = re.search(pat, cleaned, re.IGNORECASE)
            if m and len(cleaned[:m.start()].strip()) > 2:
                cleaned = cleaned[:m.start()].strip()
                break

        return cleaned

    @classmethod
    def format_status_response(
        cls,
        query: str,
        target: str,
        is_open: bool,
        is_active: bool = False,
        is_minimized: bool = False,
        is_running: bool = False,
        window_title: str = "",
        browser: str = "",
        multiple_count: int = 1
    ) -> str:
        """
        Formats application/window/tab status inquiry responses based strictly on what the user asked.
        Follows: DIRECT ANSWER → OPTIONAL USEFUL DETAIL → STOP.
        """
        q = (query or "").lower().strip(" .?!")
        # Clean potential browser-query noise from target name
        clean_target = re.sub(
            r"\b(?:konse|kaun\s+se|kaunse|kis|which|kahan|kidhar|browser|brouser|browzer|broser|mein|me|par|pe|open|hai|khula)\b",
            "",
            target or "",
            flags=re.IGNORECASE
        ).strip()
        display_target = clean_target if clean_target else (target or "Application")
        target_name = display_target.capitalize()

        # 1. Negative Check: "Chrome open nahi hai na?", "closed hai na?", "band hai na?"
        is_negative_check = bool(
            re.search(r"\b(?:nahi\s+hai\s+na|not\s+open|closed\s+hai\s+na|band\s+hai\s+na)\b", q)
        )
        if is_negative_check:
            if is_open or is_running:
                return f"Nahi, {target_name} open hai."
            return f"Nahi, {target_name} abhi open nahi hai."

        # 2. Specific Window Inquiry: "Chrome kaunsa window open hai?", "Kaunsa Chrome window active hai?", "which window is open?"
        is_which_window = bool(
            re.search(r"\b(?:kaunsa|kaunsi|konsa|konsi|which)(?:\s+\w+)?\s+(?:window|tab)\b", q)
            or re.search(r"\b(?:window|tab)\s+(?:kaunsa|kaunsi|konsa|konsi)\b", q)
            or re.search(r"\b(?:kaunsa|kaunsi|konsa|konsi)\s+(?:hai|wala)\b", q)
        )
        if is_which_window:
            clean_title = cls.clean_window_title(window_title, target)
            if not is_open:
                return f"Nahi, {target_name} abhi open nahi hai."

            title_display = f"‘{clean_title}’" if clean_title else target_name
            if "active" in q or is_active:
                return f"{title_display} wala window active hai."
            return f"{title_display} wala window open hai."

        # 3. Active / Foreground Check: "Chrome active hai kya?", "is Chrome active?", "focused hai kya?"
        is_active_check = bool(
            re.search(r"\b(?:active|foreground|focused|focus)\b", q)
        )
        if is_active_check:
            if not is_open:
                return f"Nahi, {target_name} abhi open nahi hai."
            if is_active:
                return f"Haan, {target_name} active hai."
            if is_minimized:
                return f"{target_name} open hai, lekin minimized hai."
            return f"{target_name} open hai, lekin abhi active nahi hai."

        # 4. Running / Process Check: "Chrome chal raha hai?", "is Chrome running?", "process chal raha hai?"
        is_running_check = bool(
            re.search(r"\b(?:chal\s+raha|running|process)\b", q)
        )
        if is_running_check:
            if is_open or is_running:
                return f"Haan, {target_name} chal raha hai."
            return f"Nahi, {target_name} abhi nahi chal raha."

        # 5. Minimized Check: "Chrome minimized hai kya?"
        is_minimized_check = bool(
            re.search(r"\b(?:minimized|minimize)\b", q)
        )
        if is_minimized_check:
            if not is_open:
                return f"Nahi, {target_name} abhi open nahi hai."
            if is_minimized:
                return f"Haan, {target_name} minimized hai."
            return f"Nahi, {target_name} open hai aur screen par dikh raha hai."

        # 5.5. Browser Location Inquiry: "YouTube kaun se browser mein open hai?", "kis browser me hai?", "kahan open hai?"
        is_browser_loc = bool(
            re.search(r"\b(?:kaun\s+se|kaunse|konse|kis|which|what)\s+(?:browser|brouser|browzer|broser|tab|window)\b", q)
            or re.search(r"\b(?:browser|brouser|browzer|broser)\s+(?:me(?:in)?|mein|par|pe)\b", q)
            or re.search(r"\b(?:kahan|kidhar)\s+(?:open|khula|chal\s+raha)\b", q)
            or re.search(r"\b(?:kisi\s+bhi\s+browser)\b", q)
        )
        if is_browser_loc:
            browser_map = {
                "chrome": "Google Chrome",
                "msedge": "Microsoft Edge",
                "edge": "Microsoft Edge",
                "brave": "Brave",
                "firefox": "Mozilla Firefox"
            }
            b_display = browser_map.get(browser.lower(), browser.capitalize()) if browser else "browser"
            is_english = not any(w in q for w in ("hai", "mein", "me", "kahan", "kidhar", "kaun", "konse", "kis", "kisi"))
            if is_open:
                if is_english:
                    return f"Sir, I checked and {target_name} is currently open in {b_display}."
                return f"Sir, maine check kiya, {target_name} abhi {b_display} mein open hai."
            else:
                if is_english:
                    return f"Sir, I checked and {target_name} is not open in any browser. Would you like me to open {target_name}?"
                return f"Sir, maine check kiya, {target_name} abhi kisi bhi browser mein open nahi hai. Kya aap {target_name} open karna chahte hain?"

        # 6. General / Default Open Check: "Chrome open hai kya?", "is Chrome open?", "kya Chrome open hai?"
        if is_open:
            # If opened as a website tab inside a specific browser (e.g. YouTube in Brave)
            if browser:
                return f"Haan, {target_name} {browser.capitalize()} mein open hai."

            # Minimized state is useful additional context for open status
            if is_minimized:
                return f"{target_name} open hai, lekin minimized hai."

            return f"Haan, {target_name} open hai."

        if is_running:
            return f"{target_name} background mein chal raha hai."

        return f"Nahi, {target_name} abhi open nahi hai."

    @classmethod
    def format_screen_inspection(
        cls,
        foreground_win: Any,
        all_windows: List[Any],
        is_list_request: bool = False,
        is_capability_request: bool = False
    ) -> str:
        """
        Formats screen awareness answers naturally without process filenames or technical parenthetical dumps.
        """
        # Capability inquiry: "Kya tum screen dekh sakte ho?"
        if is_capability_request:
            if not foreground_win:
                return "Ji haan Boss! Main aapki screen dekh sakta hoon. Abhi screen par koi active window open nahi hai."
            clean_name = getattr(foreground_win, "clean_name", "") or getattr(foreground_win, "process_name", "") or "App"
            clean_name = clean_name.replace(".exe", "").capitalize()
            return f"Ji haan Boss! Main aapki screen dekh sakta hoon. Abhi screen par foreground mein {clean_name} open hai."

        # List request: "Konsi windows open hain?"
        if is_list_request:
            valid_names = []
            for w in (all_windows or []):
                pname = getattr(w, "process_name", "") or ""
                pname = pname.replace(".exe", "").capitalize()
                if pname and pname not in valid_names and pname not in ("Active Window", "Program Manager", "Explorer"):
                    valid_names.append(pname)
            if valid_names:
                names_str = ", ".join(valid_names[:4])
                return f"Abhi aapke laptop ki screen par {names_str} open hain, Boss."
            return "Abhi screen par koi active application window open nahi hai, Boss."

        # General: "Screen par kya open hai?"
        if foreground_win and getattr(foreground_win, "title", ""):
            fg_title = getattr(foreground_win, "title", "")
            if fg_title not in ("Active Window", "Program Manager"):
                pname = getattr(foreground_win, "process_name", "") or "App"
                pname = pname.replace(".exe", "").capitalize()
                clean_title = cls.clean_window_title(fg_title, pname)
                if clean_title and clean_title.lower() != pname.lower():
                    return f"Abhi screen par foreground mein ‘{clean_title}’ wala {pname} open hai."
                return f"Abhi screen par foreground mein {pname} open hai."

        return "Abhi screen par koi active application open nahi hai, Boss."
