# core/knowledge/router.py
"""
Knowledge Router & Semantic Resolver for Jarvis V2.1.
Coordinates deep question classification, phonetic STT normalization,
entity extraction, anaphora resolution, disambiguation, comparative and
rate reasoning, confidence vector evaluation, quality checks, and fast-path retrieval.
"""

from typing import Any, Dict, List, Optional, Tuple
import logging
import re

from .models import (
    ConfidenceLevel,
    ConfidenceVector,
    GKQuestionType,
    KnowledgeCategory,
    KnowledgeQueryResult,
    KnowledgeSourceType
)
from .synonyms import resolve_property_key, clean_query_text
from .entity_store import EntityStore
from .reasoning_store import ReasoningStore
from .formatter import KnowledgeResponseFormatter, is_hindi_or_hinglish
from .it import ITKnowledgeEngine, get_it_knowledge_engine, ITQuestionType
from .calendar import FestivalCalendarEngine, get_festival_calendar_engine
from .news import LiveNewsEngine, get_live_news_engine
from .pipeline import (
    GKNormalizer,
    GKQuestionClassifier,
    EntityDisambiguationEngine,
    GKEntityExtractor,
    GKReasoningEngine,
    GKConfidenceEvaluator,
    GKQualityChecker,
    UserKnowledgeStore,
    FastKnowledgePath,
    get_context_tracker
)

logger = logging.getLogger("jarvis.core.knowledge.router")


TIME_SENSITIVE_TRIGGERS = [
    "current", "abhi", "present", "today", "aaj", "latest", "taza",
    "weather", "mausam", "stock price", "stock", "share price", "news", "samachar",
    "score", "match"
]


class KnowledgeRouter:
    """Authoritative semantic query router and knowledge resolution orchestrator."""

    def __init__(
        self,
        entity_store: EntityStore,
        reasoning_store: ReasoningStore,
        it_engine: Optional[ITKnowledgeEngine] = None
    ):
        self.entity_store = entity_store
        self.reasoning_store = reasoning_store
        self.it_engine = it_engine or get_it_knowledge_engine()
        self.context_tracker = get_context_tracker()
        self.entity_extractor = GKEntityExtractor(self.entity_store, self.context_tracker)
        self.reasoning_engine = GKReasoningEngine(self.entity_store)
        self.calendar_engine = get_festival_calendar_engine()
        self.news_engine = get_live_news_engine()
        self.user_knowledge_store = UserKnowledgeStore()
        self.fast_path = FastKnowledgePath()
        self._answer_verifier = None

    @property
    def answer_verifier(self):
        """Lazy accessor to AnswerVerificationEngine."""
        if self._answer_verifier is None:
            try:
                from core.intelligence.answer_verification import get_answer_verifier
                self._answer_verifier = get_answer_verifier()
            except Exception as e:
                logger.debug("Failed to load AnswerVerificationEngine: %s", e)
        return self._answer_verifier

    def _verify_and_finalize_result(
        self,
        raw_query: str,
        result: KnowledgeQueryResult,
        is_hi: bool
    ) -> KnowledgeQueryResult:
        """
        Passes candidate answer through AnswerVerificationEngine.
        Enforces factual grounding, freshness requirements, contradiction detection,
        and multi-tier confidence calibration.
        """
        if not self.answer_verifier:
            return result

        from core.intelligence.answer_verification import AnswerSource, GroundingStatus
        src_map = {
            KnowledgeSourceType.STATIC_FACT: AnswerSource.STRUCTURED_KB,
            KnowledgeSourceType.REASONING: AnswerSource.REASONING_ENGINE,
            KnowledgeSourceType.TIME_SENSITIVE: AnswerSource.LIVE_SEARCH if result.needs_fresh_fetch else AnswerSource.STRUCTURED_KB,
            KnowledgeSourceType.UNKNOWN: AnswerSource.UNKNOWN,
        }
        mapped_src = src_map.get(result.source_type, AnswerSource.UNKNOWN)

        verif_res = self.answer_verifier.verify_answer(
            query=raw_query,
            proposed_answer=result.answer_text,
            candidate_entity=result.entity_id or result.entity_name,
            candidate_property=result.property_name,
            candidate_value=result.property_value,
            source=mapped_src,
            raw_confidence=result.confidence_score,
            is_hindi=is_hi,
            metadata=result.metadata
        )

        result.metadata["answer_verification"] = verif_res.to_dict()

        if verif_res.is_contradictory:
            result.found = False
            result.answer_text = verif_res.suggested_response or result.answer_text
            result.confidence = ConfidenceLevel.LOW
            result.confidence_score = verif_res.confidence

        elif verif_res.requires_live_data or verif_res.grounding_status == GroundingStatus.TIME_SENSITIVE_STALE:
            result.is_time_sensitive = True
            result.needs_fresh_fetch = True
            if verif_res.suggested_response:
                result.answer_text = verif_res.suggested_response

        elif verif_res.grounding_status in (GroundingStatus.UNGROUNDED, GroundingStatus.LOW_CONFIDENCE) and not result.found:
            result.answer_text = verif_res.suggested_response or result.answer_text
            result.confidence = ConfidenceLevel.LOW

        return result

    def is_knowledge_candidate(self, query: str) -> bool:
        """Quickly checks if query looks like a general or IT knowledge question."""
        lowered = query.lower().strip()

        # Capability questions MUST be rejected here (handled upstream by intent/speech-act layer)
        if any(tok in lowered for tok in ["sakte ho", "sakti ho", "sakte hain", "kar paoge", "can you", "could you", "able to"]):
            return False

        # Date, Day, and Time queries MUST be rejected here (handled upstream by TimeContext / FastPath)
        if any(w in lowered for w in ["date", "time", "din", "tarikh", "samay", "clock", "baje", "month", "year"]):
            try:
                from core.time_context import get_time_context
                if get_time_context().resolve_time_query(query):
                    return False
            except Exception:
                pass

        # Reject local Wi-Fi and network credential / status queries (handled by network plugin)
        if any(tok in lowered for tok in [
            "wifi password", "wi-fi password", "network password", "wifi ka password", "wifi ke password",
            "wifi passward", "wifi pasword", "wifi paswrd"
        ]):
            return False

        # Reject local machine / system queries (passwords, specs, local state)
        if any(tok in lowered for tok in [
            "my system", "mere system", "is system", "this system",
            "my pc", "mere pc", "is pc", "this pc",
            "my computer", "mere computer", "this computer",
            "my laptop", "mere laptop", "this laptop",
            "system ka", "system ke", "pc ka", "laptop ka"
        ]) and any(w in lowered for w in ["password", "passcode", "key", "wifi", "wi-fi", "ip", "specs", "ram", "storage"]):
            return False

        # Reject obvious imperative action commands
        action_verbs = [
            "kholo", "chalao", "band karo", "lock karo", "open", "launch", "close",
            "restart", "shutdown", "set volume", "draw", "drawing", "sketch", "banao"
        ]
        if any(f" {v} " in f" {lowered} " or lowered.startswith(v) or lowered.endswith(v) for v in action_verbs):
            if not (
                lowered.startswith("what is") or lowered.startswith("who is") or
                "kya hai" in lowered or "kya hota hai" in lowered or "explain" in lowered
            ):
                return False

        # Check IT knowledge candidate
        if self.it_engine and self.it_engine.is_it_candidate(query):
            return True

        # Check Live News candidate
        if hasattr(self, "news_engine") and self.news_engine and self.news_engine.is_news_candidate(query):
            return True

        # Check fast path cache
        if self.fast_path.get(query):
            return True

        # Positive question cues
        cues = [
            "kya hai", "kya hota hai", "kya hoti hai", "what is", "who is", "which is",
            "capital", "rajdhani", "currency", "mudra", "continent", "mahadweep",
            "why does", "why do", "why is", "kyun", "kyu", "explain",
            "kisne banaya", "kisne khoja", "full form", "formula", "stands for",
            "when was", "kab hua", "kab independent", "father of", "rashtriya", "national",
            "sabse bada", "sabse lamba", "sabse uncha", "highest", "longest", "largest",
            "larger", "bigger", "smaller", "compare", "diameter", "speed", "travel",
            "chakkar", "revolution", "population", "first prime minister", "pehle pradhan mantri",
            # Festival / calendar cues
            "kab hai", "kab padega", "kab padegi", "kab tha", "kab hoga",
            "festival", "tyohaar", "parv", "ganpati", "diwali", "holi", "navratri",
            "janmashtami", "dussehra", "raksha bandhan", "rakhi", "shivratri",
            "republic day", "independence day", "gandhi jayanti", "gantantra diwas",
            "teachers day", "childrens day", "christmas", "eid", "baisakhi", "pongal",
            "onam", "chhath puja", "agla festival", "next festival", "upcoming festival",
        ]
        return any(c in lowered for c in cues)

    def route_query(self, user_query: str) -> KnowledgeQueryResult:
        """Main routing and resolution pipeline."""
        raw_query = user_query.strip()
        if not raw_query:
            return KnowledgeQueryResult(
                found=False,
                confidence=ConfidenceLevel.LOW,
                confidence_score=0.0,
                source_type=KnowledgeSourceType.UNKNOWN,
                answer_text="Koi prashn poochhein, Boss."
            )

        # 1. Fast Knowledge Path Check (< 15ms)
        cached_result = self.fast_path.get(raw_query)
        if cached_result:
            logger.debug(f"[FAST_PATH] Cache hit for query: {raw_query!r}")
            return cached_result

        # 2. Multilingual Normalization & STT Recovery
        cleaned_text, detected_lang, norm_conf = GKNormalizer.normalize(raw_query)
        is_hi = (detected_lang in ("hi", "hinglish"))

        cached_cleaned = self.fast_path.get(cleaned_text)
        if cached_cleaned:
            logger.debug(f"[FAST_PATH] Cleaned cache hit: {cleaned_text!r}")
            return cached_cleaned

        logger.debug(f"[KNOWLEDGE_ROUTER] Cleaned: {cleaned_text!r}, Lang: {detected_lang}, Conf: {norm_conf}")

        # 3. IT Knowledge Engine Check
        if self.it_engine and self.it_engine.is_it_candidate(raw_query):
            it_res = self.it_engine.query(raw_query)
            if it_res.found and it_res.confidence >= 0.5:
                conf = ConfidenceLevel.HIGH if it_res.confidence >= 0.85 else ConfidenceLevel.MEDIUM
                res = KnowledgeQueryResult(
                    found=True,
                    confidence=conf,
                    confidence_score=it_res.confidence,
                    source_type=KnowledgeSourceType.REASONING,
                    answer_text=it_res.answer_text,
                    question_type=GKQuestionType.CROSSOVER,
                    metadata={"category": KnowledgeCategory.COMPUTER_TECH},
                    entity_name=it_res.concept_id or it_res.command_name or it_res.troubleshooting_id
                )
                self.fast_path.put(cleaned_text, res)
                return res
            elif it_res.question_type != ITQuestionType.ACTION_REQUEST and it_res.clarification_needed:
                return KnowledgeQueryResult(
                    found=False,
                    confidence=ConfidenceLevel.LOW,
                    confidence_score=it_res.confidence,
                    source_type=KnowledgeSourceType.UNKNOWN,
                    answer_text=it_res.answer_text,
                    clarification_prompt=it_res.answer_text
                )

        # 3.5 Calendar / Festival Knowledge Engine Check
        if self.calendar_engine.is_calendar_candidate(raw_query):
            cal_res = self.calendar_engine.query(raw_query)
            # Only return if found AND not a forward-to-time-context signal
            if cal_res.found:
                logger.debug(f"[CALENDAR_ENGINE] Hit for query: {raw_query!r}")
                self.fast_path.put(cleaned_text, cal_res)
                return cal_res
            # If found=False but answer_text is non-empty, it's a legitimate "date out of range" refusal
            if not cal_res.found and cal_res.answer_text and not cal_res.metadata.get("forward_to_time_context"):
                return cal_res

        # 3.6 Live News Engine Check
        if hasattr(self, "news_engine") and self.news_engine and self.news_engine.is_news_candidate(raw_query):
            news_res = self.news_engine.query(raw_query)
            if news_res.found:
                logger.debug(f"[LIVE_NEWS_ENGINE] Hit for query: {raw_query!r}")
                res = KnowledgeQueryResult(
                    found=True,
                    confidence=ConfidenceLevel.HIGH,
                    confidence_score=0.95,
                    source_type=KnowledgeSourceType.TIME_SENSITIVE,
                    answer_text=news_res.formatted_text,
                    question_type=GKQuestionType.FACTUAL,
                    is_time_sensitive=True,
                    needs_fresh_fetch=True,
                    metadata={"news_category": news_res.category.value, "spoken_text": news_res.spoken_text, "live_news": True, "news_briefing": news_res.to_briefing_dict()}
                )
                verified_res = self._verify_and_finalize_result(raw_query, res, is_hi)
                self.fast_path.put(cleaned_text, verified_res)
                return verified_res
            elif news_res.formatted_text:
                res = KnowledgeQueryResult(
                    found=False,
                    confidence=ConfidenceLevel.LOW,
                    confidence_score=0.30,
                    source_type=KnowledgeSourceType.TIME_SENSITIVE,
                    answer_text=news_res.formatted_text,
                    question_type=GKQuestionType.FACTUAL,
                    is_time_sensitive=True,
                    needs_fresh_fetch=True,
                    metadata={"news_category": news_res.category.value, "error": news_res.error}
                )
                return res

        # 4. Question Type Classification
        q_type, class_conf = GKQuestionClassifier.classify(cleaned_text)

        # 5. Polysemous Term Ambiguity & Disambiguation
        is_ambig, ambig_term, resolved_ent_id, disambig_opts = EntityDisambiguationEngine.check_ambiguity(
            cleaned_text,
            active_context_domain=self.context_tracker.last_domain
        )
        if is_ambig and ambig_term:
            prompt = EntityDisambiguationEngine.format_clarification_prompt(ambig_term, disambig_opts, is_hi)
            return KnowledgeQueryResult(
                found=False,
                confidence=ConfidenceLevel.MEDIUM,
                confidence_score=0.70,
                source_type=KnowledgeSourceType.UNKNOWN,
                answer_text=prompt,
                question_type=GKQuestionType.AMBIGUOUS,
                clarification_prompt=prompt,
                disambiguation_options=disambig_opts
            )

        # 6. Multi-Step Query Decomposition ("...aur...", "...and...")
        if q_type == GKQuestionType.MULTI_STEP:
            multi_res = self.reasoning_engine.decompose_multi_step(
                cleaned_text,
                self._resolve_single_query,
                is_hindi=is_hi
            )
            if multi_res and multi_res.found:
                self.fast_path.put(cleaned_text, multi_res)
                return multi_res

        # 7. Comparison Reasoning
        if q_type == GKQuestionType.COMPARISON:
            comp_res = self.reasoning_engine.reason_comparison(cleaned_text, is_hindi=is_hi)
            if comp_res and comp_res.found:
                self.fast_path.put(cleaned_text, comp_res)
                return comp_res

        # 8. Spatial / Directional Syllogism Reasoning
        if q_type == GKQuestionType.SPATIAL_RELATION:
            spat_res = self.reasoning_engine.reason_spatial(cleaned_text, is_hindi=is_hi)
            if spat_res and spat_res.found:
                self.fast_path.put(cleaned_text, spat_res)
                return spat_res

        # 9. Mathematical Rate Reasoning
        if q_type == GKQuestionType.MATHEMATICAL_RATE:
            math_res = self.reasoning_engine.reason_math_rate(cleaned_text, is_hindi=is_hi)
            if math_res and math_res.found:
                self.fast_path.put(cleaned_text, math_res)
                return math_res

        # 10. Time-Sensitive Inquiries
        time_res = self._check_time_sensitive(raw_query, cleaned_text, is_hi)
        if time_res is not None:
            return self._verify_and_finalize_result(raw_query, time_res, is_hi)

        # 11. Conceptual / Scientific Reasoning Store
        reasoning_res = self._check_reasoning(raw_query, cleaned_text, is_hi)
        if reasoning_res is not None:
            verified_res = self._verify_and_finalize_result(raw_query, reasoning_res, is_hi)
            self.fast_path.put(cleaned_text, verified_res)
            return verified_res

        # 12. Entity-Property Store Resolution (with Anaphora support)
        entity_prop_res = self._check_entity_property(raw_query, cleaned_text, is_hi, q_type)
        if entity_prop_res is not None:
            verified_res = self._verify_and_finalize_result(raw_query, entity_prop_res, is_hi)
            self.fast_path.put(cleaned_text, verified_res)
            return verified_res

        # 13. Unknown Question Fallback (Strict Anti-Hallucination)
        refusal_msg = (
            "Is baare mein mere paas abhi reliable jaankari uplabdh nahi hai, Boss."
            if is_hi else
            "I do not have reliable information on that right now, Boss."
        )
        conf_vector = GKConfidenceEvaluator.evaluate(
            entity_conf=0.2,
            relation_conf=0.2,
            knowledge_conf=0.0,
            classification_conf=class_conf,
            transcription_conf=norm_conf,
            language_conf=1.0,
            answer_conf=0.2
        )
        fallback_res = KnowledgeQueryResult(
            found=False,
            confidence=ConfidenceLevel.LOW,
            confidence_score=0.20,
            source_type=KnowledgeSourceType.UNKNOWN,
            answer_text=refusal_msg,
            question_type=q_type,
            confidence_vector=conf_vector,
            clarification_prompt=refusal_msg
        )
        return self._verify_and_finalize_result(raw_query, fallback_res, is_hi)

    def _resolve_single_query(self, query: str) -> KnowledgeQueryResult:
        """Helper to resolve decomposed single sub-queries."""
        cleaned, lang, _ = GKNormalizer.normalize(query)
        is_hi = (lang in ("hi", "hinglish"))

        # Check time sensitive
        ts = self._check_time_sensitive(query, cleaned, is_hi)
        if ts and ts.found:
            return ts

        # Check reasoning
        rs = self._check_reasoning(query, cleaned, is_hi)
        if rs and rs.found:
            return rs

        # Check entity property
        ep = self._check_entity_property(query, cleaned, is_hi)
        if ep and ep.found:
            return ep

        return KnowledgeQueryResult(
            found=False,
            confidence=ConfidenceLevel.LOW,
            confidence_score=0.2,
            source_type=KnowledgeSourceType.UNKNOWN,
            answer_text=query
        )

    def _check_time_sensitive(self, raw_query: str, lowered: str, is_hi: bool) -> Optional[KnowledgeQueryResult]:
        """Handles time-sensitive questions (weather, stocks, news, current leaders)."""
        is_time_sensitive = any(re.search(r"\b" + re.escape(t) + r"\b", lowered) for t in TIME_SENSITIVE_TRIGGERS)

        # Guard: Historical inquiries (first PM, first president) are static historical facts, not current leaders
        is_historical = any(h in lowered for h in ["first", "pehla", "pehle", "pratham", "former", "purv"])

        # Current Leadership: India
        if not is_historical and any(w in lowered for w in ["prime minister", "pm", "pradhan mantri"]):
            if any(c in lowered for c in ["india", "bharat", "hindustan"]) or not any(other in lowered for other in ["uk", "japan", "canada", "france"]):
                ans_text = "Bharat ke vartaman Prime Minister Shri Narendra Modi hain." if is_hi else "The current Prime Minister of India is Narendra Modi."
                return KnowledgeQueryResult(
                    found=True,
                    confidence=ConfidenceLevel.HIGH,
                    confidence_score=0.95,
                    source_type=KnowledgeSourceType.STATIC_FACT,
                    answer_text=ans_text,
                    entity_id="india",
                    entity_name="India",
                    property_name="current_prime_minister",
                    property_value="Narendra Modi",
                    is_time_sensitive=True,
                    question_type=GKQuestionType.POLITICAL
                )

        if not is_historical and any(w in lowered for w in ["president", "rashtrapati"]):
            if any(c in lowered for c in ["india", "bharat", "hindustan"]) or not any(other in lowered for other in ["usa", "america", "russia", "france"]):
                ans_text = "Bharat ki vartaman Rashtrapati Smt. Droupadi Murmu hain." if is_hi else "The current President of India is Droupadi Murmu."
                return KnowledgeQueryResult(
                    found=True,
                    confidence=ConfidenceLevel.HIGH,
                    confidence_score=0.95,
                    source_type=KnowledgeSourceType.STATIC_FACT,
                    answer_text=ans_text,
                    entity_id="india",
                    entity_name="India",
                    property_name="current_president",
                    property_value="Droupadi Murmu",
                    is_time_sensitive=True,
                    question_type=GKQuestionType.POLITICAL
                )

        if any(w in lowered for w in ["president", "rashtrapati"]) and any(c in lowered for c in ["usa", "america", "us"]):
            ans_text = "The current President of the United States is Joe Biden." if not is_hi else "America ke vartaman President Joe Biden hain."
            return KnowledgeQueryResult(
                found=True,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.95,
                source_type=KnowledgeSourceType.STATIC_FACT,
                answer_text=ans_text,
                entity_id="usa",
                entity_name="United States of America",
                property_name="current_president",
                property_value="Joe Biden",
                is_time_sensitive=True,
                question_type=GKQuestionType.POLITICAL
            )

        # Weather / Stocks / News
        if any(w in lowered for w in ["weather", "mausam"]):
            return KnowledgeQueryResult(
                found=True,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.85,
                source_type=KnowledgeSourceType.TIME_SENSITIVE,
                entity_name="Weather",
                property_name="weather",
                is_time_sensitive=True,
                needs_fresh_fetch=True,
                answer_text="Mausam ki live jaankari check karne ke liye live internet access chahiye, Boss." if is_hi else "Live weather updates require an active internet connection."
            )

        if any(w in lowered for w in ["stock price", "stock", "share price"]):
            return KnowledgeQueryResult(
                found=True,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.85,
                source_type=KnowledgeSourceType.TIME_SENSITIVE,
                entity_name="Stock Market",
                property_name="stock_price",
                is_time_sensitive=True,
                needs_fresh_fetch=True,
                answer_text="Live stock price check karne ke liye real-time financial market connection chahiye, Boss." if is_hi else "Real-time stock prices require an active market feed."
            )

        if any(w in lowered for w in ["latest news", "taza khabar", "aaj ki news", "news", "headlines", "samachar"]):
            if hasattr(self, "news_engine") and self.news_engine:
                news_res = self.news_engine.query(raw_query)
                if news_res.found:
                    return KnowledgeQueryResult(
                        found=True,
                        confidence=ConfidenceLevel.HIGH,
                        confidence_score=0.95,
                        source_type=KnowledgeSourceType.TIME_SENSITIVE,
                        answer_text=news_res.formatted_text,
                        entity_name="News",
                        property_name="news",
                        is_time_sensitive=True,
                        needs_fresh_fetch=True,
                        metadata={"news_category": news_res.category.value, "spoken_text": news_res.spoken_text, "live_news": True, "news_briefing": news_res.to_briefing_dict()}
                    )
            return KnowledgeQueryResult(
                found=True,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.85,
                source_type=KnowledgeSourceType.TIME_SENSITIVE,
                entity_name="News",
                property_name="news",
                is_time_sensitive=True,
                needs_fresh_fetch=True,
                answer_text="Latest news ke liye live feed access ki zaroorat hoti hai, Boss." if is_hi else "Latest news headlines require an active news feed."
            )

        return None

    def _check_reasoning(self, raw_query: str, lowered: str, is_hi: bool) -> Optional[KnowledgeQueryResult]:
        """Checks if query matches a conceptual or scientific explanation."""
        concept = self.reasoning_store.find_concept(lowered)
        if concept:
            wants_detail = any(w in lowered for w in ["detail", "explain in detail", "vistar se", "poora batao"])
            if wants_detail and (concept.detailed_explanation_hi or concept.detailed_explanation_en):
                ans = concept.detailed_explanation_hi if is_hi else concept.detailed_explanation_en
            else:
                ans = concept.simple_explanation_hi if is_hi else concept.simple_explanation_en

            return KnowledgeQueryResult(
                found=True,
                confidence=ConfidenceLevel.HIGH,
                confidence_score=0.92,
                source_type=KnowledgeSourceType.REASONING,
                answer_text=ans,
                concept_id=concept.concept_id,
                entity_name=concept.title,
                question_type=GKQuestionType.EXPLANATION
            )
        return None

    def _check_entity_property(
        self,
        raw_query: str,
        lowered: str,
        is_hi: bool,
        q_type: GKQuestionType = GKQuestionType.FACTUAL
    ) -> Optional[KnowledgeQueryResult]:
        """Resolves queries against structured entity store with anaphora resolution."""
        # 1. Extract candidates (longest alias matching)
        candidates = self.entity_extractor.extract_entities(lowered)

        # 2. Check anaphoric pronouns ("wahan", "unka", "iska") if no direct entities matched
        is_anaphoric = False
        if not candidates:
            anaphora_match = self.entity_extractor.resolve_anaphora(lowered)
            if anaphora_match:
                anaphora_ent, p_type = anaphora_match
                candidates = [(anaphora_ent, 0.90)]
                is_anaphoric = True
                logger.debug(f"[ANAPHORA] Resolved {p_type} pronoun to entity [{anaphora_ent.entity_id}]")

        if not candidates:
            # Fallback search
            cleaned = clean_query_text(raw_query)
            candidates = self.entity_store.search_entities(cleaned)
            if not candidates:
                candidates = self.entity_store.search_entities(lowered)

        if candidates:
            entity, match_conf = candidates[0]

            # Update conversational context tracker for future turns
            self.context_tracker.update_context(entity)

            # Step 2: Extract target property
            target_property = self.entity_extractor.extract_relation(lowered, entity)
            if not target_property:
                target_property = resolve_property_key(lowered)

            # Check entity.properties keys
            if not target_property or target_property not in entity.properties:
                for prop_k in entity.properties.keys():
                    prop_phrase = prop_k.replace("_", " ")
                    if prop_phrase in lowered or (len(prop_phrase.split()) > 1 and all(w in lowered for w in prop_phrase.split() if len(w) >= 3)):
                        target_property = prop_k
                        break

            # Property key aliases fallback (e.g. language <-> official_language)
            PROPERTY_KEY_ALIASES = {
                "language": ["official_language", "official_languages"],
                "official_language": ["language", "official_languages"],
                "official_languages": ["official_language", "language"],
                "landmarks": ["famous_monuments", "famous_landmarks", "monuments"],
                "monuments": ["famous_monuments", "famous_landmarks", "landmarks"],
                "famous_monuments": ["famous_landmarks", "landmarks", "monuments"],
                "famous_landmarks": ["famous_monuments", "landmarks", "monuments"],
                "inventor": ["creator", "developed_by", "founded_by", "builder", "started_by", "architect"],
                "creator": ["inventor", "developed_by", "builder"],
                "builder": ["inventor", "creator", "architect"],
                "height": ["elevation", "altitude"],
                "elevation": ["height", "altitude"],
                "length": ["longest"],
                "speed": ["speed_of_light"],
                "temperature": ["avg_temperature", "surface_temperature"],
                "moons_count": ["moons", "satellites_count"],
            }
            if target_property and target_property not in entity.properties:
                for alias_k in PROPERTY_KEY_ALIASES.get(target_property, []):
                    if alias_k in entity.properties:
                        target_property = alias_k
                        break

            # Also check user_knowledge_store for custom entity properties
            if not target_property or target_property not in entity.properties:
                for uf in self.user_knowledge_store.list_facts_for_entity(entity.entity_id):
                    prop_phrase = uf.property_name.replace("_", " ")
                    if prop_phrase in lowered or (len(prop_phrase.split()) > 1 and all(w in lowered for w in prop_phrase.split() if len(w) >= 3)):
                        target_property = uf.property_name
                        break

            # Handle person role inquiries (e.g. "Father of the nation kaun hain?")
            if entity.entity_type == "person" and target_property == "father_of_nation":
                ans_text = f"Bharat ke Father of the Nation {entity.canonical_name} hain." if is_hi else f"The Father of the Nation is {entity.canonical_name}."
                return KnowledgeQueryResult(
                    found=True,
                    confidence=ConfidenceLevel.HIGH,
                    confidence_score=match_conf,
                    source_type=KnowledgeSourceType.STATIC_FACT,
                    answer_text=ans_text,
                    entity_id=entity.entity_id,
                    entity_name=entity.canonical_name,
                    property_name=target_property,
                    property_value=entity.canonical_name,
                    question_type=q_type
                )

            # If property found in authoritative entity store
            if target_property and target_property in entity.properties:
                val = entity.properties[target_property]
                conf = ConfidenceLevel.HIGH if match_conf >= 0.85 else ConfidenceLevel.MEDIUM
                formatted_ans = KnowledgeResponseFormatter.format(
                    KnowledgeQueryResult(
                        found=True,
                        confidence=conf,
                        confidence_score=match_conf,
                        source_type=KnowledgeSourceType.STATIC_FACT,
                        entity_id=entity.entity_id,
                        entity_name=entity.canonical_name,
                        property_name=target_property,
                        property_value=val,
                        question_type=q_type
                    ),
                    raw_query
                )
                # Verify answer quality
                is_valid, sanitized_ans = GKQualityChecker.verify_answer(
                    KnowledgeQueryResult(found=True, confidence=conf, confidence_score=match_conf, source_type=KnowledgeSourceType.STATIC_FACT, answer_text=formatted_ans, question_type=q_type),
                    raw_query
                )
                conf_vector = GKConfidenceEvaluator.evaluate(
                    entity_conf=match_conf,
                    relation_conf=0.95,
                    knowledge_conf=1.0,
                    classification_conf=0.90,
                    transcription_conf=0.95,
                    language_conf=1.0,
                    answer_conf=1.0
                )
                return KnowledgeQueryResult(
                    found=True,
                    confidence=conf,
                    confidence_score=match_conf,
                    source_type=KnowledgeSourceType.STATIC_FACT,
                    answer_text=sanitized_ans,
                    entity_id=entity.entity_id,
                    entity_name=entity.canonical_name,
                    property_name=target_property,
                    property_value=val,
                    question_type=q_type,
                    confidence_vector=conf_vector
                )

            # Check isolated User Knowledge Store (never pollutes verified entity properties)
            if target_property:
                user_fact = self.user_knowledge_store.get_fact(entity.entity_id, target_property)
                if user_fact:
                    val = user_fact.value
                    if is_hi:
                        ans_text = f"Aapke bataye anusar, {entity.canonical_name} ka {target_property.replace('_', ' ')} {val} hai."
                    else:
                        ans_text = f"According to your notes, the {target_property.replace('_', ' ')} of {entity.canonical_name} is {val}."
                    return KnowledgeQueryResult(
                        found=True,
                        confidence=ConfidenceLevel.MEDIUM,
                        confidence_score=user_fact.confidence,
                        source_type=KnowledgeSourceType.USER_TAUGHT,
                        answer_text=ans_text,
                        entity_id=entity.entity_id,
                        entity_name=entity.canonical_name,
                        property_name=target_property,
                        property_value=val,
                        question_type=q_type
                    )

            # Acronym full_form inference
            has_conflicting_attr_request = any(
                w in lowered for w in [
                    "password", "passcode", "key", "secret", "price", "speed",
                    "creator", "owner", "location", "my system", "mere system",
                    "system ka", "pc ka"
                ]
            )
            if (
                entity.entity_type == "acronym"
                and "full_form" in entity.properties
                and not has_conflicting_attr_request
                and (
                    target_property in (None, "full_form", "meaning", "stands_for")
                    or any(c in lowered for c in ["full form", "stands for", "meaning", "matlab", "ka arth", "what is", "kya hai", "kya hota"])
                )
            ):
                val = entity.properties["full_form"]
                conf = ConfidenceLevel.HIGH if match_conf >= 0.85 else ConfidenceLevel.MEDIUM
                formatted_ans = KnowledgeResponseFormatter.format(
                    KnowledgeQueryResult(
                        found=True,
                        confidence=conf,
                        confidence_score=match_conf,
                        source_type=KnowledgeSourceType.STATIC_FACT,
                        entity_id=entity.entity_id,
                        entity_name=entity.canonical_name,
                        property_name="full_form",
                        property_value=val,
                        question_type=q_type
                    ),
                    raw_query
                )
                return KnowledgeQueryResult(
                    found=True,
                    confidence=conf,
                    confidence_score=match_conf,
                    source_type=KnowledgeSourceType.STATIC_FACT,
                    answer_text=formatted_ans,
                    entity_id=entity.entity_id,
                    entity_name=entity.canonical_name,
                    property_name="full_form",
                    property_value=val,
                    question_type=q_type
                )

            # Entity Summary Fallback ("What is Mount Everest?", "India ke baare mein batao")
            if match_conf >= 0.80 and (entity.summary_hi or entity.summary_en) and not has_conflicting_attr_request:
                summary = entity.summary_hi if is_hi else entity.summary_en
                return KnowledgeQueryResult(
                    found=True,
                    confidence=ConfidenceLevel.HIGH,
                    confidence_score=match_conf,
                    source_type=KnowledgeSourceType.STATIC_FACT,
                    answer_text=summary,
                    entity_id=entity.entity_id,
                    entity_name=entity.canonical_name,
                    question_type=GKQuestionType.DEFINITION
                )

        # Cross-reference for generic questions like "longest river", "highest mountain"
        target_property = resolve_property_key(lowered)
        if target_property:
            for ent_id, ent in self.entity_store.entities.items():
                if target_property in ent.properties:
                    type_matched = bool(re.search(r"\b" + re.escape(ent.entity_type) + r"\b", lowered))
                    cat_matched = any(re.search(r"\b" + re.escape(cat.value) + r"\b", lowered) for cat in ent.categories)
                    alias_matched = any(re.search(r"\b" + re.escape(alias) + r"\b", lowered) for alias in ent.aliases)
                    if type_matched or cat_matched or alias_matched:
                        val = ent.properties[target_property]
                        formatted_ans = KnowledgeResponseFormatter.format(
                            KnowledgeQueryResult(
                                found=True,
                                confidence=ConfidenceLevel.HIGH,
                                confidence_score=0.90,
                                source_type=KnowledgeSourceType.STATIC_FACT,
                                entity_id=ent.entity_id,
                                entity_name=ent.canonical_name,
                                property_name=target_property,
                                property_value=val,
                                question_type=q_type
                            ),
                            raw_query
                        )
                        return KnowledgeQueryResult(
                            found=True,
                            confidence=ConfidenceLevel.HIGH,
                            confidence_score=0.90,
                            source_type=KnowledgeSourceType.STATIC_FACT,
                            answer_text=formatted_ans,
                            entity_id=ent.entity_id,
                            entity_name=ent.canonical_name,
                            property_name=target_property,
                            property_value=val,
                            question_type=q_type
                        )

        return None
