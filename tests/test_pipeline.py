# tests/test_pipeline.py
import os
import pytest
from main import create_jarvis
from core.state import SystemState


@pytest.fixture
def jarvis(tmp_path):
    # Setup temporary config for isolation
    cfg_content = f"""
system:
  name: "JARVIS_TEST"
  wake_words:
    - "jarvis"
    - "hey jarvis"
memory:
  db_path: "{os.path.join(tmp_path, 'test_jarvis.db').replace('\\', '/')}"
learning:
  enabled: true
brain:
  llm_provider: "mock"
plugins:
  plugin_dir: "plugins"
  auto_load: true
"""
    cfg_file = tmp_path / "test_config.yaml"
    cfg_file.write_text(cfg_content)

    return create_jarvis(str(cfg_file))


def test_wake_word_and_time_query(jarvis):
    response = jarvis.process_input("Hey Jarvis, what time is it?")
    assert "The current date and time is" in response or "time" in response.lower()
    assert jarvis.state_machine.current_state == SystemState.IDLE


def test_memory_store_and_query_flow(jarvis):
    # Store
    store_resp = jarvis.process_input("Jarvis, remember that my favorite color is Blue")
    assert "committed that to memory" in store_resp.lower() or "favorite color" in store_resp.lower()

    # Query
    query_resp = jarvis.process_input("What is my favorite color?")
    assert "blue" in query_resp.lower()


def test_system_status_command(jarvis):
    resp = jarvis.process_input("status")
    assert "System is operating nominally" in resp


def test_unregistered_chat_query(jarvis):
    resp = jarvis.process_input("Who are you?")
    assert "JARVIS" in resp
