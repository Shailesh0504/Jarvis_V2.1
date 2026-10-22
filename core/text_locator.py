# core/text_locator.py
"""
Layered Screen & Window Text Locator.

Implements multi-strategy text detection across:
1. Windows UI Automation (Controls, TextPattern, ValuePattern, ControlViewWalker)
2. Native WinRT OCR (built-in, offline, high-speed Windows OCR)
3. Pytesseract OCR fallback
4. Spatial multi-word phrase bounding box construction
5. Multi-monitor and DPI scaling coordinate transformation
"""

import asyncio
import concurrent.futures
from dataclasses import dataclass
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.text_matcher import BoundingBox, OCRToken, VisualTextMatch, get_text_matcher
from core.visual_context import VisualContext, get_visual_context_manager

logger = logging.getLogger("jarvis.core.text_locator")


class TextLocatorEngine:
    """Authoritative layered text locator engine."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.matcher = get_text_matcher()
        self.context_mgr = get_visual_context_manager()
        self._uia_client = None
        self._init_uia()

    def _init_uia(self):
        """Initializes COM UIAutomationClient."""
        try:
            import comtypes.client
            try:
                from comtypes.gen import UIAutomationClient
            except ImportError:
                comtypes.client.GetModule("UIAutomationCore.dll")
                from comtypes.gen import UIAutomationClient
            self._uia_client = comtypes.client.CreateObject(UIAutomationClient.CUIAutomation)
            self._uia_module = UIAutomationClient
            logger.info("TextLocatorEngine: UIAutomation initialized successfully.")
        except Exception as e:
            logger.debug(f"TextLocatorEngine: UIAutomation init note: {e}")
            self._uia_client = None
            self._uia_module = None

    def locate(self, query: str, context: Optional[VisualContext] = None) -> List[VisualTextMatch]:
        """
        Executes layered text search across UIA controls, focused window OCR, and screen fallback.
        Returns: List of VisualTextMatch sorted by match score.
        """
        if not query or not query.strip():
            return []

        ctx = context or self.context_mgr.capture_focused_context()
        matches: List[VisualTextMatch] = []

        # Strategy 1: UI Automation on focused window
        if self._uia_client and ctx.hwnd:
            uia_matches = self._search_via_uia(ctx.hwnd, query)
            for m in uia_matches:
                m.window_title = ctx.title
                m.process_name = ctx.process_name
            matches.extend(uia_matches)

        # If high-confidence UIA match found (>= 0.95), return immediately
        high_uia = [m for m in matches if m.match_score >= 0.95]
        if high_uia:
            return sorted(high_uia, key=lambda m: m.match_score, reverse=True)

        # Strategy 2: OCR on focused window bounds
        win_rect = ctx.rect if (ctx.rect[2] > ctx.rect[0] and ctx.rect[3] > ctx.rect[1]) else None
        if win_rect:
            ocr_matches = self._search_via_ocr(query, bbox=win_rect)
            for m in ocr_matches:
                m.window_title = ctx.title
                m.process_name = ctx.process_name
            matches.extend(ocr_matches)

        # If high-confidence OCR match found (>= 0.90), return
        high_ocr = [m for m in matches if m.match_score >= 0.90]
        if high_ocr:
            return sorted(matches, key=lambda m: (m.match_score, m.confidence), reverse=True)

        # Strategy 3: Full-screen OCR fallback
        screen_matches = self._search_via_ocr(query, bbox=None)
        for m in screen_matches:
            m.window_title = ctx.title or "Screen"
            m.process_name = ctx.process_name
        matches.extend(screen_matches)

        # Deduplicate matches
        deduped: List[VisualTextMatch] = []
        for m in sorted(matches, key=lambda it: (it.match_score, it.confidence), reverse=True):
            if not any(abs(m.bbox.center_x - k.bbox.center_x) < 25 and abs(m.bbox.center_y - k.bbox.center_y) < 18 for k in deduped):
                deduped.append(m)

        return deduped

    def _search_via_uia(self, hwnd: int, query: str) -> List[VisualTextMatch]:
        """Traverses UIAutomation tree for elements matching query."""
        if not self._uia_client or not hwnd:
            return []

        results: List[VisualTextMatch] = []
        try:
            element = self._uia_client.ElementFromHandle(hwnd)
            if not element:
                return []

            walker = self._uia_client.ControlViewWalker
            queue = [element]
            visited = 0
            max_nodes = 300

            while queue and visited < max_nodes:
                curr = queue.pop(0)
                visited += 1

                try:
                    name = getattr(curr, "CurrentName", "") or ""
                    rect = getattr(curr, "CurrentBoundingRectangle", None)
                    has_valid_rect = (rect and (rect.right > rect.left) and (rect.bottom > rect.top))

                    # 1. Inspect element Name property
                    if name and has_valid_rect:
                        score, m_type = self.matcher.compare_strings(query, name)
                        if score >= 0.80:
                            bbox = BoundingBox(rect.left, rect.top, rect.right, rect.bottom)
                            results.append(VisualTextMatch(
                                text=query,
                                matched_text=name,
                                confidence=1.0,
                                match_score=score,
                                match_type=m_type,
                                bbox=bbox,
                                strategy="uia",
                                hitbox=bbox
                            ))

                    # 2. Inspect ValuePattern
                    if self._uia_module and has_valid_rect:
                        try:
                            val_pat = curr.GetCurrentPattern(self._uia_module.UIA_ValuePatternId)
                            if val_pat:
                                val_obj = val_pat.QueryInterface(self._uia_module.IUIAutomationValuePattern)
                                val_text = getattr(val_obj, "CurrentValue", "") or ""
                                if val_text:
                                    score, m_type = self.matcher.compare_strings(query, val_text)
                                    if score >= 0.80:
                                        bbox = BoundingBox(rect.left, rect.top, rect.right, rect.bottom)
                                        results.append(VisualTextMatch(
                                            text=query,
                                            matched_text=val_text,
                                            confidence=1.0,
                                            match_score=score,
                                            match_type=m_type,
                                            bbox=bbox,
                                            strategy="uia_value",
                                            hitbox=bbox
                                        ))
                        except Exception:
                            pass

                    # Walk children
                    if walker:
                        child = walker.GetFirstChildElement(curr)
                        while child and len(queue) < max_nodes:
                            queue.append(child)
                            child = walker.GetNextSiblingElement(child)
                except Exception:
                    continue
        except Exception as e:
            logger.debug(f"UIA tree inspection error: {e}")

        return results

    def _search_via_ocr(
        self,
        query: str,
        bbox: Optional[Tuple[int, int, int, int]] = None
    ) -> List[VisualTextMatch]:
        """Captures window/screen region and runs native OCR with spatial phrase matching."""
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
                import pyautogui
                screenshot = pyautogui.screenshot()
                if clamped_bbox:
                    screenshot = screenshot.crop(clamped_bbox)
            except Exception as ex:
                logger.debug(f"Screenshot capture failed: {ex}")
                return []

        offset_x = clamped_bbox[0] if clamped_bbox else 0
        offset_y = clamped_bbox[1] if clamped_bbox else 0

        tokens: List[OCRToken] = []

        # 1. Native WinRT OCR
        try:
            import winocr

            def _run_winocr_sync():
                try:
                    async def _runner():
                        return await winocr.recognize_pil(screenshot, "en")
                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        return pool.submit(lambda: asyncio.run(_runner())).result(timeout=4.0)
                except Exception:
                    return None

            ocr_res = _run_winocr_sync()
            if ocr_res and hasattr(ocr_res, "lines") and ocr_res.lines:
                for line_idx, line in enumerate(ocr_res.lines):
                    for word_idx, w in enumerate(getattr(line, "words", [])):
                        w_text = getattr(w, "text", "") or ""
                        w_rect = getattr(w, "bounding_rect", None)
                        if w_text and w_rect:
                            wx = int(w_rect.x) + offset_x
                            wy = int(w_rect.y) + offset_y
                            ww = max(1, int(w_rect.width))
                            wh = max(1, int(w_rect.height))
                            tokens.append(OCRToken(
                                text=w_text,
                                bbox=BoundingBox(wx, wy, wx + ww, wy + wh),
                                confidence=0.95,
                                line_num=line_idx,
                                word_num=word_idx
                            ))
        except Exception as e:
            logger.debug(f"WinRT OCR note: {e}")

        # 2. Pytesseract OCR Fallback
        if not tokens:
            try:
                import pytesseract
                data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
                n_boxes = len(data.get("text", []))
                for i in range(n_boxes):
                    t = (data["text"][i] or "").strip()
                    conf = float(data.get("conf", [0])[i])
                    if t and conf > 25:
                        bx = int(data["left"][i]) + offset_x
                        by = int(data["top"][i]) + offset_y
                        bw = int(data["width"][i])
                        bh = int(data["height"][i])
                        tokens.append(OCRToken(
                            text=t,
                            bbox=BoundingBox(bx, by, bx + bw, by + bh),
                            confidence=min(1.0, conf / 100.0),
                            line_num=int(data.get("line_num", [0])[i]),
                            word_num=int(data.get("word_num", [0])[i])
                        ))
            except Exception as e:
                logger.debug(f"Pytesseract note: {e}")

        if not tokens:
            return []

        # Run spatial phrase and single token matching
        matches = self.matcher.match_spatial_tokens(query, tokens)
        for m in matches:
            m.strategy = "winocr" if "winocr" in m.strategy or len(tokens) > 0 else "ocr"

        return matches


_text_locator_instance: Optional[TextLocatorEngine] = None


def get_text_locator() -> TextLocatorEngine:
    """Returns singleton instance of TextLocatorEngine."""
    global _text_locator_instance
    if _text_locator_instance is None:
        _text_locator_instance = TextLocatorEngine()
    return _text_locator_instance
