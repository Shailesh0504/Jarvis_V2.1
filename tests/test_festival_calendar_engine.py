# tests/test_festival_calendar_engine.py
"""
Test Suite for the Jarvis Calendar & Festival Knowledge Engine.

Validates:
1. Festival date queries (current year from system clock, explicit year, relative year)
2. Festival definition queries vs date queries
3. Year inference (agle saal, pichle saal, explicit year, default = now().year)
4. Festival alias resolution (Ganpati = Ganesh Chaturthi, multiple aliases)
5. STT normalization of festival names
6. Upcoming festival queries
7. Month-based festival queries
8. National day queries
9. Anti-hallucination: unknown year data returns honest refusal
10. Action vs knowledge separation (reminders not answered as knowledge)
11. General date queries NOT intercepted by festival engine (forward to TimeContext)
12. KnowledgeRouter integration (full pipeline)
"""

import pytest
from datetime import datetime, date
from unittest.mock import patch

from core.knowledge.calendar.year_inference import YearInferenceEngine
from core.knowledge.calendar.intent_classifier import FestivalIntentClassifier
from core.knowledge.calendar.models import CalendarIntentType
from core.knowledge.calendar.festival_store import get_festival_store
from core.knowledge.calendar.engine import FestivalCalendarEngine
from core.knowledge import get_knowledge_engine, ConfidenceLevel, KnowledgeSourceType


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def engine():
    return FestivalCalendarEngine()


@pytest.fixture
def store():
    return get_festival_store()


@pytest.fixture
def ke():
    return get_knowledge_engine()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Year Inference Engine
# ─────────────────────────────────────────────────────────────────────────────

class TestYearInference:
    """Ensures year is always derived from system clock — never a hardcoded constant."""

    def test_default_year_from_system_clock(self):
        """No explicit year → must return datetime.now().year, not a hardcoded constant."""
        year, inferred = YearInferenceEngine.infer_year("Ganpati kab hai?")
        assert year == datetime.now().year, "Year must come from system clock, not a hardcoded value!"
        assert inferred is True

    def test_explicit_year_2026(self):
        year, inferred = YearInferenceEngine.infer_year("2026 mein Ganpati kab hai?")
        assert year == 2026
        assert inferred is False

    def test_explicit_year_2027(self):
        year, inferred = YearInferenceEngine.infer_year("2027 mein Diwali kab hai?")
        assert year == 2027
        assert inferred is False

    def test_next_year_inference(self):
        year, inferred = YearInferenceEngine.infer_year("agle saal Ganpati kab hai?")
        assert year == datetime.now().year + 1
        assert inferred is True

    def test_previous_year_inference(self):
        year, inferred = YearInferenceEngine.infer_year("pichle saal Holi kab thi?")
        assert year == datetime.now().year - 1
        assert inferred is True

    def test_current_year_explicit_token(self):
        year, inferred = YearInferenceEngine.infer_year("is saal Diwali kab hai?")
        assert year == datetime.now().year
        assert inferred is True

    def test_next_year_english(self):
        year, inferred = YearInferenceEngine.infer_year("next year when is Holi?")
        assert year == datetime.now().year + 1
        assert inferred is True

    def test_year_never_hardcoded(self):
        """
        CRITICAL: Simulate running in a different year. The engine must NOT use
        a hardcoded year — it must dynamically read from datetime.now().
        """
        with patch("core.knowledge.calendar.year_inference.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2030, 6, 15)
            year, _ = YearInferenceEngine.infer_year("Ganpati kab hai?")
            assert year == 2030, "Year inference must use datetime.now(), not a hardcoded constant"

    def test_extract_explicit_year_none(self):
        result = YearInferenceEngine.extract_explicit_year("Ganpati kab hai?")
        assert result is None

    def test_extract_explicit_year_present(self):
        result = YearInferenceEngine.extract_explicit_year("Diwali 2028 mein kab hai?")
        assert result == 2028


# ─────────────────────────────────────────────────────────────────────────────
# 2. Intent Classification
# ─────────────────────────────────────────────────────────────────────────────

class TestFestivalIntentClassification:

    def test_date_query_hindi(self):
        intent, conf = FestivalIntentClassifier.classify("Ganpati kab hai?")
        assert intent == CalendarIntentType.FESTIVAL_DATE_QUERY
        assert conf >= 0.85

    def test_date_query_hinglish(self):
        intent, _ = FestivalIntentClassifier.classify("Diwali is saal kab padegi?")
        assert intent == CalendarIntentType.FESTIVAL_DATE_QUERY

    def test_date_query_english(self):
        intent, _ = FestivalIntentClassifier.classify("When is Holi in 2026?")
        assert intent == CalendarIntentType.FESTIVAL_DATE_QUERY

    def test_definition_query(self):
        intent, conf = FestivalIntentClassifier.classify("Ganesh Chaturthi kya hai?")
        assert intent == CalendarIntentType.FESTIVAL_DEFINITION
        assert conf >= 0.85

    def test_definition_query_english(self):
        intent, _ = FestivalIntentClassifier.classify("What is Diwali?")
        assert intent == CalendarIntentType.FESTIVAL_DEFINITION

    def test_duration_query(self):
        intent, _ = FestivalIntentClassifier.classify("Ganpati kitne din chalega?")
        assert intent == CalendarIntentType.FESTIVAL_DURATION

    def test_upcoming_festival_query(self):
        intent, _ = FestivalIntentClassifier.classify("Agla festival kaunsa hai?")
        assert intent == CalendarIntentType.UPCOMING_FESTIVAL

    def test_month_festival_query(self):
        intent, _ = FestivalIntentClassifier.classify("September mein kaun sa festival hai?")
        assert intent == CalendarIntentType.MONTH_FESTIVAL

    def test_national_day_query(self):
        intent, _ = FestivalIntentClassifier.classify("Republic Day kab hai?")
        assert intent == CalendarIntentType.NATIONAL_DAY_QUERY

    def test_general_date_query_not_calendar(self):
        """'Aaj kya date hai?' must NOT be claimed by festival engine."""
        intent, _ = FestivalIntentClassifier.classify("Aaj kya date hai?")
        assert intent == CalendarIntentType.GENERAL_DATE_QUERY

    def test_not_calendar_action_command(self):
        """Action commands with festival names must NOT be classified as calendar knowledge queries."""
        intent, conf = FestivalIntentClassifier.classify("Ganpati ka reminder laga do")
        # The calendar engine must reject this — it's an action, not a knowledge query
        assert intent == CalendarIntentType.NOT_CALENDAR, (
            "'reminder laga do' is an action command, not a knowledge query — "
            "calendar engine must return NOT_CALENDAR"
        )

    def test_not_calendar_chrome(self):
        intent, _ = FestivalIntentClassifier.classify("Chrome kholo")
        assert intent == CalendarIntentType.NOT_CALENDAR

    def test_is_calendar_candidate_true(self):
        assert FestivalIntentClassifier.is_calendar_candidate("Ganpati kab hai?") is True

    def test_is_calendar_candidate_false(self):
        assert FestivalIntentClassifier.is_calendar_candidate("Chrome kholo") is False


# ─────────────────────────────────────────────────────────────────────────────
# 3. Festival Store / Alias Resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestFestivalAliasResolution:

    def test_ganpati_resolves_to_ganesh_chaturthi(self, store):
        fid = store.resolve_festival_id("ganpati kab hai")
        assert fid == "ganesh_chaturthi"

    def test_ganesh_chaturthi_alias(self, store):
        fid = store.resolve_festival_id("Ganesh Chaturthi kab hai")
        assert fid == "ganesh_chaturthi"

    def test_ganesh_utsav_alias(self, store):
        fid = store.resolve_festival_id("Ganesh Utsav 2026 mein kab hai")
        assert fid == "ganesh_chaturthi"

    def test_bappa_alias(self, store):
        fid = store.resolve_festival_id("bappa kab aayega")
        assert fid == "ganesh_chaturthi"

    def test_diwali_deepawali_same(self, store):
        fid1 = store.resolve_festival_id("diwali")
        fid2 = store.resolve_festival_id("deepawali")
        assert fid1 == fid2 == "diwali"

    def test_rakhi_resolves_to_raksha_bandhan(self, store):
        fid = store.resolve_festival_id("rakhi kab hai")
        assert fid == "raksha_bandhan"

    def test_republic_day_alias(self, store):
        fid = store.resolve_festival_id("republic day kab hai")
        assert fid == "republic_day"

    def test_gantantra_diwas_alias(self, store):
        fid = store.resolve_festival_id("gantantra diwas kab hai")
        assert fid == "republic_day"

    def test_independence_day_alias(self, store):
        fid = store.resolve_festival_id("swatantrata diwas kab hai")
        assert fid == "independence_day"

    def test_unknown_festival_returns_none(self, store):
        fid = store.resolve_festival_id("Halloween kab hai")
        assert fid is None


# ─────────────────────────────────────────────────────────────────────────────
# 4. Festival Date Queries — Core Engine
# ─────────────────────────────────────────────────────────────────────────────

class TestFestivalDateQueries:

    def test_ganpati_current_year_uses_system_clock(self, engine):
        """Most critical test: Ganpati kab hai? must use current year from system clock."""
        result = engine.query("Ganpati kab hai?")
        assert result.found is True
        current_year = datetime.now().year
        assert str(current_year) in result.answer_text, (
            f"Answer must contain current year {current_year} (from system clock), "
            f"not a hardcoded value. Got: {result.answer_text}"
        )

    def test_ganesh_chaturthi_explicit_2026(self, engine):
        result = engine.query("2026 mein Ganesh Chaturthi kab hai?")
        assert result.found is True
        assert "2026" in result.answer_text
        assert "14 September 2026" in result.answer_text

    def test_diwali_2026(self, engine):
        result = engine.query("2026 mein Diwali kab hai?")
        assert result.found is True
        assert "2026" in result.answer_text
        assert "8 November 2026" in result.answer_text or "November" in result.answer_text

    def test_holi_2026(self, engine):
        result = engine.query("2026 mein Holi kab hai?")
        assert result.found is True
        assert "2026" in result.answer_text
        assert "March" in result.answer_text

    def test_republic_day_is_fixed(self, engine):
        """Republic Day must always be 26 January regardless of year."""
        result = engine.query("Republic Day kab hai?")
        assert result.found is True
        assert "26 January" in result.answer_text

    def test_independence_day_is_fixed(self, engine):
        result = engine.query("Independence Day kab hai?")
        assert result.found is True
        assert "15 August" in result.answer_text

    def test_is_saal_diwali(self, engine):
        result = engine.query("Is saal Diwali kab hai?")
        assert result.found is True
        current_year = datetime.now().year
        assert str(current_year) in result.answer_text

    def test_agle_saal_ganpati(self, engine):
        result = engine.query("Agle saal Ganpati kab hai?")
        assert result.found is True
        next_year = datetime.now().year + 1
        assert str(next_year) in result.answer_text

    def test_pichle_saal_holi(self, engine):
        result = engine.query("Pichle saal Holi kab thi?")
        assert result.found is True
        prev_year = datetime.now().year - 1
        assert str(prev_year) in result.answer_text

    def test_2027_janmashtami(self, engine):
        result = engine.query("2027 mein Janmashtami kab hai?")
        assert result.found is True
        assert "2027" in result.answer_text

    def test_christmas_fixed_date(self, engine):
        result = engine.query("Christmas kab hai?")
        assert result.found is True
        assert "25 December" in result.answer_text

    def test_teachers_day_fixed(self, engine):
        result = engine.query("Teachers Day kab hai?")
        assert result.found is True
        assert "5 September" in result.answer_text


# ─────────────────────────────────────────────────────────────────────────────
# 5. Festival Definition Queries
# ─────────────────────────────────────────────────────────────────────────────

class TestFestivalDefinitionQueries:

    def test_ganpati_definition(self, engine):
        result = engine.query("Ganesh Chaturthi kya hai?")
        assert result.found is True
        answer_lower = result.answer_text.lower()
        assert any(w in answer_lower for w in ["ganesha", "ganesh", "ganesha", "elephant", "wisdom"])

    def test_diwali_definition_english(self, engine):
        result = engine.query("What is Diwali?")
        assert result.found is True
        answer_lower = result.answer_text.lower()
        assert any(w in answer_lower for w in ["light", "festival", "darkness"])

    def test_holi_definition(self, engine):
        result = engine.query("Holi kya hota hai?")
        assert result.found is True
        assert "rang" in result.answer_text.lower() or "color" in result.answer_text.lower()

    def test_republic_day_definition(self, engine):
        result = engine.query("Republic Day kya hai?")
        assert result.found is True
        answer_lower = result.answer_text.lower()
        assert any(w in answer_lower for w in ["constitution", "samvidhan", "republic", "gantantra"])


# ─────────────────────────────────────────────────────────────────────────────
# 6. Duration Queries
# ─────────────────────────────────────────────────────────────────────────────

class TestFestivalDurationQueries:

    def test_ganpati_kitne_din(self, engine):
        result = engine.query("Ganpati kitne din chalega?")
        assert result.found is True
        # Ganesh Chaturthi is 10 days
        assert "10" in result.answer_text

    def test_navratri_duration(self, engine):
        result = engine.query("Navratri 2026 mein kab se kab tak hai?")
        assert result.found is True
        assert "2026" in result.answer_text
        assert "October" in result.answer_text


# ─────────────────────────────────────────────────────────────────────────────
# 7. Upcoming Festival Queries
# ─────────────────────────────────────────────────────────────────────────────

class TestUpcomingFestivalQueries:

    def test_agla_festival(self, engine):
        result = engine.query("Agla festival kaunsa hai?")
        assert result.found is True
        assert len(result.answer_text) > 5

    def test_next_festival_english(self, engine):
        result = engine.query("Next festival kab hai?")
        assert result.found is True

    def test_upcoming_uses_current_date(self, engine):
        """Upcoming festivals must be computed from datetime.now().date()."""
        today = datetime.now().date()
        store = get_festival_store()
        upcoming = store.get_upcoming_festivals(today, limit=1)
        if upcoming:
            entry, yd = upcoming[0]
            assert yd.start_date >= today, "Upcoming festival must be on or after today"


# ─────────────────────────────────────────────────────────────────────────────
# 8. Month Festival Queries
# ─────────────────────────────────────────────────────────────────────────────

class TestMonthFestivalQueries:

    def test_september_festivals(self, engine):
        """September 2026 has Ganesh Chaturthi."""
        result = engine.query("September mein kaun sa festival hai?")
        # Should find at least one festival in september of current/nearby year
        # Result may be found or not depending on year in data; just check it processes
        assert result is not None

    def test_november_festivals_2026(self, engine):
        result = engine.query("November 2026 mein kaun sa festival hai?")
        assert result is not None


# ─────────────────────────────────────────────────────────────────────────────
# 9. Anti-Hallucination — Unknown Year Data
# ─────────────────────────────────────────────────────────────────────────────

class TestAntiHallucination:

    def test_year_out_of_range_refusal(self, engine):
        """Must refuse honestly for years beyond 2028, not fabricate a date."""
        result = engine.query("2035 mein Ganpati kab hai?")
        assert result.found is False
        assert "2035" in result.answer_text or "uplabdh nahi" in result.answer_text.lower() or "don't have" in result.answer_text.lower()

    def test_unknown_festival_refusal(self, engine):
        """Must not fabricate a date for an unknown festival."""
        result = engine.query("Halloween kab hai?")
        # Either found=False, or NOT_CALENDAR path
        if result.found:
            # If somehow it returns found, it must have come from a proper entry
            assert result.entity_id is not None


# ─────────────────────────────────────────────────────────────────────────────
# 10. General Date Queries Routing
# ─────────────────────────────────────────────────────────────────────────────

class TestGeneralDateQueryRouting:

    def test_aaj_date_not_claimed_by_festival_engine(self, engine):
        """'Aaj kya date hai?' must NOT be answered by the festival engine."""
        result = engine.query("Aaj kya date hai?")
        # Festival engine must return found=False and forward_to_time_context
        assert result.found is False
        assert result.metadata.get("forward_to_time_context") is True

    def test_kal_date_not_claimed(self, engine):
        result = engine.query("Kal kya date hogi?")
        assert result.found is False


# ─────────────────────────────────────────────────────────────────────────────
# 11. Knowledge/Action Separation
# ─────────────────────────────────────────────────────────────────────────────

class TestKnowledgeActionSeparation:

    def test_reminder_command_not_answered_as_knowledge(self, ke):
        """
        'Ganpati ka reminder laga do' is an ACTION command, not a knowledge query.
        The calendar engine must NOT claim this query (returns NOT_CALENDAR).
        Even if a downstream system classifies it differently, the calendar engine
        must not answer it as a festival date query.
        """
        engine = FestivalCalendarEngine()
        # The calendar engine itself must not be a candidate for action commands
        assert not engine.is_calendar_candidate("Ganpati ka reminder laga do"), (
            "Calendar engine must NOT claim action commands as calendar knowledge queries"
        )

    def test_festival_date_is_knowledge(self, ke):
        """'Ganpati kab hai?' must return a knowledge answer, not trigger a reminder."""
        result = ke.query("Ganpati kab hai?")
        assert result.found is True
        # Must NOT have set needs_fresh_fetch (it's not a live/external data query)
        assert result.needs_fresh_fetch is False


# ─────────────────────────────────────────────────────────────────────────────
# 12. KnowledgeRouter Full Pipeline Integration
# ─────────────────────────────────────────────────────────────────────────────

class TestKnowledgeRouterIntegration:
    """Tests that the full pipeline from KnowledgeEngine.query() routes correctly."""

    def test_ganpati_via_knowledge_engine(self, ke):
        result = ke.query("Ganpati kab hai?")
        assert result.found is True
        current_year = datetime.now().year
        assert str(current_year) in result.answer_text

    def test_diwali_2026_via_knowledge_engine(self, ke):
        result = ke.query("2026 mein Diwali kab hai?")
        assert result.found is True
        assert "2026" in result.answer_text

    def test_republic_day_via_knowledge_engine(self, ke):
        result = ke.query("Republic Day kab hai?")
        assert result.found is True
        assert "26 January" in result.answer_text

    def test_ganesh_chaturthi_definition_via_ke(self, ke):
        result = ke.query("Ganesh Chaturthi kya hai?")
        assert result.found is True
        assert "Ganesha" in result.answer_text or "ganesh" in result.answer_text.lower()

    def test_existing_gk_queries_unaffected(self, ke):
        """Existing GK queries must still work after calendar engine integration."""
        res_india = ke.query("India ki capital kya hai?")
        assert res_india.found is True
        assert "New Delhi" in res_india.answer_text

        res_pm = ke.query("Who is the Prime Minister of India?")
        assert res_pm.found is True
        assert "Narendra Modi" in res_pm.answer_text

    def test_is_knowledge_candidate_festival(self, ke):
        """Festival queries must pass the is_knowledge_candidate gate."""
        assert ke.is_knowledge_candidate("Ganpati kab hai?") is True
        assert ke.is_knowledge_candidate("2026 mein Diwali kab hai?") is True
        assert ke.is_knowledge_candidate("Republic Day kab hai?") is True

    def test_phrasing_variations_ganesh_chaturthi(self, ke):
        """All these phrasings must resolve to the same festival."""
        queries = [
            "Ganpati kab hai?",
            "Ganesh Chaturthi kab hai?",
            "Ganesh Utsav kab hai?",
            "Vinayaka Chaturthi kab hai?",
        ]
        current_year = datetime.now().year
        for q in queries:
            result = ke.query(q)
            assert result.found is True, f"Failed for: {q}"
            assert str(current_year) in result.answer_text, f"No year in response for: {q}"
            assert result.entity_id == "ganesh_chaturthi", f"Wrong entity for: {q}"

    def test_hinglish_mixed_query(self, ke):
        result = ke.query("Ganpati this year kab hai?")
        assert result.found is True
        assert str(datetime.now().year) in result.answer_text

    def test_next_festival_agla(self, ke):
        result = ke.query("Agla tyohaar kaunsa hai?")
        assert result.found is True


# ─────────────────────────────────────────────────────────────────────────────
# 13. Festival Store Data Integrity
# ─────────────────────────────────────────────────────────────────────────────

class TestFestivalStoreIntegrity:

    def test_ganesh_chaturthi_2026_date(self, store):
        yd = store.get_year_data("ganesh_chaturthi", 2026)
        assert yd is not None
        assert yd.start_date == date(2026, 9, 14)
        assert yd.end_date == date(2026, 9, 23)

    def test_diwali_2025_date(self, store):
        yd = store.get_year_data("diwali", 2025)
        assert yd is not None
        assert yd.start_date == date(2025, 10, 20)

    def test_republic_day_any_year(self, store):
        """Republic Day is fixed — 26 January for every year."""
        for year in [2024, 2025, 2026, 2027, 2028, 2029, 2030]:
            yd = store.get_year_data("republic_day", year)
            assert yd is not None, f"Republic Day data missing for {year}"
            assert yd.start_date.month == 1
            assert yd.start_date.day == 26

    def test_independence_day_any_year(self, store):
        """Independence Day is always 15 August."""
        for year in [2024, 2025, 2026, 2027]:
            yd = store.get_year_data("independence_day", year)
            assert yd is not None
            assert yd.start_date == date(year, 8, 15)

    def test_year_not_available_returns_none(self, store):
        yd = store.get_year_data("ganesh_chaturthi", 2099)
        assert yd is None

    def test_upcoming_festivals_after_today(self, store):
        today = datetime.now().date()
        upcoming = store.get_upcoming_festivals(today, limit=5)
        for entry, yd in upcoming:
            assert yd.start_date >= today

    def test_all_festivals_have_aliases(self, store):
        """Every festival must have at least 2 aliases for good alias coverage."""
        for fid in store.all_festival_ids():
            entry = store.get_festival(fid)
            assert entry is not None
            assert len(entry.aliases) >= 2, f"Festival {fid} has fewer than 2 aliases"
