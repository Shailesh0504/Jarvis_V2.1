# core/intelligence/answer_verification.py
"""
Answer Verification & Factual Grounding Engine for Jarvis V2.1 (`intelligence.answer_verification`).

Authoritative answer verification layer that inspects proposed factual and conversational answers
BEFORE they are spoken to the user:
- Answer Source Attribution: STRUCTURED_KB, REASONING_ENGINE, IT_KNOWLEDGE, CALENDAR_ENGINE,
  SYSTEM_TELEMETRY, LIVE_SEARCH, USER_PROFILE_KB, LLM_FALLBACK, UNVERIFIED_HALLUCINATION.
- Factual Grounding: Triple cross-checking (entity, property, value) against authoritative stores.
- Freshness & Currency: Detects time-sensitive leadership, live weather/markets, and tech versions.
- Contradiction Detection: Flags conflicting knowledge, false claims, and superseded data.
- Confidence Gating: Enforces the 'galat answer se better clarification/refusal' principle via
  multi-tier confidence scoring (HIGH >= 0.85, MEDIUM >= 0.60, LOW < 0.60).
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
import threading
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.intelligence.confidence import (
    ConfidenceTier,
    ConfidenceAction,
    InterpretationConfidence,
    ConfidenceEngine,
    get_confidence_engine
)

logger = logging.getLogger("jarvis.intelligence.answer_verification")


class AnswerSource(str, Enum):
    """Authoritative answer provenance / source type."""
    STRUCTURED_KB = "STRUCTURED_KB"              # Static facts from EntityStore (capitals, currencies, elements)
    REASONING_ENGINE = "REASONING_ENGINE"        # Conceptual / scientific models from ReasoningStore
    IT_KNOWLEDGE = "IT_KNOWLEDGE"                # Enterprise & systems admin store (Windows/Azure/Networking)
    CALENDAR_ENGINE = "CALENDAR_ENGINE"          # Festival & holiday calendar engine
    SYSTEM_TELEMETRY = "SYSTEM_TELEMETRY"        # Live OS telemetry (time, battery, specs, RAM, processes)
    USER_PROFILE_KB = "USER_PROFILE_KB"          # Explicit user-stored profile facts (MemoryManager)
    LIVE_SEARCH = "LIVE_SEARCH"                  # Live search / external real-time feed
    LLM_FALLBACK = "LLM_FALLBACK"                # Generative LLM response
    UNVERIFIED_HALLUCINATION = "UNVERIFIED"      # Ungrounded assertion / hallucination risk
    UNKNOWN = "UNKNOWN"                          # Unidentified source


class GroundingStatus(str, Enum):
    """Authoritative factual grounding assessment status."""
    GROUNDED = "GROUNDED"                        # Verified against authoritative ground truth
    UNGROUNDED = "UNGROUNDED"                    # Cannot be substantiated in verified knowledge; hallucination risk
    TIME_SENSITIVE_STALE = "TIME_SENSITIVE_STALE" # Fact is time-dependent and requires live fetch or currency caveat
    CONTRADICTORY = "CONTRADICTORY"              # Proposed answer contradicts known ground truth in KB
    LOW_CONFIDENCE = "LOW_CONFIDENCE"            # Insufficient confidence (< 0.60); mandates clarification or refusal


@dataclass
class AnswerVerificationResult:
    """
    Structured outcome of an answer verification evaluation.
    Enforces strict anti-hallucination and factual truthfulness.
    """
    verified: bool                               # True only if grounded, uncontradicted, and sufficiently confident
    grounding_status: GroundingStatus            # GROUNDED, UNGROUNDED, TIME_SENSITIVE_STALE, CONTRADICTORY, LOW_CONFIDENCE
    source: AnswerSource                         # Verified source of the answer
    confidence: float                            # Calibrated confidence score (0.0 to 1.0)
    confidence_tier: ConfidenceTier              # HIGH, MEDIUM, LOW
    requires_live_data: bool = False             # Whether query demands real-time internet / telemetry access
    freshness_reason: Optional[str] = None       # Explanation if live data or currency check is required
    is_contradictory: bool = False               # True if answer conflicts with known facts
    contradiction_details: Optional[str] = None  # Specifics of the conflict
    grounded_fact: Optional[str] = None          # Authoritative ground-truth fact if available
    suggested_response: Optional[str] = None     # Calibrated, safe, or corrected answer text
    refusal_reason: Optional[str] = None         # Reason for refusal if ungrounded or low confidence
    metadata: Dict[str, Any] = field(default_factory=dict)
    verified_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        """Serializes verification result into a structured dictionary."""
        return {
            "verified": self.verified,
            "grounding_status": self.grounding_status.value if hasattr(self.grounding_status, "value") else str(self.grounding_status),
            "source": self.source.value if hasattr(self.source, "value") else str(self.source),
            "confidence": round(self.confidence, 3),
            "confidence_tier": self.confidence_tier.value if hasattr(self.confidence_tier, "value") else str(self.confidence_tier),
            "requires_live_data": self.requires_live_data,
            "freshness_reason": self.freshness_reason,
            "is_contradictory": self.is_contradictory,
            "contradiction_details": self.contradiction_details,
            "grounded_fact": self.grounded_fact,
            "suggested_response": self.suggested_response,
            "refusal_reason": self.refusal_reason,
            "metadata": dict(self.metadata),
            "verified_at": self.verified_at
        }


class AnswerVerificationEngine:
    """
    Authoritative Answer Verification & Factual Grounding Engine (`intelligence.answer_verification`).
    
    Acts as the knowledge-domain counterpart to `execution.verification`.
    Verifies that conversational and factual answers are grounded in verifiable sources,
    flags time-sensitive queries requiring fresh live data, catches contradictory claims,
    and gates low-confidence answers into transparent refusals rather than hallucinations.
    """

    _instance: Optional["AnswerVerificationEngine"] = None
    _lock = threading.Lock()

    # Domain triggers for time sensitivity / freshness requirements
    FRESHNESS_TRIGGERS: Dict[str, List[str]] = {
        "weather": [
            "weather", "mausam", "temperature", "tāpmān", "tapman", "forecast", "barish", "rain",
            "garmi", "sardi", "humidity", "hawa", "wind speed"
        ],
        "finance": [
            "stock price", "share price", "stock", "nifty", "sensex", "crypto", "bitcoin",
            "gold rate", "silver rate", "exchange rate", "dollar rate", "rupee rate"
        ],
        "sports_events": [
            "score", "match", "live score", "cricket score", "ipl score", "football score",
            "wicket", "who won the match", "match kaun jeeta"
        ],
        "news": [
            "news", "samachar", "khabar", "breaking news", "latest news", "taza khabar",
            "headlines", "aaj ki news"
        ],
        "leadership_dynamic": [
            "prime minister", "pradhan mantri", "pm", "chief minister", "cm",
            "president", "rashtrapati", "governor", "ceo",
            "current prime minister", "vartaman pradhan mantri", "current pm", "aaj ka pm",
            "current president", "vartaman rashtrapati", "current chief minister", "vartaman cm",
            "current governor", "current ceo"
        ],
        "tech_releases": [
            "latest version of windows", "windows ka latest version", "latest windows release",
            "latest version of python", "python ka latest version", "latest ios", "latest android",
            "latest macos", "latest release", "latest update", "naya version"
        ]
    }

    # Known stable tech version baselines (for grounding tech version inquiries)
    KNOWN_TECH_BASELINES: Dict[str, Dict[str, Any]] = {
        "windows": {
            "canonical_name": "Windows",
            "latest_major": "Windows 11",
            "current_stable": "Windows 11 (Version 23H2 / 24H2)",
            "supported_families": ["Windows 11", "Windows 10", "Windows Server 2022", "Windows Server 2019"],
            "disclaimer_en": "Windows 11 is the current major release of Windows for consumers.",
            "disclaimer_hi": "Consumers ke liye Windows ka vartaman major release Windows 11 hai."
        },
        "python": {
            "canonical_name": "Python",
            "latest_major": "Python 3.12 / 3.13",
            "current_stable": "Python 3.12",
            "supported_families": ["Python 3.12", "Python 3.11", "Python 3.10"],
            "disclaimer_en": "Python 3.12 / 3.13 is the current production release line.",
            "disclaimer_hi": "Python ka vartaman production release line Python 3.12 / 3.13 hai."
        }
    }

    def __init__(self, confidence_engine: Optional[ConfidenceEngine] = None):
        self.confidence_engine = confidence_engine or get_confidence_engine()
        self._entity_store = None
        self._reasoning_store = None
        self._it_engine = None
        self._calendar_engine = None

    @classmethod
    def get_instance(cls) -> "AnswerVerificationEngine":
        """Thread-safe singleton accessor."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    # Lazy accessors to knowledge stores to prevent circular imports
    @property
    def entity_store(self):
        if self._entity_store is None:
            try:
                from core.knowledge.entity_store import EntityStore
                self._entity_store = EntityStore()
            except Exception as e:
                logger.debug("EntityStore load failed: %s", e)
        return self._entity_store

    @property
    def reasoning_store(self):
        if self._reasoning_store is None:
            try:
                from core.knowledge.reasoning_store import ReasoningStore
                self._reasoning_store = ReasoningStore()
            except Exception as e:
                logger.debug("ReasoningStore load failed: %s", e)
        return self._reasoning_store

    @property
    def it_engine(self):
        if self._it_engine is None:
            try:
                from core.knowledge.it import get_it_knowledge_engine
                self._it_engine = get_it_knowledge_engine()
            except Exception as e:
                logger.debug("ITKnowledgeEngine load failed: %s", e)
        return self._it_engine

    @property
    def calendar_engine(self):
        if self._calendar_engine is None:
            try:
                from core.knowledge.calendar import get_festival_calendar_engine
                self._calendar_engine = get_festival_calendar_engine()
            except Exception as e:
                logger.debug("FestivalCalendarEngine load failed: %s", e)
        return self._calendar_engine

    def _lookup_entity(self, key: str) -> Optional[Any]:
        """Safely looks up an entity by entity_id, alias, or search."""
        if not self.entity_store or not key:
            return None
        cleaned = key.lower().strip()
        if cleaned in self.entity_store.entities:
            return self.entity_store.entities[cleaned]
        alias_match = self.entity_store.get_entity_by_alias(cleaned)
        if alias_match:
            return alias_match
        search_res = self.entity_store.search_entities(cleaned)
        if search_res:
            return search_res[0][0]
        return None

    # -------------------------------------------------------------------------
    # 1. Primary Verification Entrypoint
    # -------------------------------------------------------------------------
    def verify_answer(
        self,
        query: str,
        proposed_answer: str,
        candidate_entity: Optional[str] = None,
        candidate_property: Optional[str] = None,
        candidate_value: Any = None,
        source: Optional[AnswerSource] = None,
        raw_confidence: float = 0.85,
        is_hindi: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> AnswerVerificationResult:
        """
        Main authoritative verification method.
        Evaluates source attribution, freshness requirement, factual grounding,
        contradiction detection, and multi-tier confidence calibration.
        """
        clean_query = str(query or "").strip()
        clean_answer = str(proposed_answer or "").strip()
        meta = dict(metadata or {})

        # Step 1: Attribute Answer Source
        attributed_source = source or self.attribute_source(
            clean_query, clean_answer, candidate_entity, candidate_property
        )

        # Step 2: Freshness / Time-Sensitivity Assessment
        requires_fresh, trigger_term, fresh_category = self.check_freshness_requirement(clean_query)

        # Step 3: Contradiction Detection
        is_contradictory, contra_detail = False, None
        if candidate_entity and candidate_property and candidate_value is not None:
            is_contradictory, contra_detail = self.detect_contradictions(
                entity_id=candidate_entity,
                property_name=candidate_property,
                proposed_value=str(candidate_value)
            )

        # Step 4: Factual Grounding Evaluation
        grounded_status = GroundingStatus.GROUNDED
        grounded_fact_str = None

        if is_contradictory:
            grounded_status = GroundingStatus.CONTRADICTORY
        elif requires_fresh:
            # Check if this time-sensitive inquiry has a grounded current attribute or requires live data
            if fresh_category == "news":
                if attributed_source == AnswerSource.LIVE_SEARCH and clean_answer and not any(w in clean_answer for w in ["live internet feed", "active news feed", "uplabdh nahi hai"]):
                    grounded_status = GroundingStatus.GROUNDED
                    grounded_fact_str = "Google News Live Feed"
                    meta["live_news_verified"] = True
                else:
                    grounded_status = GroundingStatus.TIME_SENSITIVE_STALE
            elif fresh_category in ("weather", "finance", "sports_events"):
                # Live environmental / market states strictly require live internet feed
                grounded_status = GroundingStatus.TIME_SENSITIVE_STALE
            elif fresh_category == "tech_releases":
                # Check tech release baselines
                tech_match = self._check_tech_baseline(clean_query, clean_answer)
                if tech_match:
                    grounded_status = GroundingStatus.GROUNDED
                    grounded_fact_str = tech_match.get("current_stable")
                    meta["tech_baseline"] = tech_match
                else:
                    grounded_status = GroundingStatus.TIME_SENSITIVE_STALE
            elif fresh_category == "leadership_dynamic":
                # Leadership query: verify if candidate value matches known current leadership
                is_grounded_lead, lead_val = self._verify_leadership_grounding(clean_query, clean_answer)
                if is_grounded_lead:
                    grounded_status = GroundingStatus.GROUNDED
                    grounded_fact_str = lead_val
                    meta["leadership_verified"] = True
                else:
                    grounded_status = GroundingStatus.TIME_SENSITIVE_STALE
        else:
            # Static facts / conceptual knowledge grounding
            is_grounded, val = self.verify_grounding(
                candidate_entity or "", candidate_property or "", candidate_value or clean_answer
            )
            if not is_grounded and attributed_source not in (
                AnswerSource.STRUCTURED_KB, AnswerSource.REASONING_ENGINE,
                AnswerSource.IT_KNOWLEDGE, AnswerSource.CALENDAR_ENGINE,
                AnswerSource.SYSTEM_TELEMETRY
            ):
                grounded_status = GroundingStatus.UNGROUNDED
            elif is_grounded:
                grounded_fact_str = str(val) if val is not None else None

        # Step 5: Confidence Calibration via ConfidenceEngine
        # Map grounding status to confidence score
        calibrated_conf = self._calibrate_confidence(
            raw_confidence=raw_confidence,
            grounding_status=grounded_status,
            source=attributed_source,
            requires_fresh=requires_fresh
        )

        # Evaluate against ConfidenceEngine 3-tier action gating
        conf_record = self.confidence_engine.evaluate_answer_turn(
            query=clean_query,
            intent_conf=0.90,
            entity_conf=0.90 if candidate_entity else 0.70,
            context_conf=0.75,
            answer_conf=calibrated_conf,
            is_hallucination_risk=(grounded_status in (GroundingStatus.UNGROUNDED, GroundingStatus.CONTRADICTORY)),
            category=str(meta.get("category", "general_knowledge"))
        )

        tier = conf_record.tier
        verified = (
            tier == ConfidenceTier.HIGH
            and grounded_status == GroundingStatus.GROUNDED
            and not is_contradictory
        )

        # Determine suggested response or refusal
        suggested_resp = clean_answer
        refusal_reason = None

        if is_contradictory:
            verified = False
            refusal_reason = f"Answer contradicts authoritative knowledge: {contra_detail}"
            suggested_resp = self._format_contradiction_resolution(clean_query, contra_detail, is_hindi)
        elif grounded_status == GroundingStatus.TIME_SENSITIVE_STALE:
            verified = False
            refusal_reason = f"Query requires fresh live data ({fresh_category}: '{trigger_term}'). Static guess rejected."
            suggested_resp = self._format_fresh_data_requirement(fresh_category or "live", is_hindi)
        elif grounded_status == GroundingStatus.UNGROUNDED or tier == ConfidenceTier.LOW:
            verified = False
            grounded_status = GroundingStatus.LOW_CONFIDENCE if tier == ConfidenceTier.LOW else GroundingStatus.UNGROUNDED
            refusal_reason = f"Answer not grounded in authoritative knowledge (confidence {calibrated_conf:.2f} < 0.60)."
            suggested_resp = (
                "Is baare mein mere paas abhi reliable verified jaankari uplabdh nahi hai, Boss."
                if is_hindi else
                "I do not have reliable verified information on that right now, Boss."
            )

        logger.info(
            "[ANSWER_VERIFICATION] query=%r verified=%s status=%s source=%s conf=%.2f tier=%s",
            clean_query, verified, grounded_status.value, attributed_source.value, calibrated_conf, tier.value
        )

        return AnswerVerificationResult(
            verified=verified,
            grounding_status=grounded_status,
            source=attributed_source,
            confidence=round(calibrated_conf, 3),
            confidence_tier=tier,
            requires_live_data=requires_fresh,
            freshness_reason=f"{fresh_category} trigger: '{trigger_term}'" if requires_fresh else None,
            is_contradictory=is_contradictory,
            contradiction_details=contra_detail,
            grounded_fact=grounded_fact_str,
            suggested_response=suggested_resp,
            refusal_reason=refusal_reason,
            metadata=meta
        )

    # -------------------------------------------------------------------------
    # 2. Source Attribution
    # -------------------------------------------------------------------------
    def attribute_source(
        self,
        query: str,
        answer: str,
        candidate_entity: Optional[str] = None,
        candidate_property: Optional[str] = None
    ) -> AnswerSource:
        """Determines the authoritative provenance / source of the answer."""
        q_low = query.lower()
        ans_low = answer.lower()

        # Check Telemetry / Local system
        if any(w in q_low for w in ["time", "samay", "date", "tarikh", "battery", "ram", "cpu", "specs"]):
            return AnswerSource.SYSTEM_TELEMETRY

        # Check Calendar Engine
        if self.calendar_engine and self.calendar_engine.is_calendar_candidate(query):
            return AnswerSource.CALENDAR_ENGINE

        # Check IT Knowledge Engine
        if self.it_engine and self.it_engine.is_it_candidate(query):
            return AnswerSource.IT_KNOWLEDGE

        # Check Reasoning Store
        if self.reasoning_store and self.reasoning_store.find_concept(q_low):
            return AnswerSource.REASONING_ENGINE

        # Check Structured EntityStore
        if candidate_entity and self.entity_store and candidate_entity in self.entity_store.entities:
            return AnswerSource.STRUCTURED_KB

        if self.entity_store:
            ent = self._lookup_entity(q_low)
            if ent:
                return AnswerSource.STRUCTURED_KB

        # Web / Live Search keywords
        if any(w in ans_low for w in ["http://", "https://", "search result", "google", "bing"]):
            return AnswerSource.LIVE_SEARCH

        # Check for empty / unknown answer
        if not answer or any(w in ans_low for w in ["reliable jaankari nahi", "reliable information", "not sure", "don't know"]):
            return AnswerSource.UNKNOWN

        # Default fallback
        return AnswerSource.UNVERIFIED_HALLUCINATION

    # -------------------------------------------------------------------------
    # 3. Freshness & Time-Sensitivity Assessment
    # -------------------------------------------------------------------------
    def check_freshness_requirement(self, query: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Determines whether the inquiry demands live, real-time, or fresh data.
        Returns: (requires_fresh_data, matched_trigger_term, category_name)
        """
        q_low = query.lower().strip()

        # Guard: Historical inquiries ("who was first prime minister", "first president") are static facts
        is_historical = any(w in q_low for w in ["first", "pehla", "pehle", "pratham", "former", "purv", "itihaas", "history"])
        if is_historical:
            return False, None, None

        # Check each freshness category
        for category, triggers in self.FRESHNESS_TRIGGERS.items():
            for trigger in triggers:
                # Use word boundary search to prevent partial token collisions
                pattern = r"\b" + re.escape(trigger) + r"\b"
                if re.search(pattern, q_low):
                    return True, trigger, category

        # Generic temporal markers ("today", "aaj", "current", "abhi", "latest", "taza")
        generic_markers = ["current", "abhi", "present", "today", "aaj", "latest", "taza"]
        for marker in generic_markers:
            if re.search(r"\b" + re.escape(marker) + r"\b", q_low):
                # Distinguish general questions containing "current" (like current electric current)
                if "electric" in q_low or "circuits" in q_low or "charge" in q_low:
                    continue
                return True, marker, "generic_time_sensitive"

        return False, None, None

    # -------------------------------------------------------------------------
    # 4. Factual Grounding & Cross-Checking
    # -------------------------------------------------------------------------
    def verify_grounding(
        self,
        entity_id: str,
        property_name: str,
        proposed_value: Any
    ) -> Tuple[bool, Optional[Any]]:
        """
        Validates whether the triple (entity_id, property_name, proposed_value)
        is grounded in the authoritative EntityStore.
        """
        if not self.entity_store or not entity_id:
            return False, None

        ent = self._lookup_entity(entity_id)
        if not ent:
            return False, None

        if not property_name:
            # If only entity is checked, verify entity existence
            return True, ent.canonical_name

        clean_prop = property_name.lower().strip()
        if clean_prop in ent.properties:
            actual_val = ent.properties[clean_prop]
            # Check string match
            if str(proposed_value).lower().strip() == str(actual_val).lower().strip():
                return True, actual_val
            # Substring match for list or extended values
            if str(actual_val).lower().strip() in str(proposed_value).lower().strip():
                return True, actual_val
            if str(proposed_value).lower().strip() in str(actual_val).lower().strip():
                return True, actual_val
            return False, actual_val

        return False, None

    # -------------------------------------------------------------------------
    # 5. Contradiction & Conflict Detection
    # -------------------------------------------------------------------------
    def detect_contradictions(
        self,
        entity_id: str,
        property_name: str,
        proposed_value: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Detects if proposed_value directly contradicts ground truth in EntityStore.
        e.g., entity='india', property='capital', proposed_value='Mumbai' -> Contradiction!
        """
        if not self.entity_store or not entity_id or not property_name:
            return False, None

        ent = self._lookup_entity(entity_id)
        if not ent:
            return False, None

        clean_prop = property_name.lower().strip()
        if clean_prop in ent.properties:
            actual_val = str(ent.properties[clean_prop]).strip()
            prop_val_clean = str(proposed_value).strip()

            # If both are non-empty and clearly distinct
            if actual_val.lower() != prop_val_clean.lower():
                # Disallow known opposing capitals, currencies, symbols
                if clean_prop in ("capital", "currency", "symbol", "continent", "state_capital"):
                    detail = (
                        f"Expected {clean_prop} for '{ent.canonical_name}' is '{actual_val}', "
                        f"but proposed answer asserted '{prop_val_clean}'."
                    )
                    logger.warning("[CONTRADICTION_DETECTED] %s", detail)
                    return True, detail

        return False, None

    # -------------------------------------------------------------------------
    # 6. Specialized Grounding Handlers
    # -------------------------------------------------------------------------
    def _verify_leadership_grounding(self, query: str, answer: str) -> Tuple[bool, Optional[str]]:
        """Verifies leadership queries like 'India ka PM kaun hai?'."""
        q_low = query.lower()
        ans_low = answer.lower()

        # India Prime Minister
        if any(w in q_low for w in ["pm", "prime minister", "pradhan mantri"]):
            if any(c in q_low for c in ["india", "bharat", "hindustan"]) or not any(o in q_low for o in ["uk", "japan", "canada"]):
                if "narendra modi" in ans_low or "modi" in ans_low:
                    return True, "Narendra Modi"
                return False, None

        # India President
        if any(w in q_low for w in ["president", "rashtrapati"]):
            if any(c in q_low for c in ["india", "bharat", "hindustan"]) or not any(o in q_low for o in ["usa", "america", "russia"]):
                if "droupadi murmu" in ans_low or "murmu" in ans_low:
                    return True, "Droupadi Murmu"
                return False, None

        # USA President
        if any(w in q_low for w in ["president", "rashtrapati"]) and any(c in q_low for c in ["usa", "america", "us"]):
            if "joe biden" in ans_low or "biden" in ans_low:
                return True, "Joe Biden"
            return False, None

        return False, None

    def _check_tech_baseline(self, query: str, answer: str) -> Optional[Dict[str, Any]]:
        """Verifies if a software/OS version question aligns with known stable releases."""
        q_low = query.lower()
        ans_low = answer.lower()

        if "windows" in q_low:
            baseline = self.KNOWN_TECH_BASELINES["windows"]
            if "11" in ans_low or "windows 11" in ans_low:
                return baseline
            # If answer claims an obsolete or unsupported version as latest (e.g. Windows 10, 7, XP)
            if any(obs in ans_low for obs in ["windows 10", "windows 7", "windows 8", "windows xp"]):
                logger.warning("[TECH_VERSION_OBSOLETE] Answer asserted obsolete Windows version as latest.")
                return None
            return baseline

        if "python" in q_low:
            baseline = self.KNOWN_TECH_BASELINES["python"]
            if any(v in ans_low for v in ["3.12", "3.13", "3.11"]):
                return baseline
            return baseline

        return None

    # -------------------------------------------------------------------------
    # 7. Helper Formatters & Confidence Calibration
    # -------------------------------------------------------------------------
    def _calibrate_confidence(
        self,
        raw_confidence: float,
        grounding_status: GroundingStatus,
        source: AnswerSource,
        requires_fresh: bool
    ) -> float:
        """Calibrates confidence based on grounding status and source reliability."""
        base = max(0.0, min(1.0, float(raw_confidence)))

        if grounding_status == GroundingStatus.CONTRADICTORY:
            return 0.10

        if grounding_status == GroundingStatus.TIME_SENSITIVE_STALE:
            return 0.50

        if grounding_status == GroundingStatus.UNGROUNDED:
            return min(base, 0.40)

        # Grounded rewards
        if grounding_status == GroundingStatus.GROUNDED:
            if source in (AnswerSource.STRUCTURED_KB, AnswerSource.SYSTEM_TELEMETRY, AnswerSource.CALENDAR_ENGINE, AnswerSource.LIVE_SEARCH):
                return max(base, 0.95)
            if source in (AnswerSource.REASONING_ENGINE, AnswerSource.IT_KNOWLEDGE):
                return max(base, 0.90)
            return max(base, 0.85)

        return base

    def _format_contradiction_resolution(self, query: str, detail: Optional[str], is_hindi: bool) -> str:
        """Formats conversational response when contradiction is caught."""
        if is_hindi:
            return f"Maaf kijiye Boss, ye jaankari sahi nahi hai. {detail or 'Fact verify karne par contradiction mila.'}"
        return f"Apologies Boss, that information is incorrect. {detail or 'A contradiction was detected during verification.'}"

    def _format_fresh_data_requirement(self, category: str, is_hindi: bool) -> str:
        """Formats transparent live data requirement refusal."""
        if category == "weather":
            return "Mausam ki live jaankari check karne ke liye live internet access chahiye, Boss." if is_hindi else "Live weather updates require an active internet connection."
        if category == "finance":
            return "Live stock / financial market rates check karne ke liye real-time feed chahiye, Boss." if is_hindi else "Real-time financial market updates require an active feed."
        if category == "sports_events":
            return "Live match score check karne ke liye real-time internet connection chahiye, Boss." if is_hindi else "Live match scores require an active sports feed."
        if category == "news":
            return "Latest news headlines check karne ke liye live internet feed chahiye, Boss." if is_hindi else "Latest news headlines require an active news feed."
        if category == "tech_releases":
            return "Software ke latest version updates verify karne ke liye live network access chahiye, Boss." if is_hindi else "Verifying the latest software releases requires active network access."
        return "Is time-sensitive query ke liye live internet access ki zaroorat hai, Boss." if is_hindi else "This time-sensitive inquiry requires live internet access."


def get_answer_verifier() -> AnswerVerificationEngine:
    """Authoritative singleton getter for AnswerVerificationEngine."""
    return AnswerVerificationEngine.get_instance()
