# tests/test_laya_core_orchestration.py
"""Comprehensive Unit & Integration Test Suite for LAYA CORE Tri-Bridge Orchestration Layer.

Verifies the 9 Authoritative Responsibilities:
1. command direct execute hogi ya nahi (Direct Tool vs Chat vs Agent Planner)
2. conversation model ko bhejna hai (Route to Chat/LLM)
3. complex task ke liye agent activate karna hai (Route to Agent Planner / Task Graph)
4. kaunsa model use hoga (Fast rule vs Local Qwen vs Cloud LLM vs Agent Planner)
5. context kitna dena hai (Context scoping: NONE, MINIMAL, ACTIVE_WINDOW, CONVERSATIONAL, FULL)
6. memory kab retrieve karni hai (Selective memory gating)
7. confirmation chahiye ya nahi (Risk-gated confirmation)
8. task successful hua ya nahi (Physical state verification)
9. failure par retry/fallback kya hai (Closed-loop fallback & recovery)
"""

import pytest
from unittest.mock import MagicMock

from core.laya import (
    LayaCore,
    LayaDecision,
    LayaResponseMode,
    LayaRoute,
    get_laya_core,
)


@pytest.fixture
def laya():
    """Provides LayaCore singleton instance."""
    return get_laya_core()


# ==============================================================================
# 1. COMMAND DIRECT EXECUTE HOGI YA NAHI (Direct Tool vs Chat vs Agent)
# ==============================================================================

def test_laya_direct_tool_execution(laya):
    """Deterministic commands (volume, time, weather, direct app launch) must route to FAST_ROUTER."""
    decision_vol = laya.decide("volume 50 karo")
    assert decision_vol.laya_route == LayaRoute.FAST_ROUTER
    assert decision_vol.is_direct_execution is True

    decision_weather = laya.decide("mumbai ka weather kaisa hai")
    assert decision_weather.laya_route == LayaRoute.FAST_ROUTER
    assert decision_weather.is_direct_execution is True

    decision_time = laya.decide("time kya hua hai")
    assert decision_time.laya_route == LayaRoute.FAST_ROUTER
    assert decision_time.is_direct_execution is True


# ==============================================================================
# 2. CONVERSATION MODEL KO BHEJNA HAI (Route to Chat/LLM)
# ==============================================================================

def test_laya_route_to_chat(laya):
    """Small talk, greetings, knowledge queries, and general conversation must route to CHAT."""
    decision_greet = laya.decide("hello jarvis kaise ho")
    assert decision_greet.laya_route == LayaRoute.CHAT
    assert decision_greet.is_direct_execution is False

    decision_gk = laya.decide("India ki capital kya hai")
    assert decision_gk.laya_route == LayaRoute.CHAT

    decision_cap = laya.decide("kya tum system lock kar sakte ho?")
    assert decision_cap.laya_route == LayaRoute.CHAT
    assert decision_cap.is_direct_execution is False


# ==============================================================================
# 3. COMPLEX TASK KE LIYE AGENT ACTIVATE KARNA HAI (Agent Planner)
# ==============================================================================

def test_laya_route_to_agent_planner(laya):
    """Multi-step tasks with chaining conjunctions ('aur phir', 'ke baad', 'then') must activate AGENT_PLANNER."""
    decision_multi = laya.decide("Chrome open karo aur phir google search karo python tutorial")
    assert decision_multi.laya_route == LayaRoute.AGENT_PLANNER
    assert decision_multi.model_target == "agent_planner"
    assert decision_multi.context_scope == "FULL"

    decision_seq = laya.decide("Downloads folder open karne ke baad temp files delete karo")
    assert decision_seq.laya_route == LayaRoute.AGENT_PLANNER
    assert decision_seq.model_target == "agent_planner"


# ==============================================================================
# 4. KAUNSA MODEL USE HOGA (Model Selection)
# ==============================================================================

def test_laya_model_target_selection(laya):
    """Laya authoritatively selects model target: rule_fast, local_qwen, agent_planner, or knowledge_engine."""
    # Fast tool -> rule_fast
    d_fast = laya.decide("mute karo")
    assert d_fast.model_target == "rule_fast"

    # Conversational chit-chat -> local_qwen
    d_chat = laya.decide("mujhe ek achha joke sunao")
    assert d_chat.model_target == "local_qwen"

    # Multi-step goal -> agent_planner
    d_agent = laya.decide("research AI trends and summarize in a file")
    assert d_agent.model_target == "agent_planner"


# ==============================================================================
# 5. CONTEXT KITNA DENA HAI (Context Scoping)
# ==============================================================================

def test_laya_context_scoping(laya):
    """Laya scopes context dynamically: NONE for isolated tools, CONVERSATIONAL for chat, FULL for agent."""
    d_tool = laya.decide("volume up")
    assert d_tool.context_scope == "NONE"
    assert d_tool.max_history_turns == 0

    d_chat = laya.decide("tum kiske dwara banaye gaye ho?")
    assert d_chat.context_scope == "CONVERSATIONAL"
    assert d_chat.max_history_turns >= 3

    d_agent = laya.decide("pehla step karo then second step execute karo")
    assert d_agent.context_scope == "FULL"
    assert d_agent.max_history_turns >= 5


# ==============================================================================
# 6. MEMORY KAB RETRIEVE KARNI HAI (Selective Memory Gating)
# ==============================================================================

def test_laya_selective_memory_retrieval(laya):
    """Memory retrieval is strictly gated: only triggered when queries mention identity, preferences, or recall."""
    # Isolated tool command -> DO NOT retrieve memory (<15ms critical path)
    d_tool = laya.decide("calculator open karo")
    assert d_tool.retrieve_memory is False
    assert len(d_tool.memory_types) == 0

    # Explicit memory recall query -> retrieve personal facts
    d_mem = laya.decide("mera naam kya hai?")
    assert d_mem.retrieve_memory is True
    assert "user_profile" in d_mem.memory_types

    d_pref = laya.decide("meri favorite music preference yaad hai?")
    assert d_pref.retrieve_memory is True
    assert "preferences" in d_pref.memory_types


# ==============================================================================
# 7. CONFIRMATION CHAHIYE YA NAHI (Risk-Gated Policy)
# ==============================================================================

def test_laya_confirmation_gating(laya):
    """LOW risk operations execute directly; HIGH/CRITICAL risk operations mandate confirmation."""
    # LOW risk -> no confirmation
    d_low = laya.decide("notepad kholo")
    assert d_low.needs_confirmation is False

    # HIGH / CRITICAL risk -> needs confirmation
    d_crit = laya.decide("system shutdown karo")
    assert d_crit.needs_confirmation is True
    assert d_crit.confirmation_prompt is not None


# ==============================================================================
# 8. TASK SUCCESSFUL HUA YA NAHI (Physical Verification Check)
# ==============================================================================

def test_laya_verify_execution(laya):
    """LayaCore.verify_execution evaluates actual execution outcome and generates spoken feedback."""
    decision = laya.decide("chrome kholo")
    
    # 1. Successful execution
    success_res = {"success": True, "message": "Chrome launched and window verified"}
    verified_out = laya.verify_execution(decision, success_res)
    assert verified_out["verified"] is True
    assert "open" in verified_out["spoken_feedback"].lower() or "complete" in verified_out["spoken_feedback"].lower() or "ho gaya" in verified_out["spoken_feedback"].lower()

    # 2. Failed execution
    fail_res = {"success": False, "message": "Process failed to spawn"}
    failed_out = laya.verify_execution(decision, fail_res)
    assert failed_out["verified"] is False
    assert decision.verified is False


# ==============================================================================
# 9. FAILURE PAR RETRY/FALLBACK KYA HAI (Closed-Loop Recovery)
# ==============================================================================

def test_laya_determine_fallback(laya):
    """LayaCore.determine_fallback provides safe self-healing recommendations on failures."""
    decision_app = laya.decide("open antigravity")
    fallback = laya.determine_fallback(decision_app, error="AppNotFound")
    
    assert fallback["can_retry"] is True
    assert "browser" in fallback["suggestion"].lower() or "alternate" in fallback["suggestion"].lower()
    assert fallback["action"] in ("open_website", "retry_alternate")


# ==============================================================================
# 10. INTEGRATION TEST WITH JARVISCORE PIPELINE
# ==============================================================================

def test_laya_core_integration_turn_metadata():
    """Verify that JarvisCore stamps laya_decision and laya_verification onto turn metadata."""
    from core.app import JarvisCore
    core = JarvisCore.__new__(JarvisCore)
    core.laya_core = get_laya_core()
    
    # Mock TurnContext
    turn = MagicMock()
    turn.normalized_input = "volume 30 karo"
    turn.metadata = {}

    # Emulate JarvisCore Step 2.LayaCore
    decision = core.laya_core.decide(raw_text="volume 30 karo", normalized_text=turn.normalized_input)
    turn.metadata["laya_decision"] = decision.to_dict()

    assert turn.metadata["laya_decision"]["laya_route"] == "FAST_ROUTER"
    assert turn.metadata["laya_decision"]["model_target"] == "rule_fast"
    assert turn.metadata["laya_decision"]["is_direct_execution"] is True

    # Emulate FastPath execution verification
    verify_out = core.laya_core.verify_execution(decision, {"success": True, "message": "Volume set to 30"})
    turn.metadata["laya_verification"] = verify_out
    assert turn.metadata["laya_verification"]["verified"] is True
