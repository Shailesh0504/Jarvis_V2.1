# core/response_engine.py
"""
Authoritative Central Response Engine for Jarvis V2.1.

Single Source of Truth (SSOT) for all final user-facing responses.
Guarantees:
1. No robotic, repetitive, template-driven speech ("Main aapki kya madad kar sakta hoon?" strictly banned).
2. Intelligent, human-like, calm, respectful personal assistant persona.
3. Natural variation with anti-repetition memory (sliding history window).
4. Truth-aware responses strictly tied to execution verification.
5. Controlled, natural 'Sir' placement.
6. Situational brevity (short acknowledgements for simple inputs, detailed only when needed).
7. First-class Hinglish, English, and Hindi support with language continuity.
"""

from collections import deque
import logging
import random
import re
from typing import Any, Deque, Dict, List, Optional, Union

from core.response_planner import (
    DeliveryMode,
    PlannedResponse,
    ResponseCategory,
    ResponseContext,
    ResponsePlanner,
)
from core.response_style import ResponseStyleManager, ResponseTone
from core.response_validator import ResponseValidator, ValidationResult

logger = logging.getLogger("jarvis.core.response_engine")


class ResponseEngine:
    """
    Central Authoritative Response Engine.
    All system modules route their structured outputs through here before speaking.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        # Track recently used responses per category to eliminate immediate repetition
        self._history_per_category: Dict[ResponseCategory, Deque[str]] = {}
        self._recent_responses_global: Deque[str] = deque(maxlen=10)
        self._last_user_language: str = "hinglish"

    @classmethod
    def get_instance(cls) -> "ResponseEngine":
        """Singleton accessor."""
        if not cls._instance:
            cls._instance = ResponseEngine()
        return cls._instance

    def _select_variant(self, category: ResponseCategory, variants: List[str]) -> str:
        """
        Selects a natural variant while ensuring recently used ones are not repeated.
        """
        if not variants:
            return ""

        if category not in self._history_per_category:
            self._history_per_category[category] = deque(maxlen=max(2, len(variants) - 1))

        recent = self._history_per_category[category]
        candidates = [v for v in variants if v not in recent]
        if not candidates:
            candidates = variants

        selected = random.choice(candidates)
        recent.append(selected)
        self._recent_responses_global.append(selected)
        return selected

    def render_response(
        self,
        context: Union[ResponseContext, Dict[str, Any], str],
        default_text: Optional[str] = None
    ) -> str:
        """
        Authoritative entry point for producing final user-facing responses.
        Takes structured context, dict, or raw text and generates validated, natural output.
        """
        # 1. Normalize into ResponseContext
        ctx: ResponseContext
        if isinstance(context, ResponseContext):
            ctx = context
        elif isinstance(context, dict):
            ctx = ResponseContext(
                user_text=context.get("user_text") or context.get("query") or context.get("raw_input") or "",
                previous_user_text=context.get("previous_user_text"),
                previous_response=context.get("previous_response"),
                intent=context.get("intent") or "",
                speech_act=context.get("speech_act") or "",
                target=context.get("target") or "",
                action_performed=context.get("action_performed") or context.get("action") or "",
                action_status=context.get("action_status") or ("success" if context.get("success", True) else "failure"),
                verification_status=context.get("verification_status") or ("verified" if context.get("verified", True) else "unverified"),
                found=context.get("found"),
                match_count=context.get("match_count", 1),
                mouse_moved=context.get("mouse_moved", False),
                focused_app=context.get("focused_app") or "",
                active_tab=context.get("active_tab") or "",
                language=context.get("language") or self._last_user_language,
                time_of_day=context.get("time_of_day") or "",
                is_follow_up=context.get("is_follow_up", False),
                parameters=context.get("parameters") or {},
            )
        else:
            # String input
            ctx = ResponseContext(
                user_text=str(context),
                language=self._last_user_language
            )

        if not ctx.language:
            ctx.language = ResponsePlanner.detect_language(ctx.user_text, self._last_user_language)
        self._last_user_language = ctx.language

        # 2. Plan response strategy and category
        plan = ResponsePlanner.plan(ctx)

        # 3. Generate natural candidate response
        # ConversationEngine has already generated a grounded contextual reply.
        # Preserve its content while retaining the shared style/validation gate.
        candidate = (default_text if default_text and ctx.parameters.get("conversation_response")
                     else self._generate_candidate(plan, ctx, default_text))

        # 4. Stylistic refinement (persona, anti-robotic filter, controlled 'Sir')
        refined = ResponseStyleManager.filter_robotic_phrases(candidate)
        refined = ResponseStyleManager.sanitize_for_tts(refined)
        refined = ResponseStyleManager.enforce_controlled_sir(refined, allow_sir=plan.allow_sir)

        # 5. 10-Point Pre-Speech Validation & Safety Gate
        val_result: ValidationResult = ResponseValidator.validate(refined, ctx)
        final_text = val_result.repaired_text if not val_result.is_valid else refined

        return final_text

    def _generate_candidate(
        self,
        plan: PlannedResponse,
        ctx: ResponseContext,
        default_text: Optional[str]
    ) -> str:
        """Synthesizes candidate dialogue using the planned category and context."""
        cat = plan.category
        lang = plan.language
        tod = plan.time_of_day
        target = ctx.target.strip()
        target_display = target.title() if target else ""

        # --- A. GREETING_TIME_AWARE ---
        if cat == ResponseCategory.GREETING_TIME_AWARE:
            if tod == "morning":
                variants = [
                    "Good morning, Sir. Kya plan hai aaj?",
                    "Good morning, Sir. Kaise chal raha hai sab?",
                    "Good morning, Sir.",
                    "Shubh prabhat, Sir! Bataiye aaj kya karna hai?",
                ] if lang != "english" else [
                    "Good morning, Sir. How's your day starting?",
                    "Good morning, Sir. What's on the schedule today?",
                    "Good morning, Sir.",
                ]
            elif tod == "afternoon":
                variants = [
                    "Good afternoon, Sir. Kaise chal raha hai din?",
                    "Good afternoon, Sir.",
                    "Good afternoon! Kaisa ja raha hai din?",
                    "Good afternoon, Sir. Sab theek chal raha hai?",
                ] if lang != "english" else [
                    "Good afternoon, Sir. How is your day going?",
                    "Good afternoon, Sir.",
                    "Good afternoon, Sir. What can I do for you?",
                ]
            elif tod == "evening":
                variants = [
                    "Good evening, Sir. Kaisa raha din?",
                    "Good evening, Sir.",
                    "Good evening! Bataiye kya help karun?",
                ] if lang != "english" else [
                    "Good evening, Sir. How was your day?",
                    "Good evening, Sir.",
                    "Good evening! How can I assist you?",
                ]
            else:  # Night
                variants = [
                    "Good night, Sir. Araam kijiye.",
                    "Good night, Sir. Standby par hoon jab zaroorat ho.",
                    "Good night, Sir.",
                ] if lang != "english" else [
                    "Good night, Sir. Sleep well.",
                    "Good night, Sir.",
                ]
            return self._select_variant(cat, variants)

        # --- B. GREETING (Generic: hi, hello, hey, namaste) ---
        if cat == ResponseCategory.GREETING:
            low_text = ctx.user_text.lower().strip()
            if low_text.startswith("hello"):
                variants = [
                    "Hello Sir.",
                    "Hello Sir, good to see you.",
                    "Namaste Sir.",
                ] if lang != "english" else [
                    "Hello Sir.",
                    "Hello Sir, good to see you.",
                ]
            else:
                variants = [
                    "Hey Sir! Kaise ho?",
                    "Hello Sir.",
                    "Hey! Kaise chal raha hai?",
                    "Namaste Sir.",
                ] if lang != "english" else [
                    "Hey Sir! How are you?",
                    "Hello Sir.",
                    "Hi Sir!",
                ]
            return self._select_variant(cat, variants)

        # --- C0. CONVERSATION_STATE (Food, meal continuations, life updates) ---
        if cat == ResponseCategory.CONVERSATION_STATE or any(w in ctx.user_text.lower() for w in ["khana", "lunch", "dinner", "pet bhar"]):
            low_text = ctx.user_text.lower()
            if any(w in low_text for w in ["kha ke aaya", "kha ke aayi", "khana ho gaya", "lunch ho gaya", "pet bhar gaya"]):
                return "Achha, welcome back! Ab khana ho gaya. 😄"
            if any(w in low_text for w in ["nahi khaya", "nahi kiya", "bhookh"]):
                return "Arey, phir pehle khana kha lijiye. 😄"
            if any(w in low_text for w in ["ja raha", "karne ja raha"]):
                return "Theek hai, aap aaram se khana kha lijiye! 😄"

        # --- C1. TIME INQUIRY ---
        if "time" in ctx.user_text.lower() and any(w in ctx.user_text.lower() for w in ["kya", "kitna", "what"]):
            if default_text and any(m in default_text.lower() for m in ["ho rahe", "ho raha", "current time", "clock", "baje", "samay", "subah", "shaam", "raat", "dopahar"]):
                return default_text
            from core.time_context import get_time_context
            tc_ans = get_time_context().resolve_time_query(ctx.user_text)
            if tc_ans:
                return tc_ans
            from datetime import datetime
            now_time = datetime.now().strftime("%I:%M %p")
            return f"Abhi time {now_time} ho raha hai, Sir."

        # --- C. SMALL_TALK (how are you, mood, fatigue) ---
        if cat == ResponseCategory.SMALL_TALK:
            low_text = ctx.user_text.lower()
            if any(w in low_text for w in ["kya kar rahe ho", "kya kar raha hai", "what are you doing"]):
                return "Bas aapki madad ke liye ready hoon, Sir. Bataiye kya chal raha hai?"
            if default_text and not ResponseStyleManager.contains_banned_template(default_text):
                # If an upstream intelligence engine provided an empathetic reply (e.g. for mood, break, chill)
                if any(w in default_text.lower() for w in ["kya hua", "break", "chill", "relax", "araam"]):
                    return default_text

            if any(w in low_text for w in ["thak", "tired", "exhausted"]):
                return "Kaafi hectic din raha lagta hai. Thoda break le lijiye, Sir."
            if any(w in low_text for w in ["mood kharab", "mood off", "sad", "upset", "pareshan"]):
                return "Kya hua Sir? Koi pareshani hai to batayein, thoda relax kijiye."
            if any(w in low_text for w in ["mood achha", "mood bahut achha", "khush", "happy", "badhiya ja raha"]):
                return "Achha! Lagta hai aaj din badhiya ja raha hai. 😄"
            if any(w in low_text for w in ["listening", "sun rahe ho", "sun raha"]) and not any(m in low_text for m in ["mic", "microphone", "device", "earbuds", "earphone", "headset", "kaunse", "kis"]):
                return "Haan Sir, main bilkul saaf sun raha hoon. Aap bataiye."

            variants = [
                "Main theek hoon, Sir. Aap batao.",
                "Main bilkul theek hoon, Sir. Aap bataiye.",
                "Main theek hoon, sab smoothly chal raha hai, Sir. Aap suniye?",
            ] if lang != "english" else [
                "I'm doing well, Sir. How about you?",
                "All systems nominal, Sir. How are you doing?",
                "Doing great, Sir. What's on your mind?",
            ]
            return self._select_variant(cat, variants)

        # --- D. THANKS ---
        if cat == ResponseCategory.THANKS:
            variants = [
                "Anytime, Sir.",
                "Glad I could help, Sir.",
                "My pleasure, Sir.",
                "Koi baat nahi, Sir.",
            ] if lang != "english" else [
                "Anytime, Sir.",
                "Glad I could help, Sir.",
                "You're very welcome, Sir.",
            ]
            return self._select_variant(cat, variants)

        # --- E. ACKNOWLEDGEMENT ---
        if cat == ResponseCategory.ACKNOWLEDGEMENT:
            low_text = ctx.user_text.lower()
            if "achha hai" in low_text or "accha hai" in low_text:
                return "Haanji, badhiya! 😄"
            if any(w in low_text for w in ["great", "nice", "perfect", "badhiya", "mast"]):
                variants = ["Nice.", "Glad it worked.", "Great!"]
            else:
                variants = [
                    "Theek hai.",
                    "Theek hai, Sir.",
                    "Got it.",
                    "Ji.",
                    "Bilkul.",
                ] if lang != "english" else [
                    "Understood, Sir.",
                    "Got it, Sir.",
                    "Right away.",
                ]
            return self._select_variant(cat, variants)

        # --- F. GOODBYE ---
        if cat == ResponseCategory.GOODBYE:
            variants = [
                "Alvida Sir, milte hain agle session mein.",
                "Goodbye, Sir. Have a great day.",
                "Bye Sir! Standby mode active.",
            ] if lang != "english" else [
                "Goodbye, Sir. Take care.",
                "Bye Sir, shutting down active interface.",
            ]
            return self._select_variant(cat, variants)

        # --- G. VISUAL_FIND ---
        if cat == ResponseCategory.VISUAL_FIND:
            if ctx.found is False:
                return f"Sir, mujhe '{target_display}' current window mein nahi mila." if lang != "english" else f"Sir, I could not find '{target_display}' in the current window."
            if ctx.match_count > 1:
                hindi_nums = {2: "do", 3: "teen", 4: "chaar", 5: "paanch"}
                num_word = hindi_nums.get(ctx.match_count, str(ctx.match_count))
                return f"Sir, ye {num_word} jagah mila hai. Maine mouse pehle wale par le gaya hai." if lang != "english" else f"Sir, found {ctx.match_count} occurrences. Moved the mouse to the first one."
            return f"Sir, '{target_display}' yahan likha hai. Maine mouse usi jagah le diya hai." if lang != "english" else f"Sir, '{target_display}' is located right here. I have moved the mouse to it."

        # --- H. VISUAL_CLICK ---
        if cat == ResponseCategory.VISUAL_CLICK:
            if ctx.action_status == "failure":
                return f"Sir, '{target_display}' par click nahi ho paya." if lang != "english" else f"Sir, could not click '{target_display}'."
            if target_display:
                return f"Ji Sir, '{target_display}' par click kar diya." if lang != "english" else f"Clicked on '{target_display}', Sir."
            return "Ji Sir, click kar diya." if lang != "english" else "Clicked, Sir."

        # --- I. BROWSER_TAB_ACTION / WINDOW_FOCUS ---
        if cat == ResponseCategory.BROWSER_TAB_ACTION:
            browser = ctx.focused_app or "Chrome"
            tab = ctx.active_tab or target_display
            if tab and browser:
                return f"Sir, {tab} {browser} mein open hai. Maine {browser} ko focus mein la diya hai." if lang != "english" else f"Sir, {tab} is open in {browser}. Focused {browser} for you."
            if browser:
                return f"{browser} ko foreground mein la diya hai, Sir." if lang != "english" else f"Focused {browser}, Sir."

        # --- J. TARGET_NOT_FOUND ---
        if cat == ResponseCategory.TARGET_NOT_FOUND:
            disp = target_display or "target"
            return f"Sir, मुझे '{disp}' active screen par nahi mila." if lang != "english" else f"Sir, '{disp}' was not found."

        # --- K. COMMAND_SUCCESS ---
        if cat == ResponseCategory.COMMAND_SUCCESS:
            action = (ctx.action_performed or "").lower()
            low_text = ctx.user_text.lower()
            is_close = any(w in action or w in low_text for w in ["close", "band"])
            is_open = any(w in action or w in low_text for w in ["open", "launch", "khol", "chala"])
            is_tab = "tab" in low_text

            if is_tab and is_close:
                variants = [
                    "Tab band kar diya, Sir.",
                    "Current tab close kar diya.",
                    "Ji Sir, tab close kar diya.",
                ] if lang != "english" else [
                    "Closed the tab, Sir.",
                    "Tab closed.",
                ]
                return self._select_variant(cat, variants)

            if is_close:
                variants = [
                    "Ji Sir, current window band kar di.",
                    "Current window band kar diya.",
                    "Ji, band kar diya.",
                    "Done, Sir.",
                ] if lang != "english" else [
                    "Closed the window, Sir.",
                    "Window has been closed.",
                    "Done, Sir.",
                ]
                return self._select_variant(cat, variants)

            if is_open and target_display:
                variants = [
                    f"{target_display} khol diya, Sir.",
                    f"Ji Sir, {target_display} open kar diya.",
                    f"{target_display} open ho gaya.",
                ] if lang != "english" else [
                    f"Opened {target_display}, Sir.",
                    f"{target_display} is now open.",
                ]
                return self._select_variant(cat, variants)

            if default_text and not ResponseStyleManager.contains_banned_template(default_text):
                return default_text

            return "Ji Sir, kar diya." if lang != "english" else "Action completed, Sir."

        # --- L. COMMAND_FAILURE ---
        if cat == ResponseCategory.COMMAND_FAILURE:
            low_text = ctx.user_text.lower()
            if any(w in low_text for w in ["close", "band"]):
                return "Sir, window band nahi ho payi." if lang != "english" else "Sir, the window could not be closed."
            if any(w in low_text for w in ["open", "khol"]):
                return f"Sir, {target_display or 'application'} open nahi ho payi." if lang != "english" else f"Sir, could not launch {target_display or 'the application'}."
            return "Sir, is baar action complete nahi ho paya." if lang != "english" else "Sir, the action could not be completed."

        # --- M. CLARIFICATION ---
        if cat == ResponseCategory.CLARIFICATION:
            variants = [
                "Sir, kaunsi window ki baat kar rahe hain?",
                "Sir, mujhe thoda context chahiye. Aap kis application ki baat kar rahe hain?",
            ] if lang != "english" else [
                "Sir, which window are you referring to?",
                "Could you provide a bit more context, Sir?",
            ]
            return self._select_variant(cat, variants)

        # Fallback to default_text if provided and clean
        if default_text and not ResponseStyleManager.contains_banned_template(default_text):
            return default_text

        # Default conversational acknowledgment
        return "Theek hai, Sir." if lang != "english" else "Understood, Sir."
