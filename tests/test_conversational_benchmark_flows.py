# tests/test_conversational_benchmark_flows.py
"""
Regression tests for human-like multi-turn conversation upgrades
(2026-09-27 rounds 1-3): capability memory, ellipsis, complaint recovery,
compose workflows (mail/message/meeting/reminder/alarm), corrections,
weather/music follow-ups, app restart, repeat, and repair fixes.
Hermetic: no OS side effects (stub core, real classifier/dialog/normalizer).
"""
import re
import types

import pytest

from core.conversational_intent import ConversationalIntentClassifier as CIC, ConversationalIntentType
from core.dialog_manager import DialogManager, WorkflowLock
from core.context import ActiveTargetContext
from core.conversation import ConversationManager


def _stub_core():
    _sm = types.SimpleNamespace(transition_to=lambda *a, **k: None)
    return types.SimpleNamespace(
        conversation_manager=ConversationManager(),
        dialog_manager=DialogManager(),
        active_context=ActiveTargetContext(),
        plugin_manager=None,
        config={},
        state_machine=_sm,
        event_bus=None,
        memory_manager=None,
        action_logger=None,
        last_execution_result=None,
        _record_turn_feedback=lambda **k: None,
    )


def _turn(text):
    return types.SimpleNamespace(normalized_input=text, raw_input=text,
                                 turn_id="t1", metadata={})


def _helper(core, text):
    from core.pipeline.input_pipeline import _maybe_start_compose_workflow
    ci = CIC.classify(text, active_context=core.active_context)
    return _maybe_start_compose_workflow(core, ci, _turn(text), text), ci


# --- Round 1: capability / ellipsis / complaint / wellbeing -----------------

def test_vlc_capability_clean_target():
    r = CIC.classify("kya tum mere liye vlc open kar sakti ho?")
    assert r.intent_type == ConversationalIntentType.CAPABILITY_QUESTION
    assert r.target == "vlc"
    assert "VLC" in (r.natural_response or "")
    assert "Mere Liye" not in (r.natural_response or "")


def test_bare_capability_feminine_returns_overview():
    r = CIC.classify("tum kya kar sakti ho?")
    assert r.intent_type == ConversationalIntentType.CAPABILITY_QUESTION
    assert r.target == "general"
    assert "applications" in (r.natural_response or "").lower()


def test_discourse_ellipsis_target_none():
    for t in ("to open karo", "toh khol do"):
        r = CIC.classify(t)
        assert r.intent_type == ConversationalIntentType.ACTION_COMMAND
        assert r.target is None, t
    # "tab band karo" (then close it) resolves to the current-window ellipsis.
    r = CIC.classify("tab band karo")
    assert r.intent_type == ConversationalIntentType.ACTION_COMMAND
    assert r.target in (None, "current"), r.target


def test_phir_se_karo_not_stripped_as_discourse():
    # "phir se karo" is REPEAT, never discourse ellipsis.
    ok, verb, tgt = CIC._detect_action_command("phir se karo")
    assert ok and tgt not in (None, "", "se", "to", "toh")


def test_praise_and_demo_suffix_stripped():
    r = CIC.classify("ye to bahut achhi baat hai to open kar ke dikhao")
    assert r.intent_type == ConversationalIntentType.ACTION_COMMAND
    assert r.target is None
    r2 = CIC.classify("vlc khol ke dikhao")
    assert r2.target == "vlc"


def test_complaint_recovery_is_action():
    r = CIC.classify("abhi tum ne bola tha ki vlc open kar sakte ho to open kyun nahi kartey")
    assert r.intent_type == ConversationalIntentType.ACTION_COMMAND
    assert r.target == "vlc"
    assert (r.parameters or {}).get("complaint_recovery") is True


def test_wellbeing_thik_variants():
    for t in ("sab thik hai", "sab theek hai", "main thik hun"):
        r = CIC.classify(t)
        assert r.intent_type == ConversationalIntentType.CONVERSATION
        assert "achha laga" in (r.natural_response or ""), t


def test_ho_gaya_no_crash_and_task_done():
    r = CIC.classify("Ho gaya")
    assert r.intent_type == ConversationalIntentType.STATEMENT
    assert (r.parameters or {}).get("task_done") is True


def test_bhej_verbs_are_commands():
    for t in ("Mail bhejo", "Rahul ko message bhejo", "Rahul ko mail bhejo"):
        r = CIC.classify(t)
        assert r.intent_type == ConversationalIntentType.ACTION_COMMAND, t
        assert "bhej" in (r.action_type or ""), t


# --- Speech repair / normalizer ----------------------------------------------

def test_negation_contrast_preserves_prohibition():
    from core.speech_repair import get_speech_repair_engine
    e = get_speech_repair_engine()
    r = e.repair_transcript("Baaki kuch mat band karna", context=None)
    assert r.final_text == "Baaki kuch mat band karna" and not r.repaired
    r2 = e.repair_transcript("Chrome mat kholo, Brave kholo", context=None)
    assert r2.final_text == "Brave kholo" and r2.repaired


def test_kal_not_corrupted_to_kar():
    from core.semantic.normalizer import HinglishNormalizer
    assert "kal" in HinglishNormalizer.normalize_text("kal ka?").lower()


# --- DialogManager compose machinery ------------------------------------------

def test_email_lock_questions_and_correction():
    dm = DialogManager()
    lock = dm.set_pending_goal("EMAIL_COMPOSE", ["recipient", "subject", "body", "send_confirm"],
                               "", turn_n=None, target_plugin="email", target_action="open_email_client",
                               initial_slots={"recipient": "Rahul"}, language="hi")
    assert dm._compose_question(lock) == "Subject kya rakhna hai?"
    core = _stub_core()
    core.dialog_manager = dm
    handled, resp = dm.process_locked_turn("Server report", core)
    assert handled and "Mail mein kya likhna hai?" in resp
    handled, resp = dm.process_locked_turn("Nahi, server update", core)
    assert handled and "server update" in resp.lower()


def test_reminder_time_parse_relative_and_clock():
    iso, disp = DialogManager._parse_compose_time("20 minute baad")
    assert iso and "20" in (disp or "")
    iso2, disp2 = DialogManager._parse_compose_time("kal 3 baje")
    assert iso2 and disp2


def test_alarm_am_hint_for_subah():
    iso, disp = DialogManager._parse_compose_time("6 baje", period_hint="am")
    assert iso and ("AM" in (disp or "") or "subah" in (disp or "").lower())


def test_question_never_fills_slot():
    dm = DialogManager()
    dm.set_pending_goal("EMAIL_COMPOSE", ["recipient", "subject", "body", "send_confirm"],
                        "", turn_n=None, initial_slots={"recipient": "Rahul"}, language="hi")
    core = _stub_core()
    core.dialog_manager = dm
    handled, resp = dm.process_locked_turn("Subject kya rakhu?", core)
    assert handled and "Subject kya rakhna hai?" in resp


def test_fresh_command_suspends_compose_lock():
    dm = DialogManager()
    dm.set_pending_goal("EMAIL_COMPOSE", ["recipient", "subject", "body", "send_confirm"],
                        "", turn_n=None, initial_slots={"recipient": "Rahul"}, language="hi")
    core = _stub_core()
    core.dialog_manager = dm
    handled, _ = dm.process_locked_turn("5 baje reminder lagao", core)
    assert handled is False
    assert dm.active_lock is None and dm.suspended_lock is not None


def test_meeting_lock_flow():
    core = _stub_core()
    resp, ci = _helper(core, "Meeting schedule karo")
    assert resp and "Kis ke saath" in resp
    assert core.dialog_manager.has_active_lock()


# --- Pipeline helper ----------------------------------------------------------

def test_email_trigger_extracts_recipient():
    core = _stub_core()
    resp, _ = _helper(core, "Rahul ko mail bhejo")
    assert resp and "Rahul" in resp and "Subject" in resp


def test_reminder_trigger_asks_title():
    core = _stub_core()
    resp, _ = _helper(core, "5 baje reminder lagao")
    assert resp and "reminder" in resp.lower()


def test_repeat_last_answer():
    core = _stub_core()
    t = _turn("Volume 50 karo")
    t.response_text = "Volume 50% kar diya hai, Boss."
    core.conversation_manager.session.turns.append(t)
    resp, _ = _helper(core, "Ek baar phir batao")
    assert resp and "dobara bata raha hoon" in resp


def test_task_done_with_suspended_lock_offers_resume():
    core = _stub_core()
    dm = core.dialog_manager
    dm.set_pending_goal("EMAIL_COMPOSE", ["subject", "body", "send_confirm"], "", turn_n=None,
                        initial_slots={"recipient": "Rahul"}, language="hi")
    dm.suspended_lock = dm.active_lock
    dm.active_lock = None
    resp, _ = _helper(core, "Ho gaya")
    assert resp and "pending" in resp and "Rahul" in resp


def test_post_reminder_correction_without_lock():
    core = _stub_core()
    core.active_context.update_command_context("REMINDER_CREATE", "create_reminder",
                                               {"reminder_id": 999, "reminder_title": "x"}, success=True)
    from unittest.mock import MagicMock
    pm = MagicMock()
    pm.execute_action.return_value = types.SimpleNamespace(success=True, data={}, error=None)
    core.plugin_manager = pm
    resp, _ = _helper(core, "Nahi, 6 baje")
    assert resp and "6 baje" in resp
    pm.execute_action.assert_called_once()
    assert pm.execute_action.call_args[0][1] == "edit_reminder"


def test_vague_negation_ack():
    core = _stub_core()
    resp, _ = _helper(core, "Baaki kuch mat band karna")
    assert resp and "haath nahi lagaunga" in resp


def test_app_restart_not_system():
    core = _stub_core()
    from unittest.mock import MagicMock
    te = MagicMock()
    from core.target_engine import ActionOutcome
    te.execute.return_value = ActionOutcome(success=True, message="ok", verified=True, status="done")
    core.target_engine = te
    core.active_context.set_application("chrome", action="open_app")
    resp, _ = _helper(core, "Isko ek baar restart kar do")
    assert resp and "restart kar diya" in resp
    assert te.execute.call_count == 2  # close + open, never system restart


def test_explicit_browser_container_parsed():
    from brain.semantic_parser import HinglishNLUParser
    a = HinglishNLUParser.parse("chatgpt ko edge browser me open karo")
    assert a is not None and a.intent == "OPEN_WEBSITE"
    assert a.parameters.get("container") == "edge"
    assert a.parameters.get("site") == "chatgpt"
    b = HinglishNLUParser.parse("chatgpt kholo")
    assert b is not None
    assert not b.parameters.get("container")  # default behavior preserved
    c = HinglishNLUParser.parse("edge kholo")
    assert c is not None and c.intent != "OPEN_WEBSITE"  # app open, not website


def test_explicit_container_executes_in_that_browser():
    core = _stub_core()
    from unittest.mock import MagicMock
    from core.target_engine import ActionOutcome
    te = MagicMock()
    te.execute.return_value = ActionOutcome(success=True, message="opened", verified=True, status="done")
    core.target_engine = te
    from core.execution.semantic_executor import SemanticActionExecutor
    from brain.semantic_parser import HinglishNLUParser
    import types as _t
    turn = _t.SimpleNamespace(normalized_input="chatgpt ko edge browser me open karo",
                              raw_input="chatgpt ko edge browser me open karo",
                              metadata={}, source="test", status="ACTIVE")
    act = HinglishNLUParser.parse("chatgpt ko edge browser me open karo")
    ex = SemanticActionExecutor(core=core)
    resp = ex.execute(act, turn=turn, start_time=0.0, source="test", ctx_key="global", lce_tokens=None)
    _handled, _msg = (resp if isinstance(resp, tuple) else (True, resp))
    assert "Edge" in _msg and "ChatGPT" in _msg and "http" not in _msg.lower()
    _req = te.execute.call_args[0][0]
    assert getattr(_req, "container", "") == "edge"


def test_mailbox_inbox_from_history():
    core = _stub_core()
    from unittest.mock import MagicMock
    pm = MagicMock()
    pm.execute_action.return_value = types.SimpleNamespace(success=True, data={}, error=None)
    core.plugin_manager = pm
    t = _turn("Gmail kholo")
    t.response_text = "gmail open ho gaya."
    core.conversation_manager.session.turns.append(t)
    resp, _ = _helper(core, "Isme inbox kholo")
    assert resp and "inbox" in resp.lower()
    pm.execute_action.assert_called_once()
    assert "mail.google.com" in pm.execute_action.call_args[0][2]["url"]
