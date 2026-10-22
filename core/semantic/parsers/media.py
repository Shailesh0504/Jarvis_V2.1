# core/semantic/parsers/media.py
"""Media playback, YouTube session control, media search, and past activity query parser."""

import re
from typing import Optional

from core.semantic.constants import (
    COMPILED_PLAY_VERBS,
    COMPILED_SEARCH_VERBS,
    PLAY_VERBS,
    SEARCH_VERBS,
    SERVICE_PATTERNS
)
from core.semantic.models import SemanticAction
from core.semantic.normalizer import HinglishNormalizer

# --- YouTube Control Precompiled Patterns ---
YT_CURRENT_RE = re.compile(r"\b(?:youtube\s+pe\s+)?(?:kuch\s+nahi\s+chal\s+raha|kya\s+chal\s+raha|current\s+video)\b", re.IGNORECASE)
YT_PAUSE_RE = re.compile(r"\s*(?:youtube\s+)?(?:pause|pause\s+karo|rok\s+do)\s*", re.IGNORECASE)
YT_RESUME_RE = re.compile(r"\s*(?:youtube\s+)?(?:resume|resume\s+karo|phir\s+se\s+chalao|continue\s+karo)\s*", re.IGNORECASE)
YT_STOP_RE = re.compile(r"\s*(?:youtube\s+)?(?:stop|stop\s+karo|band\s+karo)\s*", re.IGNORECASE)
YT_REPLAY_RE = re.compile(r"\b(?:yahi|same|ye)\s+(?:video|gaana|gana)?\s*(?:dobara|phir\s+se)\s+(?:chalao|bajao|play\s+karo)\b", re.IGNORECASE)
YT_NEXT_RE = re.compile(r"\s*(?:youtube\s+)?(?:next|next\s+video|agla\s+video|iska\s+next\s+video\s+chalao)\s*", re.IGNORECASE)
YT_PREV_RE = re.compile(r"\s*(?:youtube\s+)?(?:previous|previous\s+video|pichhla\s+video)\s*", re.IGNORECASE)
YT_SEEK_RE = re.compile(r"\b(\d+)\s*(second|seconds|sec|secs|s|minute|minutes|min)\s*(aage|piche|peeche)\s*(?:karo|kar\s+do)?\b", re.IGNORECASE)
YT_SEEK_RELATIVE_FORWARD_RE = re.compile(
    r"\b(?:thoda\s+)?(?:aage\s+(?:badhao|karo|kar\s+do|le\s+jao)|skip\s+karo|fast\s+forward|skip\s+ahead|seek\s+forward)\b|^(?:aage|forward)$",
    re.IGNORECASE
)
YT_SEEK_RELATIVE_BACKWARD_RE = re.compile(
    r"\b(?:thoda\s+)?(?:piche|peeche)\s+(?:karo|kar\s+do|le\s+jao|badhao)|rewind\s*(?:karo)?|seek\s+backward\b|^(?:peeche|piche|rewind)$",
    re.IGNORECASE
)
YT_MUTE_RE = re.compile(r"\byoutube\s+(?:mute|awaaz\s+band)\s*(?:karo)?\b", re.IGNORECASE)
YT_UNMUTE_RE = re.compile(r"\byoutube\s+(?:unmute|awaaz\s+chalu)\s*(?:karo)?\b", re.IGNORECASE)
YT_VOL_UP_RE = re.compile(r"\byoutube\s+volume\s+(?:badhao|up)\s*(?:karo)?\b", re.IGNORECASE)
YT_VOL_LEVEL_RE = re.compile(r"\byoutube\s+volume\s+(\d{1,3})\s*(?:percent|%)?\s*(?:karo|kar\s+do)?\b", re.IGNORECASE)
YT_QUEUE_RE = re.compile(r"(?:is\s+gaane\s+ke\s+baad|iske\s+baad|queue\s+mein)\s+(.+?)\s+(?:chalao|bajao|add\s+karo)$", re.IGNORECASE)
YT_CHANNEL_RE = re.compile(r"(?:youtube\s+(?:pe|par)\s+)?(.+?)\s+(?:ka\s+)?channel\s+(?:kholo|open\s+karo)$", re.IGNORECASE)
YT_PLAYLIST_RE = re.compile(r"(?:youtube\s+(?:pe|par)\s+)?(.+?)\s+playlist\s+(?:chalao|play\s+karo|kholo)$", re.IGNORECASE)

# --- Activity / History Precompiled Patterns ---
OFFSET_MIN_RE = re.compile(r"\b(\d+)\s*(?:minute|min|m)\s*(?:pehle|ago)\b", re.IGNORECASE)
WHILE_AGO_RE = re.compile(r"\b(?:thodi|kuch)\s+der\s+pehle\b|\ba\s+while\s+ago\b|\bearlier\b", re.IGNORECASE)
LAST_TIME_RE = re.compile(r"\b(?:last|pichla|pichli|pichle|previous)\b", re.IGNORECASE)
JUST_NOW_RE = re.compile(r"\b(?:abhi|just\s+now|haali\s+mein)\b", re.IGNORECASE)

MEDIA_QUERY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"(?:konsi|kaunsi|kaun\s*si|konsa|kaunsa|kaun\s*sa|which)\s+(?:video|gaana|gana|song|movie|track|clip)s?\s+(?:dekh|sun|play\s+kar|chal|dekha|suna|dekhi|suni)",
        r"(?:konsi|kaunsi|kaun\s*si|konsa|kaunsa|kaun\s*sa|which)\s+(?:video|gaana|gana|song|movie|track|clip)s?\s+(?:chal|play\s+ho|baj|dekh)\s+(?:rahi\s+thi|raha\s+tha|rahe\s+the|rahi\s+hai|raha\s+hai)",
        r"(?:main(?:\s*ne)?|maine|humne|i)?\s*(?:abhi|just\s+now)?\s*(?:konsi|kaunsi|kaun\s*si|konsa|kaunsa|kaun\s*sa|which)\s+(?:video|gaana|gana|song|movie|track|clip)s?\s+(?:dekh[aie]?|sun[aie]?|dekhi|dekha|suna|suni|play\s+ki)",
        r"(?:pichli|pichhla|pichle|pichla|last|previous)\s+(?:video|gaana|gana|song|movie|track|clip|media)s?\s+(?:konsi|kaunsi|kaun\s*si|konsa|kaunsa|kaun\s*sa|kya|which|thi|tha)",
        r"(?:last|pichla|pichli|previous)\s+(?:video|gaana|gana|song|media)s?\s+(?:kya\s+(?:tha|thi)|batao|dikhao|thi|tha)",
        r"(?:what\s+was\s+i\s+(?:watching|listening\s+to|playing)|what\s+video\s+was\s+playing|which\s+video\s+was\s+playing|what\s+song\s+was\s+playing)",
        r"(?:what\s+(?:video|song|movie|media)s?\s+(?:was\s+(?:i\s+)?(?:watching|playing)|did\s+i\s+(?:watch|see|listen)))",
        r"(?:what\s+(?:video\s+)?did\s+i\s+(?:watch|see|listen\s+to)|which\s+video\s+did\s+i\s+(?:watch|see)|what\s+did\s+i\s+(?:just\s+)?(?:watch|see))",
        r"(?:youtube\s+(?:pe|par|me|mein)\s+)?kya\s+(?:video\s+)?(?:chal|play\s+ho)\s+rah[aie]\s+th[aie]",
        r"(?:youtube\s+(?:pe|par|me|mein)\s+)?kya\s+chal\s+rah[aie]\s+th[aie]",
        r"(?:main(?:\s*ne)?|maine)?\s*(?:abhi\s+)?kya\s+(?:dekh\s+rah[aie]\s+th[aie]|sun\s+rah[aie]\s+th[aie]|dekha|suna|dekhi|suni)"
    ]
]

ACTIVITY_QUERY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"\b(?:main(?:\s*ne)?|maine\s+)?(?:abhi\s+)?(?:kya\s+kar\s+rah[aie]\s+th[aie]|what\s+was\s+i\s+doing)\b",
        r"\b(?:pichle|last)\s+(?:session|action|kaam|task)\s+mein\s+kya\s+(?:hua\s+tha|kiya\s+tha)\b",
        r"\blast\s+kya\s+kiya\s+tha\b",
        r"\b(?:konsi|kaunsi|which)\s+(?:app|application|file|window)\s+(?:open|kholi)\s+thi\b"
    ]
]

SEARCH_PLAY_MARKER_RE = re.compile(r'\b(search\s+karke|search\s+and|dhoondh\s+ke|search)\b', re.IGNORECASE)
SURROOR_PHONETIC_RE = re.compile(r'(?i)\bsur[u|o]+r\b')


def parse_youtube_control(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Maps contextual media follow-ups to structured YouTube session actions."""
    if YT_CURRENT_RE.search(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "get_current_video")
    if YT_PAUSE_RE.fullmatch(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "pause")
    if YT_RESUME_RE.fullmatch(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "resume")
    if YT_STOP_RE.fullmatch(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "stop")
    if YT_REPLAY_RE.search(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "replay")
    if YT_NEXT_RE.fullmatch(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "next")
    if YT_PREV_RE.fullmatch(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "previous")

    seek = YT_SEEK_RE.search(lowered)
    if seek:
        unit = seek.group(2).lower()
        multiplier = 60 if unit.startswith("min") else 1
        amount = int(seek.group(1)) * multiplier
        if seek.group(3).lower() in ("piche", "peeche"):
            amount *= -1
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "seek", parameters={"seconds": amount})

    if YT_SEEK_RELATIVE_FORWARD_RE.search(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "seek", parameters={"seconds": 10, "relative": True})

    if YT_SEEK_RELATIVE_BACKWARD_RE.search(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "seek", parameters={"seconds": -10, "relative": True})

    if YT_MUTE_RE.search(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "mute")
    if YT_UNMUTE_RE.search(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "unmute")
    if YT_VOL_UP_RE.search(lowered):
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "set_volume", parameters={"level": 70})

    volume = YT_VOL_LEVEL_RE.search(lowered)
    if volume:
        return SemanticAction("YOUTUBE_CONTROL", "youtube", "set_volume", parameters={"level": int(volume.group(1))})

    queue = YT_QUEUE_RE.search(lowered)
    if queue:
        query = HinglishNormalizer.clean_query(queue.group(1))
        return SemanticAction("YOUTUBE_QUEUE", "youtube", "add_to_queue", query=query, parameters={"query": query})

    channel = YT_CHANNEL_RE.search(lowered)
    if channel:
        query = HinglishNormalizer.clean_query(channel.group(1))
        return SemanticAction("YOUTUBE_CHANNEL", "youtube", "open_channel", query=query, parameters={"query": query})

    playlist = YT_PLAYLIST_RE.search(lowered)
    if playlist:
        query = HinglishNormalizer.clean_query(playlist.group(1))
        return SemanticAction("YOUTUBE_PLAYLIST", "youtube", "play_playlist", query=query, parameters={"query": query})

    return None


def parse_activity_and_media_query(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Handles questions about recent media playback, YouTube video history, and past user activity."""
    offset_minutes = 0
    temporal = "current"
    min_match = OFFSET_MIN_RE.search(lowered)
    if min_match:
        offset_minutes = int(min_match.group(1))
        temporal = "offset"
    elif WHILE_AGO_RE.search(lowered):
        temporal = "thodi_der_pehle"
    elif LAST_TIME_RE.search(lowered):
        temporal = "last"
    elif JUST_NOW_RE.search(lowered):
        temporal = "abhi"

    website = "youtube" if "youtube" in lowered else ""

    # 1. Past Media / Video queries
    if any(pat.search(lowered) for pat in MEDIA_QUERY_PATTERNS):
        return SemanticAction(
            intent="QUERY_PAST_MEDIA",
            service="activity",
            action="get_last_media",
            parameters={
                "query_type": "media",
                "website": website,
                "temporal": temporal,
                "offset_minutes": offset_minutes
            },
            confidence=1.0
        )

    # 2. General Past Activity queries
    if any(pat.search(lowered) for pat in ACTIVITY_QUERY_PATTERNS):
        return SemanticAction(
            intent="QUERY_PAST_ACTIVITY",
            service="activity",
            action="get_last_activity",
            parameters={
                "query_type": "general",
                "website": website,
                "temporal": temporal,
                "offset_minutes": offset_minutes
            },
            confidence=1.0
        )

    return None


def parse_media_playback(raw_text: str, lowered: str, context: Optional[object] = None) -> Optional[SemanticAction]:
    """Extracts play intent, service, and query from flexible Hinglish sentences."""
    if any(w in lowered for w in ["reminder", "yaad dilana", "yaad dila do", "yaad dilao", "yaad rakhna", "alarm", "chess"]):
        return None

    has_play_verb = any(pat.search(lowered) for pat in COMPILED_PLAY_VERBS)
    has_search_play = "search karke play" in lowered or "dhoondh ke play" in lowered or "search and play" in lowered

    if not has_play_verb and not has_search_play:
        return None

    # Guard: If user explicitly mentions application or targets an installed/registered app without media indicators
    has_explicit_media = any(w in lowered for w in [
        "gaana", "gana", "song", "songs", "video", "videos", "music", "track", "trailer",
        "movie", "clip", "playlist", "channel", "surroor", "surur", "suroor",
        "youtube pe", "youtube par", "youtube me", "youtube mein", "on youtube", "in youtube",
        "vlc pe", "vlc par", "vlc me", "vlc mein", "in vlc", "on vlc",
    ])
    from core.apps import get_application_registry, get_app_resolver
    app_reg = get_application_registry()
    matched_app, meta = app_reg.parse_query(lowered)
    if not matched_app and not has_explicit_media:
        resolver = get_app_resolver()
        resolved, _ = resolver.resolve_from_query(lowered)
        if resolved:
            return None
    if meta.get("is_application") or (matched_app and not has_explicit_media):
        return None

    # Determine target service (defaults to YouTube for songs/videos if unspecified)
    service = "youtube"
    service_matched_pattern = None

    if any(re.search(pat, lowered) for pat in SERVICE_PATTERNS["vlc"]):
        service = "vlc"
        for pat in SERVICE_PATTERNS["vlc"]:
            m = re.search(pat, lowered)
            if m:
                service_matched_pattern = m.group(0)
                break
    else:
        for pat in SERVICE_PATTERNS["youtube"]:
            m = re.search(pat, lowered)
            if m:
                service_matched_pattern = m.group(0)
                break

    isolated = lowered
    if service_matched_pattern:
        isolated = re.sub(re.escape(service_matched_pattern), ' ', isolated)

    for pat in PLAY_VERBS:
        isolated = re.sub(pat, ' ', isolated)

    isolated = SEARCH_PLAY_MARKER_RE.sub(' ', isolated)
    for filler in HinglishNormalizer.FILLERS:
        isolated = re.sub(filler, ' ', isolated)

    stripped_terms = isolated.split()
    non_generic_terms = [
        t for t in stripped_terms
        if t not in HinglishNormalizer.GENERIC_MEDIA_TERMS
        and t not in ["wala", "wali", "wale", "ka", "ki", "ke"]
    ]

    if not non_generic_terms:
        # Bare ambiguous action verbs ("start", "chalao") without any media keywords are open/action verbs, not media playback
        if not has_explicit_media and lowered.strip() in ("start", "chalao", "chala do", "chala de", "open", "launch", "kholo", "khol do"):
            return None

        if service == "vlc":
            return SemanticAction(
                intent="PLAY_MEDIA",
                service="vlc",
                action="play_file",
                query="",
                parameters={"path": ""},
                needs_clarification=False
            )

        # Context-aware check: if media is already active or was paused, resume it
        if context:
            has_active_media = (
                getattr(context, "website", "") == "youtube"
                or getattr(context, "application", "") in ("spotify", "vlc", "media_player")
                or getattr(context, "last_action", "") in ("pause", "pause_media", "stop_media", "stop")
            )
            if has_active_media:
                target_svc = "youtube" if getattr(context, "website", "") == "youtube" else "media"
                return SemanticAction(
                    intent="RESUME_MEDIA",
                    service=target_svc,
                    action="resume",
                    query=None,
                    parameters={"contextual_resume": True}
                )

        return SemanticAction(
            intent="PLAY_MEDIA",
            service=service,
            action="search_and_play",
            query=None,
            needs_clarification=True,
            clarification_prompt="Kaunsa gaana play karun, Boss?",
            missing_slot="media_target"
        )

    clean_q = HinglishNormalizer.clean_query(isolated)
    if "surur" in clean_q.lower() or "suroor" in clean_q.lower():
        clean_q = SURROOR_PHONETIC_RE.sub('Surroor', clean_q)

    return SemanticAction(
        intent="PLAY_MEDIA",
        service=service,
        action="search_and_play" if service == "youtube" else "play_file",
        query=clean_q,
        parameters={"query": clean_q} if service == "youtube" else {"path": clean_q}
    )


def parse_media_search(raw_text: str, lowered: str) -> Optional[SemanticAction]:
    """Extracts search intent for YouTube (without playing directly)."""
    has_search_verb = any(pat.search(lowered) for pat in COMPILED_SEARCH_VERBS)
    if not has_search_verb:
        return None

    is_yt = any(re.search(pat, lowered) for pat in SERVICE_PATTERNS["youtube"])
    if not is_yt:
        return None

    isolated = lowered
    for pat in SERVICE_PATTERNS["youtube"]:
        m = re.search(pat, isolated)
        if m:
            isolated = re.sub(re.escape(m.group(0)), ' ', isolated)
            break

    for pat in SEARCH_VERBS:
        isolated = re.sub(pat, ' ', isolated)

    for filler in HinglishNormalizer.FILLERS:
        isolated = re.sub(filler, ' ', isolated)

    stripped_terms = isolated.split()
    non_generic_terms = [
        t for t in stripped_terms
        if t not in ["wala", "wali", "wale", "ka", "ki", "ke", "pe", "par", "me", "mein"]
    ]

    if not non_generic_terms:
        return SemanticAction(
            intent="SEARCH_MEDIA",
            service="youtube",
            action="search",
            query=None,
            needs_clarification=True,
            clarification_prompt="YouTube par kya search karun, Boss?",
            missing_slot="media_target"
        )

    clean_q = HinglishNormalizer.clean_query(isolated)
    if "surur" in clean_q.lower() or "suroor" in clean_q.lower():
        clean_q = SURROOR_PHONETIC_RE.sub('Surroor', clean_q)

    return SemanticAction(
        intent="SEARCH_MEDIA",
        service="youtube",
        action="search",
        query=clean_q,
        parameters={"query": clean_q}
    )
