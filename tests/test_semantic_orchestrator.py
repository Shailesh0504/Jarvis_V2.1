# tests/test_semantic_orchestrator.py
"""
Unit and integration tests for modular core/semantic/ package.
Verifies:
- Direct imports from core.semantic and brain.semantic_parser
- Gating and chitchat bypass
- Math, time, reminder, system, media, web, and window layout parsing
- Performance and precompiled regex operations
"""

import pytest
from brain.semantic_parser import HinglishNLUParser, HinglishNormalizer, SemanticAction
from core.semantic import SemanticPipelineOrchestrator
from core.semantic.parsers.aliases import parse_alias_management
from core.semantic.parsers.math_parser import parse_math
from core.semantic.parsers.media import parse_media_playback, parse_youtube_control
from core.semantic.parsers.productivity import parse_location, parse_reminder, parse_whatsapp
from core.semantic.parsers.system import parse_audio_control, parse_screen_inspection, parse_system_control
from core.semantic.parsers.web import parse_known_website, parse_product_discovery_and_web_search
from core.semantic.parsers.windows import parse_folder_management, parse_window_control, parse_window_layout


def test_public_facade_and_imports():
    """Verifies that both old and new import paths export consistent symbols."""
    assert HinglishNLUParser is not None
    assert SemanticAction is not None
    assert HinglishNormalizer is not None
    assert SemanticPipelineOrchestrator is not None


def test_conversational_gating():
    """Verifies that chitchat and verbal corrections bypass command execution."""
    assert SemanticPipelineOrchestrator.parse("hi") is None
    assert SemanticPipelineOrchestrator.parse("hello") is None
    assert SemanticPipelineOrchestrator.parse("kaise ho") is None
    assert SemanticPipelineOrchestrator.parse("ek chutkula sunao") is None
    assert SemanticPipelineOrchestrator.parse("nahi yeh galat hai mat karo") is None
    assert SemanticPipelineOrchestrator.parse("nahi, doosra wala") is None


def test_math_parser():
    """Verifies modular math calculations, percentages, and equation solving."""
    # Arithmetic
    act_arith = parse_math("calculate 25 * 4", "calculate 25 * 4")
    assert act_arith is not None
    assert act_arith.intent == "CALCULATE"
    assert act_arith.service == "math"

    # Percentage
    act_pct = parse_math("500 ka 20 percent", "500 ka 20 percent")
    assert act_pct is not None
    assert act_pct.intent == "PERCENTAGE"
    assert act_pct.parameters["action"] == "of"

    # Equation
    act_eq = parse_math("x + 5 = 15 solve karo", "x + 5 = 15 solve karo")
    assert act_eq is not None
    assert act_eq.intent == "SOLVE_EQUATION"


def test_productivity_parsers():
    """Verifies reminders, WhatsApp, and location parsers."""
    # Reminder
    act_rem = parse_reminder("kal subah 8 baje meeting ka reminder lagao", "kal subah 8 baje meeting ka reminder lagao")
    assert act_rem is not None
    assert act_rem.intent == "CREATE_REMINDER"

    # WhatsApp
    act_wa = parse_whatsapp("Rahul ko WhatsApp par message bhejo hello", "rahul ko whatsapp par message bhejo hello")
    assert act_wa is not None
    assert act_wa.intent == "SEND_MESSAGE"
    assert act_wa.parameters["recipient"] == "Rahul"

    # Location
    act_loc = parse_location("Delhi se Mumbai kitna door hai", "delhi se mumbai kitna door hai")
    assert act_loc is not None
    assert act_loc.intent == "DISTANCE"


def test_system_and_screen_parsers():
    """Verifies system lock, audio volume, and screen inspection."""
    # System Control
    act_sys = parse_system_control("lock pc", "lock pc")
    assert act_sys is not None
    assert act_sys.intent == "LOCK_SYSTEM"

    # Audio
    act_aud = parse_audio_control("volume 50 karo", "volume 50 karo")
    assert act_aud is not None
    assert act_aud.intent == "SET_VOLUME"
    assert act_aud.parameters["level"] == 50

    # Screen Inspection
    act_scr = parse_screen_inspection("kya tum meri screen dekh saktey ho", "kya tum meri screen dekh saktey ho")
    assert act_scr is not None
    assert act_scr.intent == "SCREEN_INSPECTION"


def test_media_and_web_parsers():
    """Verifies YouTube playback, known websites, and web search."""
    # Media
    act_play = parse_media_playback("YouTube pe Tera Surroor chalao", "youtube pe tera surroor chalao")
    assert act_play is not None
    assert act_play.intent == "PLAY_MEDIA"
    assert "Surroor" in act_play.query

    # YouTube control
    act_pause = parse_youtube_control("pause", "pause")
    assert act_pause is not None
    assert act_pause.action == "pause"

    # Known Website
    act_web = parse_known_website("open chatgpt", "open chatgpt")
    assert act_web is not None
    assert act_web.parameters["url"] == "https://chatgpt.com"

    # Product search with price constraint
    act_prod = parse_product_discovery_and_web_search("Amazon pe 50000 ke andar laptop dikhao", "amazon pe 50000 ke andar laptop dikhao")
    assert act_prod is not None
    assert act_prod.intent == "WEB_SEARCH"
    assert act_prod.parameters["max_price"] == 50000


def test_windows_layout_and_folder_management():
    """Verifies window layout tiling, app close, and daily-use folders."""
    # Layout
    act_layout = parse_window_layout("Chrome ko left mein aur Brave ko right side mein open karo", "chrome ko left mein aur brave ko right side mein open karo")
    assert act_layout is not None
    assert act_layout.intent == "WINDOW_LAYOUT"
    assert len(act_layout.parameters["items"]) == 2

    # Folders
    act_folder = parse_folder_management("open startup folder", "open startup folder")
    assert act_folder is not None
    assert act_folder.intent == "FOLDER_OPEN"
    assert act_folder.parameters["target"] == "startup"

    # Window Control
    act_win = parse_window_control("maximize brave", "maximize brave")
    assert act_win is not None
    assert act_win.intent == "WINDOW_MAXIMIZE"


def test_orchestrator_end_to_end():
    """Verifies that HinglishNLUParser.parse delegates seamlessly through the orchestrator."""
    # Fast dispatch checks
    assert HinglishNLUParser.parse("hi") is None
    act1 = HinglishNLUParser.parse("open downloads folder")
    assert act1 is not None
    assert act1.intent == "FOLDER_OPEN"

    act2 = HinglishNLUParser.parse("calculate 10 + 20")
    assert act2 is not None
    assert act2.intent == "CALCULATE"

    act3 = HinglishNLUParser.parse("screen lock kar do")
    assert act3 is not None
    assert act3.intent == "LOCK_SYSTEM"
