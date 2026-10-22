from unittest.mock import patch
from core.app import JarvisCore
from core.conversation import TurnContext


def test_empty_normalized_input_handling():
    """Verify that when turn.normalized_input is empty, resp is initialized,
    turn completes cleanly, and no UnboundLocalError is raised.
    """
    core = JarvisCore()
    # Call _process_input directly to test internal pipeline response
    internal_res = core._process_input("", source="test")
    assert internal_res == ""

    # Call process_input to verify full pipeline finishes gracefully without UnboundLocalError
    final_res = core.process_input("", source="test")
    assert isinstance(final_res, str)


def test_explicit_empty_turn_normalized_input():
    """Simulate a turn where normalizer / speech understanding results in empty normalized_input

    to directly hit line 1179 in _process_input.
    """
    core = JarvisCore()
    fake_turn = TurnContext(raw_input="test noise", source="test")
    fake_turn.normalized_input = ""

    with patch.object(core.conversation_manager, "process_incoming_input", return_value=fake_turn):
        res = core._process_input("test noise", source="test")
        assert res == ""
        assert fake_turn.status == "COMPLETED"
        assert fake_turn.response_text == ""
