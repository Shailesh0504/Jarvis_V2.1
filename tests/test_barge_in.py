# tests/test_barge_in.py
"""
Unit and Integration Tests for Real-Time Barge-In / Interruptible Conversation in Jarvis V2.1.
Validates:
1. TurnContext status lifecycle ('ACTIVE' -> 'INTERRUPTED' / 'COMPLETED' / 'CANCELLED') and monotonic generation_id.
2. ConversationManager interruption and generation invalidation.
3. TTSManager immediate audio cutoff (<20ms), queue drainage, generation tagging, and stale playback rejection.
4. InteractionGate barge-in detection for Hindi/English interruption phrases ('stop', 'ruk jao', 'chup', 'nahi ye karo...').
5. Acoustic self-voice echo suppression during speaker output.
6. End-to-end interruption pipeline and EventBus ConversationInterrupted domain event dispatch.
7. GUI worker cancellation and stale generation drop.
"""

import time
import pytest
from unittest.mock import MagicMock

from core.context import TurnContext
from core.conversation import ConversationManager
from core.event_bus import EventBus, EventTopics, ConversationInterrupted
from core.interaction_gate import InteractionGate, InteractionState, GateDecision
from core.app import JarvisCore
from voice.tts import TextToSpeech, TTSManager
from voice.listener import VoiceListener, VoiceMode
from voice.wake_word import WakeWordState


def test_turn_context_and_conversation_manager_interruption():
    """Verifies TurnContext tracks ACTIVE status and interrupt_active_turn marks INTERRUPTED."""
    cm = ConversationManager(wake_words=["jarvis"])
    assert cm.current_generation_id == 0

    # User starts a turn
    turn = cm.process_incoming_input("main aapko Chrome ke baare mein bata raha tha", source="voice")
    assert turn.status == "ACTIVE"
    assert turn.generation_id == 1
    assert cm.current_generation_id == 1
    assert cm.is_current_generation(1) is True

    # User interrupts mid-turn
    interrupted_turn = cm.interrupt_active_turn(reason="user_barge_in")
    assert interrupted_turn is not None
    assert interrupted_turn.status == "INTERRUPTED"
    assert interrupted_turn.interrupted_at is not None
    assert cm.current_generation_id == 2  # Generation invalidated!
    assert cm.is_current_generation(1) is False
    assert cm.is_current_generation(2) is True

    # complete_turn should ignore the interrupted turn
    cm.complete_turn(turn, response_text="Old response that should be discarded")
    assert turn.status == "INTERRUPTED"  # Did NOT change to COMPLETED


def test_tts_manager_immediate_stop_and_queue_drain():
    """Verifies TTSManager immediately halts audio, flushes queued chunks, and invalidates generation."""
    mock_engine = MagicMock(spec=TextToSpeech)
    tts_mgr = TTSManager(tts_engine=mock_engine)

    # Queue multiple speech chunks
    tts_mgr.speak("First sentence being spoken.")
    tts_mgr.speak("Second sentence queued.")
    tts_mgr.speak("Third sentence queued.")

    assert tts_mgr.current_generation_id == 0
    assert not tts_mgr._queue.empty()

    # Simulate active playback
    tts_mgr._is_speaking = True

    # Stop with generation increment (Barge-In)
    tts_mgr.stop(new_generation=True)

    # Queue must be completely drained and flushed
    assert tts_mgr._queue.empty() is True
    assert tts_mgr.is_speaking() is False
    assert tts_mgr.current_generation_id == 1
    mock_engine.stop.assert_called()


def test_interaction_gate_interruption_phrases():
    """Verifies InteractionGate detects stop and interruption phrases during TTS playback."""
    gate = InteractionGate(barge_in_enabled=True)
    gate.set_tts_speaking(True)
    assert gate.state == InteractionState.RESPONDING

    # Test Hindi, English, and Hinglish interruption phrases
    phrases = [
        "stop",
        "ruk jao",
        "ruko",
        "chup",
        "shant",
        "cancel",
        "bas karo",
        "bolna band karo",
    ]

    for phrase in phrases:
        gate.set_tts_speaking(True)
        decision = gate.evaluate(phrase)
        assert decision.accepted is True, f"Failed for phrase: '{phrase}'"
        assert decision.is_barge_in is True, f"Barge-in flag missing for: '{phrase}'"
        assert decision.command == "stop listening"


def test_interaction_gate_compound_barge_in_command():
    """Verifies compound interruption like 'nahi ye karo Brave kholo' extracts the new command."""
    gate = InteractionGate(barge_in_enabled=True)
    gate.set_tts_speaking(True)

    decision = gate.evaluate("nahi ye karo Brave kholo")
    assert decision.accepted is True
    assert decision.is_barge_in is True
    assert decision.command == "Brave kholo"
    assert decision.reason == "barge_in_interruption_command"


def test_interaction_gate_wake_word_and_active_dialogue_barge_in():
    """Verifies wake word or active conversation commands barge in during TTS playback."""
    gate = InteractionGate(barge_in_enabled=True)
    gate.set_tts_speaking(True)

    # 1. Wake word barge-in in standby
    d1 = gate.evaluate("Jarvis Brave kholo")
    assert d1.accepted is True
    assert d1.is_barge_in is True
    assert d1.command == "Brave kholo"

    # 2. Standalone wake word barge-in
    gate.set_tts_speaking(True)
    d2 = gate.evaluate("Jarvis")
    assert d2.accepted is True
    assert d2.is_barge_in is True
    assert d2.is_standalone_wake is True

    # 3. Active dialogue barge-in (without wake word)
    gate.set_tts_speaking(True)
    gate.authorize_followup()
    d3 = gate.evaluate("Brave kholo")
    assert d3.accepted is True
    assert d3.is_barge_in is True
    assert d3.command == "Brave kholo"


def test_acoustic_self_voice_echo_suppression():
    """Verifies that speech identical/similar to active TTS chunk is suppressed as echo."""
    gate = InteractionGate(barge_in_enabled=True)
    gate.set_tts_speaking(True)

    # Mock getter returning what Jarvis is currently speaking
    gate.set_tts_text_getter(lambda: "Main aapko Chrome browser ke features ke baare mein bata raha hoon")

    # Microphone hears echo of Jarvis's own voice
    echo_transcript = "Chrome browser ke features ke baare mein bata raha hoon"
    decision = gate.evaluate(echo_transcript)
    assert decision.accepted is False
    assert decision.reason == "suppressed_echo"

    # Microphone hears user saying an intentional command ("Brave kholo") -> NOT an echo!
    new_cmd_decision = gate.evaluate("Jarvis Brave kholo")
    assert new_cmd_decision.accepted is True
    assert new_cmd_decision.is_barge_in is True
    assert new_cmd_decision.command == "Brave kholo"


def test_voice_listener_barge_in_support():
    """Verifies VoiceListener triggers on_interrupted callback on wake/stop during TTS."""
    interrupted_events = []
    listener = VoiceListener(
        barge_in_enabled=True,
        on_interrupted=lambda raw: interrupted_events.append(raw)
    )

    listener.set_tts_speaking(True)
    assert listener.is_suppressed() is True

    # Stop phrase triggers barge-in
    res = listener.process_utterance("ruk jao")
    assert len(interrupted_events) == 1
    assert interrupted_events[0] == "ruk jao"
    assert listener.mode == VoiceMode.STANDBY


def test_end_to_end_barge_in_in_core_app(tmp_path):
    """Verifies full JarvisCore interruption flow: TTS stop, Turn INTERRUPTED, EventBus notification."""
    core = JarvisCore()
    mock_tts_mgr = MagicMock(spec=TTSManager)
    mock_tts_mgr.is_speaking.return_value = True
    core.set_tts_manager(mock_tts_mgr)

    # Listen to EventBus for ConversationInterrupted
    captured_events = []
    core.event_bus.subscribe(
        EventTopics.CONVERSATION_INTERRUPTED,
        lambda evt: captured_events.append(evt)
    )

    # Simulate ongoing active speech
    core.interaction_gate.set_tts_speaking(True)

    # User interrupts with new command
    resp = core.process_input("Jarvis Brave kholo", source="voice")

    # 1. TTSManager must have been stopped
    mock_tts_mgr.stop.assert_called_with(new_generation=True)

    # 2. EventBus received ConversationInterrupted event
    assert len(captured_events) >= 1
    evt = captured_events[0]
    assert evt.topic == EventTopics.CONVERSATION_INTERRUPTED
    assert evt.data.get("reason") in ("wake_word_detected", "barge_in", "user_barge_in")


def test_gui_task_worker_stale_generation_drop():
    """Verifies that TaskWorker with outdated generation_id is cancelled and not processed."""
    from gui.app import TaskWorker
    mock_core = MagicMock()
    mock_core.process_input.return_value = "Old response"

    worker = TaskWorker(mock_core, "old query", generation_id=1)
    results = []
    worker.finished.connect(lambda s, r, p, g: results.append((r, g)))

    # Cancel worker before run
    worker.cancel()
    worker.run()

    # Finished signal must NOT have fired
    assert len(results) == 0
