# brain/conversation/model.py
"""
Human Conversation Model for Jarvis V2.

Synthesizes 7 core dimensions of human communication:
1. Words (Shabd): Literal text, vocabulary, colloquial Hinglish/Hindi/English slang.
2. Context (Sandarbh): Active app, window, website, document, last referenced entity.
3. Intention (Uddeshya): Speech-act classification (Command, Ability, Status, Troubleshooting, Banter).
4. Emotion (Bhaavna): Affective state (Anger, Frustration, Anxiety, Fatigue, Joy, Sadness, Confusion, Calm).
5. Previous Conversation (Pichhli Baatcheet): Multi-turn history, anaphora resolution ("isme", "usko", "wahi").
6. Correction (Sudhaar): Conversational repairs ("nahi ye nahi", "brave me kholo"), preference updates.
7. Situation (Sthiti): Time of day, day-part, late night, active workload, focus mode.

Strictly adheres to the No-Duplicate-Implementation Rule (AGENTS.md §1.1).
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.dialogue_act import DialogueActClassifier, DialogueAct
from core.intelligence.confidence import (
    InterpretationConfidence,
    ConfidenceTier,
    ConfidenceAction,
    get_confidence_engine,
)
from core.intent import UniversalIntentCategory
from core.reference_resolver import ReferenceResolver
from core.semantic.hindi_vocab import EmotionConcept, HindiVocabCategory, HindiVocabEngine
from core.time_context import DayPart, get_time_context
from core.topic_tracker import TopicTracker
from .context_tracker import ContextResolver
from .intents import ConversationalIntent
from .normalizer import ConversationNormalizer

logger = logging.getLogger("jarvis.brain.conversation.model")


@dataclass
class HumanConversationFrame:
    """
    Canonical ConversationFrame — Single Shared Meaning Contract for JARVIS V2.

    Represents WHAT THE USER MEANS rather than which intent matched.
    Every pipeline stage enriches or consumes this same frame instance.
    Produced once per turn by HumanConversationModel.analyze_turn() and
    enriched by ConversationFrameBridge (core/conversation/frame.py) as
    SpeechUnderstanding, DialogueAct, and ReferenceResolver outputs are ready.

    Ownership:
      Speech layer    → raw_text, normalized_text, input_quality, interpretation_status
      Semantic layer  → communicative_goal, action, entity, target, is_negated, negation_scope
      Dialogue layer  → dialogue_act, previous_turn_relation
      Context layer   → active_topic, active_workflow, active_goal, pending_question
      Reference layer → resolved_reference, reference_confidence, resolver_used
      Confidence layer→ intent_confidence, goal_confidence, overall_confidence
      Decision layer  → decision_type, execution_allowed, agent_required
      Execution layer → consumes frame; writes nothing back
      Response layer  → consumes decision_type and communicative_goal; writes nothing back
    """
    # ── Required positional fields (original 7 core dimensions) ──────────────
    words: str                                   # Original raw utterance
    normalized_words: str                        # Cleaned & normalized tokens
    context: Dict[str, Any]                      # Active window, app, website, file, entity
    intention: ConversationalIntentType          # Speech-act / intent
    speech_act: str                              # String representation of speech-act
    is_executable_command: bool                  # True only if imperative action command
    emotion: EmotionConcept                      # Primary detected emotion
    emotion_intensity: float                     # Emotion intensity from 0.0 to 1.0
    is_frustrated_or_angry: bool                 # Fast flag for empathy & calm de-escalation
    previous_conversation: List[Dict[str, str]]  # Recent turns history
    resolved_utterance: str                      # Utterance with anaphoric pronouns resolved
    resolved_entity: Optional[str]               # Entity resolved from context
    is_correction: bool                          # Whether this turn is a conversational repair
    correction_details: Optional[Dict[str, Any]] # Old value, new value, container, target
    situation: Dict[str, Any]                    # Time of day, day-part, night/workload context
    suggested_tone: str                          # "calm_empathy", "supportive_care", etc.
    universal_category: UniversalIntentCategory = UniversalIntentCategory.GENERAL_CONVERSATION
    confidence: Optional[InterpretationConfidence] = None

    # ── Turn identity ─────────────────────────────────────────────────────────
    turn_id: str = ""                            # Unique per-turn identifier
    session_id: str = ""                         # Conversation session identifier
    timestamp: float = field(default_factory=time.time)  # Unix epoch at frame creation

    # ── Speech / normalization ────────────────────────────────────────────────
    raw_utterance: str = ""
    normalized_utterance: str = ""
    language: str = "hinglish"                   # "hi", "en", "hinglish"
    detected_languages: List[str] = field(default_factory=list)  # All detected language codes
    is_code_switched: bool = False               # True if mixed Hindi/English tokens
    input_quality: str = "clean"                 # "clean", "incomplete_fragment", "unintelligible", "ambiguous"

    # ── Semantic meaning ──────────────────────────────────────────────────────
    dialogue_act: Optional[Any] = None           # DialogueAct enum / str
    communicative_goal: str = ""                 # High-level communicative goal (e.g. OPEN_APPLICATION)
    operational_intent: str = ""                 # Low-level operational intent (e.g. "open_app", "set_volume")
    action: str = ""                             # Canonical action verb ("open", "close", "set", "query")
    entity: str = ""                             # Primary domain entity
    primary_entity: str = ""                     # Dominant entity alias (same as entity for clarity)
    target: str = ""                             # Target application / item
    target_type: str = ""                        # "application", "website", "system", "file", "general"
    reference: Optional[str] = None              # Raw deictic reference token ("ye", "doosra", "last wala")
    resolved_reference: str = ""                 # Resolved deictic reference target (e.g. "YouTube")
    reference_source: str = ""                   # Source of resolution ("active_context", "thread", "visual")
    reference_confidence: float = 0.0            # Confidence in deictic resolution (0.0 = unresolved)
    resolver_used: str = ""                      # Which resolver produced the resolution

    # ── Negation & constraints ────────────────────────────────────────────────
    is_negated: bool = False                     # True if command explicitly negated
    negated_action: Optional[str] = None         # Action that was negated
    negation_scope: str = ""                     # Scope of negation ("full", "target", "action")
    exclusions: List[str] = field(default_factory=list)   # Items explicitly excluded
    constraints: List[str] = field(default_factory=list)  # Execution constraints

    # ── Semantic modifiers ────────────────────────────────────────────────────
    topic: str = "general"                       # Current conversation topic
    subtopic: Optional[str] = None               # Current subtopic
    previous_turn_relation: str = "INDEPENDENT"  # "CONTINUATION", "CORRECTION", "ANSWER", "FOLLOW_UP", "INDEPENDENT"
    time_context: Optional[str] = None           # Temporal reference ("abhi", "baad mein", "kal")
    location_context: Optional[str] = None       # Location context
    quantity: Optional[Any] = None               # Numerical quantity (e.g. 50 for volume)
    modifiers: List[str] = field(default_factory=list)

    # ── Context enrichment ────────────────────────────────────────────────────
    active_workflow: str = ""                    # Name of active workflow (from ConversationState)
    active_goal: str = ""                        # Active agent task goal
    conversation_state: Dict[str, Any] = field(default_factory=dict)
    context_used: Dict[str, Any] = field(default_factory=dict)
    memory_used: List[str] = field(default_factory=list)  # Memory tiers consulted
    evidence: List[str] = field(default_factory=list)     # Evidence supporting interpretation

    # ── Slot / multi-turn state ───────────────────────────────────────────────
    pending_question: str = ""                   # Last question Jarvis asked (awaiting answer)
    pending_goal: str = ""                       # Goal waiting for slot fill
    missing_slot: str = ""                       # Name of missing slot
    slot_values: Dict[str, Any] = field(default_factory=dict)  # Filled slot values

    # ── Correction tracking ───────────────────────────────────────────────────
    correction_target: str = ""                  # What was corrected (old value)
    correction_value: str = ""                   # Corrected / new value

    # ── Human signals ─────────────────────────────────────────────────────────
    certainty: float = 0.90
    politeness: str = "CASUAL"                   # "CASUAL", "POLITE", "URGENT", "DIRECT"
    urgency: str = "NORMAL"                      # "NORMAL", "URGENT"
    frustration_signal: bool = False             # True if anger/frustration detected
    confirmation_state: str = "NONE"             # "PENDING", "CONFIRMED", "CANCELLED", "NONE"
    cancellation_state: bool = False             # True if user cancelled a pending action
    missing_information: List[str] = field(default_factory=list)

    # ── Pragmatic layer ───────────────────────────────────────────────────────
    pragmatic_goal: Optional[str] = None         # Indirect pragmatic goal (e.g. "COOL_ENVIRONMENT")
    pragmatic_clarification: Optional[str] = None  # Suggested clarification question

    # ── Decision contract (written by ConversationFrameBridge.derive_decision) ─
    decision: str = "CHAT"                       # Legacy field: "EXECUTE", "ANSWER", "CLARIFY", "CHAT"
    decision_type: str = ""                      # Canonical: EXECUTE_FAST, EXECUTE_AGENT, ANSWER, CONVERSE, CLARIFY, etc.
    decision_reason: str = ""                    # Human-readable reason for the decision
    clarification_required: bool = False         # True if user must be asked for missing info
    execution_allowed: bool = False              # True if policy permits execution
    agent_required: bool = False                 # True if multi-step Agent path is needed

    # ── Diagnostics ───────────────────────────────────────────────────────────
    interpretation_status: str = "OK"            # "OK", "AMBIGUOUS", "LOW_CONFIDENCE", "RECOVERED"
    ambiguity_reason: str = ""                   # Why the interpretation is ambiguous
    recovery_status: str = ""                    # What recovery was applied (e.g. "spell_fix", "context_repair")

    def __post_init__(self):
        if not self.raw_utterance:
            self.raw_utterance = self.words
        if not self.normalized_utterance:
            self.normalized_utterance = self.normalized_words
        if not self.context_used:
            self.context_used = self.context
        if not self.primary_entity:
            self.primary_entity = self.entity
        # Sync frustration signal from emotion flag
        if self.is_frustrated_or_angry and not self.frustration_signal:
            self.frustration_signal = True
        # Sync execution_allowed from is_executable_command if not yet set by bridge
        if self.is_executable_command and not self.execution_allowed and not self.decision_type:
            self.execution_allowed = True

    def to_dict(self) -> Dict[str, Any]:
        """
        Safe serialization of the ConversationFrame for diagnostics and logging.
        Never serializes credentials, raw environment data, or sensitive secrets.
        """
        def _safe(v: Any) -> Any:
            """Converts non-JSON-safe objects to strings."""
            if isinstance(v, (str, int, float, bool, type(None))):
                return v
            if isinstance(v, list):
                return [_safe(i) for i in v]
            if isinstance(v, dict):
                return {str(k): _safe(val) for k, val in v.items()}
            if hasattr(v, "value"):  # Enums
                return v.value
            return str(v)

        return {
            # Turn identity
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "timestamp": self.timestamp,
            # Speech
            "raw_text": self.words,
            "normalized_text": self.normalized_utterance,
            "language": self.language,
            "detected_languages": self.detected_languages,
            "is_code_switched": self.is_code_switched,
            "input_quality": self.input_quality,
            # Meaning
            "dialogue_act": _safe(self.dialogue_act),
            "speech_act": self.speech_act,
            "communicative_goal": self.communicative_goal,
            "operational_intent": self.operational_intent,
            "action": self.action,
            "entity": self.entity,
            "target": self.target,
            "target_type": self.target_type,
            "reference": self.reference,
            "resolved_reference": self.resolved_reference,
            "reference_source": self.reference_source,
            "reference_confidence": round(self.reference_confidence, 3),
            "resolver_used": self.resolver_used,
            # Negation
            "is_negated": self.is_negated,
            "negated_action": self.negated_action,
            "negation_scope": self.negation_scope,
            "exclusions": self.exclusions,
            "constraints": self.constraints,
            # Context
            "topic": self.topic,
            "subtopic": self.subtopic,
            "previous_turn_relation": self.previous_turn_relation,
            "active_workflow": self.active_workflow,
            "active_goal": self.active_goal,
            "time_context": self.time_context,
            "quantity": _safe(self.quantity),
            "modifiers": self.modifiers,
            # Slot state
            "pending_question": self.pending_question,
            "pending_goal": self.pending_goal,
            "missing_slot": self.missing_slot,
            "slot_values": _safe(self.slot_values),
            # Correction
            "is_correction": self.is_correction,
            "correction_target": self.correction_target,
            "correction_value": self.correction_value,
            # Human signals
            "emotion": _safe(self.emotion),
            "emotion_intensity": round(self.emotion_intensity, 3),
            "frustration_signal": self.frustration_signal,
            "politeness": self.politeness,
            "urgency": self.urgency,
            "confirmation_state": self.confirmation_state,
            "cancellation_state": self.cancellation_state,
            # Confidence
            "certainty": round(self.certainty, 3),
            "intent_confidence": round(self.confidence.intent_confidence, 3) if self.confidence else None,
            "entity_confidence": round(self.confidence.entity_confidence, 3) if self.confidence else None,
            "goal_confidence": round(self.confidence.goal_confidence, 3) if self.confidence else None,
            "reference_confidence_from_engine": round(self.confidence.reference_confidence, 3) if self.confidence else None,
            "overall_confidence": round(self.confidence.composite, 3) if self.confidence else None,
            "confidence_tier": _safe(self.confidence.tier) if self.confidence else None,
            # Decision contract
            "decision": self.decision,
            "decision_type": self.decision_type,
            "decision_reason": self.decision_reason,
            "clarification_required": self.clarification_required,
            "execution_allowed": self.execution_allowed,
            "agent_required": self.agent_required,
            # Diagnostics
            "interpretation_status": self.interpretation_status,
            "ambiguity_reason": self.ambiguity_reason,
            "recovery_status": self.recovery_status,
            "evidence": self.evidence,
            "memory_used": self.memory_used,
            "resolver_used_diag": self.resolver_used,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "HumanConversationFrame":
        """
        Reconstructs a minimal HumanConversationFrame from a serialized dict.
        Intended for testing and replay — not all fields are guaranteed present.
        """
        from core.intent import UniversalIntentCategory
        from core.conversational_intent import ConversationalIntentType
        from core.semantic.hindi_vocab import EmotionConcept

        raw = d.get("raw_text", d.get("words", ""))
        norm = d.get("normalized_text", d.get("normalized_words", raw))

        intention_val = d.get("speech_act", "UNKNOWN")
        try:
            intention = ConversationalIntentType(intention_val)
        except Exception:
            intention = ConversationalIntentType.UNKNOWN

        emotion_val = d.get("emotion", "calm")
        try:
            emotion = EmotionConcept(emotion_val)
        except Exception:
            emotion = EmotionConcept.CALM

        frame = cls(
            words=raw,
            normalized_words=norm,
            context=d.get("context_used", {}),
            intention=intention,
            speech_act=d.get("speech_act", ""),
            is_executable_command=d.get("execution_allowed", False),
            emotion=emotion,
            emotion_intensity=d.get("emotion_intensity", 0.0),
            is_frustrated_or_angry=d.get("frustration_signal", False),
            previous_conversation=[],
            resolved_utterance=d.get("normalized_text", raw),
            resolved_entity=d.get("resolved_reference") or d.get("target"),
            is_correction=d.get("is_correction", False),
            correction_details=None,
            situation={},
            suggested_tone="natural_friendly",
        )
        # Apply optional fields
        frame.turn_id = d.get("turn_id", "")
        frame.session_id = d.get("session_id", "")
        frame.language = d.get("language", "hinglish")
        frame.input_quality = d.get("input_quality", "clean")
        frame.dialogue_act = d.get("dialogue_act")
        frame.communicative_goal = d.get("communicative_goal", "")
        frame.operational_intent = d.get("operational_intent", "")
        frame.action = d.get("action", "")
        frame.entity = d.get("entity", "")
        frame.target = d.get("target", "")
        frame.target_type = d.get("target_type", "")
        frame.resolved_reference = d.get("resolved_reference", "")
        frame.reference_confidence = d.get("reference_confidence", 0.0)
        frame.is_negated = d.get("is_negated", False)
        frame.negation_scope = d.get("negation_scope", "")
        frame.previous_turn_relation = d.get("previous_turn_relation", "INDEPENDENT")
        frame.topic = d.get("topic", "general")
        frame.active_workflow = d.get("active_workflow", "")
        frame.active_goal = d.get("active_goal", "")
        frame.pending_question = d.get("pending_question", "")
        frame.pending_goal = d.get("pending_goal", "")
        frame.missing_slot = d.get("missing_slot", "")
        frame.decision_type = d.get("decision_type", "")
        frame.decision_reason = d.get("decision_reason", "")
        frame.clarification_required = d.get("clarification_required", False)
        frame.execution_allowed = d.get("execution_allowed", False)
        frame.agent_required = d.get("agent_required", False)
        frame.interpretation_status = d.get("interpretation_status", "OK")
        frame.ambiguity_reason = d.get("ambiguity_reason", "")
        frame.recovery_status = d.get("recovery_status", "")
        frame.cancellation_state = d.get("cancellation_state", False)
        frame.confirmation_state = d.get("confirmation_state", "NONE")
        frame.decision = d.get("decision", "CHAT")
        return frame


class EmotionAnalyzer:
    """
    Detects affective states and emotional undertones across Hindi, Hinglish, and English.
    """

    # Extended affective triggers for high-accuracy emotion detection
    EMOTION_PATTERNS: Dict[EmotionConcept, List[Tuple[re.Pattern, float]]] = {
        EmotionConcept.ANGER: [
            (re.compile(r"\b(gussa|gusse|naraz|chidh|dimag kharab|mood kharab|dimag ka dahi|pagal ho gaya|irritat|bakwas|bekar|bhad me|shut up|chup kar|chup ho ja|nonsense)\b", re.I), 0.90),
            (re.compile(r"\b(chal kyun nahi raha|kaam kyun nahi kar raha|kuch nahi ho raha|failing|error bar bar|kitni baar bolu|kitni bar bola)\b", re.I), 0.85),
            (re.compile(r"\b(arrey yaar|arre yaar|are yaar|yaar fir se)\b", re.I), 0.70),
        ],
        EmotionConcept.ANXIETY: [
            (re.compile(r"\b(tension|pareshani|pareshan|stress|stressed|anxiety|ghabrahat|dar lag raha|panic|dar|problem ho gayi|badi mushkil|phas gaya|phas gayi)\b", re.I), 0.85),
            (re.compile(r"\b(kya karun|kaise hoga|urgent hai|emergency|jaldi karo please|jaldi|quickly)\b", re.I), 0.75),
        ],
        EmotionConcept.FATIGUE: [
            (re.compile(r"\b(thak gaya|thak gayi|thakan|tired|exhausted|sleepy|nind|neend aa rahi|neend|sir dard|sar dard|headache|energy nahi|so jaunga|sone ja raha)\b", re.I), 0.90),
            (re.compile(r"\b(aaj bohot lamba din tha|bohot kaam tha|rest chahiye|aaram karna hai)\b", re.I), 0.80),
        ],
        EmotionConcept.JOY: [
            (re.compile(r"\b(khush|khushi|happy|mast|maza aa gaya|maza|awesome|badhiya|superb|party|jeet gaya|pass ho gaya|zabardast|congrats|great job|shabash)\b", re.I), 0.90),
            (re.compile(r"\b(love you|bohot achha|too good|thank you so much|dil khush ho gaya)\b", re.I), 0.85),
        ],
        EmotionConcept.SADNESS: [
            (re.compile(r"\b(dukh|dukhi|sad|dil toot gaya|upset|depression|depressed|rona aa raha|crying|cry|bura lag raha|mood off|akela|lonely)\b", re.I), 0.90),
            (re.compile(r"\b(kuch achha nahi lag raha|koi nahi hai|man udaas hai|udas)\b", re.I), 0.85),
        ],
        EmotionConcept.CONFUSED: [
            (re.compile(r"\b(confused|confusion|samajh nahi aa raha|samajh nahi aaya|uljhan|kya chal raha hai|pata nahi kya ho gaya|gadbad)\b", re.I), 0.85),
            (re.compile(r"\b(doubt hai|clear nahi hai|lost)\b", re.I), 0.75),
        ],
    }

    @classmethod
    def analyze(cls, text: str) -> Tuple[EmotionConcept, float, List[str]]:
        """
        Analyzes utterance text for emotional undertones.
        Returns: (primary_emotion, intensity, matched_cues)
        """
        if not text:
            return EmotionConcept.CALM, 0.0, []

        norm = text.lower().strip()
        best_emotion = EmotionConcept.CALM
        max_intensity = 0.0
        all_cues = []

        # 1. Pattern and lexicon match
        for concept, pattern_list in cls.EMOTION_PATTERNS.items():
            for pat, weight in pattern_list:
                m = pat.search(norm)
                if m:
                    cue = m.group(0)
                    all_cues.append(cue)
                    if weight > max_intensity:
                        max_intensity = weight
                        best_emotion = concept

        # 2. Cross-check with HindiVocabEngine for single-word and phrase emotional vocab
        words = norm.split()
        for w in words:
            res = HindiVocabEngine.classify(w)
            if res:
                cat, concept = res
                if cat == HindiVocabCategory.EMOTION:
                    try:
                        concept_enum = EmotionConcept(concept) if not isinstance(concept, EmotionConcept) else concept
                    except Exception:
                        concept_enum = None
                    if concept_enum and 0.75 > max_intensity:
                        max_intensity = 0.75
                        best_emotion = concept_enum
                        all_cues.append(w)
                elif cat == HindiVocabCategory.BODY_STATE and str(concept) in ("FATIGUE", "SLEEP_STATE"):
                    if 0.85 > max_intensity:
                        max_intensity = 0.85
                        best_emotion = EmotionConcept.FATIGUE
                        all_cues.append(w)

        # 3. Also check multi-word enriched speech entities
        try:
            enriched = HindiVocabEngine.enrich_speech_entities(norm)
            if enriched.emotion:
                concept_enum = EmotionConcept(enriched.emotion) if not isinstance(enriched.emotion, EmotionConcept) else enriched.emotion
                if 0.80 > max_intensity:
                    max_intensity = 0.80
                    best_emotion = concept_enum
                    all_cues.append(str(enriched.emotion))
            if enriched.body_state and str(enriched.body_state) in ("FATIGUE", "SLEEP_STATE"):
                if 0.85 > max_intensity:
                    max_intensity = 0.85
                    best_emotion = EmotionConcept.FATIGUE
                    all_cues.append(str(enriched.body_state))
        except Exception:
            pass

        return best_emotion, round(max_intensity, 2), all_cues


class HumanConversationModel:
    """
    Authoritative Human Conversation Model for Jarvis V2.
    Holistically analyzes user speech across Words, Context, Intention, Emotion,
    Previous Conversation, Correction, and Situation to generate human-aligned
    understanding frames and emotion-adapted responses.
    """

    def __init__(
        self,
        learning_manager: Optional[Any] = None,
        context_resolver: Optional[ContextResolver] = None
    ):
        self.learning_manager = learning_manager
        self.context_resolver = context_resolver or ContextResolver()
        self.emotion_analyzer = EmotionAnalyzer()
        self.speech_act_classifier = ConversationalIntentClassifier()

    @staticmethod
    def _detect_language_and_code_switching(text: str) -> Tuple[str, bool]:
        """Detects language (hi, en, hinglish) and code-switching presence."""
        if not text:
            return "hinglish", False

        # Devanagari script check
        has_devanagari = bool(re.search(r"[\u0900-\u097F]", text))
        if has_devanagari:
            has_latin = bool(re.search(r"[a-zA-Z]", text))
            return ("hinglish", True) if has_latin else ("hi", False)

        low = text.lower()
        hindi_tokens = {
            "kholo", "karo", "khol", "chala", "chalao", "band", "hai", "hain", "hoon", "hu",
            "bhai", "yaar", "mat", "nahi", "main", "aaj", "kal", "baad", "abhi", "isko", "usko",
            "ise", "use", "isme", "usme", "ye", "yeh", "woh", "wahi", "same", "doosra", "pehla",
            "teesra", "kaunsa", "kaise", "kya", "kyun", "kahan", "kitna", "suno", "sun", "theek",
            "achha", "accha", "badhiya", "garmi", "thand", "thak", "khana", "chahiye", "zara",
            "laga", "rehne", "ruko", "ruk", "waise", "doge", "chalte", "sakte", "paoge",
            "mera", "meri", "mere", "mujhe", "thoda", "thodi", "thode", "liye", "aur", "pe",
            "par", "jo", "hum", "humein", "tum", "aap", "ka", "ki", "ke", "ko", "se", "mein", "kar"
        }
        english_tokens = {
            "open", "close", "launch", "start", "stop", "system", "lock", "pc", "computer",
            "application", "window", "tab", "browser", "please", "can", "you", "what", "is",
            "the", "weather", "today", "tomorrow", "file", "folder", "volume", "sound", "mute",
            "unmute", "clear", "clean", "temp", "temporary", "recycle", "bin", "help", "thanks",
            "thank", "chrome", "edge", "brave", "excel", "notepad", "calculator", "task", "work",
            "meeting", "presentation", "ready", "desktop", "low", "high"
        }

        words = set(re.findall(r"\b[a-z0-9_\-\.]+\b", low))
        hi_count = len(words.intersection(hindi_tokens))
        en_count = len(words.intersection(english_tokens))

        if hi_count > 0 and en_count > 0:
            return "hinglish", True
        elif en_count > 0 and hi_count == 0:
            return "en", False
        elif hi_count > 0:
            return "hinglish", False
        return "hinglish", False

    @staticmethod
    def _detect_politeness_and_urgency(text: str) -> Tuple[str, str]:
        """Classifies politeness and urgency signals."""
        low = text.lower()
        is_polite = bool(re.search(
            r"\b(?:please|kripya|zara|can\s+you|could\s+you|would\s+you|khol\s+sakte\s+ho|khol\s+doge|kar\s+sakte\s+ho|kar\s+doge)\b",
            low
        ))
        is_urgent = bool(re.search(
            r"\b(?:jaldi|turant|urgent|emergency|fast|quickly|abhi\s+ke\s+abhi)\b",
            low
        ))
        politeness = "POLITE" if is_polite else ("URGENT" if is_urgent else ("DIRECT" if re.search(r"\b(?:kholo|karo|band|lock)\b", low) else "CASUAL"))
        urgency = "URGENT" if is_urgent else "NORMAL"
        return politeness, urgency

    @staticmethod
    def _detect_negation(text: str) -> Tuple[bool, Optional[str]]:
        """
        Enforces the Negation Invariant:
        Identifies explicitly negated user desires and instructions.
        """
        low = text.lower()
        neg_patterns = [
            (r"\b(?:(?:mat|nahi)\s+(?:kholo|open\s+karo|open|chalao|chalana|start\s+karo|kholna))\b", "open"),
            (r"\b(?:don'?t\s+open|do\s+not\s+open|never\s+open)\b", "open"),
            (r"\b(?:band\s+(?:mat|nahi)\s+karo|close\s+(?:mat|nahi)\s+karo|(?:mat|nahi)\s+(?:band\s+karo|close\s+karo|band|close))\b", "close"),
            (r"\b(?:nahi\s+(?:band\s+karna|close\s+karna))\b", "close"),
            (r"\b(?:don'?t\s+close|do\s+not\s+close)\b", "close"),
            (r"\b(?:(?:mat|nahi)\s+(?:karo|karna)|don'?t\s+do|do\s+not\s+do)\b", "action"),
            (r"\b(?:maine\s+.+?\s+nahi\s+bola(?:tha)?)\b", "statement"),
            (r"\b(?:nahi\s+chahiye|woh\s+nahi\s+chahiye|mujhe\s+(?:woh\s+)?nahi\s+chahiye)\b", "request"),
        ]
        for pat, act in neg_patterns:
            if re.search(pat, low):
                return True, act
        return False, None

    @staticmethod
    def _detect_pragmatic_meaning(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Detects pragmatic indirect statements where literal meaning is not enough.
        Returns (pragmatic_goal, clarification_prompt, stated_fact).
        """
        low = text.lower()
        if re.search(r"\b(?:bahut\s+garmi\s+hai|bohot\s+garmi|garmi\s+lag\s+rahi|it'?s\s+(?:so\s+)?hot)\b", low):
            return "COOL_ENVIRONMENT", "AC chala doon?", "USER_STATED = HOT"
        if re.search(r"\b(?:bahut\s+thand\s+hai|bohot\s+thand|thand\s+lag\s+rahi|it'?s\s+(?:so\s+)?cold)\b", low):
            return "WARM_ENVIRONMENT", "Heater chala doon?", "USER_STATED = COLD"
        if re.search(r"\b(?:bahut\s+andhera\s+hai|andhera\s+hai|kuch\s+dikh\s+nahi\s+raha|it'?s\s+(?:too\s+)?dark)\b", low):
            return "INCREASE_LIGHT", "Lights on kar doon?", "USER_STATED = DARK"
        return None, None, None

    @staticmethod
    def _extract_temporal_and_quantity(text: str) -> Tuple[Optional[str], Optional[Any]]:
        """Extracts temporal references and numerical quantities."""
        low = text.lower()
        time_tokens = [
            "abhi", "ab", "thodi der mein", "baad mein", "kal", "aaj", "parso",
            "agle hafte", "next week", "pehle", "phir", "uske baad", "last mein"
        ]
        matched_time = None
        for tok in time_tokens:
            if re.search(rf"\b{re.escape(tok)}\b", low):
                matched_time = tok
                break

        quantity = None
        m_num = re.search(r"\b(\d+)\b", low)
        if m_num:
            try:
                quantity = int(m_num.group(1))
            except Exception:
                quantity = m_num.group(1)
        return matched_time, quantity

    def analyze_turn(
        self,
        raw_input: str,
        active_context: Optional[Any] = None,
        recent_turns: Optional[List[Any]] = None,
        situation_override: Optional[Dict[str, Any]] = None,
        topic_tracker: Optional[Any] = None,
        conversation_state: Optional[Any] = None
    ) -> HumanConversationFrame:
        """
        Core entry point: analyzes user input along all 29 dimensions and returns
        a complete HumanConversationFrame.
        """
        clean_words = ConversationNormalizer.clean(raw_input)

        # 1. Words Layer: Normalize, resolve vocabulary aliases if learning is active
        normalized_words = clean_words
        if self.learning_manager and hasattr(self.learning_manager, "resolve_vocabulary"):
            normalized_words = self.learning_manager.resolve_vocabulary(clean_words)

        # Language & Code-Switching
        language, is_code_switched = self._detect_language_and_code_switching(raw_input)

        # Politeness & Urgency
        politeness, urgency = self._detect_politeness_and_urgency(clean_words)

        # Negation Invariant Gating
        is_negated, negated_action = self._detect_negation(clean_words)

        # Pragmatic Understanding
        pragmatic_goal, pragmatic_clarification, pragmatic_stated = self._detect_pragmatic_meaning(clean_words)

        # Temporal & Quantity
        time_context, quantity = self._extract_temporal_and_quantity(clean_words)

        # 2. Context Layer: Extract active desktop/system environment
        context_dict = self._extract_active_context(active_context)

        # 3. Emotion Layer: Affective state and intensity
        emotion, intensity, cues = self.emotion_analyzer.analyze(raw_input)
        is_frustrated_or_angry = emotion in (EmotionConcept.ANGER, EmotionConcept.ANXIETY) and intensity >= 0.70

        # 4. Previous Conversation & Anaphora Layer:
        # Resolve 'isme', 'usko', 'wahi wala' with active context and recent turns
        resolved_text, resolved_entity = self._resolve_anaphora_with_context(
            clean_words,
            active_context=active_context,
            recent_turns=recent_turns
        )

        # Reference resolution
        reference_expr = None
        if ReferenceResolver.has_reference(clean_words):
            ref_match = ReferenceResolver.resolve(clean_words, active_context=active_context)
            if ref_match and ref_match.resolved:
                reference_expr = ref_match.target_name

        # 5. Correction Layer: Detect verbal repair or container preference
        is_correction = False
        correction_details = None
        if self.learning_manager and hasattr(self.learning_manager, "detect_correction"):
            corr_res = self.learning_manager.detect_correction(raw_input, active_context=active_context)
            if corr_res.is_correction:
                is_correction = True
                correction_details = {
                    "concept": corr_res.concept,
                    "target": corr_res.target,
                    "old_value": corr_res.old_value,
                    "new_value": corr_res.new_value or corr_res.preferred_container,
                    "preferred_container": corr_res.preferred_container,
                    "type": corr_res.correction_type
                }
        else:
            # Fallback inline regex repair check
            repair_match = re.search(r"^(?:nahi|no)[,\s]+([a-zA-Z0-9_\-]+)\s+nahi\s+([a-zA-Z0-9_\-]+)", clean_words, re.I)
            if repair_match:
                is_correction = True
                correction_details = {
                    "old_value": repair_match.group(1),
                    "new_value": repair_match.group(2)
                }

        # 6. Intention Layer (Speech-Act Gating):
        speech_act_result = self.speech_act_classifier.classify(resolved_text or clean_words)
        intent_type = speech_act_result.intent_type

        # Negation Invariant & Pragmatic Gating: Negated commands or ambiguous pragmatic remarks must NOT execute
        is_executable = speech_act_result.is_executable and not is_correction and not is_negated and not bool(pragmatic_goal)

        # Dialogue Act Layer
        active_top = getattr(topic_tracker, "active_topic", "general") if topic_tracker else "general"
        da_res = DialogueActClassifier.classify(
            normalized_words,
            active_topic=active_top,
            conversation_state=conversation_state
        )

        # Communicative Goal & Decision Formulation
        canonical_action_map = {
            "kholo": "open", "khol": "open", "open": "open", "launch": "open", "start": "open",
            "chala": "open", "chalao": "open", "chala do": "open", "khol do": "open", "open karo": "open",
            "start kar do": "open", "khol doge": "open", "kholna": "open", "chalte hain": "open",
            "laga do": "open", "kar do": "open",
            "band": "close", "band karo": "close", "band kar do": "close", "band kar de": "close",
            "close": "close", "close karo": "close", "close kar do": "close",
            "stop": "close", "terminate": "close", "kill": "close",
            "lock": "lock", "unlock": "unlock", "minimize": "minimize", "maximize": "maximize"
        }
        raw_act = (
            getattr(speech_act_result, "action_type", "")
            or da_res.entities.get("action", "")
            or ("close" if "band" in clean_words or "close" in clean_words else ("open" if any(w in clean_words for w in ("khol", "open", "chala", "chalo", "laga")) else ""))
        )
        if "minimize" in clean_words:
            action_verb = "minimize"
        elif "maximize" in clean_words:
            action_verb = "maximize"
        elif any(w in clean_words for w in ("band", "close")):
            action_verb = "close"
        else:
            action_verb = canonical_action_map.get(raw_act.lower().strip(), raw_act)

        target_name = (
            getattr(speech_act_result, "target", "")
            or resolved_entity
            or reference_expr
            or da_res.entities.get("target", "")
            or ""
        )
        if not target_name:
            for app in ("chrome", "edge", "notepad", "excel", "brave", "spotify", "calculator", "system", "pc"):
                if app in clean_words.lower().split():
                    target_name = app
                    break

        if is_negated:
            act_str = action_verb.upper() if action_verb else (negated_action.upper() if negated_action else "EXECUTE")
            comm_goal = f"DO_NOT_{act_str}"
            decision = "ANSWER"
        elif pragmatic_goal:
            comm_goal = pragmatic_goal
            decision = "CLARIFY"
        elif is_executable:
            comm_goal = f"{action_verb.upper()}_{target_name.upper()}" if (action_verb and target_name) else "EXECUTE_COMMAND"
            decision = "EXECUTE"
        elif intent_type in (
            ConversationalIntentType.CAPABILITY_QUESTION,
            ConversationalIntentType.STATUS_QUESTION,
            ConversationalIntentType.STATUS_AFTER_ACTION,
            ConversationalIntentType.INFORMATION_QUESTION,
            ConversationalIntentType.CANCELLATION,
            ConversationalIntentType.REJECTION,
            ConversationalIntentType.TROUBLESHOOTING
        ):
            comm_goal = f"QUERY_{intent_type.value}"
            decision = "ANSWER"
        else:
            comm_goal = str(da_res.act.value if hasattr(da_res.act, "value") else da_res.act)
            decision = "CHAT"

        prev_relation = "CORRECTION" if is_correction else (
            "CONTINUATION" if (recent_turns and (ReferenceResolver.has_reference(clean_words) or clean_words in ("ab band karo", "next", "same", "wahi", "theek hai")))
            else "INDEPENDENT"
        )

        # 7. Situation Layer: Time of day, day-part, workload, late night
        situation = situation_override or self._evaluate_situation()

        # Determine optimal response tone
        suggested_tone = self._determine_response_tone(
            emotion=emotion,
            intensity=intensity,
            is_frustrated_or_angry=is_frustrated_or_angry,
            intent_type=intent_type,
            is_correction=is_correction,
            situation=situation
        )

        formatted_recent = []
        if recent_turns:
            for t in recent_turns[-5:]:
                if isinstance(t, dict):
                    formatted_recent.append(t)
                elif hasattr(t, "raw_input") and hasattr(t, "response_text"):
                    formatted_recent.append({"role": "user", "content": t.raw_input})
                    if t.response_text:
                        formatted_recent.append({"role": "assistant", "content": t.response_text})

        universal_cat = getattr(
            speech_act_result, "universal_category", UniversalIntentCategory.GENERAL_CONVERSATION
        ) if speech_act_result else UniversalIntentCategory.GENERAL_CONVERSATION

        # Evaluate Interpretation Confidence across dimensions
        conf_engine = get_confidence_engine()
        intent_conf = getattr(speech_act_result, "confidence", 0.88) if speech_act_result else 0.88
        entity_conf = 0.95 if (resolved_entity or target_name) else (0.80 if context_dict.get("is_active") else 0.65)
        context_conf = 0.95 if context_dict.get("is_active") else 0.75
        action_conf = 0.92 if is_executable else (0.45 if is_negated else 0.70)
        answer_conf = 0.85 if intent_type in (ConversationalIntentType.INFORMATION_QUESTION, ConversationalIntentType.CAPABILITY_QUESTION) else 0.75

        # Pragmatic lower confidence to prevent premature execution
        if pragmatic_goal:
            intent_conf = 0.58
            action_conf = 0.50

        frame_confidence = conf_engine.evaluate(
            intent_confidence=intent_conf,
            entity_confidence=entity_conf,
            context_confidence=context_conf,
            action_confidence=action_conf,
            answer_confidence=answer_conf,
            language_confidence=0.96,
            speech_confidence=0.95,
            goal_confidence=0.90 if not pragmatic_goal else 0.58,
            reference_confidence=0.92 if reference_expr else 0.85,
            turn_type="action" if is_executable else "answer",
            raw_query=raw_input,
            candidate_entities=[target_name] if target_name else [],
            metadata={"universal_category": universal_cat.value if hasattr(universal_cat, "value") else str(universal_cat)}
        )

        frame = HumanConversationFrame(
            words=raw_input,
            normalized_words=normalized_words,
            context=context_dict,
            intention=intent_type,
            speech_act=intent_type.value,
            is_executable_command=is_executable,
            emotion=emotion,
            emotion_intensity=intensity,
            is_frustrated_or_angry=is_frustrated_or_angry,
            previous_conversation=formatted_recent,
            resolved_utterance=resolved_text,
            resolved_entity=resolved_entity or target_name or None,
            is_correction=is_correction,
            correction_details=correction_details,
            situation=situation,
            suggested_tone=suggested_tone,
            universal_category=universal_cat,
            confidence=frame_confidence,
            raw_utterance=raw_input,
            normalized_utterance=normalized_words,
            language=language,
            is_code_switched=is_code_switched,
            dialogue_act=da_res.act,
            communicative_goal=comm_goal,
            action=action_verb,
            entity="application" if target_name in ("chrome", "excel", "notepad", "brave", "edge", "spotify") else ("system" if target_name in ("system", "screen", "pc") else ("volume" if target_name == "volume" else "general")),
            target=target_name,
            reference=reference_expr,
            topic=active_top,
            subtopic=getattr(da_res, "subtopic_hint", None),
            conversation_state={"user_state": getattr(conversation_state, "user_state", {})} if conversation_state else {},
            previous_turn_relation=prev_relation,
            time_context=time_context,
            location_context=None,
            quantity=quantity,
            modifiers=[],
            is_negated=is_negated,
            negated_action=negated_action,
            certainty=0.90 if not pragmatic_goal else 0.58,
            politeness=politeness,
            urgency=urgency,
            missing_information=[],
            context_used=context_dict,
            decision=decision,
            pragmatic_goal=pragmatic_goal,
            pragmatic_clarification=pragmatic_clarification
        )

        logger.debug(
            "HumanConversationFrame: intent=%s, goal=%s, decision=%s, negated=%s, pragmatic=%s, conf=%.2f (%s)",
            intent_type.value, comm_goal, decision, is_negated, pragmatic_goal,
            frame_confidence.composite, frame_confidence.tier.value
        )
        return frame

    def _extract_active_context(self, active_context: Optional[Any]) -> Dict[str, Any]:
        """Extracts active window, app, website, file, and entity from runtime context."""
        ctx: Dict[str, Any] = {
            "application": "",
            "window": "",
            "website": "",
            "file": "",
            "target": "",
            "last_entity": "",
            "is_active": False
        }
        if not active_context:
            return ctx

        ctx["application"] = getattr(active_context, "application", "") or ""
        ctx["window"] = getattr(active_context, "window", "") or ""
        ctx["website"] = getattr(active_context, "website", "") or ""
        ctx["file"] = getattr(active_context, "last_file", "") or ""
        ctx["target"] = getattr(active_context, "target", "") or ctx["website"] or ctx["application"]
        ctx["last_entity"] = getattr(active_context, "last_entity", "") or ""
        ctx["is_active"] = bool(ctx["application"] or ctx["website"] or ctx["window"] or ctx["file"])
        return ctx

    def _resolve_anaphora_with_context(
        self,
        text: str,
        active_context: Optional[Any] = None,
        recent_turns: Optional[List[Any]] = None
    ) -> Tuple[str, Optional[str]]:
        """
        Resolves conversational pronouns and references ('isme', 'usko', 'wahi wala')
        using both active target context and recent conversational turns.
        """
        active_entity = None
        if active_context:
            active_entity = (
                getattr(active_context, "website", None)
                or getattr(active_context, "application", None)
                or getattr(active_context, "last_entity", None)
            )

        resolved_text, entity = self.context_resolver.resolve(
            text,
            recent_turns=recent_turns,
            active_entity=active_entity
        )
        return resolved_text, entity

    def _evaluate_situation(self) -> Dict[str, Any]:
        """Evaluates situational and environmental context (time, day-part, focus)."""
        time_ctx = get_time_context()
        now = time_ctx.now()
        hour = now.hour
        day_part = time_ctx.get_day_part(now)
        is_late_night = hour >= 23 or hour < 5
        is_work_hours = 9 <= hour < 18

        return {
            "hour": hour,
            "day_part": day_part.value if hasattr(day_part, "value") else str(day_part),
            "is_late_night": is_late_night,
            "is_work_hours": is_work_hours,
            "timestamp": time.time()
        }

    def _determine_response_tone(
        self,
        emotion: EmotionConcept,
        intensity: float,
        is_frustrated_or_angry: bool,
        intent_type: ConversationalIntentType,
        is_correction: bool,
        situation: Dict[str, Any]
    ) -> str:
        """Selects the human response tone based on emotional, situational, and speech-act cues."""
        if is_frustrated_or_angry or intent_type == ConversationalIntentType.TROUBLESHOOTING:
            return "calm_empathy"
        if emotion == EmotionConcept.FATIGUE:
            return "supportive_care"
        if emotion == EmotionConcept.JOY and intensity >= 0.70:
            return "enthusiastic"
        if is_correction:
            return "receptive_repair"
        if situation.get("is_late_night"):
            return "concise_quiet"
        if intent_type == ConversationalIntentType.CAPABILITY_QUESTION:
            return "informative_direct"
        return "natural_friendly"
