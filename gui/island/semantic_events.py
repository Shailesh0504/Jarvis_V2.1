# gui/island/semantic_events.py
"""Central Semantic Event Layer for JARVIS Coucou-style Sound + Mochi Visual System.

Authoritative orchestrator ensuring:
SEMANTIC EVENT → DEDUPLICATION / COOLDOWN → CHARACTER STATE UPDATE → SOUND → ANIMATION → UI RESPONSE

Behavioural Rules:
1. Master Sound → Visual coordination: Every important JARVIS event coordinates
   Sound + Visual State + Animation + UI Response together.
2. Deduplication & Cooldowns: Event IDs prevent duplicate triggers. Cooldowns
   protect against multi-call spam (e.g. reasoning loops, progress callbacks).
3. Zero Audio Coupling to Render Loops: Sounds never fire from frame loops,
   mouse moves, partial STT, RMS/VAD, or unthrottled progress updates.
4. Upload Progress Gating: tick.wav ONLY fires when crossing deciles 10%, 20%, ..., 90%.
   Never at 0%, never at 100%, never on every progress callback.
5. Pinned Approval: Approval requests keep the character in orange approval state
   with '!' badge and pin the UI from auto-closing.
"""

import logging
import time
import threading
from typing import Any, Dict, Optional, Set, Tuple

from ..sound_effects import Sound

logger = logging.getLogger("jarvis.gui.semantic_events")

# Default per-event cooldown windows (in seconds)
EVENT_COOLDOWNS: Dict[str, float] = {
    "task_started": 0.8,
    "work": 0.8,
    "thinking_started": 4.0,
    "think": 4.0,
    "search_started": 3.0,
    "search": 3.0,
    "approval_required": 2.0,
    "approval": 2.0,
    "user_approved": 0.8,
    "approve": 0.8,
    "task_success": 1.2,
    "finish": 1.2,
    "task_failed": 1.5,
    "error": 1.5,
    "question_asked": 2.0,
    "question": 2.0,
    "rate_limited": 3.0,
    "ratelimit": 3.0,
    "idle_sleep": 10.0,
    "sleep": 10.0,
    "dizzy": 2.5,
    "slap": 0.2,
    "annoyed": 1.5,
    "character_hover": 1.5,
    "hover": 1.5,
    "sustained_hover": 30.0,
    "love": 30.0,
    "wink": 3.0,
    "proud": 3.0,
    "yawn": 8.0,
    "message_sent": 0.3,
    "send": 0.3,
    "tick": 0.1,
    "file_accepted": 1.0,
    "gulp": 1.0,
    "attach": 1.0,
    "hidden_to_compact": 0.5,
    "peek": 0.5,
    "compact_to_expanded": 0.5,
    "open": 0.5,
    "expanded_to_compact": 0.5,
    "close": 0.5,
    "startup_greeting": 10.0,
    "greet": 10.0,
    "ui_blip": 0.2,
    "blip": 0.2,
    "pop": 0.5,
}

# Semantic Event -> (Sound Name, Character State, Default Cooldown)
EVENT_DISPATCH_TABLE: Dict[str, Tuple[str, Optional[str], float]] = {
    # P0 Visibility
    "hidden_to_compact": ("peek", "idle", 0.5),
    "peek": ("peek", "idle", 0.5),
    "compact_to_expanded": ("open", "idle", 0.5),
    "open": ("open", "idle", 0.5),
    "expanded_to_compact": ("close", "idle", 0.5),
    "close": ("close", "idle", 0.5),

    # P0 Greeting & Tasks
    "startup_greeting": ("greet", "happy", 10.0),
    "greet": ("greet", "happy", 10.0),
    "task_started": ("work", "working", 0.8),
    "work": ("work", "working", 0.8),
    "thinking_started": ("think", "thinking", 4.0),
    "think": ("think", "thinking", 4.0),
    "search_started": ("search", "searching", 3.0),
    "search": ("search", "searching", 3.0),
    "approval_required": ("approval", "approval", 2.0),
    "approval": ("approval", "approval", 2.0),
    "user_approved": ("approve", "happy", 0.8),
    "approve": ("approve", "happy", 0.8),
    "user_denied": ("blip", "idle", 0.2),
    "task_success": ("finish", "finished", 1.2),
    "finish": ("finish", "finished", 1.2),
    "task_failed": ("error", "error", 1.5),
    "error": ("error", "error", 1.5),

    # P1 Interactions & Emotes
    "question_asked": ("question", "question", 2.0),
    "question": ("question", "question", 2.0),
    "rate_limited": ("rate", "ratelimit", 3.0),
    "ratelimit": ("rate", "ratelimit", 3.0),
    "idle_sleep": ("sleep", "sleeping", 10.0),
    "sleep": ("sleep", "sleeping", 10.0),
    "dizzy": ("dizzy", "dizzy", 2.5),
    "character_clicked": ("slap", None, 0.2),
    "slap": ("slap", None, 0.2),
    "character_annoyed": ("annoyed", "annoyed", 1.5),
    "annoyed": ("annoyed", "annoyed", 1.5),
    "character_hover": ("hover", None, 1.5),
    "hover": ("hover", None, 1.5),
    "sustained_hover": ("love", "love", 30.0),
    "love": ("love", "love", 30.0),
    "wink": ("wink", "wink", 3.0),
    "proud": ("proud", "proud", 3.0),
    "yawn": ("yawn", "sleeping", 8.0),
    "message_sent": ("send", "idle", 0.3),
    "send": ("send", "idle", 0.3),

    # P2 Progress & UI
    "tick": ("tick", None, 0.1),
    "file_accepted": ("gulp", None, 1.0),
    "gulp": ("gulp", None, 1.0),
    "file_attached": ("attach", None, 1.0),
    "attach": ("attach", None, 1.0),
    "ui_blip": ("blip", None, 0.2),
    "blip": ("blip", None, 0.2),
    "pop": ("pop", None, 0.5),
}


class SemanticEventManager:
    """Singleton managing semantic visual events, cooldowns, and targets."""

    _instance: Optional["SemanticEventManager"] = None

    def __init__(self):
        self._lock = threading.Lock()
        self._character = None
        self._island = None
        self._visibility_mgr = None
        self._main_window = None

        self._last_event_time: Dict[str, float] = {}
        self._seen_event_ids: Dict[Tuple[str, str], float] = {}
        self._last_ticked_deciles: Dict[str, Set[int]] = {}  # session_id -> set of deciles (10..90)

    @classmethod
    def instance(cls) -> "SemanticEventManager":
        if cls._instance is None:
            cls._instance = SemanticEventManager()
        return cls._instance

    def register_targets(
        self,
        character: Optional[Any] = None,
        island: Optional[Any] = None,
        visibility_mgr: Optional[Any] = None,
        main_window: Optional[Any] = None
    ) -> None:
        """Registers active GUI components for event orchestration."""
        with self._lock:
            if character is not None:
                self._character = character
            if island is not None:
                self._island = island
            if visibility_mgr is not None:
                self._visibility_mgr = visibility_mgr
            if main_window is not None:
                self._main_window = main_window

    def get_targets(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "character": self._character,
                "island": self._island,
                "visibility_mgr": self._visibility_mgr,
                "main_window": self._main_window,
            }

    def dispatch(
        self,
        event: str,
        event_id: str = "",
        percent: Optional[int] = None,
        character: Optional[Any] = None,
        island: Optional[Any] = None,
        visibility_mgr: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Processes a semantic event with dedup, cooldown, state change, sound, and animations."""
        clean_event = str(event).lower().strip()
        now = time.monotonic()

        # Resolve targets (explicit params take precedence, then registered singleton)
        char = character or self._character
        isl = island or self._island
        vm = visibility_mgr or self._visibility_mgr

        # Special handling for upload_progress: strictly 10% decile gating
        if clean_event in ("upload_progress", "progress"):
            return self._handle_upload_progress(percent, event_id, char, isl, now)

        config = EVENT_DISPATCH_TABLE.get(clean_event)
        if config is None:
            logger.debug(f"[JARVIS_SEMANTIC_EVENT] Unknown event={clean_event}")
            return {"handled": False, "event": clean_event, "suppressed": "unknown_event"}

        sound_name, target_state, default_cooldown = config

        # Deduplication check
        with self._lock:
            # 1. Prune stale event IDs (> 10s)
            stale_keys = [k for k, ts in self._seen_event_ids.items() if now - ts > 10.0]
            for k in stale_keys:
                del self._seen_event_ids[k]

            # 2. Check exact (event, event_id) duplicate
            if event_id:
                key = (clean_event, str(event_id))
                if key in self._seen_event_ids:
                    logger.debug(f"[JARVIS_SEMANTIC_EVENT] SUPPRESSED event={clean_event} id={event_id} reason=duplicate_id")
                    return {"handled": True, "event": clean_event, "suppressed": "duplicate_id", "sound_played": False}
                self._seen_event_ids[key] = now

            # 3. Check cooldown
            cooldown = default_cooldown
            last_time = self._last_event_time.get(clean_event, 0.0)
            if now - last_time < cooldown:
                logger.debug(f"[JARVIS_SEMANTIC_EVENT] SUPPRESSED event={clean_event} reason=cooldown")
                return {"handled": True, "event": clean_event, "suppressed": "cooldown", "sound_played": False}

            self._last_event_time[clean_event] = now

        # Execute coordinated response:
        # A. UI Response / Pinning
        if clean_event in ("approval_required", "approval"):
            if vm is not None and hasattr(vm, "set_pinned"):
                vm.set_pinned(True)
        elif clean_event in ("user_approved", "approve", "user_denied"):
            if vm is not None and hasattr(vm, "set_pinned"):
                vm.set_pinned(False)

        # B. Sound playback
        sound_played = False
        if sound_name:
            sound_played = Sound.play(
                sound_name,
                reason=f"semantic_{clean_event}",
                event_id=event_id,
                cooldown_ms=int(default_cooldown * 1000)
            )

        # C. Character visual state and animations
        if char is not None:
            # Custom animations per event
            if clean_event in ("character_clicked", "slap"):
                if hasattr(char, "trigger_slap"):
                    char.trigger_slap()
            elif clean_event == "dizzy":
                if hasattr(char, "trigger_dizzy"):
                    char.trigger_dizzy()
                elif hasattr(char, "set_system_state"):
                    char.set_system_state("dizzy")
            elif clean_event in ("file_accepted", "gulp"):
                if hasattr(char, "trigger_gulp"):
                    char.trigger_gulp()
                elif hasattr(char, "set_system_state"):
                    char.set_system_state("happy")
            elif clean_event in ("sustained_hover", "love"):
                if hasattr(char, "trigger_love_emote"):
                    char.trigger_love_emote()
                elif hasattr(char, "set_system_state"):
                    char.set_system_state("love")
            elif target_state is not None:
                if hasattr(char, "set_system_state"):
                    char.set_system_state(target_state)

        logger.debug(
            f"[JARVIS_SEMANTIC_EVENT] EMIT event={clean_event} sound={sound_name} "
            f"state={target_state} sound_played={sound_played}"
        )

        return {
            "handled": True,
            "event": clean_event,
            "sound": sound_name,
            "state": target_state,
            "sound_played": sound_played,
        }

    def _handle_upload_progress(
        self,
        percent: Optional[int],
        session_id: str,
        char: Optional[Any],
        isl: Optional[Any],
        now: float
    ) -> Dict[str, Any]:
        """Rules: Strictly tick only at deciles 10, 20, ..., 90. 0%=no tick, 100%=approve/finish."""
        if percent is None:
            return {"handled": False, "reason": "missing_percent"}

        try:
            pct = int(percent)
        except Exception:
            return {"handled": False, "reason": "invalid_percent"}

        sess = session_id or "default"
        with self._lock:
            if sess not in self._last_ticked_deciles:
                self._last_ticked_deciles[sess] = set()
            ticked = self._last_ticked_deciles[sess]

        # 0% = no tick
        if pct <= 0:
            return {"handled": True, "event": "upload_progress", "percent": pct, "sound_played": False}

        # 100% = complete -> approve/finish
        if pct >= 100:
            with self._lock:
                self._last_ticked_deciles.pop(sess, None)
            sound_played = Sound.play("approve", reason="upload_complete", event_id=f"{sess}_100")
            if char is not None and hasattr(char, "set_system_state"):
                char.set_system_state("happy")
            return {
                "handled": True,
                "event": "upload_complete",
                "percent": 100,
                "sound": "approve",
                "sound_played": sound_played,
            }

        # Check if pct hits a new decile (10, 20, 30, ..., 90)
        # We only tick if pct is an exact multiple of 10 or crossed a decile boundary
        decile = (pct // 10) * 10
        if 10 <= decile <= 90:
            with self._lock:
                if decile not in ticked:
                    ticked.add(decile)
                    should_tick = True
                else:
                    should_tick = False

            if should_tick:
                sound_played = Sound.play("tick", reason=f"upload_{decile}", event_id=f"{sess}_{decile}", cooldown_ms=0)
                return {
                    "handled": True,
                    "event": "upload_progress",
                    "percent": pct,
                    "decile": decile,
                    "sound": "tick",
                    "sound_played": sound_played,
                }

        return {"handled": True, "event": "upload_progress", "percent": pct, "sound_played": False}


# ── Global Functional API ──────────────────────────────────────────────────
_manager = SemanticEventManager.instance()


def jarvis_visual_event(event: str, **kwargs) -> Dict[str, Any]:
    """Public authoritative entry point for all JARVIS Coucou-style semantic events."""
    return _manager.dispatch(event, **kwargs)


def register_visual_targets(
    character: Optional[Any] = None,
    island: Optional[Any] = None,
    visibility_mgr: Optional[Any] = None,
    main_window: Optional[Any] = None
) -> None:
    """Registers GUI widgets with the semantic event manager."""
    _manager.register_targets(character, island, visibility_mgr, main_window)
