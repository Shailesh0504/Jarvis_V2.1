# core/visual_interaction.py
"""
Visual Text Interaction Engine (Authoritative Orchestrator).

Orchestrates:
1. Live focused window & viewport capture
2. Sub-action determination (FIND_TEXT, POINT_TO_TEXT, CLICK_TEXT, DOUBLE_CLICK_TEXT, SELECT_TEXT)
3. Deictic and ordinal reference resolution from VisualReferenceManager
4. Layered text search via TextLocatorEngine
5. Verified cursor movement and action execution via MouseController
6. Human-grade conversational response generation
"""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional

from core.mouse_controller import MouseActionResult, get_mouse_controller
from core.text_locator import TextLocatorEngine, get_text_locator
from core.text_matcher import VisualTextMatch
from core.visual_context import VisualContext, get_visual_context_manager
from core.visual_reference import VisualReferenceManager, get_visual_reference_manager

logger = logging.getLogger("jarvis.core.visual_interaction")


@dataclass
class VisualInteractionResult:
    action: str
    target_query: str
    display_name: str
    success: bool
    verified: bool
    message: str
    match: Optional[VisualTextMatch] = None
    matches_count: int = 0
    mouse_result: Optional[MouseActionResult] = None


class VisualInteractionEngine:
    """Authoritative orchestrator for VISUAL_TEXT_INTERACTION."""

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        self.context_mgr = get_visual_context_manager()
        self.locator = get_text_locator()
        self.mouse = get_mouse_controller()
        self.ref_mgr = get_visual_reference_manager()

    @staticmethod
    def format_display_name(text: str) -> str:
        """Formats target text into clean display name for natural speech feedback."""
        if not text:
            return ""
        s = text.strip()
        # Title case if length > 3 and not all-uppercase acronym
        if len(s) > 3 and not (s.isupper() and len(s) <= 4):
            return s.title()
        return s.upper() if len(s) <= 3 else s

    def execute(
        self,
        target_text: str,
        sub_action: str = "FIND_TEXT",
        ordinal_index: Optional[int] = None,
        raw_utterance: str = ""
    ) -> VisualInteractionResult:
        """
        Executes the visual text interaction:
        - sub_action: 'FIND_TEXT', 'POINT_TO_TEXT', 'CLICK_TEXT', 'DOUBLE_CLICK_TEXT', 'SELECT_TEXT'
        - Default action is NEVER click.
        """
        action = sub_action.upper()
        if action not in {"FIND_TEXT", "POINT_TO_TEXT", "CLICK_TEXT", "DOUBLE_CLICK_TEXT", "SELECT_TEXT"}:
            action = "FIND_TEXT"

        display_name = self.format_display_name(target_text)

        # 1. Check for Deictic Reference or Ordinal Selection
        # (e.g. 'ab is par click karo', 'isko select karo', 'doosre wale par click karo')
        is_ref = self.ref_mgr.is_deictic_reference(raw_utterance or target_text)
        has_ordinal = (ordinal_index is not None or self.ref_mgr.extract_ordinal_index(raw_utterance or target_text) is not None)

        target_match: Optional[VisualTextMatch] = None
        matches_found: List[VisualTextMatch] = []
        last_search = self.ref_mgr.get_last_search()

        if is_ref or (has_ordinal and last_search):
            target_match = self.ref_mgr.resolve_reference(raw_utterance or target_text, ordinal_index=ordinal_index)
            if target_match:
                display_name = self.format_display_name(target_match.text)
                matches_found = [target_match]
            elif not last_search:
                return VisualInteractionResult(
                    action=action,
                    target_query=target_text,
                    display_name=display_name,
                    success=False,
                    verified=False,
                    message="Sir, koi previous visual target yaad nahi hai. Please text ka naam batayein."
                )
        elif is_ref or (has_ordinal and not target_text):
            return VisualInteractionResult(
                action=action,
                target_query=target_text,
                display_name=display_name,
                success=False,
                verified=False,
                message="Sir, koi previous visual target yaad nahi hai. Please text ka naam batayein."
            )

        # 2. Fresh visual search if not resolved by reference
        if not target_match:
            if not target_text or not target_text.strip():
                return VisualInteractionResult(
                    action=action,
                    target_query=target_text,
                    display_name=display_name,
                    success=False,
                    verified=False,
                    message="Aap screen par kya dhoondhna chahte hain, please text ka naam batayein."
                )

            # Capture live focused window context
            ctx = self.context_mgr.capture_focused_context()

            # Execute layered text search
            matches_found = self.locator.locate(target_text, context=ctx)

            if not matches_found:
                logger.info(f"[VISUAL_INTERACTION] Target '{target_text}' not found on focused window.")
                return VisualInteractionResult(
                    action=action,
                    target_query=target_text,
                    display_name=display_name,
                    success=False,
                    verified=False,
                    message=f"Sir, mujhe '{display_name}' current window mein nahi mila."
                )

            # Store search in visual memory
            req_idx = ordinal_index if ordinal_index is not None else self.ref_mgr.extract_ordinal_index(raw_utterance)
            sel_idx = max(0, min(req_idx if req_idx is not None else 0, len(matches_found) - 1))

            self.ref_mgr.store_search(
                query=target_text,
                window_hwnd=ctx.hwnd,
                application=ctx.process_name or ctx.title,
                matches=matches_found,
                tab=ctx.active_tab,
                selected_index=sel_idx
            )
            target_match = matches_found[sel_idx]

        # 3. Perform Verified Mouse Action based on sub_action
        mouse_res: Optional[MouseActionResult] = None
        center_x = target_match.bbox.center_x
        center_y = target_match.bbox.center_y

        if action in ("FIND_TEXT", "POINT_TO_TEXT"):
            # Move cursor to center of match
            mouse_res = self.mouse.move_to(center_x, center_y, smooth=True)
            if len(matches_found) > 1 and not is_ref:
                hindi_nums = {2: "do", 3: "teen", 4: "chaar", 5: "paanch"}
                num_word = hindi_nums.get(len(matches_found), str(len(matches_found)))
                message = f"Sir, ye {num_word} jagah mila hai. Maine pehle wale par mouse le gaya hai."
            else:
                message = f"Sir, '{display_name}' yahan likha hai. Maine mouse usi jagah le diya hai."

        elif action == "CLICK_TEXT":
            # Click center of match (or accessible hitbox)
            mouse_res = self.mouse.click(center_x, center_y, hitbox=target_match.hitbox)
            message = f"Ji Sir, '{display_name}' par click kar diya."

        elif action == "DOUBLE_CLICK_TEXT":
            mouse_res = self.mouse.double_click(center_x, center_y, hitbox=target_match.hitbox)
            message = f"Ji Sir, '{display_name}' par double-click kar diya."

        elif action == "SELECT_TEXT":
            mouse_res = self.mouse.select_text(target_match.bbox)
            message = f"Ji Sir, '{display_name}' ko select kar diya."

        else:
            mouse_res = self.mouse.move_to(center_x, center_y, smooth=True)
            message = f"Sir, '{display_name}' yahan likha hai. Maine mouse usi jagah le diya hai."

        success = bool(mouse_res.success) if mouse_res else True
        verified = bool(mouse_res.verified) if mouse_res else True

        logger.info(
            f"[VISUAL_INTERACTION] Completed action={action} target='{display_name}' "
            f"matches={len(matches_found)} verified={verified}"
        )

        return VisualInteractionResult(
            action=action,
            target_query=target_text,
            display_name=display_name,
            success=success,
            verified=verified,
            message=message,
            match=target_match,
            matches_count=len(matches_found),
            mouse_result=mouse_res
        )


_visual_interaction_instance: Optional[VisualInteractionEngine] = None


def get_visual_interaction_engine() -> VisualInteractionEngine:
    """Returns singleton instance of VisualInteractionEngine."""
    global _visual_interaction_instance
    if _visual_interaction_instance is None:
        _visual_interaction_instance = VisualInteractionEngine()
    return _visual_interaction_instance
