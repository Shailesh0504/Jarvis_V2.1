# core/intelligence/decision_engine.py
"""
Proactive Decision and Intent Engine for Jarvis V2.
Synthesizes live desktop context from ActivityMemory and learned behavioral habits
from PatternLearningEngine to evaluate opportunistic triggers with anti-nuisance guardrails.
"""

import logging
import threading
import time
from typing import Any, Dict, List, Optional

from core.observer.models import ActivityEvent, ActivityImportance, ActivityType
from .models import PatternRecord, PatternType, ProactiveSuggestion, SuggestionUrgency, TimePeriod
from .pattern_engine import PatternLearningEngine

logger = logging.getLogger("jarvis.core.intelligence.decision")

# Applications where unsolicited interruptions are suppressed during focus
FOCUS_APPLICATIONS = {
    "excel", "winword", "word", "powerpnt", "powerpoint",
    "code", "vscode", "pycharm", "pycharm64", "devenv", "sublime_text",
    "notepad", "notepad++"
}


class ProactiveDecisionEngine:
    """
    Opportunistic decision-making engine that evaluates whether Jarvis should
    proactively suggest an action, play media, adjust volume, or offer task resumption.
    Strictly enforces distraction guardrails and minimum confidence thresholds.
    """

    def __init__(
        self,
        pattern_engine: Optional[PatternLearningEngine] = None,
        memory: Optional[Any] = None,
        min_confidence: float = 0.70,
        enable_distraction_guard: bool = True
    ):
        self.pattern_engine = pattern_engine or PatternLearningEngine()
        self.memory = memory
        self.min_confidence = max(0.50, min_confidence)
        self.enable_distraction_guard = enable_distraction_guard
        self._lock = threading.RLock()

    def is_user_in_focus_state(self, current_event: Optional[ActivityEvent] = None) -> bool:
        """
        Determines if the user is actively working in a deep focus environment
        (e.g., editing documents, writing code in IDEs).
        """
        if not self.enable_distraction_guard:
            return False

        ev = current_event
        if not ev and self.memory and hasattr(self.memory, "get_current_context"):
            ev = self.memory.get_current_context()

        if not ev:
            return False

        # Check event type
        if ev.event_type in (ActivityType.DOCUMENT_EDITED, ActivityType.FILE_OPENED):
            return True

        # Check focused application
        app = (ev.application or "").lower().strip()
        if app in FOCUS_APPLICATIONS:
            return True

        return False

    def evaluate_opportunity(
        self,
        current_event: Optional[ActivityEvent] = None
    ) -> Optional[ProactiveSuggestion]:
        """
        Evaluates current desktop context against learned habits to determine
        if an opportunistic proactive suggestion should be generated.
        Returns a ProactiveSuggestion if a high-confidence candidate exists, else None.
        """
        try:
            with self._lock:
                ev = current_event
                if not ev and self.memory and hasattr(self.memory, "get_current_context"):
                    ev = self.memory.get_current_context()

                if not ev:
                    return None

                # 1. Distraction Guardrail: suppress non-urgent suggestions in focus states
                if self.is_user_in_focus_state(ev):
                    logger.debug("User is in focus state (%s); suppressing proactive suggestions", ev.application)
                    return None

                # 2. Evaluate Task Resumption (e.g. user returns after being idle)
                suggestion = self._evaluate_resumption_opportunity(ev)
                if suggestion:
                    return suggestion

                # 3. Evaluate Contextual Volume Habit Trigger
                suggestion = self._evaluate_volume_opportunity(ev)
                if suggestion:
                    return suggestion

                # 4. Evaluate Media Preference Trigger (e.g. YouTube/Spotify opened)
                suggestion = self._evaluate_media_opportunity(ev)
                if suggestion:
                    return suggestion

                # 5. Evaluate App-to-App Transition Trigger (e.g. Chrome -> YouTube)
                suggestion = self._evaluate_transition_opportunity(ev)
                if suggestion:
                    return suggestion

                return None
        except Exception as e:
            logger.error("Error evaluating proactive opportunity: %s", e, exc_info=True)
            return None

    def _evaluate_resumption_opportunity(self, ev: ActivityEvent) -> Optional[ProactiveSuggestion]:
        """Evaluates whether to offer resuming previous work when user returns from idle."""
        if ev.event_type != ActivityType.USER_ACTIVE:
            return None

        if not self.memory or not hasattr(self.memory, "get_recent_history"):
            return None

        recent = self.memory.get_recent_history(limit=5)
        # Look for the last active task before idle
        for prev_ev in recent:
            if prev_ev.event_type not in (ActivityType.USER_IDLE, ActivityType.USER_ACTIVE):
                if prev_ev.content_title or prev_ev.application:
                    target_name = prev_ev.content_title or prev_ev.application
                    return ProactiveSuggestion(
                        intent="RESUME_TASK",
                        action="resume_context",
                        target=target_name,
                        confidence=0.75,
                        rationale=f"Aap pehle {target_name} par kaam kar rahe the, kya use continue karein?",
                        urgency=SuggestionUrgency.NORMAL,
                        metadata={
                            "previous_event_id": prev_ev.event_id,
                            "application": prev_ev.application,
                            "content_title": prev_ev.content_title
                        }
                    )
        return None

    def _evaluate_volume_opportunity(self, ev: ActivityEvent) -> Optional[ProactiveSuggestion]:
        """Evaluates whether current volume should be adjusted to match learned habits."""
        # Triggers when media playback starts or when in a media application
        is_media = (
            ev.event_type == ActivityType.VIDEO_PLAYED or
            (ev.website or "").lower() == "youtube" or
            (ev.application or "").lower() in ("spotify", "vlc")
        )
        if not is_media:
            return None

        time_period = TimePeriod.from_timestamp(ev.timestamp)
        app = (ev.application or "general").lower()
        predicted_vol = self.pattern_engine.get_predicted_volume(time_period=time_period, app=app)
        if predicted_vol is None:
            return None

        # Check current volume from event metadata or volume controller
        curr_vol = None
        if ev.metadata and "volume" in ev.metadata:
            curr_vol = ev.metadata["volume"]
        elif ev.metadata and "new_volume" in ev.metadata:
            curr_vol = ev.metadata["new_volume"]
        else:
            try:
                from plugins.audio.volume_controller import get_system_volume
                vol_info = get_system_volume()
                if isinstance(vol_info, dict) and "level" in vol_info:
                    curr_vol = vol_info["level"]
            except Exception:
                pass

        if curr_vol is not None and abs(curr_vol - predicted_vol) >= 10:
            return ProactiveSuggestion(
                intent="ADJUST_VOLUME",
                action="set_volume",
                target=str(predicted_vol),
                confidence=0.80,
                rationale=f"Aapke aamtaur par {time_period.value.lower()} mein volume {predicted_vol}% rakhne ki aadat hai.",
                urgency=SuggestionUrgency.LOW,
                metadata={
                    "current_volume": curr_vol,
                    "target_volume": predicted_vol,
                    "time_period": time_period.value
                }
            )

        return None

    def _evaluate_media_opportunity(self, ev: ActivityEvent) -> Optional[ProactiveSuggestion]:
        """Evaluates whether to suggest favorite music/artist when user opens media platform."""
        app = (ev.application or "").lower()
        site = (ev.website or "").lower()
        is_media_surface = (site == "youtube" or app in ("spotify", "vlc", "youtube"))

        if not is_media_surface:
            return None

        # If already playing a specific video, do not interrupt
        if ev.event_type == ActivityType.VIDEO_PLAYED:
            return None

        # Find highest confidence media preference
        strong_patterns = self.pattern_engine.get_strong_patterns(min_confidence=self.min_confidence)
        media_patterns = [p for p in strong_patterns if p.pattern_type == PatternType.MEDIA_PREFERENCE]
        if not media_patterns:
            return None

        # Select highest confidence media pattern
        best_pattern = max(media_patterns, key=lambda p: (p.confidence, p.frequency))
        key = best_pattern.pattern_key

        target_artist = ""
        if key.startswith("media_artist:"):
            target_artist = key.replace("media_artist:", "").replace("_", " ").title()
        elif "content_title" in best_pattern.data:
            target_artist = best_pattern.data["content_title"]
        else:
            target_artist = key.split(":")[-1].replace("_", " ").title()

        if not target_artist:
            return None

        time_period = TimePeriod.from_timestamp(ev.timestamp)
        return ProactiveSuggestion(
            intent="MEDIA_PLAY_ARTIST",
            action="play_music",
            target=target_artist,
            confidence=best_pattern.confidence,
            rationale=f"Aap aksar {target_artist} sunte hain, kya play karun?",
            urgency=SuggestionUrgency.NORMAL,
            metadata={
                "artist": target_artist,
                "pattern_key": key,
                "time_period": time_period.value
            }
        )

    def _evaluate_transition_opportunity(self, ev: ActivityEvent) -> Optional[ProactiveSuggestion]:
        """Evaluates whether to suggest opening next app based on sequential transitions."""
        curr_app = (ev.application or "").lower().strip()
        if not curr_app:
            return None

        strong_patterns = self.pattern_engine.get_strong_patterns(min_confidence=self.min_confidence)
        trans_prefix = f"trans:{curr_app}->"

        matching = [
            p for p in strong_patterns
            if p.pattern_type == PatternType.APP_TRANSITION and p.pattern_key.startswith(trans_prefix)
        ]
        if not matching:
            return None

        best_trans = max(matching, key=lambda p: (p.confidence, p.frequency))
        next_app = best_trans.pattern_key.split("->")[-1].strip()

        return ProactiveSuggestion(
            intent="LAUNCH_APP",
            action="open_app",
            target=next_app,
            confidence=best_trans.confidence,
            rationale=f"{curr_app.capitalize()} ke baad aap aamtaur par {next_app.capitalize()} kholte hain, kya use open karun?",
            urgency=SuggestionUrgency.NORMAL,
            metadata={
                "from_app": curr_app,
                "to_app": next_app,
                "pattern_key": best_trans.pattern_key
            }
        )
