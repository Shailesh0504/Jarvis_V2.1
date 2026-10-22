# plugins/activity_monitor/plugin.py
"""
Activity Monitor Plugin for Jarvis V2.
Provides persistent, passive screen awareness and temporal activity memory
for tracking watched YouTube videos, active applications, and window focus history.
"""

import logging
from typing import Any, Dict, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from .commands import ACTIONS
from .extractors import YouTubeTitleExtractor
from .memory import ActivityEvent, ActivityMemory
from .observer import ActivityObserver
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.activity_monitor")


class ActivityMonitorPlugin(BasePlugin):
    """
    Manages screen activity tracking, YouTube video detection,
    and temporal queries over past viewing history.
    """

    def __init__(self, manifest: Optional[PluginManifest] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(manifest=manifest, config=config)
        self.memory = ActivityMemory()
        self.extractor = YouTubeTitleExtractor()
        self.observer = ActivityObserver(
            memory=self.memory,
            extractor=self.extractor,
            poll_interval=3.0
        )

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="activity_monitor",
            version="1.0.0",
            description="Silent background screen awareness and structured activity memory observer.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS
        )

    def start_observer(self) -> None:
        """Starts the background activity observer thread if not already running."""
        if not self.observer.is_active:
            try:
                self.observer.start()
                logger.info("ActivityMonitor observer thread started successfully")
            except RuntimeError as e:
                logger.debug("Observer thread start note: %s", e)

    def stop_observer(self) -> None:
        """Stops the background activity observer."""
        if self.observer:
            self.observer.stop()

    def execute(self, action_name: str, parameters: Dict[str, Any]) -> PluginResult:
        """Executes declared activity monitor actions."""
        try:
            if action_name == "get_current_activity":
                return self._handle_get_current_activity(parameters)
            elif action_name == "get_past_activity":
                return self._handle_get_past_activity(parameters)
            elif action_name == "get_activity_history":
                return self._handle_get_activity_history(parameters)
            elif action_name == "poll_activity":
                return self._handle_poll_activity(parameters)
            elif action_name == "get_idle_time":
                return self._handle_get_idle_time(parameters)
            elif action_name == "get_top_applications":
                return self._handle_get_top_applications(parameters)
            elif action_name == "get_productivity_score":
                return self._handle_get_productivity_score(parameters)
            elif action_name == "set_idle_alert":
                return self._handle_set_idle_alert(parameters)
            elif action_name == "export_activity_log":
                return self._handle_export_activity_log(parameters)
            elif action_name == "clear_activity_history":
                return self._handle_clear_activity_history(parameters)
            elif action_name == "get_session_summary":
                return self._handle_get_session_summary(parameters)
            elif action_name == "track_website_domain":
                return self._handle_track_website_domain(parameters)
            elif action_name == "get_focus_switches":
                return self._handle_get_focus_switches(parameters)
            elif action_name == "get_break_recommendation":
                return self._handle_get_break_recommendation(parameters)
            else:
                return PluginResult(
                    success=False,
                    error=f"Unknown action '{action_name}' in ActivityMonitor plugin."
                )
        except Exception as e:
            logger.error("ActivityMonitor execution error on action '%s': %s", action_name, e, exc_info=True)
            return PluginResult(
                success=False,
                error=f"Activity monitor error: {str(e)}"
            )

    def _handle_get_current_activity(self, parameters: Dict[str, Any]) -> PluginResult:
        # Check active event or poll once
        event = self.memory.active_event
        if not event:
            event = self.observer.poll_once()

        if not event:
            return PluginResult(
                success=True,
                data={
                    "event": None,
                    "message": "Boss, abhi koi active window ya activity detect nahi hui."
                }
            )

        # Build honest response
        if event.website == "youtube":
            if event.content_title and event.confidence >= 0.5:
                msg = f"Boss, aap abhi YouTube par '{event.content_title}' dekh rahe hain."
            else:
                msg = "Boss, aap YouTube dekh rahe hain, lekin specific video ka title detect nahi ho paya."
        elif event.application:
            app_disp = event.application.capitalize()
            if event.content_title:
                msg = f"Boss, aap abhi {app_disp} par '{event.content_title}' dekh rahe hain."
            else:
                msg = f"Boss, aap abhi {app_disp} use kar rahe hain."
        else:
            msg = "Boss, abhi koi specific activity detect nahi hui."

        return PluginResult(
            success=True,
            data={
                "event": event.to_dict(),
                "message": msg
            }
        )

    def _handle_get_past_activity(self, parameters: Dict[str, Any]) -> PluginResult:
        website = parameters.get("website", "").strip() or None
        temporal = parameters.get("temporal", "current").strip()
        offset_minutes = int(parameters.get("offset_minutes", 0) or 0)

        # Query temporal activity memory
        event = self.memory.query_temporal(
            website=website,
            temporal=temporal,
            offset_minutes=offset_minutes
        )

        # Zero-hallucination honest response formulation
        if not event:
            site_text = f"{website} par " if website else ""
            if offset_minutes > 0:
                msg = f"Boss, lagbhag {offset_minutes} minute pehle ka koi {site_text}record nahi mila."
            else:
                msg = f"Boss, mujhe is samay {site_text}ka koi recorded video ya activity nahi mili."
            return PluginResult(
                success=True,
                data={
                    "event": None,
                    "found": False,
                    "message": msg
                }
            )

        if event.website == "youtube":
            if event.content_title and event.confidence >= 0.5:
                if offset_minutes > 0:
                    msg = f"Boss, lagbhag {offset_minutes} minute pehle aap YouTube par '{event.content_title}' dekh rahe the."
                elif temporal in ("last", "previous", "pichla", "pichli"):
                    msg = f"Boss, pichla video jo aap YouTube par dekh rahe the wo tha: '{event.content_title}'."
                elif temporal in ("thodi_der_pehle", "a_while_ago", "earlier"):
                    msg = f"Boss, thodi der pehle aap YouTube par '{event.content_title}' dekh rahe the."
                else:
                    msg = f"Boss, aap abhi YouTube par '{event.content_title}' dekh rahe the."
            else:
                msg = "Boss, aap YouTube dekh rahe the, lekin main specific video ka title detect nahi kar paya."
        elif event.content_title:
            app_disp = (event.application or "screen").capitalize()
            if offset_minutes > 0:
                msg = f"Boss, lagbhag {offset_minutes} minute pehle aap {app_disp} par '{event.content_title}' dekh rahe the."
            else:
                msg = f"Boss, aap {app_disp} par '{event.content_title}' dekh rahe the."
        else:
            app_disp = (event.application or "screen").capitalize()
            msg = f"Boss, aap {app_disp} use kar rahe the, lekin koi specific content title nahi mila."

        return PluginResult(
            success=True,
            data={
                "event": event.to_dict(),
                "found": True,
                "message": msg
            }
        )

    def _handle_get_activity_history(self, parameters: Dict[str, Any]) -> PluginResult:
        limit = int(parameters.get("limit", 10) or 10)
        history = self.memory.get_history(limit=limit)
        return PluginResult(
            success=True,
            data={
                "history": history,
                "count": len(history),
                "message": f"Boss, pichli {len(history)} activities retrieve kar li hain."
            }
        )

    def _handle_poll_activity(self, parameters: Dict[str, Any]) -> PluginResult:
        event = self.observer.poll_once()
        return PluginResult(
            success=True,
            data={
                "event": event.to_dict() if event else None,
                "polled": True
            }
        )

    def _get_idle_time_seconds(self) -> float:
        import ctypes
        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        try:
            lii = LASTINPUTINFO()
            lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
                millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
                return max(0.0, float(millis) / 1000.0)
        except Exception:
            pass
        return 0.0

    def _handle_get_idle_time(self, parameters: Dict[str, Any]) -> PluginResult:
        idle_sec = self._get_idle_time_seconds()
        idle_min = round(idle_sec / 60.0, 2)
        is_idle = idle_sec >= 60.0
        return PluginResult(
            success=True,
            data={
                "idle_seconds": round(idle_sec, 1),
                "idle_minutes": idle_min,
                "is_idle": is_idle,
                "message": f"System has been idle for {idle_min} minutes ({round(idle_sec, 1)} seconds)."
            }
        )

    def _get_all_events(self) -> list:
        with self.memory._lock:
            all_ev = list(self.memory._events)
            if self.memory._active_event:
                all_ev.append(self.memory._active_event)
            return all_ev

    def _handle_get_top_applications(self, parameters: Dict[str, Any]) -> PluginResult:
        limit = int(parameters.get("limit", 5) or 5)
        events = self._get_all_events()
        app_stats: Dict[str, Dict[str, Any]] = {}
        for ev in events:
            app = (ev.application or "Unknown").lower()
            dur = ev.duration_seconds
            if app not in app_stats:
                app_stats[app] = {"application": app, "total_seconds": 0.0, "session_count": 0}
            app_stats[app]["total_seconds"] += dur
            app_stats[app]["session_count"] += 1

        ranked = sorted(app_stats.values(), key=lambda x: x["total_seconds"], reverse=True)[:limit]
        for it in ranked:
            it["total_seconds"] = round(it["total_seconds"], 1)
            it["total_minutes"] = round(it["total_seconds"] / 60.0, 2)

        return PluginResult(
            success=True,
            data={
                "top_applications": ranked,
                "count": len(ranked),
                "message": f"Top {len(ranked)} applications ranked by active duration."
            }
        )

    def _handle_get_productivity_score(self, parameters: Dict[str, Any]) -> PluginResult:
        PRODUCTIVE_KEYWORDS = {
            "code", "pycharm", "cursor", "devenv", "notepad++", "sublime", "word",
            "excel", "powerpoint", "terminal", "powershell", "cmd", "git", "bash",
            "slack", "teams", "zoom", "outlook", "github", "docs"
        }
        ENTERTAINMENT_KEYWORDS = {
            "spotify", "vlc", "netflix", "steam", "discord", "game", "youtube"
        }

        events = self._get_all_events()
        prod_sec = 0.0
        ent_sec = 0.0
        neutral_sec = 0.0

        for ev in events:
            app = (ev.application or "").lower()
            site = (ev.website or "").lower()
            dur = max(1.0, ev.duration_seconds)

            if any(k in app for k in PRODUCTIVE_KEYWORDS) or any(k in site for k in PRODUCTIVE_KEYWORDS):
                prod_sec += dur
            elif any(k in app for k in ENTERTAINMENT_KEYWORDS) or any(k in site for k in ENTERTAINMENT_KEYWORDS):
                ent_sec += dur
            else:
                neutral_sec += dur

        total_sec = prod_sec + ent_sec + neutral_sec
        if total_sec > 0:
            score = round((prod_sec / (prod_sec + ent_sec if (prod_sec + ent_sec) > 0 else total_sec)) * 100, 1)
        else:
            score = 100.0

        return PluginResult(
            success=True,
            data={
                "productivity_score": score,
                "productive_seconds": round(prod_sec, 1),
                "entertainment_seconds": round(ent_sec, 1),
                "neutral_seconds": round(neutral_sec, 1),
                "total_seconds": round(total_sec, 1),
                "message": f"Productivity score: {score}% ({round(prod_sec/60, 1)}m productive, {round(ent_sec/60, 1)}m entertainment)."
            }
        )

    def _handle_set_idle_alert(self, parameters: Dict[str, Any]) -> PluginResult:
        threshold = int(parameters.get("threshold_minutes", 15) or 15)
        idle_sec = self._get_idle_time_seconds()
        idle_min = round(idle_sec / 60.0, 2)
        exceeded = idle_min >= threshold
        msg = f"System idle ({idle_min}m) has exceeded threshold ({threshold}m)!" if exceeded else f"System idle ({idle_min}m) is within limit ({threshold}m)."
        return PluginResult(
            success=True,
            data={
                "threshold_minutes": threshold,
                "current_idle_minutes": idle_min,
                "alert_triggered": exceeded,
                "message": msg
            }
        )

    def _handle_export_activity_log(self, parameters: Dict[str, Any]) -> PluginResult:
        import os
        import json
        import csv
        fmt = str(parameters.get("format", "json")).strip().lower()
        out_path = str(parameters.get("output_path", "")).strip()
        if not out_path:
            out_path = os.path.join(os.getcwd(), "data", f"activity_log_export.{fmt}")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        events = self._get_all_events()
        raw_events = [ev.to_dict() for ev in events]

        if fmt == "csv":
            if raw_events:
                fields = list(raw_events[0].keys())
                with open(out_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fields)
                    writer.writeheader()
                    for r in raw_events:
                        r_copy = dict(r)
                        if isinstance(r_copy.get("metadata"), dict):
                            r_copy["metadata"] = json.dumps(r_copy["metadata"])
                        writer.writerow(r_copy)
            else:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write("event_id,application,website,content_title,duration_seconds\n")
        else:
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(raw_events, f, indent=2)

        return PluginResult(
            success=True,
            data={
                "output_path": out_path,
                "records_exported": len(raw_events),
                "format": fmt,
                "message": f"Exported {len(raw_events)} activity records to {out_path}."
            }
        )

    def _handle_clear_activity_history(self, parameters: Dict[str, Any]) -> PluginResult:
        with self.memory._lock:
            count = len(self.memory._events)
            self.memory._events.clear()
            self.memory._active_event = None
        return PluginResult(
            success=True,
            data={"cleared_count": count, "message": f"Cleared {count} activity events from memory."}
        )

    def _handle_get_session_summary(self, parameters: Dict[str, Any]) -> PluginResult:
        events = self._get_all_events()
        total_sec = sum(ev.duration_seconds for ev in events)
        unique_apps = set(ev.application for ev in events if ev.application)
        longest = max(events, key=lambda x: x.duration_seconds) if events else None

        return PluginResult(
            success=True,
            data={
                "total_events": len(events),
                "total_duration_seconds": round(total_sec, 1),
                "total_duration_minutes": round(total_sec / 60.0, 2),
                "unique_applications_count": len(unique_apps),
                "unique_applications": sorted(list(unique_apps)),
                "longest_session": longest.to_dict() if longest else None,
                "message": f"Session summary: {len(events)} events across {len(unique_apps)} applications ({round(total_sec/60, 1)}m monitored)."
            }
        )

    def _handle_track_website_domain(self, parameters: Dict[str, Any]) -> PluginResult:
        events = self._get_all_events()
        domain_stats: Dict[str, float] = {}
        for ev in events:
            domain = ev.website or (ev.application if ev.application in {"chrome", "brave", "firefox", "msedge"} else None)
            if domain:
                domain_stats[domain] = domain_stats.get(domain, 0.0) + ev.duration_seconds

        ranked = [{"domain": d, "total_seconds": round(s, 1), "total_minutes": round(s / 60.0, 2)}
                  for d, s in sorted(domain_stats.items(), key=lambda x: x[1], reverse=True)]

        return PluginResult(
            success=True,
            data={"domains": ranked, "count": len(ranked)}
        )

    def _handle_get_focus_switches(self, parameters: Dict[str, Any]) -> PluginResult:
        events = self._get_all_events()
        switches = 0
        last_app = None
        for ev in events:
            if ev.application and ev.application != last_app:
                if last_app is not None:
                    switches += 1
                last_app = ev.application

        assessment = "Low" if switches < 5 else ("Moderate" if switches < 15 else "High (Multitasking)")
        return PluginResult(
            success=True,
            data={
                "total_switches": switches,
                "events_count": len(events),
                "distraction_level": assessment,
                "message": f"Detected {switches} window focus switches. Multitasking level: {assessment}."
            }
        )

    def _handle_get_break_recommendation(self, parameters: Dict[str, Any]) -> PluginResult:
        max_continuous = int(parameters.get("max_continuous_minutes", 50) or 50)
        events = self._get_all_events()
        active_sec = sum(ev.duration_seconds for ev in events)
        active_min = round(active_sec / 60.0, 1)
        recommend_break = active_min >= max_continuous

        return PluginResult(
            success=True,
            data={
                "active_work_minutes": active_min,
                "max_continuous_minutes": max_continuous,
                "recommend_break": recommend_break,
                "message": f"A break is recommended! You have worked continuously for {active_min} minutes." if recommend_break else f"Keep going! Worked {active_min}/{max_continuous} minutes before recommended rest."
            }
        )
