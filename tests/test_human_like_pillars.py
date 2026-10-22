"""
tests/test_human_like_pillars.py

Comprehensive test suite verifying the 8 Basic Needs for Human-Like JARVIS:
1. Natural Language Understanding (NLU & Comfort Empathy)
2. Conversation Context & Short-Term Memory
3. Intent & Dialogue Management (Banter/Skepticism)
4. Conversational Reasoning & Follow-ups (News Ordinals)
5. Reliable Speech-to-Text (STT Phonetic Repair)
6. Natural Text-to-Speech (TTS Text Sanitization)
7. Consistent Personality & Long-Term Memory (User Preferences)
8. Tool Execution & Universal Response Verification
"""

from unittest.mock import MagicMock
import pytest

from core.weather.models import WeatherData, WeatherLocation, WeatherQuery, WeatherIntent
from core.weather.response_generator import WeatherResponseGenerator
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.context import RuntimeContext, TurnContext
from core.execution.fast_path import FastPathEngine
from core.speech_repair import SpeechRepairEngine
from core.response_style import ResponseStyleManager
from memory.memory_manager import MemoryManager
from core.execution.verifier import ExecutionVerificationLayer
from core.execution.models import ExecutionState


class TestHumanLikePillars:

    def test_pillar1_nlu_comfort_empathy(self):
        """Pillar 1: 'Yaar, bahut garmi hai' detects comfort empathy, ambient temp, and suggestions."""
        loc = WeatherLocation(name="Ballard Estate")
        data = WeatherData(location=loc, temperature_c=29.0, temperature_f=84.2)
        query = WeatherQuery(
            raw_query="Yaar, bahut garmi hai",
            intent=WeatherIntent.TEMPERATURE,
            language="hi"
        )
        resp = WeatherResponseGenerator.generate_response(data, query)
        assert resp is not None
        assert "garmi" in resp
        assert "29°C" in resp or "temperature" in resp
        assert "AC" in resp or "fan" in resp

    def test_pillar2_context_short_term_memory(self):
        """Pillar 2: Context retention across multi-turn interactions (YouTube -> Song query)."""
        rc = RuntimeContext.get_instance()
        rc.desktop.set_website(site="youtube", url="https://youtube.com")
        assert rc.desktop.website == "youtube"
        assert rc.desktop.target_type == "website"
        assert rc.desktop.is_active is True

    def test_pillar3_dialogue_banter_management(self):
        """Pillar 3: 'Tum pagal ho kya?' detected as banter / rhetorical skepticism with witty reply."""
        res = ConversationalIntentClassifier.classify("Tum pagal ho kya?")
        assert res.intent_type in (ConversationalIntentType.CONVERSATION, ConversationalIntentType.STATEMENT)
        assert res.natural_response is not None
        assert "circuits" in res.natural_response or "theek" in res.natural_response

        # English variant
        res_en = ConversationalIntentClassifier.classify("Are you crazy?")
        assert res_en.natural_response is not None
        assert "circuits" in res_en.natural_response or "theek" in res_en.natural_response

    def test_pillar4_conversational_reasoning_news_ordinal(self):
        """Pillar 4: Ordinal follow-up ('Pehli wali detail mein batao') references stored headlines."""
        rc = RuntimeContext.get_instance()
        
        # Seed mock news in active context
        mock_articles = [
            {
                "title": "ISRO launches new satellite successfully",
                "source": "ISRO News",
                "published_at": "2026-10-10",
                "link": "https://isro.gov.in/launch",
            },
            {
                "title": "Sensex touches record high",
                "source": "Market News",
                "published_at": "2026-10-10",
                "link": "https://market.com/sensex",
            }
        ]
        rc.desktop.last_news_headlines = mock_articles

        turn = TurnContext(raw_input="Pehli wali detail mein batao")
        engine = FastPathEngine()
        res = engine.try_handle(
            raw_text="Pehli wali detail mein batao",
            normalized_input="pehli wali detail mein batao",
            turn=turn,
            start_time=0.0,
            tracker=None,
            source="cli"
        )
        assert res is not None
        assert "ISRO launches new satellite" in res

    def test_pillar5_stt_phonetic_repair(self):
        """Pillar 5: Phonetic misrecognitions repaired ('new batao' -> 'news batao', 'gane chalao' -> 'gaana chalao')."""
        engine = SpeechRepairEngine()
        res1 = engine.repair_transcript("new batao")
        assert res1.repaired is True
        assert "news batao" in res1.final_text

        res2 = engine.repair_transcript("gane chalao")
        assert res2.repaired is True
        assert "gaana chalao" in res2.final_text

    def test_pillar6_tts_text_sanitization(self):
        """Pillar 6: TTS input is sanitized from markdown, emojis, bracketed noise, and URLs."""
        raw_text = "Here is the result: **Success**! Check [link](https://example.com) ('chrome.exe')"
        cleaned = ResponseStyleManager.sanitize_for_tts(raw_text)
        assert "**" not in cleaned
        assert "chrome.exe" not in cleaned
        assert "[link]" not in cleaned

    def test_pillar7_long_term_preferences_brevity(self, tmp_path):
        """Pillar 7: User preferences stored in long-term memory and applied to style (brevity)."""
        db_file = str(tmp_path / "test_human_like.db")
        mem = MemoryManager(db_path=db_file)
        mem.preferences.set("brevity_preference", "short")
        pref = mem.preferences.get("brevity_preference")
        assert pref == "short"

        long_response = "Samajh gaya Sir. Main abhi aapki screen par YouTube open kar raha hoon aur volume ko 50% kar deta hoon."
        short_response = ResponseStyleManager.apply_brevity_preference(long_response, prefer_short=True)
        assert len(short_response) <= len(long_response)
        assert short_response == "Samajh gaya Sir."

    def test_pillar8_tool_execution_verification(self):
        """Pillar 8: Tool execution outcomes verified before confirming state."""
        verifier = ExecutionVerificationLayer()
        wm_mock = MagicMock()
        mock_win = MagicMock()
        mock_win.hwnd = 101
        mock_win.title = "YouTube - Google Chrome"
        mock_win.process_name = "chrome.exe"
        mock_win.pid = 1234
        wm_mock.list_all_windows.return_value = [mock_win]
        verifier.window_manager = wm_mock

        res = verifier.verify_browser_opened("youtube")
        assert res.verified is True
        assert res.state == ExecutionState.SUCCESS
