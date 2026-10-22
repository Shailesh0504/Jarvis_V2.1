# core/semantic/parsers/productivity.py
"""Productivity parser for reminders, WhatsApp messages/calls, location/geography, and time/date."""

import datetime
import re
from typing import Optional

from core.semantic.models import SemanticAction

# --- Reminder Precompiled Patterns ---
REMINDER_KW_PATS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\byaad\s+dilana\b', r'\byaad\s+dila\s+do\b', r'\byaad\s+dilao\b',
        r'\byaad\s+rakhna\b', r'\bremind\s+me\b', r'\breminder\b', r'\breminders\b',
        r'\bsnooze\b'
    ]
]
RID_RE = re.compile(r'\b(?:reminder\s*#?|#)(\d+)\b', re.IGNORECASE)
CANCEL_KW_RE = re.compile(r'\b(reminder|reminders|cancel|delete|hatao|hata\s+do|rok\s+do|karo|kar\s+do|ko|ka|ki|ke|please)\b', re.IGNORECASE)
RID_STRIP_RE = re.compile(r'#?\d+')
SNOOZE_MINS_RE = re.compile(r'(\d+)\s*(?:minute|min|minutes|m)', re.IGNORECASE)
TIME_DIGITS_RE = re.compile(r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm|baje|minute|min|hour|ghante)?\b', re.IGNORECASE)
SHAAM_RE = re.compile(r'\b(?:shaam\s+ko|in\s+the\s+evening|shaam\s+mein)\b', re.IGNORECASE)
SUBAH_RE = re.compile(r'\b(?:subah\s+ko|in\s+the\s+morning|subah\s+mein|subah)\b', re.IGNORECASE)
RAAT_RE = re.compile(r'\b(?:raat\s+ko|at\s+night|raat\s+mein)\b', re.IGNORECASE)
DOPAHAR_RE = re.compile(r'\b(?:dopahar\s+ko|in\s+the\s+afternoon|dopahar\s+mein)\b', re.IGNORECASE)
REL_MINS_RE = re.compile(r'(\d+)\s*(?:minute|minutes|minut|minuts|mint|mints|min|mins|m)\s*(?:baad|ke\s+baad|later|me|mein)?', re.IGNORECASE)
REL_HRS_RE = re.compile(r'(\d+)\s*(?:ghante|ghanta|ghanto|hour|hours|hr|hrs)\s*(?:baad|ke\s+baad|later|me|mein)?', re.IGNORECASE)
AMPM_RE = re.compile(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)', re.IGNORECASE)
PERIOD_TIME_RE = re.compile(r'(subah|dopahar|shaam|raat)\s*(\d{1,2})(?::(\d{2}))?\s*(?:baje)?', re.IGNORECASE)
BAJE_RE = re.compile(r'(\d{1,2})(?::(\d{2}))?\s*baje', re.IGNORECASE)
AT_RE = re.compile(r'at\s*(\d{1,2})(?::(\d{2}))?', re.IGNORECASE)

TEMPORAL_STRIPPERS = [
    re.compile(p, re.IGNORECASE) for p in [
        r'\b(?:mujhe|mera|mere|ko|ka|ki|ke|liye|mein|me|par|pe|se)\b',
        r'\b\d+\s*(?:minute|minutes|minut|minuts|mint|mints|min|mins|m|ghante|ghanta|ghanto|hour|hours|hr|hrs)\s*(?:baad|ke\s+baad|later|me|mein)?\b',
        r'\b(?:kal|aaj|parso|today|tomorrow|yesterday)\b',
        r'\b(?:subah|dopahar|shaam|raat|morning|evening|night|afternoon)\b',
        r'\b(?:har\s+din|every\s+day|daily|har\s+monday|every\s+monday|har\s+hafte|weekly)\b',
        r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm|baje)\b',
        r'\b(?:yaad\s+dilana|yaad\s+dila\s+do|yaad\s+dilao|yaad\s+rakhna|reminder\s+laga\s+do|reminder\s+set\s+karo|reminder\s+lagao|remind\s+me|reminder)\b',
        r'\b(?:karo|kar\s+do|kar|do|kijiye|bana\s+do|banao|set\s+karo|lagana|laga)\b',
        r'\b(?:bhai|yaar|dost|please|zara)\b'
    ]
]

# --- WhatsApp Precompiled Patterns ---
WA_OPEN_RE1 = re.compile(r'\b(?:open|kholo|launch|start)\s+whats?app\b', re.IGNORECASE)
WA_OPEN_RE2 = re.compile(r'\bwhats?app\s+(?:kholo|open|launch)\b', re.IGNORECASE)
WA_DRAFT_RE = re.compile(r'draft\s+(?:message|karo)?\s*(?:for|to|ke\s+liye)?\s*([a-zA-Z\s]+?)\s+(?:ki|that|ke\s+liye|text)\s+(.+)', re.IGNORECASE)
WA_CALL_RE1 = re.compile(r'([a-zA-Z\s]+?)\s+ko\s+(?:whats?app\s+)?(?:video\s+)?call\s*(?:karo|laga\s+do|lagao|kar)', re.IGNORECASE)
WA_CALL_RE2 = re.compile(r'call\s+([a-zA-Z\s]+?)\s+(?:on\s+whats?app|via\s+whats?app)', re.IGNORECASE)
WA_CHAT_RE1 = re.compile(r'([a-zA-Z\s]+?)\s+(?:ka|ki|ke)?\s*chat\s*(?:kholo|open\s+karo|open|dikhao)', re.IGNORECASE)
WA_CHAT_RE2 = re.compile(r'open\s+chat\s+(?:with\s+)?([a-zA-Z\s]+)', re.IGNORECASE)
WA_SEARCH_RE = re.compile(r'whats?app\s+(?:par|pe|mein|in)?\s*search\s*(?:karo)?\s*(.+)', re.IGNORECASE)
WA_MSG_KI_RE = re.compile(r'([a-zA-Z\s]+?)\s+ko\s+(?:whats?app\s+(?:par|pe)?\s*)?(?:message|msg)?\s*(?:karo|bhejo|kar\s+do|send\s+karo)?\s*(?:ki|that)\s+(.+)', re.IGNORECASE)
WA_MSG_DIRECT_RE = re.compile(r'([a-zA-Z\s]+?)\s+ko\s+whats?app\s+(?:par|pe)?\s*(?:hi|hello|msg|message)?\s*(?:bhejo|bhej\s+do|send\s+karo|karo)\s*(.*)', re.IGNORECASE)
WA_MSG_EN_RE = re.compile(r'(?:send\s+message|send\s+whatsapp|message)\s+(?:to\s+)?([a-zA-Z\s]+?)(?:\:|\s+saying|\s+that|\s+ki)\s+(.+)', re.IGNORECASE)

# --- Location Precompiled Patterns ---
DIST_RE1 = re.compile(r'([a-zA-Z\s]+?)\s+se\s+([a-zA-Z\s]+?)\s+(?:kitna\s+door|kitni\s+doori|ki\s+doori|distance)', re.IGNORECASE)
DIST_RE2 = re.compile(r'distance\s+(?:between|from)\s+([a-zA-Z\s]+?)\s+(?:and|to)\s+([a-zA-Z\s]+)', re.IGNORECASE)
DIR_RE1 = re.compile(r'([a-zA-Z\s]+?)\s+se\s+([a-zA-Z\s]+?)\s+(?:directions|rasta|route)', re.IGNORECASE)
DIR_RE2 = re.compile(r'directions\s+(?:to|for)\s+([a-zA-Z\s]+)', re.IGNORECASE)
MAP_RE1 = re.compile(r'([a-zA-Z\s]+?)\s+(?:ka|ki)?\s*(?:map|naksha)\s*(?:dikhao|kholo|open|show)?', re.IGNORECASE)
MAP_RE2 = re.compile(r'(?:map|naksha)\s+(?:of|show|dikhao)?\s*([a-zA-Z\s]+)', re.IGNORECASE)
NEAR_RE1 = re.compile(r'(?:mere\s+paas|pass\s+mein|paas\s+mein|nearest|near\s+me)\s+([a-zA-Z\s]+)', re.IGNORECASE)
NEAR_RE2 = re.compile(r'([a-zA-Z\s]+)\s+(?:mere\s+paas|pass\s+mein|near\s+me)', re.IGNORECASE)
CAP_RE1 = re.compile(r'([a-zA-Z\s]+?)\s+(?:ki|ka)?\s*(?:capital|rajdhani)', re.IGNORECASE)
CAP_RE2 = re.compile(r'capital\s+of\s+([a-zA-Z\s]+)', re.IGNORECASE)
WHERE_RE1 = re.compile(r'([a-zA-Z\s]+?)\s+(?:kaha\s+hai|kahan\s+hai|kis\s+country\s+mein\s+hai|kis\s+state\s+mein\s+hai|kis\s+desh\s+mein\s+hai|kis\s+rajya\s+mein\s+hai|location\s+batao)', re.IGNORECASE)
WHERE_RE2 = re.compile(r'(?:where\s+is|location\s+of)\s+([a-zA-Z\s]+)', re.IGNORECASE)
TIME_FILE_CLEAN_RE = re.compile(r"\btime\s+files?\s+(?:clean|clear|delete|remove|saaf|click)\b", re.IGNORECASE)


def parse_reminder(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Parses reminder requests in Hindi, Hinglish, and English."""
    has_reminder_kw = any(pat.search(lowered) for pat in REMINDER_KW_PATS)
    if not has_reminder_kw:
        return None

    # 1. Toggle Reminders (On / Off / Disable / Enable)
    if any(w in lowered for w in ["reminders band karo", "reminder off", "reminder band", "disable reminders", "reminders off"]):
        return SemanticAction(
            intent="TOGGLE_REMINDERS",
            service="reminder",
            action="toggle_reminders",
            query="disable",
            parameters={"enabled": False}
        )
    if any(w in lowered for w in ["reminders chalu karo", "reminder on", "enable reminders", "reminders on"]):
        return SemanticAction(
            intent="TOGGLE_REMINDERS",
            service="reminder",
            action="toggle_reminders",
            query="enable",
            parameters={"enabled": True}
        )

    # 2. Cancel / Delete Reminder
    if any(w in lowered for w in ["cancel", "delete", "hatao", "hata do", "rok do"]) and any(w in lowered for w in ["reminder", "reminders"]):
        rid_match = RID_RE.search(lowered)
        rid = int(rid_match.group(1)) if rid_match else 0
        clean_kw = CANCEL_KW_RE.sub(' ', lowered)
        clean_kw = RID_STRIP_RE.sub(' ', clean_kw).strip()
        return SemanticAction(
            intent="CANCEL_REMINDER",
            service="reminder",
            action="cancel_reminder",
            query=str(rid or clean_kw),
            parameters={"reminder_id": rid, "title": clean_kw}
        )

    # 3. Snooze Reminder
    if "snooze" in lowered or "thodi der baad" in lowered:
        mins_m = SNOOZE_MINS_RE.search(lowered)
        snooze_mins = int(mins_m.group(1)) if mins_m else 10
        rid_match = RID_RE.search(lowered)
        rid = int(rid_match.group(1)) if rid_match else 0
        return SemanticAction(
            intent="SNOOZE_REMINDER",
            service="reminder",
            action="snooze_reminder",
            query=str(snooze_mins),
            parameters={"reminder_id": rid, "minutes": snooze_mins}
        )

    # 4. List Reminders
    if any(w in lowered for w in ["dikhao", "batao", "list", "show", "check"]) and any(w in lowered for w in ["reminders", "reminder"]):
        filter_type = "pending"
        if any(w in lowered for w in ["aaj", "today"]):
            filter_type = "today"
        elif any(w in lowered for w in ["saare", "all", "sab"]):
            filter_type = "all"
        elif any(w in lowered for w in ["completed", "done", "pure"]):
            filter_type = "completed"
        elif any(w in lowered for w in ["missed", "chhut"]):
            filter_type = "missed"
        elif any(w in lowered for w in ["recurring", "daily", "har din"]):
            filter_type = "recurring"

        return SemanticAction(
            intent="LIST_REMINDERS",
            service="reminder",
            action="list_reminders",
            query=filter_type,
            parameters={"filter": filter_type}
        )

    # 5. Create Reminder
    has_ambiguous_period = False
    ambiguous_period_name = ""
    has_time_digits = bool(TIME_DIGITS_RE.search(lowered))

    if not has_time_digits:
        if SHAAM_RE.search(lowered):
            has_ambiguous_period = True
            ambiguous_period_name = "Shaam"
        elif SUBAH_RE.search(lowered):
            has_ambiguous_period = True
            ambiguous_period_name = "Subah"
        elif RAAT_RE.search(lowered):
            has_ambiguous_period = True
            ambiguous_period_name = "Raat"
        elif DOPAHAR_RE.search(lowered):
            has_ambiguous_period = True
            ambiguous_period_name = "Dopahar"

    if has_ambiguous_period:
        prompt = f"{ambiguous_period_name} ko kitne baje ka reminder lagana hai, Boss? E.g., 6 PM ya 7 PM?"
        return SemanticAction(
            intent="CREATE_REMINDER",
            service="reminder",
            action="create_reminder",
            clarification_prompt=prompt,
            query=raw_text,
            parameters={"ambiguous": True}
        )

    # 5b. Parse Temporal Expression & Recurrence
    now_dt = datetime.datetime.now().astimezone()
    target_dt = now_dt
    recurrence = "none"
    recurrence_rule = ""

    if any(w in lowered for w in ["har din", "every day", "daily", "roz"]):
        recurrence = "daily"
    elif any(w in lowered for w in ["har monday", "every monday", "har somwar"]):
        recurrence = "weekly"
        recurrence_rule = "monday"
    elif any(w in lowered for w in ["har tuesday", "every tuesday", "har mangalwar"]):
        recurrence = "weekly"
        recurrence_rule = "tuesday"
    elif any(w in lowered for w in ["har wednesday", "every wednesday", "har budhwar"]):
        recurrence = "weekly"
        recurrence_rule = "wednesday"
    elif any(w in lowered for w in ["har thursday", "every thursday", "har guruwar"]):
        recurrence = "weekly"
        recurrence_rule = "thursday"
    elif any(w in lowered for w in ["har friday", "every friday", "har shukrawar"]):
        recurrence = "weekly"
        recurrence_rule = "friday"
    elif any(w in lowered for w in ["har saturday", "every saturday", "har shaniwar"]):
        recurrence = "weekly"
        recurrence_rule = "saturday"
    elif any(w in lowered for w in ["har sunday", "every sunday", "har raviwar"]):
        recurrence = "weekly"
        recurrence_rule = "sunday"
    elif any(w in lowered for w in ["har hafte", "weekly"]):
        recurrence = "weekly"

    rel_mins = 0
    rel_m = REL_MINS_RE.search(lowered)
    if rel_m:
        rel_mins += int(rel_m.group(1))

    rel_hrs = REL_HRS_RE.search(lowered)
    if rel_hrs:
        rel_mins += int(rel_hrs.group(1)) * 60

    if rel_mins > 0 and recurrence == "none":
        target_dt = now_dt + datetime.timedelta(minutes=rel_mins)
    else:
        date_offset_days = 0
        if "parso" in lowered or "day after tomorrow" in lowered:
            date_offset_days = 2
        elif "kal" in lowered or "tomorrow" in lowered:
            date_offset_days = 1

        hour = 9
        minute = 0
        matched_time = False

        ampm_m = AMPM_RE.search(lowered)
        if ampm_m:
            matched_time = True
            h = int(ampm_m.group(1))
            m = int(ampm_m.group(2)) if ampm_m.group(2) else 0
            is_pm = ampm_m.group(3).lower() == "pm"
            if is_pm and h < 12:
                h += 12
            elif not is_pm and h == 12:
                h = 0
            hour, minute = h, m

        if not matched_time:
            period_m = PERIOD_TIME_RE.search(lowered)
            if period_m:
                matched_time = True
                period = period_m.group(1).lower()
                h = int(period_m.group(2))
                m = int(period_m.group(3)) if period_m.group(3) else 0
                if period in ("dopahar", "shaam", "raat") and h < 12:
                    h += 12
                elif period == "subah" and h == 12:
                    h = 0
                hour, minute = h, m

        if not matched_time:
            baje_m = BAJE_RE.search(lowered) or AT_RE.search(lowered)
            if baje_m:
                matched_time = True
                h = int(baje_m.group(1))
                m = int(baje_m.group(2)) if baje_m.group(2) else 0
                if 1 <= h <= 6:
                    h += 12
                hour, minute = h, m

        target_date = now_dt.date() + datetime.timedelta(days=date_offset_days)
        candidate_dt = now_dt.replace(year=target_date.year, month=target_date.month, day=target_date.day, hour=hour, minute=minute, second=0, microsecond=0)

        if date_offset_days == 0 and candidate_dt <= now_dt and recurrence == "none":
            candidate_dt += datetime.timedelta(days=1)

        target_dt = candidate_dt

    title_raw = lowered
    for pat in TEMPORAL_STRIPPERS:
        title_raw = pat.sub(' ', title_raw)

    clean_title = re.sub(r'\s+', ' ', title_raw).strip()
    if not clean_title:
        clean_title = "Reminder"

    iso_time = target_dt.astimezone().isoformat()

    return SemanticAction(
        intent="CREATE_REMINDER",
        service="reminder",
        action="create_reminder",
        query=clean_title,
        parameters={
            "title": clean_title,
            "remind_time": iso_time,
            "recurrence": recurrence,
            "recurrence_rule": recurrence_rule
        }
    )


def parse_whatsapp(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Detects and parses WhatsApp messaging, drafting, calling, searching, and opening commands."""
    # 1. Open WhatsApp
    if WA_OPEN_RE1.search(lowered) or WA_OPEN_RE2.search(lowered):
        return SemanticAction(
            intent="OPEN_WHATSAPP",
            service="whatsapp",
            action="open_whatsapp",
            query=raw_text,
            parameters={}
        )

    # 2. Cancel Active Draft
    if any(w in lowered for w in ["cancel draft", "cancel message", "mat bhejo", "message mat bhejo", "draft mat bhejo"]):
        return SemanticAction(
            intent="CANCEL_ACTION",
            service="whatsapp",
            action="cancel_action",
            query=raw_text,
            parameters={}
        )

    # 3. Draft Message
    m_draft = WA_DRAFT_RE.search(raw_text)
    if m_draft and ("draft" in lowered):
        rec = m_draft.group(1).strip()
        msg = m_draft.group(2).strip()
        return SemanticAction(
            intent="DRAFT_MESSAGE",
            service="whatsapp",
            action="draft_message",
            query=raw_text,
            parameters={"recipient": rec, "message": msg}
        )

    # 4. WhatsApp Call
    m_call = WA_CALL_RE1.search(lowered)
    m_call2 = WA_CALL_RE2.search(lowered)
    if m_call or m_call2:
        rec = m_call.group(1).strip() if m_call else m_call2.group(1).strip()
        is_video = "video" in lowered
        return SemanticAction(
            intent="CALL_CONTACT",
            service="whatsapp",
            action="call_contact",
            query=raw_text,
            parameters={"recipient": rec, "video": is_video}
        )

    # 5. Open Chat
    m_chat = WA_CHAT_RE1.search(lowered)
    m_chat2 = WA_CHAT_RE2.search(lowered)
    if m_chat or m_chat2:
        rec = m_chat.group(1).strip() if m_chat else m_chat2.group(1).strip()
        return SemanticAction(
            intent="OPEN_CHAT",
            service="whatsapp",
            action="open_chat",
            query=raw_text,
            parameters={"recipient": rec}
        )

    # 6. Search Chat
    m_search = WA_SEARCH_RE.search(raw_text)
    if m_search:
        q = m_search.group(1).strip()
        return SemanticAction(
            intent="SEARCH_CHAT",
            service="whatsapp",
            action="search_chat",
            query=q,
            parameters={"query": q}
        )

    # 7. Natural Hinglish Message Sending
    m_msg_ki = WA_MSG_KI_RE.search(raw_text)
    if m_msg_ki:
        rec = m_msg_ki.group(1).strip()
        msg = m_msg_ki.group(2).strip()
        rec = re.sub(r'^(?:please|jarvis)\s+', '', rec, flags=re.IGNORECASE).strip()
        return SemanticAction(
            intent="SEND_MESSAGE",
            service="whatsapp",
            action="send_message",
            query=raw_text,
            parameters={"recipient": rec, "message": msg}
        )

    m_msg_direct = WA_MSG_DIRECT_RE.search(raw_text)
    if m_msg_direct:
        rec = m_msg_direct.group(1).strip()
        rest = m_msg_direct.group(2).strip()
        msg_text = rest if rest else ("Hi" if "hi" in lowered else "Hello")
        return SemanticAction(
            intent="SEND_MESSAGE",
            service="whatsapp",
            action="send_message",
            query=raw_text,
            parameters={"recipient": rec, "message": msg_text}
        )

    m_msg_en = WA_MSG_EN_RE.search(raw_text)
    if m_msg_en:
        rec = m_msg_en.group(1).strip()
        msg = m_msg_en.group(2).strip()
        return SemanticAction(
            intent="SEND_MESSAGE",
            service="whatsapp",
            action="send_message",
            query=raw_text,
            parameters={"recipient": rec, "message": msg}
        )

    return None


def parse_location(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Detects and parses location, distance, directions, maps, and geography queries."""
    # 1. Distance Queries
    m_dist1 = DIST_RE1.search(lowered)
    m_dist2 = DIST_RE2.search(lowered)
    if m_dist1:
        orig, dest = m_dist1.group(1).strip(), m_dist1.group(2).strip()
        return SemanticAction(
            intent="DISTANCE",
            service="location",
            action="distance",
            query=raw_text,
            parameters={"origin": orig, "destination": dest}
        )
    elif m_dist2:
        orig, dest = m_dist2.group(1).strip(), m_dist2.group(2).strip()
        return SemanticAction(
            intent="DISTANCE",
            service="location",
            action="distance",
            query=raw_text,
            parameters={"origin": orig, "destination": dest}
        )

    # 2. Directions / Route Queries
    m_dir1 = DIR_RE1.search(lowered)
    m_dir2 = DIR_RE2.search(lowered)
    if m_dir1:
        orig, dest = m_dir1.group(1).strip(), m_dir1.group(2).strip()
        return SemanticAction(
            intent="DIRECTIONS",
            service="location",
            action="directions",
            query=raw_text,
            parameters={"origin": orig, "destination": dest}
        )
    elif m_dir2:
        dest = m_dir2.group(1).strip()
        return SemanticAction(
            intent="DIRECTIONS",
            service="location",
            action="directions",
            query=raw_text,
            parameters={"origin": "current location", "destination": dest}
        )

    # 3. Open Map Queries
    if ("map" in lowered or "naksha" in lowered) and not any(w in lowered for w in ["mindmap", "roadmap", "site"]):
        m_map1 = MAP_RE1.search(lowered)
        m_map2 = MAP_RE2.search(lowered)
        place_cand = ""
        if m_map2 and m_map2.group(1).strip() not in ("dikhao", "kholo", "show"):
            place_cand = m_map2.group(1).strip()
        elif m_map1 and m_map1.group(1).strip():
            place_cand = m_map1.group(1).strip()

        if place_cand:
            return SemanticAction(
                intent="OPEN_MAP",
                service="location",
                action="open_map",
                query=raw_text,
                parameters={"place": place_cand}
            )

    # 4. Nearby POI Search
    m_near = NEAR_RE1.search(lowered)
    m_near2 = NEAR_RE2.search(lowered)
    if m_near or m_near2 or any(w in lowered for w in ["nearest", "mere paas", "pass mein"]):
        cat = m_near.group(1).strip() if m_near else (m_near2.group(1).strip() if m_near2 else "place")
        cat = re.sub(r'\s+(?:dhoondo|kaha\s+hai|kahan\s+hai|search\s+karo|batao)$', '', cat).strip()
        return SemanticAction(
            intent="NEARBY_SEARCH",
            service="location",
            action="nearby_search",
            query=raw_text,
            parameters={"category": cat or "place", "location": "current location"}
        )

    # 5. Capital & Country Queries
    m_cap = CAP_RE1.search(lowered)
    m_cap2 = CAP_RE2.search(lowered)
    if m_cap or m_cap2:
        cntry = m_cap.group(1).strip() if m_cap else m_cap2.group(1).strip()
        return SemanticAction(
            intent="COUNTRY_INFO",
            service="location",
            action="country_info",
            query=raw_text,
            parameters={"country": cntry}
        )

    if "kitne states" in lowered or "states count" in lowered:
        cntry = re.sub(r'\s*(?:mein|me)?\s*kitne\s+states.*$', '', lowered).strip()
        if cntry:
            return SemanticAction(
                intent="COUNTRY_INFO",
                service="location",
                action="country_info",
                query=raw_text,
                parameters={"country": cntry}
            )

    # 6. Where is X? / Location Info
    m_where = WHERE_RE1.search(lowered)
    m_where2 = WHERE_RE2.search(lowered)
    if m_where or m_where2:
        place = m_where.group(1).strip() if m_where else m_where2.group(1).strip()
        place = re.sub(r'^(?:is\s+place\s+ki|ye\s+jagah|ye)\s+', '', place).strip()
        if place and not any(w in place for w in ["meeting", "file", "folder", "chabi", "phone", "gadi"]):
            return SemanticAction(
                intent="LOCATION_INFO",
                service="location",
                action="location_info",
                query=raw_text,
                parameters={"place": place}
            )

    return None


def parse_time_date(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Detects time, date, weekday, relative date (tomorrow), day-part, and combined queries."""
    if TIME_FILE_CLEAN_RE.search(lowered):
        return None
    if any(w in lowered for w in ["reminder", "remind", "yaad", "yaad dila", "yaad dilana", "message", "bhejo", "draft", "whatsapp", "call karo", "call karne", "kholo", "open", "play", "shutdown", "restart", "lock"]):
        return None
    try:
        from core.time_context import get_time_context
        tc = get_time_context()
        resolved = tc.resolve_time_query(raw_text)
        if resolved:
            return SemanticAction(
                intent="GET_TIME",
                service="system",
                action="get_time",
                query=raw_text,
                parameters={"query": raw_text}
            )
    except Exception:
        pass
    return None
