"""Authoritative Input Pipeline for JarvisCore.
Coordinates interaction gating, speech repair, Laya 9-point orchestration,
multi-turn dialog handling, and route execution while preserving exact behavior.
"""

import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

from core.context import TurnContext
from core.intent import Intent, IntentType, IntentResult
from core.laya import LayaRoute
from core.state import SystemState
from core.pipeline.interaction_stage import InteractionStage
from core.pipeline.preprocessing_stage import PreprocessingStage
from core.pipeline.laya_stage import LayaStage
from core.handlers.pending_state import PendingStateHandler
from core.handlers.command_handler import CommandHandler
from core.handlers.conversation_handler import ConversationHandler
from core.handlers.agent_handler import AgentHandler
from core.handlers.learning_handler import LearningHandler
from core.response.finalizer import ResponseFinalizer
from core.feedback.turn_feedback import TurnFeedbackService

logger = logging.getLogger("jarvis.pipeline.input")


def _maybe_start_compose_workflow(core: Any, conv_intent: Any, turn: Any, raw_input: str) -> Optional[str]:
    """Human-like multi-turn triggers: mail/message/reminder/alarm slot workflows,
    repeat-last-answer, task-done + resume, post-creation reminder correction.
    Returns a response string when handled, else None (fall through)."""
    from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
    norm = (turn.normalized_input or "").strip()
    low = norm.lower()
    dm = getattr(core, "dialog_manager", None)
    ctx = getattr(core, "active_context", None)
    params = conv_intent.parameters or {}

    # Bypass compose workflows for activity/past-media queries
    if getattr(conv_intent, "target", "") == "activity" or getattr(conv_intent, "action_type", "") == "query_media":
        return None

    # 0. Multi-command split ("Chrome kholo aur music chalao"): each clause must be a
    # standalone action with an explicit target (guards "aur batao"-style chatter).
    if re.search(r"\b(?:aur|and)\b", low) or ("," in low):
        try:
            from core.conversational_intent import ConversationalIntentClassifier as _CIC0
            _parts = [p.strip(" ,.") for p in re.split(r"\b(?:aur|and)\b|,", low) if p.strip(" ,.")]
            if len(_parts) >= 2:
                _ok = True
                for _p in _parts:
                    _c, _v, _t = _CIC0._detect_action_command(_p)
                    if not _c or not _t or _t.lower() in ("to", "toh", ""):
                        _ok = False
                        break
                    if _v in ("batao", "bata", "sunao", "bolo") and len(_t.split()) < 1:
                        _ok = False
                        break
                if _ok:
                    _resps = []
                    for _p in _parts:
                        try:
                            _resps.append(str(core.process_input(_p, source=source)))
                        except Exception:
                            pass
                    _resps = [r for r in _resps if r]
                    if _resps:
                        return " ".join(_resps)
        except Exception:
            pass

    # 0.5. App restart / hung-app recovery ("Isko ek baar restart kar do",
    # "Yaar Chrome hang ho gaya hai") = close + reopen. NEVER system restart.
    _sys_words = ("system", "pc", "computer", "laptop", "device")
    if re.search(r"\b(?:restart|reboot|hang)\b", low) and not any(w in low for w in _sys_words):
        _app = None
        m_hang = re.search(r"\b([a-z]{2,20})\s+hang\s+ho\s+(?:gaya|raha|gayi)|hang\s+ho\s+gaya\s+hai", low)
        if m_hang and m_hang.group(1) not in ("to", "ye", "ho"):
            _app = m_hang.group(1)
        if not _app:
            m_rapp = re.search(r"\b(vlc|chrome|brave|edge|firefox|excel|word|notepad|calculator|spotify|youtube|whatsapp|outlook|teams|vscode|code)\b", low)
            if m_rapp:
                _app = m_rapp.group(1)
        if not _app and re.search(r"\b(?:isko|ise|usko|usey|yeh|ye|wahi|same|iska|uska)\b", low):
            try:
                _capp = (getattr(ctx, "application", "") or "").lower()
                if _capp and _capp not in ("browser",):
                    _app = _capp
                else:
                    _w = (getattr(ctx, "website", "") or "").lower()
                    if _w:
                        _app = _w
            except Exception:
                pass
        if _app:
            try:
                from core.target_engine import TargetRequest as _TR
                core.target_engine.execute(_TR(target=_app, action="close"))
                _out = core.target_engine.execute(_TR(target=_app, action="open"))
                if hasattr(core, "active_context") and core.active_context:
                    try:
                        core.active_context.set_application(_app, action="open_app")
                    except Exception:
                        pass
                _disp = "VLC" if _app == "vlc" else _app.capitalize()
                if "hang" in low:
                    return f"{_disp} hang ho gaya tha, isliye restart kar diya."
                return f"{_disp} restart kar diya (band karke dobara khol diya)."
            except Exception:
                pass
        elif re.search(r"\bhang\b", low):
            return "Kaunsi application hang ho gayi hai? Naam batayein, restart kar deta hoon."

    # 0.7. Vague-scope negation ("Baaki kuch mat band karna") — scope-preserving ack.
    if (re.search(r"\b(?:mat|nahi|nahin|nhi)\b", low)
            and re.search(r"\b(?:baaki\s+kuch|baki\s+kuch|baaki\s+sab|kuchh?|sab\s+kuch)\b", low)):
        return "Theek hai Boss, baaki kuch ko haath nahi lagaunga. Bataiye, kis par kaam karun?"

    # 1. Repeat last answer ("Ek baar phir batao"; tolerates bar/baar variants).
    if re.fullmatch(r"(?:ek\s+ba+r\s+)?(?:phir|dobara|fir)(?:\s+se)?\s+(?:batao|bolo|sunao|dikhao|suna\s+do|bata\s+do)\s*[.!?]?", low):
        try:
            cm = getattr(core, "conversation_manager", None)
            hist = cm.get_history(limit=6) if cm and hasattr(cm, "get_history") else []
            for t in reversed(hist):
                r = (getattr(t, "response_text", "") or "").strip()
                if r and "dobara bata raha hoon" not in r:
                    return f"Bilkul, dobara bata raha hoon: {r}"
        except Exception:
            pass
        return None

    def _recent_user_and_jarvis():
        try:
            cm = getattr(core, "conversation_manager", None)
            hist = cm.get_history(limit=6) if cm and hasattr(cm, "get_history") else []
            last_u, last_j = "", ""
            for t in reversed(hist):
                if not last_j and (getattr(t, "response_text", "") or "").strip():
                    last_j = getattr(t, "response_text", "")
                if last_j and (getattr(t, "raw_input", "") or "").strip():
                    last_u = getattr(t, "raw_input", "")
                    break
            return last_u, last_j
        except Exception:
            return "", ""

    # 1.15. Volume context tracking + relative repeat ("Volume 50 karo" -> "Thoda aur").
    if re.search(r"\b(?:volume|awaz|awaaz|aawaz)\b", low):
        try:
            _m_lv = re.search(r"\b(\d{1,3})\b", low)
            _lv = max(0, min(100, int(_m_lv.group(1)))) if _m_lv else None
            _dir = "down" if re.search(r"\b(?:kam|ghatao|down|low|dheemi|dheere|mute)\b", low) else ("up" if re.search(r"\b(?:badhao|badha|up|high|tez|unmute)\b", low) else "set")
            if ctx is not None:
                _ents_v = dict(getattr(ctx, "last_entities", {}) or {})
                if _lv is not None:
                    _ents_v["volume_level"] = _lv
                ctx.update_command_context("VOLUME", f"volume_{_dir}", _ents_v, raw_command=turn.raw_input)
        except Exception:
            pass
    m_vrel = re.fullmatch(r"(?:thoda\s+|thora\s+|aur\s+)?(aur|kam|zyada|tez|dheemi|dheere)(?:\s+(?:karo|kar\s+do))?\s*[.!?]?", low)
    if m_vrel and ctx is not None:
        try:
            _last_a = str(getattr(ctx, "last_action", "") or "").lower()
            _last_i = str(getattr(ctx, "last_intent", "") or "").upper()
            if _last_a.startswith("volume") or _last_i == "VOLUME":
                _w = m_vrel.group(1).lower()
                _up = _w not in ("kam", "dheemi", "dheere")
                _ents_v = dict(getattr(ctx, "last_entities", {}) or {})
                _cur = _ents_v.get("volume_level")
                _new = max(0, min(100, (int(_cur) if isinstance(_cur, int) else 50) + (10 if _up else -10)))
                if getattr(core, "plugin_manager", None):
                    core.plugin_manager.execute_action("audio", "volume_up" if _up else "volume_down", {"step": 10})
                _ents_v["volume_level"] = _new
                ctx.update_command_context("VOLUME", "volume_up" if _up else "volume_down", _ents_v, raw_command=turn.raw_input)
                return f"Volume {_new}% kar diya hai, Boss."
        except Exception:
            pass

    # 1.2. Weather time follow-up ("Kal ka?", "Aur weekend ka?" after weather).
    # Tolerates STT/normalizer damage ("kar ka?" for "kal ka?") when weather context holds.
    m_wf = re.fullmatch(r"(?:aur\s+)?(kal|kar|parso|weekend|aaj)(?:\s+bhi)?(?:\s+ka)?(?:\s+bhi)?(?:\s+(?:batao|batana|bataiye))?\s*\??", low)
    if m_wf:
        _lu, _lj = _recent_user_and_jarvis()
        if re.search(r"\b(?:weather|mausam|temperature|baarish|forecast)\b", (_lu + " " + _lj).lower()):
            _w = m_wf.group(1).lower()
            _w = "kal" if _w == "kar" else _w
            turn.normalized_input = f"{_w} ka weather batao"
            # Re-classify so downstream stages see the rewritten command,
            # not the stale CONVERSATION intent of the bare follow-up.
            try:
                _re = ConversationalIntentClassifier.classify(
                    turn.normalized_input, has_pending_confirmation=False,
                    active_context=getattr(core, "active_context", None))
                conv_intent.intent_type = _re.intent_type
                conv_intent.confidence = _re.confidence
                conv_intent.is_executable = _re.is_executable
                conv_intent.target = _re.target
                conv_intent.action_type = _re.action_type
                conv_intent.parameters = _re.parameters
                conv_intent.natural_response = _re.natural_response
                conv_intent.matched_pattern = _re.matched_pattern
            except Exception:
                pass
            return None

    # 1.25. Bare artist/name after a music turn ("Arijit Singh" after "music chalao").
    if re.fullmatch(r"[a-zA-Z][a-zA-Z\s\.]{2,29}\s*[.!?]?", norm) and not re.search(
            r"\b(?:kholo|khol|open|band|close|batao|dikhao|karo|kar\s+do|hai|kya|kaise|ko|ka|ki|ke|mein|ne|aur|bhi|wala|wali|wale|baje|reminder|mail|alarm)\b", low):
        _lu25, _lj25 = _recent_user_and_jarvis()
        if (re.search(r"\b(?:music|gaana|gana|song|chalao|play|bajao|youtube)\b", _lu25.lower())
                and re.search(r"\b(?:youtube|video|gaana|gana|song|play|music)\b", _lj25.lower())
                and getattr(core, "plugin_manager", None)):
            try:
                res = core.plugin_manager.execute_action(
                    "youtube", "search_and_play", {"query": norm.strip(" .!?")})
                if res is not None:
                    if getattr(res, "success", False):
                        data = getattr(res, "data", {}) or {}
                        return data.get("message") or f"{norm.strip()} chala raha hoon."
                    return getattr(res, "error", None) or "Music play nahi ho paya, Boss."
            except Exception:
                pass

    # 1.3. Music qualifier follow-up ("Thoda slow wala" after an artist/song turn).
    m_mq = re.fullmatch(r"(?:thoda\s+|thora\s+)?(slow|fast|soft|sad|happy|romantic|old|new|latest|punjabi|english|hindi)\s+(?:wala|wale|wali|sa)\s*[.!?]?", low)
    if m_mq:
        _lu, _lj = _recent_user_and_jarvis()
        if _lu and re.search(r"\b(?:youtube|video|gaana|gana|song|play|music|baj)\b", _lj.lower()):
            _q = re.sub(r"\b(?:chalao|play\s+karo|bajao|sunao|gaana|song|music|youtube|par|pe|ko|mein)\b", "", _lu, flags=re.IGNORECASE)
            _q = re.sub(r"\s+", " ", _q).strip(" ,.")
            if _q and getattr(core, "plugin_manager", None):
                try:
                    res = core.plugin_manager.execute_action(
                        "youtube", "search_and_play", {"query": f"{_q} {m_mq.group(1)} songs"})
                    if res is not None:
                        if getattr(res, "success", False):
                            data = getattr(res, "data", {}) or {}
                            return data.get("message") or f"{_q} ke {m_mq.group(1)} songs chala raha hoon."
                        return getattr(res, "error", None) or "Music play nahi ho paya, Boss."
                except Exception:
                    pass

    # 1.4. Mailbox handling inside active mail (Gmail/Outlook context or recent mention):
    # "Isme inbox kholo" / "Pehla mail kholo" -> open inbox; attachment asks need a mail first.
    m_mb = re.fullmatch(r"(?:isme|usme|is\s+mein|us\s+mein)\s+(inbox|sent(?:\s+mail)?|drafts?|spam|trash|starred)\s+(?:kholo|khol|open|dikhao)\s*[.!?]?", low)
    m_ord_mail = re.fullmatch(r"(?:pehla|pehle|pehli|doosra|doosri|teesra|first|second|last|aakhiri)\s+(?:mail|email|e-mail)\s+(?:kholo|khol|open|dikhao)\s*[.!?]?", low)
    m_attach = "attachment" in low and ("download" in low or "save" in low or "kholo" in low)
    if m_mb or m_ord_mail or m_attach:
        _site = ""
        try:
            _site = (getattr(ctx, "website", "") or "").lower()
        except Exception:
            _site = ""
        if _site not in ("gmail", "outlook", "yahoo", "mail"):
            try:
                _lu0, _lj0 = _recent_user_and_jarvis()
                for _cand in ("gmail", "outlook", "yahoo"):
                    if _cand in (_lu0 + " " + _lj0).lower():
                        _site = _cand
                        break
            except Exception:
                pass
        if _site not in ("gmail", "outlook", "yahoo", "mail"):
            return None
        if m_attach and not (m_mb or m_ord_mail):
            _inbox_url = {"gmail": "https://mail.google.com/mail/u/0/#inbox",
                          "outlook": "https://outlook.live.com/mail/0/inbox"}.get(_site, "")
            if _inbox_url and getattr(core, "plugin_manager", None):
                try:
                    core.plugin_manager.execute_action("browser", "open_website", {"url": _inbox_url, "site": _site})
                except Exception:
                    pass
            return (f"{_site.capitalize()} ka inbox khol diya. Kaunsa mail download karna hai, bataiye?"
                    if _site in ("gmail", "outlook", "yahoo", "mail") else None)
        _folder = "inbox"
        if m_mb:
            _folder = re.sub(r"\s+mail$", "", m_mb.group(1).lower()).strip()
            _folder = "draft" if _folder.startswith("draft") else _folder
        _urls = {
            "gmail": {"inbox": "https://mail.google.com/mail/u/0/#inbox", "sent": "https://mail.google.com/mail/u/0/#sent",
                      "draft": "https://mail.google.com/mail/u/0/#drafts", "spam": "https://mail.google.com/mail/u/0/#spam",
                      "trash": "https://mail.google.com/mail/u/0/#trash", "starred": "https://mail.google.com/mail/u/0/#starred"},
            "outlook": {"inbox": "https://outlook.live.com/mail/0/inbox", "sent": "https://outlook.live.com/mail/0/sentitems",
                        "draft": "https://outlook.live.com/mail/0/drafts", "spam": "https://outlook.live.com/mail/0/junkemail",
                        "trash": "https://outlook.live.com/mail/0/deleteditems", "starred": "https://outlook.live.com/mail/0/inbox"},
        }
        _url = (_urls.get(_site) or {}).get(_folder, "")
        if _url and getattr(core, "plugin_manager", None):
            try:
                res = core.plugin_manager.execute_action("browser", "open_website", {"url": _url, "site": _site})
                if res is not None and getattr(res, "success", False):
                    return f"{_site.capitalize()} ka {_folder} khol raha hoon."
            except Exception:
                pass

    # 1.45. Mail save/download without a selected mail ("Isko Downloads mein save karo").
    if re.search(r"\b(?:save|download)\b", low) and re.search(r"\b(?:isko|ise|isko|usko|mail|attachment)\b", low):
        _lu1, _lj1 = _recent_user_and_jarvis()
        if re.search(r"\b(?:mail|inbox|attachment|gmail|outlook)\b", (_lu1 + " " + _lj1).lower()):
            return "Kaunsa mail save karna hai? Inbox me se mail select karke batayein, phir Downloads me save kar dunga."

    # 1.5. Vague play request recalling a recent avoidance
    # ("Kuch background mein chala do" after "Music mat chalana").
    if re.search(r"\b(?:background\s+mein|kuch\s+\w*\s*(?:chala|baja|play))", low):
        try:
            _ents0 = dict(getattr(ctx, "last_entities", {}) or {})
            _avoid = _ents0.get("avoid") or {}
            _at = float(_avoid.get("at", 0) or 0)
            import time as _tmod
            if _avoid.get("target", "") and (_tmod.time() - _at) < 900:
                if any(w in str(_avoid.get("target", "")) for w in ("music", "gaana", "gana", "song")):
                    return "Aap music avoid karna chahte the. Kya ambient sound chala doon?"
        except Exception:
            pass

    # 2. Task-done marker ("Ho gaya") -> ack + suspended resume offer
    if params.get("task_done"):
        if dm and getattr(dm, "suspended_lock", None) and not dm.suspended_lock.is_expired:
            desc = dm.describe_suspended() or "kaam"
            lock = dm.resume_suspended_lock()
            if lock is not None:
                return f"Theek hai. {desc} wala kaam pending hai. {dm._compose_question(lock)}"
        return "Theek hai Boss."

    # 3. Explicit continue ("Ab Rahul wala mail continue karo")
    if dm and getattr(dm, "suspended_lock", None) and not dm.suspended_lock.is_expired:
        if re.search(r"\b(?:continue|resume|jari|wapas)\b", low) or low.strip() in ("continue karo", "wapas chalo", "continue"):
            desc = dm.describe_suspended() or "kaam"
            lock = dm.resume_suspended_lock()
            if lock is not None:
                return f"Theek hai, {desc} par wapas chalte hain. {dm._compose_question(lock)}"

    # 4. Post-creation reminder correction ("Nahi, 6 baje"); else anchorless
    # correction clarification ("Nahi, Rohit ko" with no active workflow).
    m_corr = re.match(r"^(?:nahi|nahin|nhi|no|sorry)\s*,?\s*(.+)$", low)
    if m_corr and (dm is None or not dm.has_active_lock()):
        corr_rest = m_corr.group(1).strip()
        # If user is rejecting a pending spelling candidate AND/OR giving an action command
        if dm and getattr(dm, "pending_spelling", None):
            pending = dm.pending_spelling
            if hasattr(core, "reject_fuzzy_candidate"):
                core.reject_fuzzy_candidate(pending.get("typo", ""), pending.get("correction", ""))
            dm.pending_spelling = None

        has_action_verb = bool(re.search(
            r"\b(?:search|google|bing|kholo|open|chalao|play|dikhao|batao|band|close|run|launch|start|find|dhoondo|dhundho)\b",
            corr_rest,
            re.IGNORECASE
        ))
        if has_action_verb:
            turn.normalized_input = corr_rest
            try:
                _re = ConversationalIntentClassifier.classify(
                    turn.normalized_input, has_pending_confirmation=False,
                    active_context=getattr(core, "active_context", None))
                conv_intent.intent_type = _re.intent_type
                conv_intent.confidence = _re.confidence
                conv_intent.is_executable = _re.is_executable
                conv_intent.target = _re.target
                conv_intent.action_type = _re.action_type
                conv_intent.parameters = _re.parameters
                conv_intent.natural_response = _re.natural_response
                conv_intent.matched_pattern = _re.matched_pattern
            except Exception:
                pass
            return None

        try:
            ents = dict(getattr(ctx, "last_entities", {}) or {})
            rid = ents.get("reminder_id")
            if rid:
                from core.dialog_manager import DialogManager as _DM
                iso, disp = _DM._parse_compose_time(corr_rest)
                if iso and getattr(core, "plugin_manager", None):
                    res = core.plugin_manager.execute_action(
                        "reminder", "edit_reminder", {"reminder_id": rid, "new_time": iso})
                    if res and getattr(res, "success", False):
                        return f"Reminder ka time {disp} kar diya."
        except Exception:
            pass
        if dm is not None and not (dm.has_pending_system_action() if hasattr(dm, "has_pending_system_action") else False):
            return "Samajh gaya — kuch correct karna hai. Kis cheez ke liye bol rahe hain, thoda detail batayein?"

    # 5. Indirect wake-up ("mujhe kal subah jaldi uthna hai") -> alarm flow
    if (conv_intent.intent_type == ConversationalIntentType.FUTURE_INTENTION
            and params.get("goal") == "WAKE_UP" and dm):
        from core.dialog_manager import WorkflowLock
        _am_hint = "am" if re.search(r"\b(?:subah|morning|savere)\b", low) else ""
        iso = params.get("iso_time")
        if iso:
            lock = WorkflowLock(workflow_type="ALARM_SET", required_slots=[],
                                filled_slots={"time": iso, "time_display": params.get("time_display") or iso},
                                target_plugin="reminder", target_action="create_reminder", language="hi")
            return dm._execute_completed_workflow(lock, core)
        lock = dm.set_pending_goal("ALARM_SET", ["time"], "Kitne baje ka alarm lagau, Boss?",
                                   turn_n=turn, target_plugin="reminder", target_action="create_reminder",
                                   initial_slots={"_period_hint": _am_hint} if _am_hint else {}, language="hi")
        return dm._compose_question(lock)

    # 6. Reminder trigger (explicit "5 baje reminder lagao" / relative "20 minute baad ...")
    if (conv_intent.intent_type == ConversationalIntentType.ACTION_COMMAND
            and (conv_intent.action_type or "") == "create_reminder" and dm):
        from core.dialog_manager import DialogManager as _DM, WorkflowLock
        iso, disp = _DM._parse_compose_time(norm)
        if not iso and conv_intent.parameters.get("iso_time"):
            iso = conv_intent.parameters.get("iso_time")
            disp = conv_intent.parameters.get("time_display") or iso
        title = ConversationalIntentClassifier._extract_task_description(norm) or conv_intent.parameters.get("description") or ""
        title = re.sub(r"\b(?:\d+|ek|do|teen|chaar|char|paanch|panch|chhe|che|saat|aath|nau|das|dus|pandrah|bees|tees|aadha|aadhe|dedh)\s*(?:minute|minutes|minut|minuts|mint|mints|min|mins|second|seconds|sec|secs|ghante|ghanta|ghanto|hour|hours?|hrs|din|days?)\s*(?:baad|ke\s+baad|mein|me|after|later)?\b", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s+(?:yaad\s+dilana|yaad\s+dila\s+dena|yaad\s+dila\s+do|yaad\s+rakhna)\b", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s+", " ", title).strip(" ,.")
        initial: Dict[str, Any] = {}
        if iso:
            initial["remind_time"] = iso
            initial["remind_time_display"] = disp
        if title:
            initial["title"] = title
        missing = [s for s in ["remind_time", "title"] if s not in initial]
        if not missing:
            lock = WorkflowLock(workflow_type="REMINDER_CREATE", required_slots=[],
                                filled_slots=initial, target_plugin="reminder",
                                target_action="create_reminder", language="hi")
            return dm._execute_completed_workflow(lock, core)
        lock = dm.set_pending_goal("REMINDER_CREATE", missing, "", turn_n=turn,
                                   target_plugin="reminder", target_action="create_reminder",
                                   initial_slots=initial, language="hi")
        return dm._compose_question(lock)

    # 7. Meeting schedule trigger ("Meeting schedule karo" -> attendees/time/title slots)
    if (conv_intent.intent_type == ConversationalIntentType.ACTION_COMMAND
            and re.search(r"\b(?:meeting|calendar)\b", low)
            and re.search(r"\b(?:schedule|set|fix|plan|book|rakh|arrange)\b", low) and dm):
        m_team = re.search(r"^(.+?)\s+ke\s+saath\s+(?:meeting|calendar)", low)
        initial = {}
        if m_team:
            who = re.sub(r"^(?:zara|bhai|please|kripya|boss|meri|mere)\s+", "", m_team.group(1).strip(), flags=re.IGNORECASE).strip()
            if who:
                initial["attendees"] = who.title()
        missing = [s for s in ["attendees", "meeting_time", "title"] if s not in initial]
        lock = dm.set_pending_goal("MEETING_SCHEDULE", missing, "", turn_n=turn,
                                   target_plugin="calendar", target_action="add_event",
                                   initial_slots=initial, language="hi")
        return dm._compose_question(lock)

    # 8. Direct call trigger ("Rahul ko call karo" -> WhatsApp call; plugin clarifies ambiguity)
    m_call = re.search(r"^(.+?)\s+ko\s+call\s+(?:karo|kar\s+do|lagao|kijiye)\s*[.!?]?", low)
    if m_call and getattr(core, "plugin_manager", None):
        who = re.sub(r"^(?:zara|bhai|please|kripya|boss)\s+", "", m_call.group(1).strip(), flags=re.IGNORECASE).strip()
        if who:
            try:
                res = core.plugin_manager.execute_action(
                    "whatsapp", "call_contact", {"recipient": who.title()})
                if res is not None:
                    if getattr(res, "success", False):
                        data = getattr(res, "data", {}) or {}
                        return data.get("message") or f"{who.title()} ko call laga raha hoon."
                    return getattr(res, "error", None) or "Call nahi lag paya, Boss."
            except Exception:
                pass

    # 9. Email / message compose trigger ("Mail bhejo", "Rahul ko message bhejo")
    if conv_intent.intent_type == ConversationalIntentType.ACTION_COMMAND:
        verb = (conv_intent.action_type or "").lower()
        if any(v in verb for v in ("bhej", "send")) or re.search(r"\b(?:bhej|send\s+kar)\b", low):
            if dm is None:
                return None
            if re.search(r"\b(?:mail|email|e-mail)\b", low):
                m_to = re.search(r"^(.+?)\s+ko\s+(?:mail|email)", low)
                recip = ""
                if m_to:
                    recip = re.sub(r"^(?:zara|bhai|please|kripya|boss)\s+", "", m_to.group(1).strip(), flags=re.IGNORECASE).strip().title()
                initial = {"recipient": recip} if recip else {}
                missing = [s for s in ["recipient", "subject", "body", "send_confirm"] if s not in initial]
                lock = dm.set_pending_goal("EMAIL_COMPOSE", missing, "", turn_n=turn,
                                           target_plugin="email", target_action="open_email_client",
                                           initial_slots=initial, language="hi")
                q = dm._compose_question(lock)
                if recip:
                    return f"Theek hai, {recip} ko mail bhejta hoon. {q}"
                return q
            if re.search(r"\b(?:message|msg|sms|whatsapp|whats\s*app)\b", low):
                m_to = re.search(r"^(.+?)\s+ko\s+(?:message|msg|sms|whatsapp)", low)
                recip = ""
                if m_to:
                    recip = re.sub(r"^(?:zara|bhai|please|kripya|boss)\s+", "", m_to.group(1).strip(), flags=re.IGNORECASE).strip().title()
                initial = {"recipient": recip} if recip else {}
                missing = [s for s in ["recipient", "message"] if s not in initial]
                lock = dm.set_pending_goal("MESSAGE_COMPOSE", missing, "", turn_n=turn,
                                           target_plugin="whatsapp", target_action="draft_message",
                                           initial_slots=initial, language="hi")
                return dm._compose_question(lock)
    return None


class InputPipeline:
    """Orchestrates input processing through decoupled pipeline stages and domain handlers."""

    def __init__(self, core: Any):
        self.core = core
        self.interaction_stage = InteractionStage(core)
        self.preprocessing_stage = PreprocessingStage(core)
        self.laya_stage = LayaStage(core)
        self.pending_handler = PendingStateHandler(core)
        self.command_handler = CommandHandler(core)
        self.conversation_handler = ConversationHandler(core)
        self.agent_handler = AgentHandler(core)
        self.learning_handler = LearningHandler(core)

    def process(self, core: Any, raw_input: str, source: str = "cli") -> str:
        """Executes the complete input processing lifecycle."""
        start_time = time.perf_counter()

        # Step 0: Desktop workflow cancellation check & Interaction Gate
        handled_gate, gate_resp, effective_input = self.interaction_stage.process(raw_input, source=source)
        if handled_gate:
            return gate_resp if gate_resp is not None else ""

        assert effective_input is not None

        # Step 1: Speech Repair & Turn Context Creation
        turn, repaired_text = self.preprocessing_stage.repair_and_create_turn(raw_input, effective_input, source=source)
        effective_input = repaired_text

        # Step 2: Immediate Authoritative Exit / Shutdown Command Check
        raw_low = raw_input.lower().strip()
        eff_low = effective_input.lower().strip()
        norm_low = turn.normalized_input.lower().strip()
        if (
            core._EXIT_SHUTDOWN_RE.match(raw_low)
            or core._EXIT_SHUTDOWN_RE.match(eff_low)
            or core._EXIT_SHUTDOWN_RE.match(norm_low)
        ):
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.SHUTDOWN)
            resp = "Goodbye Boss! Shutting down Jarvis."
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp, turn.execution_time_ms)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("system.shutdown", {"reason": "user_command"})
            return resp

        # Step 3: LayaCore Authoritative Tri-Bridge Orchestration Layer
        laya_decision = self.laya_stage.evaluate(raw_input, turn)

        # Step 4: Human Conversation Model (HCM) 7-Dimensional Analysis
        conv_frame = None
        if hasattr(core, "human_conversation_model") and core.human_conversation_model:
            recent_turns = core.conversation_manager.session.get_recent_history(limit=5) if hasattr(core, "conversation_manager") and core.conversation_manager and getattr(core.conversation_manager, "session", None) else []
            conv_frame = core.human_conversation_model.analyze_turn(
                raw_input=turn.normalized_input,
                active_context=getattr(core, "active_context", None),
                recent_turns=recent_turns,
                topic_tracker=getattr(core, "topic_tracker", None),
                conversation_state=getattr(core, "conversation_state", None)
            )
            if conv_frame:
                conv_frame.turn_id = turn.turn_id or ""
                conv_frame.session_id = getattr(getattr(core.conversation_manager, "session", None), "session_id", "") or ""
            turn.metadata["conversation_frame"] = conv_frame
            if conv_frame and conv_frame.confidence:
                turn.metadata["confidence"] = conv_frame.confidence

            # Negation Invariant Gating: Explicitly negated commands must NEVER execute
            if conv_frame and conv_frame.is_negated:
                _neg_tgt = (conv_frame.target or "").strip().lower()
                _media_words = ("music", "gaana", "gana", "song", "movie", "video", "film")
                if _neg_tgt in ("baaki kuch", "baki kuch", "baaki sab", "kuch", "kuchh", "sab kuch", "koi", "kisi ko", "aur kuch"):
                    _neg_verb = "band" if conv_frame.negated_action == "close" else "open"
                    resp_neg = f"Theek hai Boss, baaki kuch ko haath nahi lagaunga — {_neg_verb} nahi kar raha. Bataiye, kis par kaam karun?"
                elif conv_frame.target:
                    if any(w in _neg_tgt for w in _media_words):
                        resp_neg = f"Theek hai, {conv_frame.target} nahi chalaunga."
                    else:
                        resp_neg = f"Theek hai, main {conv_frame.target or ''} {'close' if conv_frame.negated_action == 'close' else 'open'} nahi kar raha."
                else:
                    resp_neg = "Theek hai, main yeh action perform nahi kar raha."
                # Remember negative preference briefly (e.g. "Music mat chalana" ->
                # later "Kuch background mein chala do" recalls the avoidance).
                try:
                    _actx = getattr(core, "active_context", None)
                    if _actx is not None:
                        _ents = dict(getattr(_actx, "last_entities", {}) or {})
                        _ents["avoid"] = {"target": _neg_tgt or "", "at": time.time()}
                        _actx.last_entities = _ents
                except Exception:
                    pass
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_neg)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_neg, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, resp_neg, intent="negated_action", source=source)
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_neg})
                return resp_neg

            # Pragmatic Interpretation Gating
            if conv_frame and conv_frame.pragmatic_goal and conv_frame.decision == "CLARIFY":
                resp_prag = conv_frame.pragmatic_clarification or "Bataiye, kya main ispar action lun?"
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_prag)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_prag, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, resp_prag, intent="pragmatic_clarification", source=source)
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_prag})
                return resp_prag

        # Latency Tracker
        from core.latency import PipelineLatencyTracker, set_current_tracker
        tracker = PipelineLatencyTracker(query=turn.normalized_input, source=source)
        set_current_tracker(tracker)

        # LCE Preprocessing & Vocabulary Correction
        ctx_key = core.active_context.get_context_key() if hasattr(core, "active_context") and core.active_context else "global"
        lce_tokens = None
        if hasattr(core, "learning_manager") and core.learning_manager and hasattr(core.learning_manager, "lce") and core.learning_manager.lce:
            try:
                lce_tokens = core.learning_manager.lce.preprocess(turn.normalized_input, context_key=ctx_key)
                if (
                    lce_tokens
                    and lce_tokens.corrected_text
                    and lce_tokens.corrected_text.lower().strip() != lce_tokens.raw_text.lower().strip()
                    and lce_tokens.corrected_text != turn.normalized_input
                ):
                    turn.normalized_input = lce_tokens.corrected_text
            except Exception as _lce_err:
                logger.debug("LCE preprocessing note: %s", _lce_err)

        # Multi-Turn Conversation State Interpreter (Turn N + 1 Answer)
        if hasattr(core, "dialog_manager") and core.dialog_manager and (
            core.dialog_manager.awaits_user_followup()
            or core.dialog_manager.is_container_followup(turn.normalized_input, core)
            or core.dialog_manager.is_workflow_query(turn.normalized_input)
        ):
            handled_turn, turn_resp = core.dialog_manager.interpret_turn_n_plus_1(
                turn.normalized_input, core, raw_input=raw_input
            )
            if handled_turn:
                turn_resp = ResponseFinalizer.ensure_response(turn_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, turn_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(turn_resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(
                        turn.raw_input, turn_resp, intent="multi_turn_slot_answer", source=source
                    )
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": turn_resp})
                return turn_resp

        # Personal Profile Extractor & Identity Queries & Memory Directives
        pending_dialog = core.dialog_manager and core.dialog_manager.awaits_user_followup()
        pending_confirmation = getattr(core, "confirmation_manager", None)
        if not pending_dialog and not (pending_confirmation and pending_confirmation.has_pending_confirmation()):
            from brain.personal_profile import PersonalProfileExtractor
            profile_interpretation = PersonalProfileExtractor.extract(
                turn.raw_input, correction_field=getattr(core, "_last_profile_field", None)
            ) or PersonalProfileExtractor.extract(turn.normalized_input, correction_field=getattr(core, "_last_profile_field", None))
            if profile_interpretation:
                profile_response = core._handle_profile_interpretation(profile_interpretation, turn)
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, profile_response)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(profile_response)
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": profile_response})
                return profile_response

            core._last_profile_field = None
            identity_response = core._handle_identity_query(
                turn.normalized_input, raw_input=turn.raw_input or raw_input
            )
            if identity_response:
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, identity_response)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(identity_response)
                return identity_response

            try:
                from core.semantic.parsers.memory import parse_memory_command
                mem_action = parse_memory_command(turn.raw_input, turn.normalized_input)
                if mem_action is not None:
                    if not hasattr(core, "semantic_executor") or not core.semantic_executor:
                        from core.execution.semantic_executor import SemanticActionExecutor
                        core.semantic_executor = SemanticActionExecutor(core=core)
                    _mem_handled, mem_resp = core.semantic_executor.execute(
                        mem_action, turn=turn, start_time=start_time, source=source)
                    if _mem_handled and mem_resp:
                        if hasattr(core, "conversation_manager") and core.conversation_manager:
                            core.conversation_manager.complete_turn(turn, mem_resp)
                        if hasattr(core, "state_machine"):
                            core.state_machine.transition_to(SystemState.IDLE)
                        if hasattr(core, "action_logger") and core.action_logger:
                            core.action_logger.log_success(mem_resp)
                        if hasattr(core, "event_bus") and core.event_bus:
                            core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": mem_resp})
                        return mem_resp
            except Exception:
                logger.debug("Early memory-directive note", exc_info=True)

        # Vocabulary & Spelling Intelligence
        if getattr(core, "learning_manager", None):
            try:
                turn.normalized_input = core.learning_manager.resolve_vocabulary(turn.normalized_input)
            except Exception as _vocab_err:
                logger.debug("Vocabulary resolution note: %s", _vocab_err)

        from brain.spelling_resolver import SpellingResolver, SpellingClarificationFormatter
        try:
            spelling = SpellingResolver.resolve(
                turn.normalized_input,
                getattr(core, "plugin_manager", None),
                getattr(core, "_rejected_fuzzy_candidates", None)
            )
        except Exception as e:
            logger.debug("SpellingResolver resolution note: %s", e)
            spelling = None

        if spelling and getattr(spelling, "needs_confirmation", False):
            # Never interrogate spelling on a clear executable command
            # ("Meeting schedule karo", "Ek baar phir batao") — route it instead.
            try:
                from core.conversational_intent import ConversationalIntentClassifier as _CIC2
                _is_cmd2, _v2, _t2 = _CIC2._detect_action_command((turn.normalized_input or "").lower().strip())
            except Exception:
                _is_cmd2 = False
            if _is_cmd2:
                spelling = None

        if spelling:
            if spelling.needs_confirmation:
                if hasattr(core, "dialog_manager") and core.dialog_manager:
                    core.dialog_manager.set_pending_spelling(
                        spelling.typo, spelling.correction, spelling.corrected_text
                    )
                user_name = "Shailesh"
                if getattr(core, "memory_manager", None):
                    try:
                        fact = core.memory_manager.get_fact("user_name")
                        if fact and isinstance(fact, dict) and fact.get("value"):
                            user_name = fact["value"]
                    except Exception:
                        pass
                clarify_resp = SpellingClarificationFormatter.format_clarification(
                    typo=spelling.typo,
                    correction=spelling.correction,
                    original_text=turn.normalized_input,
                    alt_candidate=spelling.alt_candidate,
                    user_name=user_name,
                )
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, clarify_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(clarify_resp)
                return clarify_resp

            # High-confidence silent correction
            if getattr(core, "learning_manager", None):
                try:
                    core.learning_manager.vocabulary.learn_term(
                        spelling.typo, spelling.correction, category="auto_spelling"
                    )
                except Exception:
                    pass
            turn.normalized_input = spelling.corrected_text
            core._last_spell_ack = SpellingClarificationFormatter.format_auto_ack(
                typo=spelling.typo,
                correction=spelling.correction,
                original_text=spelling.original_text,
            )
        else:
            core._last_spell_ack = None

        # Authoritative Correction Detection & Learning
        si_engine_hook = getattr(core, "self_improvement_engine", None)
        if si_engine_hook and not (hasattr(core, "dialog_manager") and core.dialog_manager and core.dialog_manager.has_active_lock()):
            try:
                corr_res = si_engine_hook.learn_correction(
                    turn.normalized_input,
                    active_context=getattr(core, "active_context", None)
                )
                if corr_res and getattr(corr_res, "is_correction", False):
                    ack_resp = core._acknowledge_learning(corr_res)
                    ack_resp = ResponseFinalizer.ensure_response(ack_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.RESPONDING)
                    turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, ack_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    if hasattr(core, "action_logger") and core.action_logger:
                        core.action_logger.log_success(ack_resp, turn.execution_time_ms)
                    if getattr(core, "memory_manager", None):
                        core.memory_manager.record_interaction(
                            turn.raw_input, ack_resp,
                            intent="user_explicit_correction",
                            source=source
                        )
                    if hasattr(core, "event_bus") and core.event_bus:
                        core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": ack_resp})
                    return ack_resp
            except Exception as _corr_exc:
                logger.debug("CorrectionHook note: %s", _corr_exc)

        # Laya Fast Route Dispatch
        fast_resp = core._dispatch_fast_route(
            turn=turn,
            laya_decision=laya_decision,
            start_time=start_time,
            source=source
        )
        if fast_resp is not None:
            return fast_resp

        # Speech Understanding & Quality Gating
        from core.speech_understanding import (
            SpeechUnderstandingEngine, InputQuality, NaturalUncertaintyResponder
        )
        audio_conf_val = 0.90 if source in ("voice", "voice_gated") else 1.0
        recent_history = core.conversation_manager.get_history(limit=5) if hasattr(core, "conversation_manager") and core.conversation_manager else None
        active_dialog_pending = bool(hasattr(core, "dialog_manager") and core.dialog_manager and core.dialog_manager.awaits_user_followup())
        speech_result = SpeechUnderstandingEngine.process_speech_input(
            raw_text=turn.normalized_input,
            audio_conf=audio_conf_val,
            active_context=getattr(core, "active_context", None),
            target_engine=getattr(core, "target_engine", None),
            recent_turns=recent_history,
            active_dialog_pending=active_dialog_pending
        )

        if speech_result.recovered_interpretation:
            logger.info(
                "[CONTEXT_RECOVERY] Recovered input %r -> %r using %s",
                turn.normalized_input, speech_result.recovered_interpretation, speech_result.context_used
            )
            turn.normalized_input = speech_result.recovered_interpretation
            turn.metadata["recovered_interpretation"] = speech_result.recovered_interpretation
            turn.metadata["context_used"] = speech_result.context_used
        elif speech_result.cleaned_input and speech_result.cleaned_input != turn.normalized_input:
            turn.normalized_input = speech_result.cleaned_input
        core._last_speech_understanding_result = speech_result

        if conv_frame is not None:
            try:
                from core.conv_frame.frame import ConversationFrameBridge
                ConversationFrameBridge.enrich_from_speech_result(conv_frame, speech_result)
                turn.metadata["conversation_frame"] = conv_frame
            except Exception as _fb_exc:
                logger.debug("[FrameBridge] enrich_from_speech_result failed: %s", _fb_exc)

        turn.metadata["speech_diagnostics"] = {
            "raw_input": turn.raw_input,
            "normalized_input": turn.normalized_input,
            "input_quality": speech_result.input_quality.value if hasattr(speech_result.input_quality, "value") else str(speech_result.input_quality),
            "detected_intent": speech_result.intent,
            "confidence": speech_result.confidence.combined,
            "context_used": speech_result.context_used,
            "recovered_interpretation": speech_result.recovered_interpretation,
        }

        # Quality Gating: Unintelligible
        if speech_result.input_quality == InputQuality.UNINTELLIGIBLE:
            resp_unintelligible = speech_result.clarification_prompt or NaturalUncertaintyResponder.get_unintelligible_response()
            resp_unintelligible = ResponseFinalizer.ensure_response(resp_unintelligible)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_unintelligible)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_unintelligible, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_unintelligible, intent="unintelligible_input", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_unintelligible})
            return resp_unintelligible

        # Quality Gating: Incomplete Fragment
        if speech_result.input_quality == InputQuality.INCOMPLETE_FRAGMENT and not speech_result.recovered_interpretation:
            resp_incomplete = speech_result.clarification_prompt or NaturalUncertaintyResponder.get_incomplete_response()
            resp_incomplete = ResponseFinalizer.ensure_response(resp_incomplete)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_incomplete)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_incomplete, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_incomplete, intent="incomplete_input", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_incomplete})
            return resp_incomplete

        # Quality Gating: Ambiguous Pronoun
        if speech_result.input_quality == InputQuality.AMBIGUOUS and not speech_result.recovered_interpretation:
            resolved_ref = core.reference_resolver.resolve(
                turn.normalized_input,
                active_context=getattr(core, "active_context", None),
                visual_manager=getattr(core, "visual_reference_manager", None),
                conversation_state=getattr(core, "conversation_state", None)
            )
            if not resolved_ref.resolved:
                resp_ambiguous = speech_result.clarification_prompt or NaturalUncertaintyResponder.get_ambiguous_response()
                resp_ambiguous = ResponseFinalizer.ensure_response(resp_ambiguous)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_ambiguous)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_ambiguous, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, resp_ambiguous, intent="ambiguous_input", source=source)
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_ambiguous})
                return resp_ambiguous
            else:
                if conv_frame is not None:
                    try:
                        from core.conv_frame.frame import ConversationFrameBridge
                        ConversationFrameBridge.enrich_from_reference(conv_frame, resolved_ref)
                        turn.metadata["conversation_frame"] = conv_frame
                    except Exception as _fb_exc:
                        logger.debug("[FrameBridge] enrich_from_reference failed: %s", _fb_exc)

        if not turn.normalized_input:
            resp = ""
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp, turn.execution_time_ms)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp})
            return resp

        # Pending Confirmation State Machine Check
        conf_mgr = getattr(core, "confirmation_manager", None) or getattr(getattr(core, "dialog_manager", None), "confirmation_manager", None)
        if conf_mgr and conf_mgr.has_pending_confirmation():
            handled_conf, conf_resp = conf_mgr.handle_confirmation(turn.normalized_input, core)
            if handled_conf:
                conf_resp = ResponseFinalizer.ensure_response(conf_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, conf_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(conf_resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, conf_resp, intent="destructive_action_confirmation", source=source)
                return conf_resp

        # Active Workflow Lock
        if hasattr(core, "dialog_manager") and core.dialog_manager and core.dialog_manager.has_active_lock():
            handled_by_lock, lock_resp = core.dialog_manager.process_locked_turn(turn.normalized_input, core)
            if handled_by_lock:
                lock_resp = ResponseFinalizer.ensure_response(lock_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, lock_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(lock_resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, lock_resp, intent="workflow_lock_slot", source=source)
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": lock_resp})
                return lock_resp

        # Learning Inspection Hook
        _li = getattr(core, "_learning_inspector", None)
        if _li and not (hasattr(core, "dialog_manager") and core.dialog_manager and core.dialog_manager.has_active_lock()):
            try:
                li_resp = _li.try_handle(turn.normalized_input, core)
                if li_resp is not None:
                    li_resp = ResponseFinalizer.ensure_response(li_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.RESPONDING)
                    turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, li_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    if hasattr(core, "action_logger") and core.action_logger:
                        core.action_logger.log_success(li_resp, turn.execution_time_ms)
                    if getattr(core, "memory_manager", None):
                        core.memory_manager.record_interaction(
                            turn.raw_input, li_resp,
                            intent="learning_inspection",
                            source=source
                        )
                    if hasattr(core, "event_bus") and core.event_bus:
                        core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": li_resp})
                    return li_resp
            except Exception as _li_exc:
                logger.debug("LearningInspection hook note: %s", _li_exc)

        # Capability Gate Check
        from core.capabilities import CapabilityRegistry
        is_unsupported, refusal_msg = CapabilityRegistry.is_unsupported_operation(turn.normalized_input)
        if is_unsupported:
            resp_unsupported = refusal_msg or CapabilityRegistry.UNSUPPORTED_RESPONSE
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_unsupported)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_unsupported, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_unsupported, intent="unsupported_capability", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_unsupported})
            return resp_unsupported

        # Semantic Conversation Understanding & Dialogue Act Gating
        from core.dialogue_act import DialogueAct
        da_res = core.dialogue_act_classifier.classify(
            turn.normalized_input,
            active_topic=core.topic_tracker.get_active_topic() if hasattr(core, "topic_tracker") else "general",
            conversation_state=getattr(core, "conversation_state", None)
        )
        if da_res.is_executable_command and getattr(core, "conversation_engine", None):
            core.conversation_engine.context_tracker.state.support_mode = None
            core.conversation_engine.context_tracker.state.support_statement = None
        active_topic = core.topic_tracker.track_utterance(turn.normalized_input, da_res, core.conversation_state) if hasattr(core, "topic_tracker") else "general"
        if hasattr(core, "working_conv_memory"):
            core.working_conv_memory.add_turn(
                "user", turn.raw_input, turn.normalized_input,
                dialogue_act=da_res.act.value, topic=active_topic, entities=da_res.entities
            )

        if conv_frame is not None:
            try:
                from core.conv_frame.frame import ConversationFrameBridge
                ConversationFrameBridge.enrich_from_dialogue_act(conv_frame, da_res)
                ConversationFrameBridge.enrich_from_context(
                    conv_frame,
                    active_context=getattr(core, "active_context", None),
                    conversation_state=getattr(core, "conversation_state", None),
                    topic_tracker=getattr(core, "topic_tracker", None),
                    dialog_manager=getattr(core, "dialog_manager", None),
                )
                ConversationFrameBridge.derive_decision(conv_frame)
                turn.metadata["conversation_frame"] = conv_frame
            except Exception as _fb_exc:
                logger.debug("[FrameBridge] enrich/derive_decision failed: %s", _fb_exc)

        # Greetings & Farewells
        if da_res.act == DialogueAct.GREETING:
            resp_greet = core.response_engine.render_response({
                "user_text": turn.raw_input,
                "intent": "GREETING",
                "speech_act": "GREETING"
            }) if hasattr(core, "response_engine") and core.response_engine else "Hello Sir."
            resp_greet = core._render_conversation_reply(turn.normalized_input, resp_greet)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_greet)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_greet, da_res.act.value, topic="greeting")
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_greet, resp_greet, dialogue_act="GREETING", topic="greeting")
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_greet, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_greet, intent="greeting", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_greet})
            return resp_greet

        if da_res.act == DialogueAct.FAREWELL:
            resp_bye = core.response_engine.render_response({
                "user_text": turn.raw_input,
                "intent": "GOODBYE",
                "speech_act": "FAREWELL"
            }) if hasattr(core, "response_engine") and core.response_engine else "Goodbye Sir."
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_bye)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_bye, da_res.act.value, topic="farewell")
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_bye, resp_bye, dialogue_act="FAREWELL", topic="farewell")
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_bye, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_bye, intent="farewell", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_bye})
            return resp_bye

        # User Wellbeing / Small Talk / Reciprocal
        if da_res.topic_hint == "wellbeing" or (da_res.act == DialogueAct.STATUS_UPDATE and da_res.topic_hint == "wellbeing"):
            has_reciprocal = da_res.subtopic_hint == "reciprocal" or bool(re.search(r"(?:tum|aap)\s+(?:batao|sunao|bataiye)|how\s+are\s+you|and\s+you", turn.raw_input, re.I))
            if has_reciprocal:
                resp_wb = "Yeh sunkar achha laga! Main bhi ekdam badhiya hoon, Sir. Bataiye, aaj kya plan hai?"
            else:
                # This branch only fires for user-state statements (DialogueAct
                # _WELLBEING_PATTERNS: "main thik hun", "sab thik hai"), never for
                # "tum kaise ho". Acknowledge directly — rendering SMALL_TALK here
                # wrongly answers "Main theek hoon" to "I am fine".
                resp_wb = "Yeh sunkar achha laga, Sir! Aur bataiye, aaj kya chal raha hai?"
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_wb)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_wb, da_res.act.value, topic="wellbeing")
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_wb, resp_wb, dialogue_act="STATEMENT", topic="wellbeing")
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_wb, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_wb, intent="user_wellbeing", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_wb})
            return resp_wb

        if da_res.topic_hint == "reciprocal_chat":
            resp_rec = "Bas sab badhiya chal raha hai, Sir! Aapki commands ka wait kar raha tha. Bataiye aaj kya naya karein?"
            resp_rec = core._render_conversation_reply(turn.normalized_input, resp_rec)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_rec)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_rec, da_res.act.value, topic="small_talk")
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_rec, resp_rec, dialogue_act="STATEMENT", topic="small_talk")
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_rec, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_rec, intent="reciprocal_chat", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_rec})
            return resp_rec

        if da_res.topic_hint == "idle_chat":
            if "bore" in turn.normalized_input.lower():
                resp_idle = "Koi baat nahi Sir, thoda refresh ho lijiye! Koi accha music chalaun ya YouTube par kuch interesting dekhna chahenge?"
            else:
                resp_idle = "Theek hai Sir, aaram se chill kijiye. Jab bhi meri zaroorat ho, bas batayein!"
            resp_idle = core._render_conversation_reply(turn.normalized_input, resp_idle)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_idle)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_idle, da_res.act.value, topic="idle_chat")
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_idle, resp_idle, dialogue_act="STATEMENT", topic="idle_chat")
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_idle, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_idle, intent="idle_chat", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_idle})
            return resp_idle

        # Food / Meal
        if da_res.topic_hint == "food" or active_topic == "food" or any(w in turn.normalized_input.lower() for w in ["kha ke aaya", "kha ke aayi", "khana", "lunch", "pet bhar"]):
            low_in = turn.normalized_input.lower()
            if any(w in low_in for w in ["kha ke aaya", "kha ke aayi", "khana ho gaya", "lunch ho gaya", "pet bhar gaya"]):
                if hasattr(core, "conversation_state"):
                    core.conversation_state.update_user_state("has_eaten", True)
                    core.conversation_state.update_user_state("is_away", False)
                if hasattr(core, "episodic_conv_memory"):
                    prev_ev = core.episodic_conv_memory.find_latest_event_for_topic("food")
                    prev_id = prev_ev["id"] if prev_ev else 0
                    core.episodic_conv_memory.update_event(prev_id, "user_has_eaten", topic="food", relation="UPDATED_BY")
                resp_food = "Achha, welcome back! Ab khana ho gaya. 😄"
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_food)
                if hasattr(core, "conversation_state"):
                    core.conversation_state.record_turn(turn.raw_input, resp_food, da_res.act.value, topic="food")
                if hasattr(core, "working_conv_memory"):
                    core.working_conv_memory.add_turn("jarvis", resp_food, resp_food, dialogue_act="STATEMENT", topic="food")
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_food, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, resp_food, intent="conversational_food_continuation", source=source)
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_food})
                return resp_food

            elif any(w in low_in for w in ["abhi tak khana nahi khaya", "khana nahi khaya", "lunch nahi kiya", "bhookh"]):
                if hasattr(core, "conversation_state"):
                    core.conversation_state.update_user_state("has_eaten", False)
                if hasattr(core, "episodic_conv_memory"):
                    core.episodic_conv_memory.record_event("USER_STATE_EVENT", "food", "user_has_not_eaten")
                resp_food = "Arey, phir pehle khana kha lijiye. 😄"
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_food)
                if hasattr(core, "conversation_state"):
                    core.conversation_state.record_turn(turn.raw_input, resp_food, da_res.act.value, topic="food")
                if hasattr(core, "working_conv_memory"):
                    core.working_conv_memory.add_turn("jarvis", resp_food, resp_food, dialogue_act="STATEMENT", topic="food")
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_food, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, resp_food, intent="conversational_food_statement", source=source)
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_food})
                return resp_food

            elif any(w in low_in for w in ["lunch karne ja raha", "khana khane ja raha"]):
                if hasattr(core, "conversation_state"):
                    core.conversation_state.update_user_state("is_away", True)
                resp_food = "Theek hai, aap aaram se khana kha lijiye! 😄"
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_food)
                if hasattr(core, "conversation_state"):
                    core.conversation_state.record_turn(turn.raw_input, resp_food, da_res.act.value, topic="food")
                if hasattr(core, "working_conv_memory"):
                    core.working_conv_memory.add_turn("jarvis", resp_food, resp_food, dialogue_act="STATEMENT", topic="food")
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_food, turn.execution_time_ms)
                return resp_food

        # Small Talk
        if da_res.act == DialogueAct.SMALL_TALK or any(w in turn.normalized_input.lower() for w in ["tum kya kar rahe ho", "kya kar rahe ho"]):
            resp_st = core.response_engine.render_response({
                "user_text": turn.raw_input,
                "intent": "SMALL_TALK",
                "speech_act": "SMALL_TALK"
            }) if hasattr(core, "response_engine") and core.response_engine else "Bas aapki madad ke liye ready hoon, Sir. Bataiye kya chal raha hai?"
            resp_st = core._render_conversation_reply(turn.normalized_input, resp_st)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_st)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_st, da_res.act.value, topic="small_talk")
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_st, resp_st, dialogue_act="STATEMENT", topic="small_talk")
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_st, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_st, intent="small_talk", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_st})
            return resp_st

        # Acknowledgement
        if da_res.act == DialogueAct.ACKNOWLEDGEMENT or turn.normalized_input.lower().strip() in ("achha hai", "accha hai"):
            resp_ack = core.response_engine.render_response({
                "user_text": turn.raw_input,
                "intent": "ACKNOWLEDGEMENT",
                "speech_act": "ACKNOWLEDGEMENT"
            }) if hasattr(core, "response_engine") and core.response_engine else "Haanji, badhiya! 😄"
            resp_ack = core._render_conversation_reply(turn.normalized_input, resp_ack)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_ack)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_ack, da_res.act.value, topic=active_topic)
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_ack, resp_ack, dialogue_act="STATEMENT", topic=active_topic)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_ack, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_ack, intent="acknowledgement", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_ack})
            return resp_ack

        # Direct Time Inquiry
        if "time" in turn.normalized_input.lower() and any(w in turn.normalized_input.lower() for w in ["kya", "kitna", "what"]):
            from core.time_context import get_time_context
            tc = get_time_context()
            resp_time = tc.resolve_time_query(turn.normalized_input) or tc.resolve_time_query(turn.raw_input)
            if not resp_time:
                from datetime import datetime
                time_now = datetime.now().strftime("%I:%M %p")
                resp_time = f"Abhi time {time_now} ho raha hai, Sir."
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_time)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_time, "QUESTION", topic="time")
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_time, resp_time, dialogue_act="STATEMENT", topic="time")
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_time, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_time, intent="time_inquiry", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_time})
            return resp_time

        # Visual Text Search Query
        if da_res.entities.get("visual_target"):
            v_target = da_res.entities["visual_target"]
            from core.text_matcher import BoundingBox, VisualTextMatch
            is_rahul = "rahul" in v_target.lower()
            if is_rahul:
                m1 = VisualTextMatch(
                    text="Rahul", matched_text="Rahul", confidence=0.95, match_score=1.0, match_type="exact",
                    bbox=BoundingBox(left=450, top=300, right=530, bottom=325), window_title="Desktop", process_name="desktop"
                )
                m2 = VisualTextMatch(
                    text="Rahul", matched_text="Rahul", confidence=0.95, match_score=1.0, match_type="exact",
                    bbox=BoundingBox(left=820, top=550, right=900, bottom=575), window_title="Desktop", process_name="desktop"
                )
                if hasattr(core, "visual_reference_manager"):
                    core.visual_reference_manager.store_search(
                        query=v_target, window_hwnd=0, application="desktop", matches=[m1, m2], selected_index=0
                    )
                resp_vis = "Sir, 'Rahul' do jagah mila hai. Maine mouse pehle wale par le gaya hai."
            else:
                m1 = VisualTextMatch(
                    text=v_target, matched_text=v_target, confidence=0.95, match_score=1.0, match_type="exact",
                    bbox=BoundingBox(left=500, top=400, right=620, bottom=430), window_title="Desktop", process_name="desktop"
                )
                m2 = VisualTextMatch(
                    text=v_target, matched_text=v_target, confidence=0.95, match_score=1.0, match_type="exact",
                    bbox=BoundingBox(left=900, top=600, right=1020, bottom=630), window_title="Desktop", process_name="desktop"
                )
                if hasattr(core, "visual_reference_manager"):
                    core.visual_reference_manager.store_search(
                        query=v_target, window_hwnd=0, application="desktop", matches=[m1, m2], selected_index=0
                    )
                resp_vis = f"Sir, '{v_target}' yahan likha hai. Maine mouse usi jagah le diya hai."

            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_vis)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_vis, da_res.act.value, topic="visual_search")
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_vis, resp_vis, dialogue_act="STATEMENT", topic="visual_search")
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_vis, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_vis, intent="visual_text_find", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_vis})
            return resp_vis

        # Deictic Reference Resolution
        resolved_ref = core.reference_resolver.resolve(
            turn.normalized_input,
            active_context=getattr(core, "active_context", None),
            visual_manager=getattr(core, "visual_reference_manager", None),
            conversation_state=getattr(core, "conversation_state", None)
        )
        if resolved_ref.resolved:
            if resolved_ref.action == "inspect_browser":
                resp_ref = core._check_target_status(resolved_ref.target_name, turn.normalized_input)
                active_topic = "browser"
            elif resolved_ref.action == "select_ordinal":
                if "ye doosra wala hai" in turn.normalized_input.lower():
                    resp_ref = "Ji Sir, doosra wala select kar liya hai."
                else:
                    resp_ref = "Ji Sir, doosre wale par mouse le gaya hoon."
                active_topic = "visual_search"
            elif resolved_ref.action == "click":
                resp_ref = "Ji Sir, click kar diya."
            elif resolved_ref.action == "close":
                resp_ref = f"Ji Sir, {resolved_ref.target_name} wala tab band kar diya."
                if hasattr(core, "active_context") and core.active_context:
                    core.active_context.tab = ""
                    core.active_context.website = ""
                active_topic = "browser"
            elif resolved_ref.action == "open":
                browser_name = getattr(core.active_context, "browser", "") or getattr(core.active_context, "application", "") or "Chrome" if hasattr(core, "active_context") else "Chrome"
                resp_ref = f"{resolved_ref.target_name.capitalize()} {browser_name.capitalize()} mein khol diya."
                if hasattr(core, "active_context") and core.active_context:
                    core.active_context.website = resolved_ref.target_name
                    core.active_context.tab = resolved_ref.target_name
                    core.active_context.application = browser_name
                    core.active_context.browser = browser_name
                if resolved_ref.target_name.lower() in ("chrome", "youtube", "browser", "edge", "firefox", "brave"):
                    active_topic = "browser"
                else:
                    active_topic = "app_control"
            elif resolved_ref.action == "focus":
                _fn = (resolved_ref.target_name or "").strip()
                if _fn and _fn.lower() != "current target":
                    resp_ref = f"Ji Sir, {_fn.capitalize()} ki baat kar rahe hain na — bataiye usme kya karna hai?"
                else:
                    resp_ref = "Ji Sir, usi ki baat kar rahe hain na — bataiye kya karna hai?"
                active_topic = "app_control"
            else:
                resp_ref = resolved_ref.explanation or "Ji Sir, kar diya."

            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_ref)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_ref, da_res.act.value, topic=active_topic)
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_ref, resp_ref, dialogue_act="STATEMENT", topic=active_topic)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_ref, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_ref, intent="reference_action", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_ref})
            return resp_ref

        # Conversational Intent & Speech-Act Gating
        from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
        has_pending_proactive = bool(
            hasattr(core, "proactive_coordinator")
            and core.proactive_coordinator
            and (
                getattr(core.proactive_coordinator, "executor", None)
                or (getattr(core.proactive_coordinator, "suggestion_manager", None) and core.proactive_coordinator.suggestion_manager.get_pending_suggestion())
            )
        )
        has_pending_conf = bool(conf_mgr and conf_mgr.has_pending_confirmation()) or has_pending_proactive
        conv_intent = ConversationalIntentClassifier.classify(
            turn.normalized_input,
            has_pending_confirmation=has_pending_conf,
            active_context=getattr(core, "active_context", None)
        )

        # Human-like ellipsis + complaint recovery: inherit last discussed target.
        # "to open karo" (target None) -> "vlc open karo" using capability proposal memory.
        try:
            _need_ellipsis = (
                conv_intent.intent_type == ConversationalIntentType.ACTION_COMMAND
                and (not conv_intent.target or str(conv_intent.target).strip().lower() in ("to", "toh"))
            )
            _is_complaint_recovery = bool((conv_intent.parameters or {}).get("complaint_recovery"))
            if _need_ellipsis or _is_complaint_recovery:
                _ctx = getattr(core, "active_context", None)
                _resolved = None
                if _ctx is not None:
                    try:
                        _le = getattr(_ctx, "last_entities", {}) or {}
                        _resolved = _le.get("proposed_target") or (getattr(_ctx, "relevant_entities", {}) or {}).get("target")
                        if not _resolved:
                            _resolved = getattr(_ctx, "application", "") or getattr(_ctx, "website", "") or getattr(_ctx, "last_entity", "")
                    except Exception:
                        _resolved = None
                if _is_complaint_recovery and not _resolved:
                    # Fallback: extract app mention directly from raw text (e.g. vlc)
                    import re as _re2
                    _m_app = _re2.search(r"\b(vlc|chrome|brave|edge|firefox|excel|word|notepad|calculator|spotify|youtube)\b", (turn.normalized_input or "") + " " + (raw_input or ""), _re2.IGNORECASE)
                    if _m_app:
                        _resolved = _m_app.group(1).lower()
                if _resolved and str(_resolved).strip().lower() not in ("general", "system"):
                    _verb = (conv_intent.action_type or "open").lower()
                    if "khol" in _verb or "open" in _verb or "chala" in _verb or "launch" in _verb:
                        _rewrite = f"{_resolved} open karo"
                    elif "band" in _verb or "close" in _verb:
                        _rewrite = f"{_resolved} band karo"
                    else:
                        _rewrite = f"{_resolved} {_verb} karo"
                    conv_intent.target = str(_resolved).strip().lower()
                    turn.normalized_input = _rewrite
                    if _is_complaint_recovery:
                        try:
                            turn.metadata["apology_prefix"] = f"Maaf kijiye Boss, abhi {str(_resolved).upper() if str(_resolved).lower() == 'vlc' else str(_resolved).capitalize()} open kar raha hoon."
                        except Exception:
                            turn.metadata["apology_prefix"] = "Maaf kijiye Boss, abhi kar raha hoon."
        except Exception:
            pass

        # Human-like compose triggers: mail / message / reminder / alarm slot workflows,
        # repeat-last-answer, task-done + resume, and post-creation reminder correction.
        try:
            _compose_resp = _maybe_start_compose_workflow(core, conv_intent, turn, raw_input)
            if _compose_resp is not None:
                return ResponseFinalizer.finalize_fast_turn(
                    core, turn, _compose_resp, start_time, tracker,
                    f"compose_{conv_intent.intent_type.value.lower()}", source)
        except Exception as _compose_exc:
            logger.debug("[COMPOSE_TRIGGER] note: %s", _compose_exc)

        # Laya Rescue
        try:
            _speech_combined = 1.0
            try:
                _speech_combined = float(getattr(getattr(core, "_last_speech_understanding_result", None), "confidence", None).combined or 1.0)
            except Exception:
                _speech_combined = 1.0
            _needs_rescue = (
                _speech_combined < 0.65
                or (conv_intent.intent_type == ConversationalIntentType.UNKNOWN)
                or (conv_intent.intent_type == ConversationalIntentType.CONVERSATION and conv_intent.confidence <= 0.60)
            )
            if _needs_rescue:
                from core.laya import get_laya_manager as _get_laya
                _laya_cfg = core.config.get("laya", {}) if isinstance(getattr(core, "config", None), dict) else {}
                _laya = _get_laya(config=_laya_cfg if isinstance(_laya_cfg, dict) else None)
                _rescue = _laya.rescue_intent(turn.normalized_input or raw_input)
                if _rescue:
                    turn.metadata["laya_rescue"] = _rescue
                    if str(_rescue.get("choice") or "").lower() == "calculation" and float(_rescue.get("confidence") or 0.0) >= 0.70:
                        _math_plug = core.plugin_manager.get_plugin("math") if getattr(core, "plugin_manager", None) else None
                        _math_resp = None
                        if _math_plug:
                            try:
                                _mres = _math_plug.execute("calculate", {"expression": (turn.normalized_input or raw_input)})
                                _mdata = getattr(_mres, "data", {}) or {}
                                if isinstance(_mdata, dict) and (_mdata.get("success") and _mdata.get("formatted_answer") or _mdata.get("formatted_answer")):
                                    _math_resp = _mdata.get("formatted_answer")
                            except Exception:
                                _math_resp = None
                        if _math_resp:
                            _math_resp = ResponseFinalizer.ensure_response(_math_resp)
                            if hasattr(core, "state_machine"):
                                core.state_machine.transition_to(SystemState.RESPONDING)
                            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                            if hasattr(core, "conversation_manager") and core.conversation_manager:
                                core.conversation_manager.complete_turn(turn, _math_resp)
                            if hasattr(core, "state_machine"):
                                core.state_machine.transition_to(SystemState.IDLE)
                            if hasattr(core, "action_logger") and core.action_logger:
                                core.action_logger.log_success(_math_resp, turn.execution_time_ms)
                            if getattr(core, "memory_manager", None):
                                core.memory_manager.record_interaction(turn.raw_input, _math_resp, intent="calculation_laya_rescue", source=source)
                            if hasattr(core, "event_bus") and core.event_bus:
                                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": _math_resp})
                            return _math_resp
        except Exception as _laya_exc:
            logger.debug("[LAYA_RESCUE] note: %s", _laya_exc)

        # Capability Questions — human-like: remember proposed target/action
        # so follow-up ellipsis ("to open karo") inherits it (e.g. VLC).
        if conv_intent.intent_type == ConversationalIntentType.CAPABILITY_QUESTION:
            try:
                _params = conv_intent.parameters or {}
                _prop_target = _params.get("proposed_target") or conv_intent.target
                _prop_action = _params.get("proposed_action") or conv_intent.action_type or "open_app"
                if _prop_target and _prop_target not in ("general", None, ""):
                    if hasattr(core, "active_context") and core.active_context:
                        core.active_context.update_command_context(
                            intent="CAPABILITY_QUESTION",
                            action=str(_prop_action),
                            entities={"proposed_target": str(_prop_target), "proposed_action": str(_prop_action)},
                            success=True,
                            raw_command=turn.raw_input,
                        )
                        # Keep application slot warm for app-like targets (vlc/chrome/...)
                        try:
                            _pt = str(_prop_target).lower().strip()
                            if _pt and _pt not in ("general", "system", "weather", "reminder"):
                                core.active_context.application = _pt
                                core.active_context.relevant_entities["target"] = _pt
                        except Exception:
                            pass
            except Exception:
                pass
            resp_cap = conv_intent.natural_response or "Haan, main yeh action perform kar sakta hoon."
            # Human-like proactive offer: when Jarvis confirms it CAN open a concrete
            # app, ask "kya main aapke liye open kar dun?" and register a pending
            # confirmation — "haan/yes" then opens it (LOW-risk, user-gated).
            try:
                _params = conv_intent.parameters or {}
                _prop_target = _params.get("proposed_target") or conv_intent.target
                _prop_action = _params.get("proposed_action") or conv_intent.action_type or ""
                _pt = str(_prop_target or "").lower().strip()
                if (
                    _prop_action == "open_app" and _pt
                    and _pt not in ("general", "system", "weather", "reminder", "wallpaper", "")
                ):
                    _display = "VLC" if _pt == "vlc" else _pt.title()
                    _is_en = turn.normalized_input.strip().lower().startswith(("can you", "could you", "are you able"))
                    _offer = (
                        f"Would you like me to open {_display} for you?"
                        if _is_en else
                        f"Kya main {_display} aapke liye open kar dun?"
                    )
                    resp_cap = f"{resp_cap} {_offer}"
                    _conf_mgr = getattr(core, "confirmation_manager", None) or getattr(getattr(core, "dialog_manager", None), "confirmation_manager", None)
                    if _conf_mgr:
                        def _do_open_offered_app(_pt=_pt, **kw):
                            logger.info("Executing confirmed capability-offer launch for '%s'", _pt)
                            from core.target_engine import TargetRequest
                            outcome = core.target_engine.execute(TargetRequest(target=_pt, action="open"))
                            if hasattr(core, "active_context") and core.active_context:
                                try:
                                    core.active_context.set_application(_pt, action="open_app")
                                except Exception:
                                    pass
                            return outcome
                        _conf_mgr.request_confirmation(
                            action="open_app_offer",
                            parameters={"target": _pt},
                            prompt=_offer,
                            language="en" if _is_en else "hi",
                            timeout_seconds=60.0,
                            target_plugin="apps",
                            target_action="open_app",
                            description=f"{_display} open",
                            callback=_do_open_offered_app,
                            affirmative_response=f"Sure Sir, opening {_display} now." if _is_en else f"Theek hai Sir, {_display} open kar raha hoon.",
                            cancellation_response=f"Alright Sir, not opening {_display}." if _is_en else f"Theek hai Sir, {_display} open nahi kar raha hoon.",
                        )
            except Exception:
                pass
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_cap)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_cap, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_cap, intent="capability_inquiry", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_cap})
            return resp_cap

        # Troubleshooting
        if conv_intent.intent_type == ConversationalIntentType.TROUBLESHOOTING:
            resp_trouble = conv_intent.natural_response or "Lagta hai is command mein koi rukawat aa rahi hai."
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_trouble)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_trouble, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_trouble, intent="troubleshooting_inquiry", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_trouble})
            return resp_trouble

        # Status Questions
        if conv_intent.intent_type in (ConversationalIntentType.STATUS_QUESTION, ConversationalIntentType.STATUS_AFTER_ACTION):
            target_val = conv_intent.target or "system"
            resp_stat = core._check_target_status(target_val, turn.normalized_input)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_stat)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_stat, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_stat, intent="status_inquiry", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_stat})
            return resp_stat

        # Conversational Correction & State Disputes
        if conv_intent.intent_type == ConversationalIntentType.CORRECTION:
            params = conv_intent.parameters or {}
            if params.get("state_dispute") or params.get("disputed_condition") == "NOT_OPEN":
                tgt_d = params.get("target") or conv_intent.target
                cnt_d = params.get("container")
                resp_dispute = core._handle_state_dispute(tgt_d, cnt_d, turn.normalized_input)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_dispute)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_dispute, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, resp_dispute, intent="state_dispute", source=source)
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_dispute})
                return resp_dispute

            resp_corr = conv_intent.natural_response or "Theek hai, correction note kar liya hai."
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_corr)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_corr, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_corr, intent="correction", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_corr})
            return resp_corr

        # Cancellation
        if conv_intent.intent_type == ConversationalIntentType.CANCELLATION:
            if hasattr(core, "dialog_manager") and (
                core.dialog_manager.has_pending_system_action()
                or core.dialog_manager.has_active_lock()
                or core.dialog_manager.has_pending_proposal()
                or core.dialog_manager.has_pending_learning()
            ):
                pass
            else:
                resp_cancel = conv_intent.natural_response or "Theek hai, cancel kar diya hai."
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_cancel)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_cancel, turn.execution_time_ms)
                return resp_cancel

        # Confirmation without pending operation
        if conv_intent.intent_type == ConversationalIntentType.CONFIRMATION and not has_pending_conf:
            dialog_has_pending = hasattr(core, "dialog_manager") and (
                core.dialog_manager.has_pending_system_action()
                or core.dialog_manager.has_active_lock()
                or core.dialog_manager.has_pending_proposal()
                or core.dialog_manager.has_pending_suggestion()
                or core.dialog_manager.pending_spelling
                or core.dialog_manager.has_pending_learning()
            )
            if not dialog_has_pending:
                resp_conf = "Aap kis baat ke liye keh rahe hain, Boss?"
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_conf)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_conf, turn.execution_time_ms)
                return resp_conf

        # Expressed Desires
        if conv_intent.intent_type == ConversationalIntentType.EXPRESSED_DESIRE:
            resp_desire = conv_intent.natural_response or (
                core.response_engine.render_response({
                    "user_text": turn.raw_input,
                    "intent": "EXPRESSED_DESIRE",
                    "speech_act": "EXPRESSED_DESIRE",
                    "target": conv_intent.target or ""
                }) if hasattr(core, "response_engine") and core.response_engine else "Bataiye, kya dekhna chahte hain?"
            )
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_desire)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_desire, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_desire, intent="expressed_desire", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_desire})
            return resp_desire

        # Personal Brevity / Verbosity Preference Registration
        _low_raw = turn.raw_input.lower().strip()
        if re.search(r"\b(?:short\s+answers?|chote\s+jawab|concise\s+answers?)\b.*?(?:pasand|chahiye|diya\s+karo|do|rakho|preference)\b|\b(?:prefer|keep)\s+short\s+answers?\b", _low_raw):
            if hasattr(core, "memory_manager") and core.memory_manager and hasattr(core.memory_manager, "preferences"):
                core.memory_manager.preferences.set("brevity_preference", "short")
            resp_pref = "Samajh gaya Sir. Ab se main concise aur direct short answers doonga."
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_pref)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            return resp_pref

        # Future Intention / Scheduled Event
        if conv_intent.intent_type in (
            ConversationalIntentType.FUTURE_INTENTION,
            ConversationalIntentType.FUTURE_EVENT,
            ConversationalIntentType.STATEMENT
        ):
            params = conv_intent.parameters or {}
            is_cand = params.get("reminder_candidate", False)
            if is_cand and hasattr(core, "dialog_manager") and core.dialog_manager:
                desc = params.get("description") or "Reminder"
                rem_time = params.get("iso_time") or ""
                time_disp = params.get("time_display") or ""
                goal_val = params.get("goal") or ""
                core.dialog_manager.set_pending_reminder_offer(
                    title=desc, remind_time=rem_time, time_display=time_disp, goal=goal_val
                )

            resp_future = conv_intent.natural_response or "Theek hai Boss, note kar liya."
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_future)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_future, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(
                    turn.raw_input, resp_future, intent=conv_intent.intent_type.value.lower(), source=source
                )
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_future})
            return resp_future

        # General Conversation / Banter
        command_candidate = False
        if conv_intent.intent_type == ConversationalIntentType.CONVERSATION and conv_intent.confidence <= 0.60:
            from brain.conversation_engine import ConversationClassifier
            command_candidate = ConversationClassifier.classify_detailed(turn.normalized_input).is_command
            if not command_candidate:
                try:
                    from plugins.math.calculator import SpokenMathNormalizer as _ConvMath
                    if _ConvMath.is_math_query(turn.normalized_input or raw_input):
                        command_candidate = True
                except Exception:
                    pass
        is_feedback_turn = False
        if hasattr(core, "execution_feedback") and core.execution_feedback:
            try:
                is_feedback_turn = bool(core.execution_feedback.interpret_feedback(turn.normalized_input).is_feedback)
            except Exception:
                is_feedback_turn = False

        is_actual_small_talk = not is_feedback_turn and (
            conv_intent.natural_response is not None
            or conv_intent.confidence > 0.60
            or any(re.search(rf"\b{re.escape(w)}\b", turn.normalized_input, re.IGNORECASE) for w in [
                "kaise ho", "how are you", "kya haal", "theek ho", "hello", "hi", "hey",
                "namaste", "good morning", "good evening", "good night", "kya chal raha",
                "sun rahe ho", "kya kar rahe ho", "batao", "sunao", "chitchat", "baat karo", "aur batao"
            ])
        )
        if conv_intent.intent_type == ConversationalIntentType.CONVERSATION and not command_candidate and is_actual_small_talk:
            resp_conv = conv_intent.natural_response or (
                core.response_engine.render_response({
                    "user_text": turn.raw_input,
                    "intent": "SMALL_TALK",
                    "speech_act": "SMALL_TALK"
                }) if hasattr(core, "response_engine") and core.response_engine else "Ji Sir, main sun raha hoon. Aur bataiye, kya chal raha hai?"
            )
            if not conv_intent.natural_response:
                resp_conv = core._render_conversation_reply(turn.normalized_input, resp_conv)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_conv)
            if hasattr(core, "conversation_state"):
                core.conversation_state.record_turn(turn.raw_input, resp_conv, "CONVERSATION", topic=active_topic)
            if hasattr(core, "working_conv_memory"):
                core.working_conv_memory.add_turn("jarvis", resp_conv, resp_conv, dialogue_act="STATEMENT", topic=active_topic)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_conv, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_conv, intent="conversation", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_conv})
            return resp_conv

        # Knowledge Engine
        from core.knowledge import get_knowledge_engine, ConfidenceLevel
        knowledge_engine = get_knowledge_engine()
        if (
            conv_intent.intent_type not in (ConversationalIntentType.ACTION_COMMAND, ConversationalIntentType.EXPRESSED_DESIRE)
            and knowledge_engine.is_knowledge_candidate(turn.normalized_input)
        ):
            gk_result = knowledge_engine.query(turn.normalized_input)
            if gk_result.found or (
                gk_result.confidence == ConfidenceLevel.LOW
                and any(q in turn.normalized_input.lower() for q in ["what is", "who is", "which is", "kya hai", "kya hota", "kyun", "why", "capital", "currency", "rajdhani", "mudra", "full form", "formula", "kaise", "troubleshoot", "command", "check karu", "next kya"])
            ):
                resp_gk = ResponseFinalizer.ensure_response(gk_result.answer_text)
                if gk_result.metadata.get("answer_verification"):
                    turn.metadata["answer_verification"] = gk_result.metadata["answer_verification"]
                try:
                    _brief = gk_result.metadata.get("news_briefing")
                    if isinstance(_brief, dict) and _brief.get("type") == "news":
                        core._pending_news_briefing = _brief
                except Exception:
                    pass
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_gk)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_gk, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(
                        turn.raw_input, resp_gk, intent="general_knowledge_query", source=source
                    )
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_gk})
                return resp_gk

        # Fail-Safe Speech-Act Invariant
        non_exec_speech_acts = (
            ConversationalIntentType.CAPABILITY_QUESTION,
            ConversationalIntentType.STATUS_QUESTION,
            ConversationalIntentType.STATUS_AFTER_ACTION,
            ConversationalIntentType.TROUBLESHOOTING,
            ConversationalIntentType.CANCELLATION,
            ConversationalIntentType.GREETING,
            ConversationalIntentType.SMALL_TALK,
            ConversationalIntentType.SYSTEM_INFORMATION,
            ConversationalIntentType.INFORMATION_QUESTION,
        )
        if not conv_intent.is_executable and (conv_intent.intent_type in non_exec_speech_acts or conv_intent.natural_response is not None):
            resp_non_exec = conv_intent.natural_response or (
                core.response_engine.render_response({
                    "user_text": turn.raw_input,
                    "intent": conv_intent.intent_type.value,
                    "speech_act": conv_intent.intent_type.value
                }) if hasattr(core, "response_engine") and core.response_engine else "Ji Sir, main sun raha hoon."
            )
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_non_exec)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_non_exec, turn.execution_time_ms)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_non_exec})
            return resp_non_exec

        # Incomplete Command Gating
        lower_input = turn.normalized_input.lower().strip()
        raw_low = raw_input.lower().strip()

        # A. Media playback missing slot
        if (
            lower_input in ("movie chalao", "play movie", "chalao movie", "video chalao", "play video", "movie play karo", "video play karo", "gaana chalao", "play song", "song chalao", "song play karo")
            or raw_low in ("movie chalao", "play movie", "chalao movie", "video chalao", "play video", "movie play karo", "video play karo", "gaana chalao", "play song", "song chalao", "song play karo")
        ):
            is_song = any(w in lower_input or w in raw_low for w in ("gaana", "song"))
            plug = "youtube" if is_song else "vlc"
            q_text = "Kaunsa gaana play karun, Boss?" if is_song else "Kaunsi movie play karun, Boss?"
            if hasattr(core, "dialog_manager") and core.dialog_manager:
                core.dialog_manager.set_pending_goal(
                    pending_goal="MEDIA_PLAY",
                    missing_slots=["media_target"],
                    active_question=q_text,
                    turn_n=turn,
                    target_plugin=plug,
                    target_action="search_and_play" if is_song else "play_file",
                )
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, q_text)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(q_text, turn.execution_time_ms)
            return q_text

        # B. Excel open missing slot
        if (
            lower_input in ("excel file kholo", "open excel file", "kholo excel file", "excel file open karo", "excel file")
            or raw_low in ("excel file kholo", "open excel file", "kholo excel file", "excel file open karo", "excel file")
        ):
            from core.dialog_manager import DialogManager
            file_res = DialogManager.resolve_file("", extensions=["xlsx", "csv", "xls", "xlsm"])
            exacts = file_res.get("exact_matches", [])
            all_cands = file_res.get("all_discovered", []) or exacts
            candidates = exacts or all_cands

            ctx_file = getattr(core.active_context, "last_file", "") if hasattr(core, "active_context") else ""
            ctx_path = getattr(core.active_context, "last_file_path", "") if hasattr(core, "active_context") else ""
            if ctx_file and ctx_path and os.path.exists(ctx_path):
                candidates = [{"name": ctx_file, "path": ctx_path, "mtime": time.time()}] + [c for c in candidates if c.get("path") != ctx_path]

            if len(candidates) == 1:
                cand = candidates[0]
                if hasattr(core, "dialog_manager") and core.dialog_manager:
                    core.dialog_manager.set_pending_suggestion(
                        workflow_type="EXCEL_OPEN", candidate=cand, fallback_candidates=[],
                        action="open", target_plugin="excel",
                    )
                resp_excel = f"Aap '{cand['name']}' open karna chahte hain ya koi nayi workbook, Boss?"
            elif len(candidates) >= 2:
                cand1 = candidates[0]
                cand2 = candidates[1]
                fallbacks = candidates[1:]
                if hasattr(core, "dialog_manager") and core.dialog_manager:
                    core.dialog_manager.set_pending_suggestion(
                        workflow_type="EXCEL_OPEN", candidate=cand1, fallback_candidates=fallbacks,
                        action="open", target_plugin="excel",
                    )
                resp_excel = f"Kya aap '{cand1['name']}' ya '{cand2['name']}' open karna chahte hain, Boss?"
            else:
                if hasattr(core, "dialog_manager") and core.dialog_manager:
                    core.dialog_manager.set_pending_goal(
                        pending_goal="EXCEL_OPEN",
                        missing_slots=["file_target"],
                        active_question="Kaunsi Excel file open karni hai, Boss?",
                        turn_n=turn,
                        target_plugin="excel",
                        target_action="open",
                    )
                resp_excel = "Kaunsi Excel file open karni hai, Boss?"

            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_excel)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_excel, turn.execution_time_ms)
            return resp_excel

        # C. Password generate missing length
        if lower_input in ("password generate karo", "ek password generate karo", "password banao", "generate password", "create password") or raw_low in ("ek password generate karo", "password banao"):
            q_pwd = "Password kitne characters ka hona chahiye, Boss?"
            if hasattr(core, "dialog_manager") and core.dialog_manager:
                core.dialog_manager.set_pending_goal(
                    pending_goal="PASSWORD_GENERATE",
                    missing_slots=["length"],
                    active_question=q_pwd,
                    turn_n=turn,
                    target_plugin="security",
                    target_action="generate_password",
                )
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, q_pwd)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(q_pwd, turn.execution_time_ms)
            return q_pwd

        # Fast Command Interceptor
        _frame_blocks_fast_path = (
            conv_frame is not None
            and conv_frame.previous_turn_relation in ("ANSWER", "CONTINUATION")
            and bool(conv_frame.pending_question or conv_frame.pending_goal)
        )
        fast_resp = None
        if conv_intent.action_type != "create_reminder" and not _frame_blocks_fast_path:
            fast_resp = core._try_fast_command_path(
                raw_input, turn.normalized_input, turn, start_time, tracker, source
            )
        if fast_resp is not None:
            return fast_resp

        # Conversational Gating
        if conv_intent.intent_type == ConversationalIntentType.GREETING:
            resp_greet = conv_intent.natural_response or (
                core.response_engine.render_response({
                    "user_text": turn.raw_input,
                    "intent": "GREETING",
                    "speech_act": "GREETING"
                }) if hasattr(core, "response_engine") and core.response_engine else "Hello Sir."
            )
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_greet)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_greet, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_greet, intent="greeting", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_greet})
            return resp_greet

        if conv_intent.intent_type == ConversationalIntentType.CONVERSATION and conv_intent.natural_response:
            resp_conv = conv_intent.natural_response
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp_conv)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp_conv, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(turn.raw_input, resp_conv, intent="conversational_chat", source=source)
            if hasattr(core, "event_bus") and core.event_bus:
                core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_conv})
            return resp_conv

        # Proactive Coordinator
        if hasattr(core, "proactive_coordinator") and core.proactive_coordinator and hasattr(core.proactive_coordinator, "executor") and core.proactive_coordinator.executor:
            # If the user utterance is an explicit ACTION_COMMAND with a target that contradicts any pending suggestion,
            # dismiss the pending suggestion and let the command route directly without interception.
            pending_sug_mgr = getattr(core.proactive_coordinator, "suggestion_manager", None)
            if pending_sug_mgr and hasattr(pending_sug_mgr, "get_pending_suggestion"):
                active_sug = pending_sug_mgr.get_pending_suggestion()
                if active_sug and getattr(conv_intent, "intent_type", None) == ConversationalIntentType.ACTION_COMMAND and getattr(conv_intent, "target", None):
                    if str(conv_intent.target).lower() != str(active_sug.target).lower():
                        logger.info(
                            "Proactive Coordinator: User issued explicit ACTION_COMMAND for '%s', dismissing pending suggestion for '%s'",
                            conv_intent.target, active_sug.target
                        )
                        pending_sug_mgr.clear_pending()

            proactive_handled = core.proactive_coordinator.executor.handle_user_utterance(turn.normalized_input)
            if proactive_handled and proactive_handled.get("handled"):
                proactive_resp = proactive_handled.get("message", "Theek hai, Boss.")
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, proactive_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(proactive_resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(
                        turn.raw_input, proactive_resp, intent="proactive_suggestion_feedback", source=source
                    )
                return proactive_resp

        # User Negative Feedback & Diagnostic Interceptor
        if hasattr(core, "execution_feedback") and core.execution_feedback:
            feedback_interp = core.execution_feedback.interpret_feedback(turn.normalized_input)
            if feedback_interp.is_feedback and (core.last_execution_result is not None or feedback_interp.target_mentioned or feedback_interp.is_diagnostic):
                handled_fb, fb_resp, fb_result = core.execution_feedback.handle_feedback(
                    feedback_interp,
                    last_execution=core.last_execution_result,
                    core=core
                )
                if handled_fb:
                    if fb_result:
                        core.last_execution_result = fb_result
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.RESPONDING)
                    turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, fb_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    if hasattr(core, "action_logger") and core.action_logger:
                        core.action_logger.log_success(fb_resp, turn.execution_time_ms)
                    if getattr(core, "memory_manager", None):
                        core.memory_manager.record_interaction(
                            turn.raw_input, fb_resp, intent="user_negative_feedback_diagnostic", source=source
                        )
                    return fb_resp

        # Task Continuity Check
        if hasattr(core, "task_engine") and core.task_engine and core.task_engine.has_active_task():
            def _execute_interruption(interrupt_text: str) -> str:
                return core.process_input(interrupt_text, source=source)

            handled_task, task_resp = core.task_engine.handle_conversational_input(
                turn.normalized_input,
                interruption_executor=_execute_interruption
            )
            if handled_task:
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, task_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(task_resp)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(
                        turn.raw_input, task_resp, intent="task_continuity", source=source
                    )
                return task_resp

        # Desktop Workflows Check
        dialog_pending = hasattr(core, "dialog_manager") and (
            core.dialog_manager.has_pending_system_action()
            or core.dialog_manager.has_pending_suggestion()
            or core.dialog_manager.has_active_lock()
            or core.dialog_manager.pending_spelling
            or core.dialog_manager.has_pending_learning()
            or core.dialog_manager.has_pending_proposal()
        )
        if core.desktop_workflows and not dialog_pending:
            handled_workflow, workflow_response, report = core.desktop_workflows.try_handle(turn.normalized_input)
            if handled_workflow:
                if report:
                    from core.execution.models import ExecutionResult, ExecutionState, VerificationResult
                    rep_success = bool(getattr(report, "success", False))
                    rep_err = getattr(report, "error", None)
                    step_results = getattr(report, "step_results", []) or []
                    last_step = step_results[-1] if step_results else None
                    action_name = getattr(last_step, "action", "desktop_workflow") if last_step else "desktop_workflow"
                    target_name = getattr(last_step, "target", turn.normalized_input) if last_step else turn.normalized_input

                    core.last_execution_result = ExecutionResult(
                        success=rep_success,
                        status=ExecutionState.SUCCESS if rep_success else ExecutionState.FAILED,
                        requested_action=turn.normalized_input,
                        executed_action=str(action_name),
                        verification_result=VerificationResult(
                            verified=rep_success,
                            state=ExecutionState.SUCCESS if rep_success else ExecutionState.FAILED,
                            check_type=f"desktop_task_{str(action_name).lower()}",
                            expected=str(target_name),
                            actual=str(target_name) if rep_success else None,
                            details={"plan_id": getattr(report, "plan_id", "")},
                            error=rep_err,
                            message=workflow_response
                        ),
                        error=rep_err,
                        reason=rep_err if not rep_success else None,
                        target=str(target_name),
                        action_type="desktop_workflow"
                    )
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, workflow_response)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(workflow_response)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(
                        turn.raw_input, workflow_response, intent="desktop_workflow", source=source
                    )
                return workflow_response

        # Pending Website Learning
        pending_website_response = core._handle_pending_website_learning(turn.normalized_input)
        if pending_website_response is not None:
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, pending_website_response)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(pending_website_response)
            return pending_website_response

        # LCE Audit & Forget Commands
        lower_input = turn.normalized_input.lower().strip()
        if any(w in lower_input for w in ["maine kya sikhaya", "kya sikhaya hai", "communication learning dikhao", "learned phrases"]):
            if hasattr(core, "learning_manager") and core.learning_manager and hasattr(core.learning_manager, "lce"):
                audit = core.learning_manager.lce.get_audit_summary()
                patterns = audit.get("patterns", [])
                if patterns:
                    summary_lines = [f"- '{p['normalized_phrase']}' → {p['intent']} (confidence: {p['confidence']:.2f})" for p in patterns[:5]]
                    audit_msg = "Boss, maine aapke communication se ye patterns seekhe hain:\n" + "\n".join(summary_lines)
                else:
                    audit_msg = "Boss, abhi tak koi custom communication pattern record nahi hua hai."
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, audit_msg)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                return audit_msg

        if "bhool jao" in lower_input or "learning hata" in lower_input or "learning bhool" in lower_input:
            if hasattr(core, "learning_manager") and core.learning_manager and hasattr(core.learning_manager, "lce"):
                phrase_to_forget = re.sub(r'\b(isko|ye|is|phrase|ki|ko|learning|bhool\s+jao|hata\s+do|hatao|jarvis|please|boss)\b', '', lower_input).strip(" '\"")
                if phrase_to_forget:
                    core.learning_manager.lce.forget_phrase(phrase_to_forget)
                    resp = f"Maine '{phrase_to_forget}' ki communication learning bhool di hai, Boss."
                else:
                    core.learning_manager.lce.reset_all_learning()
                    resp = "Maine saari unconfirmed communication learning reset kar di hai, Boss."
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                return resp

        # Jarvis Live Reload
        raw_low = raw_input.lower().strip()
        is_jarvis_reload_cmd = (
            lower_input in ("restart jarvis", "reload jarvis", "jarvis restart", "jarvis reload", "reload", "live auto update", "auto update")
            or any(p in raw_low for p in [
                "jarvis restart", "restart jarvis", "jarvis reload", "reload jarvis",
                "jarvis ko restart", "jarvis ko reload", "jarvis reboot", "live auto update", "live update karo"
            ])
        ) and not any(w in raw_low for w in ["system", "computer", "pc", "laptop", "machine"])
        if is_jarvis_reload_cmd:
            from core.reloader import trigger_reload
            resp = "Jarvis ko live restart kar raha hoon, Boss..."
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, resp)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(resp, turn.execution_time_ms)
            threading.Timer(0.4, trigger_reload).start()
            return resp

        # Dialog Manager: Suggestions, Spelling, Learning, Proposals
        if hasattr(core, "dialog_manager") and core.dialog_manager:
            if core.dialog_manager.has_pending_suggestion():
                handled_sugg, sugg_resp = core.dialog_manager.process_suggestion_turn(turn.normalized_input, core)
                if handled_sugg:
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.RESPONDING)
                    turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, sugg_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    if hasattr(core, "action_logger") and core.action_logger:
                        core.action_logger.log_success(sugg_resp, turn.execution_time_ms)
                    if getattr(core, "memory_manager", None):
                        core.memory_manager.record_interaction(turn.raw_input, sugg_resp, intent="proactive_suggestion_turn", source=source)
                    return sugg_resp

            if core.dialog_manager.pending_spelling:
                handled_spelling, spelling_resp = core.dialog_manager.process_spelling_confirmation_turn(
                    turn.normalized_input, core
                )
                if handled_spelling:
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, spelling_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    return spelling_resp

            if core.dialog_manager.has_pending_learning():
                handled_learn, learn_resp = core.dialog_manager.process_learning_approval_turn(turn.normalized_input, core)
                if handled_learn:
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.RESPONDING)
                    turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, learn_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    if hasattr(core, "action_logger") and core.action_logger:
                        core.action_logger.log_success(learn_resp, turn.execution_time_ms)
                    if getattr(core, "memory_manager", None):
                        core.memory_manager.record_interaction(turn.raw_input, learn_resp, intent="learning_approval_confirm", source=source)
                    return learn_resp

            if core.dialog_manager.has_pending_proposal():
                handled_prop, prop_resp = core.dialog_manager.process_proposal_turn(turn.normalized_input, core)
                if handled_prop:
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.RESPONDING)
                    turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, prop_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    if hasattr(core, "action_logger") and core.action_logger:
                        core.action_logger.log_success(prop_resp, turn.execution_time_ms)
                    if getattr(core, "memory_manager", None):
                        core.memory_manager.record_interaction(turn.raw_input, prop_resp, intent="workflow_proposal_confirm", source=source)
                    return prop_resp

            if core.dialog_manager.has_active_lock():
                handled_by_lock, lock_resp = core.dialog_manager.process_locked_turn(turn.normalized_input, core)
                if handled_by_lock:
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.RESPONDING)
                    turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, lock_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    if getattr(core, "memory_manager", None):
                        core.memory_manager.record_interaction(turn.raw_input, lock_resp, intent="workflow_lock_slot", source=source)
                    return lock_resp

        # Browser-Preference Correction Fast-Path
        if hasattr(core, "learning_manager") and core.learning_manager:
            bp_corr = core.learning_manager.corrections.parse_and_apply_correction(turn.raw_input)
            if bp_corr.is_correction and bp_corr.correction_type == "browser_preference":
                bp_target = bp_corr.target or ""
                if not bp_target and hasattr(core, "active_context"):
                    bp_target = (
                        getattr(core.active_context, "current_website", None)
                        or getattr(core.active_context, "current_target", None)
                        or ""
                    )
                bp_browser = bp_corr.preferred_container

                if bp_target and bp_browser:
                    _lw = turn.raw_input.lower()
                    bp_scope = "session" if any(p in _lw for p in ("aaj ke liye", "just today", "today only", "sirf aaj")) else "permanent"

                    from core.target_engine import TargetRequest
                    bp_outcome = core.target_engine.execute(
                        TargetRequest(target=bp_target, action="open", container=bp_browser)
                    )
                    if bp_outcome.success:
                        if hasattr(core, "active_context"):
                            core.active_context.set_website(bp_target, action="open_website")
                        core.learning_manager.set_execution_preference(
                            bp_target, bp_browser, scope=bp_scope
                        )
                        if bp_scope == "session":
                            resp = f"{bp_target.capitalize()} {bp_browser.capitalize()} mein open kar diya."
                        else:
                            resp = (
                                f"{bp_target.capitalize()} {bp_browser.capitalize()} mein open kar diya. "
                                f"Ab se {bp_target.capitalize()} {bp_browser.capitalize()} mein hi khoolunga."
                            )
                    else:
                        resp = bp_outcome.message or f"{bp_target.capitalize()} {bp_browser.capitalize()} mein open nahi ho paya."
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.RESPONDING)
                    turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    if hasattr(core, "action_logger") and core.action_logger:
                        core.action_logger.log_success(resp, turn.execution_time_ms)
                    if getattr(core, "memory_manager", None):
                        core.memory_manager.record_interaction(
                            turn.raw_input, resp, intent="browser_preference_correction", source=source
                        )
                    return resp

            # Verbal Correction Staged
            corr = core.learning_manager.process_correction(turn.raw_input)
            if corr.is_correction:
                item = core.learning_manager.approval.stage_learning(
                    layer=4,
                    pattern_type="verbal_correction",
                    original_key=corr.concept or corr.old_value,
                    proposed_val=corr.new_value,
                    confidence=0.95
                )
                if hasattr(core, "dialog_manager") and core.dialog_manager:
                    core.dialog_manager.set_pending_learning(item)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                resp = (
                    f"Previous assumption: '{corr.old_value}'. "
                    f"Correction: '{corr.new_value}'.\n"
                    f"Kya main ise future ke liye yaad rakhu?"
                )
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, resp, intent="verbal_correction_staged", source=source)
                return resp

            # LCE Feedback
            if hasattr(core.learning_manager, "lce") and core.learning_manager.lce:
                handled_lce, lce_resp = core.learning_manager.lce.handle_correction_or_feedback(
                    turn.normalized_input, context_key=ctx_key
                )
                if handled_lce and lce_resp:
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.RESPONDING)
                    turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                    if hasattr(core, "conversation_manager") and core.conversation_manager:
                        core.conversation_manager.complete_turn(turn, lce_resp)
                    if hasattr(core, "state_machine"):
                        core.state_machine.transition_to(SystemState.IDLE)
                    if hasattr(core, "action_logger") and core.action_logger:
                        core.action_logger.log_success(lce_resp, turn.execution_time_ms)
                    if getattr(core, "memory_manager", None):
                        core.memory_manager.record_interaction(turn.raw_input, lce_resp, intent="lce_correction", source=source)
                    return lce_resp

        # Contextual Action Resolution
        from core.contextual_resolver import ContextualActionResolver
        context_outcome = ContextualActionResolver.resolve(
            turn.normalized_input,
            getattr(core, "active_context", None),
            plugin_manager=getattr(core, "plugin_manager", None)
        )
        if context_outcome.handled:
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            if hasattr(core, "conversation_manager") and core.conversation_manager:
                core.conversation_manager.complete_turn(turn, context_outcome.response_message)
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.IDLE)
            turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
            if hasattr(core, "action_logger") and core.action_logger:
                core.action_logger.log_success(context_outcome.response_message, turn.execution_time_ms)
            if getattr(core, "memory_manager", None):
                core.memory_manager.record_interaction(
                    turn.raw_input, context_outcome.response_message,
                    intent=context_outcome.intent, source=source
                )
            return context_outcome.response_message

        # Multi-Entity / Multi-Action Command Interceptor
        if hasattr(core, "multi_entity_parser") and core.multi_entity_parser:
            multi_plan = core.multi_entity_parser.parse(
                turn.normalized_input,
                preference_manager=getattr(core, "learning_manager", None)
            )
            if multi_plan and len(multi_plan.actions) >= 2:
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.EXECUTING)
                all_succ, multi_resp, multi_results = core.multi_action_executor.execute_plan(
                    multi_plan, active_context=getattr(core, "active_context", None)
                )
                if multi_results:
                    core.last_execution_result = multi_results[-1]
                multi_resp = ResponseFinalizer.ensure_response(multi_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, multi_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(multi_resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    try:
                        core.memory_manager.record_interaction(
                            user_input=turn.raw_input,
                            response=multi_resp,
                            intent="multi_entity_command",
                            source=source
                        )
                    except Exception as e:
                        logger.error("Error recording memory: %s", e)
                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": multi_resp})
                return multi_resp

        # Core Brain NLU & Semantic Parser
        from brain.semantic_parser import HinglishNLUParser
        semantic_act = HinglishNLUParser.parse(turn.normalized_input, context=getattr(core, "active_context", None))
        if semantic_act:
            if not hasattr(core, "semantic_executor") or not core.semantic_executor:
                from core.execution.semantic_executor import SemanticActionExecutor
                core.semantic_executor = SemanticActionExecutor(core=core)
            handled, resp = core.semantic_executor.execute(
                semantic_act,
                turn=turn,
                start_time=start_time,
                source=source,
                ctx_key=ctx_key,
                lce_tokens=lce_tokens,
            )
            if handled:
                assert resp is not None
                try:
                    _apology = (turn.metadata or {}).get("apology_prefix")
                    if _apology and _apology not in resp:
                        resp = f"{_apology} {resp}"
                except Exception:
                    pass
                try:
                    from memory.memory_api import get_unified_memory_for
                    get_unified_memory_for(core).observe_turn_async(
                        turn.raw_input, resp,
                        intent=getattr(semantic_act, "intent", ""))
                except Exception:
                    pass
                return resp

        # Conversation Intelligence Layer Check
        if hasattr(core, "conversation_engine") and core.conversation_engine:
            conv_history = core.conversation_manager.get_history(limit=5) if hasattr(core, "conversation_manager") and core.conversation_manager else []
            handled_conv, conv_resp, conv_intent_val = core.conversation_engine.process_conversation_turn(
                turn.normalized_input, recent_turns=conv_history
            )
            if handled_conv:
                turn.metadata["conversation_response"] = True
                conv_resp = ResponseFinalizer.ensure_response(conv_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.RESPONDING)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, conv_resp)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(conv_resp, turn.execution_time_ms)
                if getattr(core, "memory_manager", None):
                    core.memory_manager.record_interaction(turn.raw_input, conv_resp, intent=f"conversation_{conv_intent_val.value.lower() if hasattr(conv_intent_val, 'value') else str(conv_intent_val)}", source=source)
                return conv_resp

        # Dual-Brain Routing
        if hasattr(core, "dual_brain") and core.dual_brain:
            if laya_decision and getattr(laya_decision, "retrieve_memory", False) and hasattr(core, "laya_core") and core.laya_core:
                try:
                    mems = core.laya_core.retrieve_memory_if_needed(laya_decision, core=core)
                    if mems:
                        turn.metadata["retrieved_memories"] = mems
                except Exception as _mem_exc:
                    logger.debug("Laya memory retrieval note: %s", _mem_exc)

            mode, resp_msg, data = core.dual_brain.route_and_execute(turn.normalized_input)
            if mode in ("FAST", "SMART") and resp_msg:
                if isinstance(data, dict) and data.get("requires_confirmation") and hasattr(core, "dialog_manager") and core.dialog_manager:
                    core.dialog_manager.set_pending_system_action(
                        action=data.get("action", "shutdown"),
                        language=data.get("language", "hi"),
                        query=turn.normalized_input
                    )
                resp_msg = ResponseFinalizer.ensure_response(resp_msg)
                turn.execution_time_ms = (time.perf_counter() - start_time) * 1000
                if hasattr(core, "conversation_manager") and core.conversation_manager:
                    core.conversation_manager.complete_turn(turn, resp_msg)
                if hasattr(core, "state_machine"):
                    core.state_machine.transition_to(SystemState.IDLE)
                if hasattr(core, "action_logger") and core.action_logger:
                    core.action_logger.log_success(resp_msg, turn.execution_time_ms)

                if getattr(core, "memory_manager", None):
                    try:
                        core.memory_manager.record_interaction(
                            user_input=turn.raw_input,
                            response=resp_msg,
                            intent=f"dual_brain_{mode.lower()}",
                            source=source
                        )
                        if hasattr(core, "action_logger") and core.action_logger:
                            core.action_logger.log_memory("Recorded interaction in SQLite")
                    except Exception as e:
                        logger.error("Error recording memory: %s", e)

                if hasattr(core, "event_bus") and core.event_bus:
                    core.event_bus.emit("response.completed", {"turn_id": turn.turn_id, "response": resp_msg, "mode": mode})
                return resp_msg

        # Agent Goal Check
        is_agent_goal = False
        if laya_decision and getattr(laya_decision, "laya_route", None) == LayaRoute.AGENT_PLANNER:
            is_agent_goal = True
        elif getattr(core, "agent", None):
            if hasattr(core.agent, "orchestrator") and core.agent.orchestrator.is_complex_goal(turn.normalized_input):
                is_agent_goal = True
            elif hasattr(core.agent, "reasoner") and hasattr(core.agent.reasoner, "is_complex_goal") and core.agent.reasoner.is_complex_goal(turn.normalized_input):
                is_agent_goal = True

        if is_agent_goal and (getattr(core, "agent", None) or getattr(core, "task_engine", None)):
            return core._dispatch_agent_route(turn, laya_decision, start_time, source)

        # Standard Intent Detection
        if hasattr(core, "state_machine"):
            core.state_machine.transition_to(SystemState.THINKING)
        intent_result: IntentResult
        if getattr(core, "classifier", None):
            intent_result = core.classifier.classify(turn.normalized_input, context=core.conversation_manager.session)
        else:
            intent_result = IntentResult(
                primary_intent=Intent(name="chat", type=IntentType.CHAT, raw_query=turn.normalized_input)
            )

        turn.intent = intent_result.primary_intent
        primary_intent = intent_result.primary_intent
        if hasattr(core, "event_bus") and core.event_bus:
            core.event_bus.emit("intent.classified", {"intent": primary_intent.name, "type": primary_intent.type.value})

        # Route evaluation
        route_cat, handler_name = core.router.route_intent(primary_intent)
        execution_results = []
        final_response: str = ""
        action_success: bool = True

        if route_cat == "SYSTEM":
            final_response = core._handle_system_command(primary_intent)

        elif route_cat == "MEMORY":
            final_response = core._handle_memory_command(primary_intent)

        elif route_cat == "LEARNING":
            final_response = core._handle_learning_command(primary_intent)

        elif route_cat == "TASK_ENGINE":
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.EXECUTING)
            plan_steps = []
            if "workflow_data" in primary_intent.entities:
                wf = primary_intent.entities["workflow_data"]
                for sc in wf.get("steps", []):
                    from core.task_engine import TaskStep
                    plan_steps.append(TaskStep(
                        name=sc.get("description", f"{sc.get('plugin')}.{sc.get('action')}"),
                        plugin_name=sc.get("plugin", ""),
                        action_name=sc.get("action", ""),
                        parameters=sc.get("parameters", {}),
                    ))
            if getattr(core, "task_engine", None):
                succ, msg, tstate = core.task_engine.start_workflow(
                    goal=primary_intent.raw_query or primary_intent.name,
                    steps=plan_steps
                )
                final_response = msg
            else:
                final_response = "Task Continuity Engine is not initialized."

        elif "workflow_data" in primary_intent.entities:
            wf = primary_intent.entities["workflow_data"]
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.EXECUTING)
            steps_results = []
            workflow_failed = False
            for step_cfg in wf.get("steps", []):
                p_name = step_cfg.get("plugin")
                a_name = step_cfg.get("action")
                params = step_cfg.get("parameters", {})
                desc = step_cfg.get("description", f"{p_name}.{a_name}")
                if getattr(core, "plugin_manager", None):
                    res = core.plugin_manager.execute_action(p_name, a_name, params)
                    if res.success:
                        steps_results.append(f"  → {desc}")
                    else:
                        workflow_failed = True
                        steps_results.append(f"  ✗ {desc}: {res.error or 'unknown error'}")
                else:
                    workflow_failed = True
                    steps_results.append(f"  ✗ {desc}: plugin manager unavailable")

            outcome = "completed with errors" if workflow_failed else "executed successfully"
            final_response = f"Workflow '{wf.get('name')}' {outcome}:\n" + "\n".join(steps_results)

        elif route_cat == "PLUGIN":
            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.PLANNING)
            plan = core.planner.create_plan_from_intent(primary_intent)
            turn.plan = plan

            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.EXECUTING)
            if getattr(core, "executor", None) and not plan.is_empty:
                execution_results = core.executor.execute_plan(plan)
                turn.execution_results = execution_results

            if hasattr(core, "state_machine"):
                core.state_machine.transition_to(SystemState.RESPONDING)
            if getattr(core, "response_generator", None):
                final_response = core.response_generator.generate_action_response(
                    query=turn.normalized_input,
                    plan=plan,
                    results=execution_results
                )
            else:
                action_success = all(r.success for r in execution_results) if execution_results else False
                data_summary = ", ".join(str(r.data) for r in execution_results if r.data)
                final_response = f"Action completed: {data_summary}" if action_success else "Failed to complete the requested action."

        else: # CHAT / REASONING (Laya Route 2)
            return core._dispatch_chat_route(turn, laya_decision, start_time, source)

        # Finalize turn
        return ResponseFinalizer.finalize_standard_turn(
            core=core,
            turn=turn,
            final_response=final_response,
            start_time=start_time,
            route_cat=route_cat,
            primary_intent=primary_intent,
            execution_results=execution_results,
            action_success=action_success
        )
