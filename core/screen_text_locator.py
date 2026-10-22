# core/screen_text_locator.py
"""
Screen & Focused Window Text Locator with Visual Mouse Guidance.

Inspects the user's active/foreground window or desktop screen to locate
specified text elements using multi-strategy inspection:
1. Windows UIAutomation (Controls, TextPattern, ValuePattern) with RapidFuzz
2. Screen/Window OCR Fallback (Pytesseract/Windows OCR)
3. Smooth human-like mouse cursor movement to target coordinates
4. Conversational relative position feedback
"""

from dataclasses import dataclass
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.core.screen_text_locator")

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


@dataclass
class TextMatchResult:
    text: str
    matched_text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    center_x: int
    center_y: int
    window_title: str = ""
    process_name: str = ""
    strategy: str = "uia"


class ScreenTextLocator:
    """Authoritative screen text locator and visual pointer."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self._uia_client = None
        self._init_uia()

    def _init_uia(self):
        try:
            import comtypes.client
            try:
                # pyrefly: ignore [missing-import]
                from comtypes.gen import UIAutomationClient
            except ImportError:
                comtypes.client.GetModule("UIAutomationCore.dll")
                # pyrefly: ignore [missing-import]
                from comtypes.gen import UIAutomationClient
            self._uia_client = comtypes.client.CreateObject(UIAutomationClient.CUIAutomation)
            self._uia_module = UIAutomationClient
            logger.info("UIAutomation initialized successfully.")
        except Exception as e:
            logger.debug(f"UIAutomation initialization note: {e}")
            self._uia_client = None
            self._uia_module = None

    def get_foreground_window_info(self) -> Dict[str, Any]:
        """Returns details about currently active foreground window."""
        info = {
            "hwnd": 0,
            "title": "",
            "process_name": "",
            "rect": (0, 0, 0, 0)
        }
        try:
            # pyrefly: ignore [untyped-import]
            import win32gui
            # pyrefly: ignore [untyped-import]
            import win32process
            # pyrefly: ignore [untyped-import]
            import psutil

            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                info["hwnd"] = hwnd
                info["title"] = (win32gui.GetWindowText(hwnd) or "").strip()
                try:
                    info["rect"] = win32gui.GetWindowRect(hwnd)
                except Exception:
                    pass
                try:
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid:
                        proc = psutil.Process(pid)
                        info["process_name"] = proc.name()
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"get_foreground_window_info error: {e}")
        return info

    def _clean_query_text(self, text: str) -> str:
        """Strips conversational noise and extracts core search string."""
        if not text:
            return ""
        s = text.strip()

        # Visual search gating: reject UI object control commands / deictic references from visual text search
        # (e.g., 'is window ko close karo', 'se window ko close karo', 'isko band karo', 'ye window')
        cmd_words = {"close", "band", "minimize", "maximize", "restore", "kholo", "open", "hatao", "lao", "terminate", "kill"}
        obj_words = {"window", "app", "application", "tab", "screen", "cursor", "pointer"}
        deictic_words = {"is", "iss", "se", "ye", "yeh", "this", "current", "active", "isko", "ise", "isse", "isey"}

        low = s.lower().strip()
        tokens = set(re.findall(r'[a-zA-Z0-9]+', low))

        has_cmd = bool(tokens & cmd_words)
        has_obj_or_deictic = bool((tokens & obj_words) or (tokens & deictic_words))
        if has_cmd and has_obj_or_deictic:
            return ""
        if tokens.issubset(deictic_words | obj_words | {"ko", "ka", "ki", "ke", "karo", "kar", "do", "kijiye"}):
            return ""

        # Remove surrounding quotes
        s = re.sub(r"^[\"']|[\"']$", "", s).strip()
        # Remove leading markers like 'word', 'text', 'ye', 'the', 'ismein', 'screen par', etc.
        s = re.sub(
            r"^(?:the\s+word|the\s+text|word|text|ye\s+word|ye\s+text|yeh\s+word|yeh\s+text|the|"
            r"ismein|isme|ispe|yahan|idhar|is\s+page\s+par|is\s+page\s+pe|is\s+window\s+mein|is\s+window\s+me|"
            r"is\s+screen\s+par|is\s+screen\s+pe|screen\s+par|screen\s+pe|window\s+mein|window\s+me)\s+",
            "",
            s,
            flags=re.IGNORECASE
        ).strip()
        # Remove trailing Hindi particles and location phrases
        s = re.sub(
            r"\s+(?:ko|ka|ki|kahan|kidhar|kahan\s+hai|kidhar\s+hai|kahan\s+likha\s+hai|kidhar\s+likha\s+hai|"
            r"kahan\s+par|likha\s+hai|likhi\s+hai|likha\s+hua\s+hai|likha|likhi)$",
            "",
            s,
            flags=re.IGNORECASE
        ).strip()
        return s

    @staticmethod
    def _normalize_transliteration(text: str) -> str:
        """Normalizes common Hindi-English phonetic variations (e.g., aashram/ashram)."""
        w = text.lower().strip()
        w = re.sub(r'aa+', 'a', w)
        w = re.sub(r'ee+', 'i', w)
        w = re.sub(r'oo+', 'u', w)
        w = re.sub(r'sh+', 's', w)
        return w

    def _score_text_match(self, query: str, candidate: str) -> float:
        """
        Robust scoring similarity between query and candidate text.
        Handles:
        1. Exact match (1.0)
        2. Substring phrase match (0.98)
        3. Phonetic/transliteration phrase match e.g. 'aashram' vs 'ashram' (0.96)
        4. Multi-word coverage: multi-word query words must all be reasonably matched.
           Single-word partial matches (e.g. 'Paramhans' for 'paramhans aashram') are rejected.
        5. Single-word fuzzy match with rapidfuzz / Levenshtein
        """
        if not candidate or not query:
            return 0.0
        q_raw = query.lower().strip()
        c_raw = candidate.lower().strip()

        if q_raw == c_raw:
            return 1.0

        q_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', q_raw)
        c_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', c_raw)

        q_words = [w for w in q_clean.split() if w]
        c_words = [w for w in c_clean.split() if w]

        if not q_words or not c_words:
            return 0.0

        # Exact phrase substring
        if q_raw in c_raw:
            return 0.98

        # Normalized phrase substring (handles 'aashram' vs 'ashram')
        q_norm = " ".join(self._normalize_transliteration(w) for w in q_words)
        c_norm = " ".join(self._normalize_transliteration(w) for w in c_words)
        if q_norm in c_norm:
            return 0.96

        if HAS_RAPIDFUZZ:
            # Multi-word query token recall
            if len(q_words) >= 2:
                word_scores = []
                for qw in q_words:
                    qw_norm = self._normalize_transliteration(qw)
                    best_w = 0.0
                    for cw in c_words:
                        if qw == cw:
                            best_w = 100.0
                            break
                        cw_norm = self._normalize_transliteration(cw)
                        if qw_norm == cw_norm:
                            best_w = max(best_w, 95.0)
                            continue
                        r1 = fuzz.ratio(qw, cw)
                        r2 = fuzz.ratio(qw_norm, cw_norm)
                        r = max(r1, r2)
                        if r > best_w:
                            best_w = r
                        # Substring only if both words are substantial (>= 4 chars)
                        if len(qw) >= 4 and len(cw) >= 4 and (qw in cw or cw in qw):
                            sub_ratio = min(len(qw), len(cw)) / max(len(qw), len(cw))
                            best_w = max(best_w, sub_ratio * 90.0)
                    word_scores.append(best_w)

                matched_count = sum(1 for s in word_scores if s >= 75.0)
                coverage = matched_count / len(q_words)
                avg_score = sum(word_scores) / max(len(word_scores), 1)

                if coverage < 0.75:
                    return min(0.40, (avg_score / 100.0) * coverage)
                return min(1.0, (avg_score / 100.0))

            # Single word query
            token_ratio = fuzz.token_set_ratio(q_raw, c_raw) / 100.0
            partial_ratio = fuzz.partial_ratio(q_raw, c_raw) / 100.0
            ratio = fuzz.ratio(q_norm, c_norm) / 100.0
            return min(1.0, max(token_ratio, partial_ratio, ratio))
        else:
            # Fallback word-overlap
            q_set = set(q_words)
            c_set = set(c_words)
            if q_set.issubset(c_set):
                return 0.92
            overlap = len(q_set.intersection(c_set)) / len(q_set)
            return overlap * 0.85

    def _search_uia_element_tree(
        self,
        root_element: Any,
        target_clean: str,
        max_nodes: int = 800
    ) -> Optional[TextMatchResult]:
        """Breadth-first search traversing UIA element hierarchy."""
        if not root_element:
            return None

        from collections import deque
        queue = deque([root_element])
        nodes_checked = 0
        best_match: Optional[TextMatchResult] = None
        best_score = 0.0

        walker = None
        if self._uia_client:
            try:
                walker = self._uia_client.ControlViewWalker
            except Exception:
                walker = None

        sw, sh = 1920, 1080
        try:
            # pyrefly: ignore [untyped-import]
            import pyautogui
            sw, sh = pyautogui.size()
        except Exception:
            pass

        while queue and nodes_checked < max_nodes:
            el = queue.popleft()
            nodes_checked += 1

            try:
                name = getattr(el, "CurrentName", "") or ""
                rect = getattr(el, "CurrentBoundingRectangle", None)

                # Check Name match
                if name and rect:
                    score = self._score_text_match(target_clean, name)
                    if score > best_score and score >= 0.80:
                        w = rect.right - rect.left
                        h = rect.bottom - rect.top
                        if w > 0 and h > 0:
                            cx = rect.left + w // 2
                            cy = rect.top + h // 2
                            # Must be within visible screen viewport
                            if 0 <= cx < sw and 0 <= cy < sh:
                                best_score = score
                                best_match = TextMatchResult(
                                    text=target_clean,
                                    matched_text=name,
                                    confidence=score,
                                    x=rect.left,
                                    y=rect.top,
                                    width=w,
                                    height=h,
                                    center_x=cx,
                                    center_y=cy,
                                    strategy="uia_name"
                                )
                                if score >= 0.99:
                                    return best_match

                # Check ValuePattern (for edit controls, search bars, inputs)
                if self._uia_module and hasattr(el, "GetCurrentPattern") and rect:
                    try:
                        val_pat = el.GetCurrentPattern(self._uia_module.UIA_ValuePatternId)
                        if val_pat:
                            val_obj = val_pat.QueryInterface(self._uia_module.IUIAutomationValuePattern)
                            val_text = getattr(val_obj, "CurrentValue", "") or ""
                            if val_text:
                                score = self._score_text_match(target_clean, val_text)
                                if score > best_score and score >= 0.80:
                                    w = rect.right - rect.left
                                    h = rect.bottom - rect.top
                                    if w > 0 and h > 0:
                                        cx = rect.left + w // 2
                                        cy = rect.top + h // 2
                                        if 0 <= cx < sw and 0 <= cy < sh:
                                            best_score = score
                                            best_match = TextMatchResult(
                                                text=target_clean,
                                                matched_text=val_text,
                                                confidence=score,
                                                x=rect.left,
                                                y=rect.top,
                                                width=w,
                                                height=h,
                                                center_x=cx,
                                                center_y=cy,
                                                strategy="uia_value"
                                            )
                                            if score >= 0.99:
                                                return best_match
                    except Exception:
                        pass

                # Add children to queue via ControlViewWalker
                if walker:
                    try:
                        child = walker.GetFirstChildElement(el)
                        while child and len(queue) < max_nodes:
                            queue.append(child)
                            child = walker.GetNextSiblingElement(child)
                    except Exception:
                        pass
            except Exception:
                continue

        return best_match

    def _locate_via_uia(self, hwnd: int, target_clean: str) -> Optional[TextMatchResult]:
        """Locates text using Windows UI Automation on specific window or desktop."""
        if not self._uia_client:
            return None

        # 1. Try from window handle
        if hwnd:
            try:
                win_element = self._uia_client.ElementFromHandle(hwnd)
                if win_element:
                    match = self._search_uia_element_tree(win_element, target_clean)
                    if match:
                        return match
            except Exception as e:
                logger.debug(f"ElementFromHandle failed for hwnd={hwnd}: {e}")

        # 2. Try from Focused Element
        try:
            focused = self._uia_client.GetFocusedElement()
            if focused:
                match = self._search_uia_element_tree(focused, target_clean, max_nodes=200)
                if match:
                    return match
        except Exception:
            pass

        return None

    def _locate_via_ocr(
        self,
        bbox: Optional[Tuple[int, int, int, int]],
        target_clean: str
    ) -> Optional[TextMatchResult]:
        """OCR text locator using Windows Native WinRT OCR with fallback to pytesseract."""
        clamped_bbox = None
        if bbox:
            bx1 = max(0, bbox[0])
            by1 = max(0, bbox[1])
            bx2 = max(bx1 + 10, bbox[2])
            by2 = max(by1 + 10, bbox[3])
            clamped_bbox = (bx1, by1, bx2, by2)

        try:
            from PIL import ImageGrab
            screenshot = ImageGrab.grab(bbox=clamped_bbox) if clamped_bbox else ImageGrab.grab()
        except Exception:
            try:
                # pyrefly: ignore [untyped-import]
                import pyautogui
                screenshot = pyautogui.screenshot()
                if clamped_bbox:
                    screenshot = screenshot.crop(clamped_bbox)
            except Exception as e:
                logger.debug(f"Screen capture note: {e}")
                return None

        offset_x = clamped_bbox[0] if clamped_bbox else 0
        offset_y = clamped_bbox[1] if clamped_bbox else 0

        # Method 1: Windows Native WinRT OCR (fast, built-in, offline)
        try:
            import winocr
            import asyncio
            import concurrent.futures

            def _run_winocr_sync():
                try:
                    async def _runner():
                        return await winocr.recognize_pil(screenshot, "en")
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        return pool.submit(lambda: asyncio.run(_runner())).result(timeout=4.0)
                except Exception as ex:
                    logger.debug(f"winocr recognition note: {ex}")
                    return None

            ocr_res = _run_winocr_sync()
            if ocr_res and hasattr(ocr_res, "lines") and ocr_res.lines:
                target_words = target_clean.lower().split()
                best_match: Optional[TextMatchResult] = None
                best_score = 0.0

                for line in ocr_res.lines:
                    line_text = getattr(line, "text", "") or ""
                    if not line_text:
                        continue

                    score = self._score_text_match(target_clean, line_text)

                    if score > best_score and score >= 0.75:
                        matched_words = []
                        for w in getattr(line, "words", []):
                            w_clean = re.sub(r'[^a-zA-Z0-9]', '', getattr(w, "text", "")).lower()
                            if not w_clean:
                                continue
                            w_norm = self._normalize_transliteration(w_clean)
                            for tw in target_words:
                                tw_norm = self._normalize_transliteration(tw)
                                if (HAS_RAPIDFUZZ and (fuzz.ratio(w_clean, tw) >= 75 or fuzz.ratio(w_norm, tw_norm) >= 75)) or w_clean in tw or tw in w_clean:
                                    matched_words.append(w)
                                    break

                        if matched_words:
                            min_x = min(int(w.bounding_rect.x) for w in matched_words)
                            min_y = min(int(w.bounding_rect.y) for w in matched_words)
                            max_x = max(int(w.bounding_rect.x + w.bounding_rect.width) for w in matched_words)
                            max_y = max(int(w.bounding_rect.y + w.bounding_rect.height) for w in matched_words)
                            bw = max(1, max_x - min_x)
                            bh = max(1, max_y - min_y)
                            cx = offset_x + min_x + bw // 2
                            cy = offset_y + min_y + bh // 2

                            best_score = score
                            best_match = TextMatchResult(
                                text=target_clean,
                                matched_text=" ".join(getattr(w, "text", "") for w in matched_words),
                                confidence=score,
                                x=offset_x + min_x,
                                y=offset_y + min_y,
                                width=bw,
                                height=bh,
                                center_x=cx,
                                center_y=cy,
                                strategy="winocr"
                            )
                            if score >= 0.99:
                                return best_match

                if best_match:
                    return best_match
        except Exception as e:
            logger.debug(f"winocr search skipped: {e}")

        # Method 2: pytesseract fallback
        try:
            import pytesseract
            data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
            n_boxes = len(data.get("text", []))
            target_words = target_clean.lower().split()

            for i in range(n_boxes):
                box_word = (data["text"][i] or "").strip()
                if not box_word:
                    continue
                score = self._score_text_match(target_words[0], box_word)
                if score >= 0.80 and int(data["conf"][i]) > 30:
                    bx = offset_x + int(data["left"][i])
                    by = offset_y + int(data["top"][i])
                    bw = int(data["width"][i])
                    bh = int(data["height"][i])
                    cx = bx + bw // 2
                    cy = by + bh // 2
                    return TextMatchResult(
                        text=target_clean,
                        matched_text=box_word,
                        confidence=score,
                        x=bx,
                        y=by,
                        width=bw,
                        height=bh,
                        center_x=cx,
                        center_y=cy,
                        strategy="pytesseract_ocr"
                    )
        except Exception as e:
            logger.debug(f"OCR search skipped or unavailable: {e}")
        return None

    def locate_text(self, query_text: str, target_hwnd: Optional[int] = None) -> Optional[TextMatchResult]:
        """
        Locates target text on focused window or screen.
        Returns TextMatchResult with exact coordinates or None.
        """
        clean_target = self._clean_query_text(query_text)
        if not clean_target:
            return None

        fg_info = self.get_foreground_window_info()
        hwnd = target_hwnd or fg_info["hwnd"]
        pname = (fg_info.get("process_name") or "").lower()
        is_browser = any(b in pname for b in ("chrome", "brave", "edge", "firefox"))

        # Web Browsers:
        # Browser DOM contains thousands of virtual/off-screen nodes.
        # Native WinRT OCR reads what is visually rendered on the screen.
        if is_browser:
            # 1. OCR on focused browser window
            win_rect = fg_info["rect"] if (fg_info["rect"][2] > fg_info["rect"][0]) else None
            if win_rect:
                ocr_match = self._locate_via_ocr(win_rect, clean_target)
                if ocr_match and ocr_match.confidence >= 0.80:
                    ocr_match.window_title = fg_info["title"]
                    ocr_match.process_name = fg_info["process_name"]
                    return ocr_match

            # 2. OCR on full screen
            ocr_match = self._locate_via_ocr(None, clean_target)
            if ocr_match and ocr_match.confidence >= 0.80:
                ocr_match.window_title = fg_info["title"]
                ocr_match.process_name = fg_info["process_name"]
                return ocr_match

            # 3. UIA fallback for browser chrome, address bar, or tabs
            if self._uia_client:
                uia_match = self._locate_via_uia(hwnd, clean_target)
                if uia_match and uia_match.confidence >= 0.80:
                    uia_match.window_title = fg_info["title"]
                    uia_match.process_name = fg_info["process_name"]
                    return uia_match

            return ocr_match

        # Desktop Applications:
        # Strategy 1: UI Automation on focused window
        if self._uia_client:
            uia_match = self._locate_via_uia(hwnd, clean_target)
            if uia_match and uia_match.confidence >= 0.80:
                uia_match.window_title = fg_info["title"]
                uia_match.process_name = fg_info["process_name"]
                return uia_match

        # Strategy 2: OCR on focused window bounds
        win_rect = fg_info["rect"] if (fg_info["rect"][2] > fg_info["rect"][0]) else None
        if win_rect:
            ocr_match = self._locate_via_ocr(win_rect, clean_target)
            if ocr_match and ocr_match.confidence >= 0.80:
                ocr_match.window_title = fg_info["title"]
                ocr_match.process_name = fg_info["process_name"]
                return ocr_match

        # Strategy 3: OCR on full screen
        ocr_match = self._locate_via_ocr(None, clean_target)
        if ocr_match and ocr_match.confidence >= 0.80:
            ocr_match.window_title = fg_info["title"]
            ocr_match.process_name = fg_info["process_name"]
            return ocr_match

        # Strategy 4: Desktop UIAutomation Fallback
        if self._uia_client:
            try:
                root = self._uia_client.GetRootElement()
                match = self._search_uia_element_tree(root, clean_target, max_nodes=400)
                if match and match.confidence >= 0.80:
                    match.window_title = fg_info["title"]
                    match.process_name = fg_info["process_name"]
                    return match
            except Exception:
                pass

        return None

    def move_cursor_to(self, x: int, y: int, smooth: bool = True) -> bool:
        """Moves mouse cursor smoothly to coordinates with human-like glide."""
        try:
            # pyrefly: ignore [untyped-import]
            import pyautogui
            pyautogui.FAILSAFE = False
            sw, sh = pyautogui.size()
            cx = max(0, min(sw - 1, x))
            cy = max(0, min(sh - 1, y))

            if smooth:
                # pyrefly: ignore [missing-attribute]
                pyautogui.moveTo(cx, cy, duration=0.55, tween=pyautogui.easeInOutQuad)
                # Subtle micro-nudge visual indicator
                pyautogui.moveRel(4, 0, duration=0.08)
                pyautogui.moveRel(-4, 0, duration=0.08)
            else:
                pyautogui.moveTo(cx, cy)
            return True
        except Exception as e:
            logger.debug(f"move_cursor_to error: {e}")
            return False

    def get_human_location_desc(self, x: int, y: int, screen_w: int = 1920, screen_h: int = 1080) -> str:
        """
        Maps (x, y) coordinates to human natural language relative position.
        e.g. 'screen par upar daayein taraf (top-right)'
        """
        x_rel = x / max(1, screen_w)
        y_rel = y / max(1, screen_h)

        if y_rel < 0.33:
            if x_rel < 0.33:
                return "screen par upar baayein taraf (top-left)"
            elif x_rel > 0.66:
                return "screen par upar daayein taraf (top-right)"
            else:
                return "screen par upar ki taraf (top-center)"
        elif y_rel > 0.66:
            if x_rel < 0.33:
                return "screen par neeche baayein taraf (bottom-left)"
            elif x_rel > 0.66:
                return "screen par neeche daayein taraf (bottom-right)"
            else:
                return "screen par neeche ki taraf (bottom-center)"
        else:
            if x_rel < 0.33:
                return "screen par baayein taraf beech mein (left side)"
            elif x_rel > 0.66:
                return "screen par daayein taraf beech mein (right side)"
            else:
                return "screen ke bilkul beech mein (center)"

    def locate_and_point(self, query_text: str) -> str:
        """
        End-to-end command handler:
        1. Locates text on focused window/screen
        2. Moves mouse pointer to exact location
        3. Returns natural, human-like conversational feedback
        """
        clean_target = self._clean_query_text(query_text)
        if not clean_target:
            return "Aap screen par kya dhoondhna chahte hain, please text ka naam batayein."

        display_name = clean_target.title() if len(clean_target) > 3 else clean_target.upper()
        match = self.locate_text(clean_target)

        if match:
            # Move cursor to center of match
            self.move_cursor_to(match.center_x, match.center_y, smooth=True)

            # Get screen dimensions for human relative position
            sw, sh = 1920, 1080
            try:
                # pyrefly: ignore [untyped-import]
                import pyautogui
                sw, sh = pyautogui.size()
            except Exception:
                pass

            pos_desc = self.get_human_location_desc(match.center_x, match.center_y, sw, sh)
            win_ctx = ""
            if match.window_title and match.window_title not in ("Active Window", "Program Manager", "Desktop 1"):
                short_title = match.window_title[:30]
                win_ctx = f"'{short_title}' window mein "

            logger.info(
                f"[SCREEN_LOCATOR] Found '{clean_target}' via {match.strategy}: "
                f"matched='{match.matched_text}' conf={match.confidence:.2f} "
                f"at ({match.center_x}, {match.center_y}) pos='{pos_desc}' win='{match.window_title}'"
            )

            return f"Sir, '{display_name}' {win_ctx}{pos_desc} likha hua mila hai. Maine mouse cursor wahan point kar diya hai."

        logger.info(f"[SCREEN_LOCATOR] '{clean_target}' not found on focused window or screen.")
        return f"Sir, active window par '{display_name}' likha hua nahi mila."


_locator_instance = None

def get_screen_text_locator() -> ScreenTextLocator:
    """Returns singleton instance of ScreenTextLocator."""
    global _locator_instance
    if _locator_instance is None:
        _locator_instance = ScreenTextLocator()
    return _locator_instance
