# core/semantic/slot_extractor.py
"""
Generic, Authoritative Semantic Slot Extraction, Normalization & Type-Safe Validation Engine.
Decomposes natural English, Hindi, and Hinglish utterances into individual slot candidates,
normalizes them to canonical forms, and validates each slot against its schema.
Guarantees zero raw Python exceptions and transactional multi-turn slot preservation.
"""

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("jarvis.semantic.slot_extractor")


class ValidationStatus(str, Enum):
    VALID = "VALID"
    INVALID = "INVALID"
    UNSET = "UNSET"


@dataclass
class SlotValue:
    """Represents a validated, normalized individual slot candidate."""
    raw_value: str
    normalized_value: Any
    confidence: float = 0.95
    source_span: Tuple[int, int] = (0, 0)
    validation_status: ValidationStatus = ValidationStatus.VALID
    reason: str = ""


@dataclass
class SlotExtractionResult:
    """
    Container for multi-slot extraction results.
    Provides rich attribute inspection alongside dict-like mapping access.
    """
    slots: Dict[str, SlotValue] = field(default_factory=dict)
    unresolved_slots: List[str] = field(default_factory=list)
    confidence: float = 0.95
    source_text: str = ""
    raw_matches: Dict[str, str] = field(default_factory=dict)
    has_matches: bool = False

    def __getitem__(self, key: str) -> Any:
        item = self.slots[key]
        return item.normalized_value if isinstance(item, SlotValue) else item

    def get(self, key: str, default: Any = None) -> Any:
        if key in self.slots:
            item = self.slots[key]
            return item.normalized_value if isinstance(item, SlotValue) else item
        return default

    def get_slot_value(self, key: str) -> Optional[SlotValue]:
        return self.slots.get(key)

    def keys(self):
        return self.slots.keys()

    def values(self):
        return [v.normalized_value if isinstance(v, SlotValue) else v for v in self.slots.values()]

    def items(self):
        return [(k, v.normalized_value if isinstance(v, SlotValue) else v) for k, v in self.slots.items()]

    def slot_items(self):
        return self.slots.items()

    def __contains__(self, key: str) -> bool:
        return key in self.slots

    def __iter__(self):
        return iter(self.slots)

    def __len__(self) -> int:
        return len(self.slots)

    def __bool__(self) -> bool:
        return self.has_matches or bool(self.slots)


# Backward compatibility alias
ExtractedSlots = SlotExtractionResult


class SlotNormalizer:
    """Normalizes natural language slot tokens into canonical typed representations."""

    HINDI_NUMBERS = {
        "ek": 1,
        "do": 2,
        "teen": 3,
        "char": 4,
        "paanch": 5,
        "panch": 5,
        "chhe": 6,
        "saat": 7,
        "aath": 8,
        "nau": 9,
        "dus": 10,
        "gyarah": 11,
        "barah": 12,
        "bees": 20,
        "tees": 30,
        "chaalis": 40,
        "chalis": 40,
        "pachaas": 50,
        "pachas": 50,
        "saath": 60,
        "sattar": 70,
        "assi": 80,
        "nabbe": 90,
        "sau": 100,
        "hazaar": 1000,
        "hazar": 1000,
        "lakh": 100000,
        "lac": 100000,
        "crore": 10000000,
        "cr": 10000000,
    }

    @classmethod
    def normalize_horizon(cls, raw: str) -> Optional[str]:
        cleaned = raw.strip().lower()
        if cleaned in ("1_month", "short_term"):
            return "1_MONTH"
        if cleaned == "long_term":
            return "LONG_TERM"
        if any(w in cleaned for w in ("1 month", "1month", "one month", "ek month", "ek mahina", "1 mahine", "short term", "swing")):
            return "1_MONTH"
        if any(w in cleaned for w in ("long term", "longterm", "lamba samay", "saal", "year")):
            return "LONG_TERM"
        return None

    @classmethod
    def normalize_capital(cls, raw: str) -> Tuple[Optional[float], str]:
        """Normalizes extracted capital string into numeric float and currency."""
        cleaned = raw.strip().lower().replace(",", "")
        currency = "INR"

        # Hindi word number check (e.g. 'pachaas hazaar')
        m_hindi = re.search(
            r"\b(ek|do|teen|char|paanch|panch|dus|bees|tees|chaalis|chalis|pachaas|pachas|saath|sattar|assi|nabbe)\s+(hazaar|hazar|lakh|lac|crore|cr)\b",
            cleaned,
            re.I,
        )
        if m_hindi:
            base = float(cls.HINDI_NUMBERS.get(m_hindi.group(1).lower(), 1))
            mult = float(cls.HINDI_NUMBERS.get(m_hindi.group(2).lower(), 1))
            return base * mult, currency

        # Suffix multipliers
        mult = 1.0
        if re.search(r"(?:(?<=\d)\s*(?:lakh|lac)\b|\b(?:lakh|lac)\b)", cleaned):
            mult = 100000.0
            cleaned = re.sub(r"(?:(?<=\d)\s*(?:lakh|lac)\b|\b(?:lakh|lac)\b)", "", cleaned).strip()
        elif re.search(r"(?:(?<=\d)\s*(?:crore|cr)\b|\b(?:crore|cr)\b)", cleaned):
            mult = 10000000.0
            cleaned = re.sub(r"(?:(?<=\d)\s*(?:crore|cr)\b|\b(?:crore|cr)\b)", "", cleaned).strip()
        elif re.search(r"(?:(?<=\d)\s*k\b|\b(?:k|hazaar|hazar|thousand)\b)", cleaned):
            mult = 1000.0
            cleaned = re.sub(r"(?:(?<=\d)\s*k\b|\b(?:k|hazaar|hazar|thousand)\b)", "", cleaned).strip()

        # Extract numeric digits
        m_num = re.search(r"(\d+(?:\.\d+)?)", cleaned)
        if m_num:
            try:
                val = float(m_num.group(1)) * mult
                return val, currency
            except ValueError:
                pass
        return None, currency

    @classmethod
    def normalize_risk(cls, raw: str) -> Optional[str]:
        cleaned = raw.strip().lower()
        if any(w in cleaned for w in ("moderate", "medium", "beech", "balanced")):
            return "MODERATE"
        if any(w in cleaned for w in ("conservative", "low", "kam", "safe", "surakshit")):
            return "CONSERVATIVE"
        if any(w in cleaned for w in ("aggressive", "high", "zyada", "jyada")):
            return "AGGRESSIVE"
        return None

    @classmethod
    def normalize_sector(cls, raw: str) -> Optional[str]:
        cleaned = raw.strip().upper()
        if "IT" in cleaned or "TECH" in cleaned:
            return "IT"
        if "BANK" in cleaned:
            return "BANKING"
        if "AUTO" in cleaned:
            return "AUTO"
        if "PHARMA" in cleaned:
            return "PHARMA"
        if "ENERGY" in cleaned or "POWER" in cleaned:
            return "ENERGY"
        if "FMCG" in cleaned:
            return "FMCG"
        if "DEFENCE" in cleaned or "DEFENSE" in cleaned:
            return "DEFENCE"
        if "METAL" in cleaned:
            return "METALS"
        return None


class TypeSafeSlotValidator:
    """
    Performs schema validation on individual extracted slot candidates.
    Never operates on the full conversational sentence.
    Catches all internal conversion errors and returns structured ValidationStatus.
    """

    VALID_HORIZONS = {"1_MONTH", "SHORT_TERM", "LONG_TERM"}
    VALID_RISK_PROFILES = {"CONSERVATIVE", "MODERATE", "AGGRESSIVE"}
    VALID_CURRENCIES = {"INR", "USD", "EUR", "GBP"}

    @classmethod
    def validate_slot(cls, slot_name: str, candidate_val: Any, raw_str: str = "") -> Tuple[ValidationStatus, Any, str]:
        canonical_name = slot_name.lower().strip()
        if candidate_val is None:
            return ValidationStatus.INVALID, None, f"EMPTY_{canonical_name.upper()}"

        # 1. Capital / Investment Amount (NUMERIC FLOAT/INT >= 0)
        if canonical_name in ("capital", "investment_amount", "amount", "budget"):
            # Never validate an entire unextracted conversational sentence as capital
            val_str = str(candidate_val).strip()
            word_count = len(val_str.split())
            if word_count > 4 and not any(w in val_str.lower() for w in cls.HINDI_NUMBERS):
                return ValidationStatus.INVALID, None, "SENTENCE_CANNOT_BE_CAPITAL"

            val, _ = SlotNormalizer.normalize_capital(str(candidate_val))
            if val is not None and val >= 0:
                return ValidationStatus.VALID, val, ""
            return ValidationStatus.INVALID, None, "UNPARSEABLE_AMOUNT"

        # 2. Risk Profile / Tolerance (ENUM - NEVER NUMERIC)
        if canonical_name in ("risk_profile", "risk_tolerance", "risk"):
            # Guard: risk profile is NOT numeric. Never call float/int on it.
            if isinstance(candidate_val, (int, float)):
                return ValidationStatus.INVALID, None, "RISK_CANNOT_BE_NUMERIC: Risk profile cannot be numeric"

            cand_str = str(candidate_val).strip()
            if cand_str.isdigit() or re.match(r'^\d', cand_str):
                return ValidationStatus.INVALID, None, "RISK_CANNOT_BE_NUMERIC: Risk profile cannot be numeric"

            normalized_risk = SlotNormalizer.normalize_risk(cand_str)
            if normalized_risk in cls.VALID_RISK_PROFILES:
                return ValidationStatus.VALID, normalized_risk, ""
            return ValidationStatus.INVALID, None, "INVALID_RISK_PROFILE"

        # 3. Horizon (ENUM)
        if canonical_name in ("horizon", "time_horizon", "duration"):
            normalized_horizon = SlotNormalizer.normalize_horizon(str(candidate_val))
            if normalized_horizon in cls.VALID_HORIZONS:
                return ValidationStatus.VALID, normalized_horizon, ""
            return ValidationStatus.INVALID, None, "INVALID_HORIZON"

        # 4. Currency (ENUM)
        if canonical_name == "currency":
            curr_str = str(candidate_val).upper().strip()
            if curr_str in cls.VALID_CURRENCIES:
                return ValidationStatus.VALID, curr_str, ""
            return ValidationStatus.INVALID, None, "INVALID_CURRENCY"

        # 5. Sector Preference
        if canonical_name in ("sector", "sector_preference"):
            normalized_sec = SlotNormalizer.normalize_sector(str(candidate_val))
            if normalized_sec:
                return ValidationStatus.VALID, normalized_sec, ""
            return ValidationStatus.INVALID, None, "INVALID_SECTOR"

        # 6. Generic non-empty string slots (file_target, media_target, etc.)
        str_val = str(candidate_val).strip()
        if str_val and len(str_val.split()) <= 8:
            return ValidationStatus.VALID, str_val, ""
        return ValidationStatus.INVALID, None, f"INVALID_{canonical_name.upper()}"


class SemanticSlotExtractor:
    """
    Authoritative Semantic Slot Extractor for Jarvis multi-turn conversations.
    Guarantees:
    1. Simultaneous extraction of multiple pending slots in a single compound sentence.
    2. Deep Hinglish normalization (e.g. 'pachaas hazaar' -> 50000, 'ek mahina' -> 1_MONTH).
    3. Strict slot verification against schema (prevents false slot capture).
    4. Domain-agnostic extensibility across Equity, Reminders, Media, Apps, etc.
    """

    HINDI_NUMBERS = SlotNormalizer.HINDI_NUMBERS

    # Commands indicating an interruption rather than a slot answer
    INTERRUPTION_COMMANDS = [
        re.compile(r"\b(?:volume|awaz|awaaz|aawaz)\s*(?:ko\s*)?(?:\d+|kam|badhao|mute|tez)\b", re.I),
        re.compile(r"\b(?:volume|awaz|awaaz|aawaz)\s+(?:kam|badhao|dheemi|tez)\b", re.I),
        re.compile(r"\b(?:open|kholo|launch|chalao)\s+(?:chrome|brave|notepad|calc|calculator|excel|word|spotify|vlc)\b", re.I),
        re.compile(r"\b(?:system\s*lock|lock\s*(?:pc|computer|system)|shutdown|restart)\b", re.I),
        re.compile(r"\b(?:aaj\s*ka\s*)?(?:time|weather|mausam|samay)\s*(?:kya|batao)\b", re.I),
        re.compile(r"\b(?:stop|pause|ruk\s*jao|ruko|chup|shant|band\s*karo)\b", re.I),
        # Repeat-last-answer and task-done markers are never slot values
        re.compile(r"\b(?:ek\s+baar\s+)?(?:phir|dobara|fir)(?:\s+se)?\s+(?:batao|bolo|sunao|dikhao|suna\s+do|bata\s+do)\b", re.I),
        re.compile(r"^(?:ho\s+gaya(?:\s+hai)?|done(?:\s+ho\s+gaya)?|kaam\s+ho\s+gaya)\s*[.!?]?\s*$", re.I),
    ]

    @classmethod
    def extract_slots(
        cls,
        text: str,
        missing_slots: Optional[List[str]] = None,
        expected_slots: Optional[List[str]] = None,
        workflow_type: str = "",
    ) -> SlotExtractionResult:
        """
        Authoritative extraction pipeline:
        1. Semantic Slot Decomposition
        2. Slot Candidate Normalization
        3. Per-Slot Type Validation
        Produces structured SlotExtractionResult.
        """
        clean_text = str(text).strip() if not isinstance(text, str) else text.strip()
        target_missing = expected_slots or missing_slots or []
        result = SlotExtractionResult(source_text=clean_text)

        raw_matches: Dict[str, str] = {}
        slots: Dict[str, SlotValue] = {}

        # -------------------------------------------------------------------
        # 1. Horizon Slot Candidate Extraction & Validation
        # -------------------------------------------------------------------
        h_cand, h_raw, h_span = cls._extract_horizon_candidate(clean_text)
        if h_cand:
            h_norm = SlotNormalizer.normalize_horizon(h_cand)
            status, val, reason = TypeSafeSlotValidator.validate_slot("horizon", h_norm, raw_str=h_raw)
            if status == ValidationStatus.VALID:
                slot_val = SlotValue(
                    raw_value=h_raw,
                    normalized_value=val,
                    confidence=0.98,
                    source_span=h_span,
                    validation_status=status
                )
                slots["horizon"] = slot_val
                raw_matches["horizon"] = h_raw

        # -------------------------------------------------------------------
        # 2. Capital / Investment Amount Extraction & Validation
        # -------------------------------------------------------------------
        c_cand, c_raw, c_span, curr = cls._extract_capital_candidate(clean_text)
        if c_cand:
            c_norm, c_curr = SlotNormalizer.normalize_capital(c_cand)
            status, val, reason = TypeSafeSlotValidator.validate_slot("capital", c_norm, raw_str=c_raw)
            if status == ValidationStatus.VALID:
                slot_val = SlotValue(
                    raw_value=c_raw,
                    normalized_value=val,
                    confidence=0.98,
                    source_span=c_span,
                    validation_status=status
                )
                slots["capital"] = slot_val
                slots["investment_amount"] = slot_val
                raw_matches["capital"] = c_raw

                # Add currency slot
                curr_status, curr_val, _ = TypeSafeSlotValidator.validate_slot("currency", curr or c_curr)
                if curr_status == ValidationStatus.VALID:
                    slots["currency"] = SlotValue(
                        raw_value=curr or c_curr,
                        normalized_value=curr_val,
                        confidence=0.99,
                        validation_status=ValidationStatus.VALID
                    )

        # -------------------------------------------------------------------
        # 3. Risk Profile / Tolerance Extraction & Validation
        # -------------------------------------------------------------------
        r_cand, r_raw, r_span = cls._extract_risk_candidate(clean_text)
        if r_cand:
            r_norm = SlotNormalizer.normalize_risk(r_cand)
            status, val, reason = TypeSafeSlotValidator.validate_slot("risk_profile", r_norm, raw_str=r_raw)
            if status == ValidationStatus.VALID:
                slot_val = SlotValue(
                    raw_value=r_raw,
                    normalized_value=val,
                    confidence=0.98,
                    source_span=r_span,
                    validation_status=status
                )
                slots["risk_profile"] = slot_val
                slots["risk_tolerance"] = slot_val
                raw_matches["risk_profile"] = r_raw

        # -------------------------------------------------------------------
        # 4. Sector Preference Extraction & Validation
        # -------------------------------------------------------------------
        s_cand, s_raw, s_span = cls._extract_sector_candidate(clean_text)
        if s_cand:
            s_norm = SlotNormalizer.normalize_sector(s_cand)
            status, val, reason = TypeSafeSlotValidator.validate_slot("sector", s_norm, raw_str=s_raw)
            if status == ValidationStatus.VALID:
                slot_val = SlotValue(
                    raw_value=s_raw,
                    normalized_value=val,
                    confidence=0.95,
                    source_span=s_span,
                    validation_status=status
                )
                slots["sector"] = slot_val
                slots["sector_preference"] = slot_val
                raw_matches["sector"] = s_raw

        # -------------------------------------------------------------------
        # 5. Domain-agnostic slot extraction for explicitly missing slots
        # -------------------------------------------------------------------
        if target_missing:
            for s in target_missing:
                s_clean = s.lower()
                if s_clean in ("file_target", "file") and "file_target" not in slots:
                    f_cand, f_raw, f_span = cls._extract_file_candidate(clean_text)
                    if f_cand:
                        status, val, reason = TypeSafeSlotValidator.validate_slot("file_target", f_cand, raw_str=f_raw)
                        if status == ValidationStatus.VALID:
                            slots["file_target"] = SlotValue(raw_value=f_raw, normalized_value=val, source_span=f_span)
                            raw_matches["file_target"] = f_raw
                elif s_clean in ("media_target", "song", "movie", "video") and "media_target" not in slots:
                    m_cand, m_raw, m_span = cls._extract_media_candidate(clean_text)
                    if m_cand:
                        status, val, reason = TypeSafeSlotValidator.validate_slot("media_target", m_cand, raw_str=m_raw)
                        if status == ValidationStatus.VALID:
                            slots["media_target"] = SlotValue(raw_value=m_raw, normalized_value=val, source_span=m_span)
                            raw_matches["media_target"] = m_raw

        result.slots = slots
        result.raw_matches = raw_matches
        result.has_matches = bool(slots)
        return result

    @classmethod
    def is_interruption(cls, text: str, missing_slots: Optional[List[str]] = None) -> bool:
        """
        Determines if the utterance is an interruption command rather than a slot answer.
        """
        clean_text = str(text).strip() if not isinstance(text, str) else text.strip()
        lowered = clean_text.lower()

        # Check explicit interruption patterns (volume, system control, etc.)
        for pat in cls.INTERRUPTION_COMMANDS:
            if pat.search(lowered):
                return True

        return False

    # -----------------------------------------------------------------------
    # Candidate Extraction Spanning Methods
    # -----------------------------------------------------------------------

    @classmethod
    def _extract_horizon_candidate(cls, text: str) -> Tuple[Optional[str], str, Tuple[int, int]]:
        one_month_pat = re.compile(
            r"\b(?:"
            r"(?:1|ek|one)\s*(?:month|mahina|mahine)(?:\s*ke\s*liye)?"
            r"|short\s*term\s*(?:1|ek|one)?\s*(?:month|mahina|mahine)?"
            r"|next\s*(?:1|one)\s*month"
            r"|around\s*1\s*month"
            r"|1\s*m\b"
            r"|short\s*term"
            r"|swing(?:\s*trading)?"
            r")\b",
            re.IGNORECASE,
        )
        m = one_month_pat.search(text)
        if m:
            return m.group(0), m.group(0), m.span()

        long_pat = re.compile(r"\b(?:long\s*term|lamba\s*samay|1\s*saal|1\s*year)\b", re.I)
        m2 = long_pat.search(text)
        if m2:
            return m2.group(0), m2.group(0), m2.span()

        return None, "", (0, 0)

    @classmethod
    def _extract_capital_candidate(cls, text: str) -> Tuple[Optional[str], str, Tuple[int, int], str]:
        currency = "INR"

        # Guard against volume, brightness, zoom, or non-financial numerical settings
        if re.search(r"\b(?:volume|awaz|awaaz|brightness|zoom|step)\b", text, re.IGNORECASE):
            return None, "", (0, 0), currency

        # 1. Hindi textual numbers like 'pachaas hazaar', 'ek lakh', 'bees hazaar'
        hindi_m = re.search(
            r"\b(ek|do|teen|char|paanch|panch|dus|bees|tees|chaalis|chalis|pachaas|pachas|saath|sattar|assi|nabbe)\s+(hazaar|hazar|lakh|lac|crore|cr)\b",
            text,
            re.IGNORECASE,
        )
        if hindi_m:
            return hindi_m.group(0), hindi_m.group(0), hindi_m.span(), currency

        # 2. Standard numeric expressions with optional units and currency symbols
        num_pat = re.compile(
            r"(?:(?:mera\s*)?(?:budget|capital|amount|investment|paas)\s*(?:hai\s*)?(?:is\s*)?(?:₹|rs\.?|inr)?\s*(\d+(?:[.,]\d+)?\s*(?:lakh|lac|crore|cr|k\b|hazaar\b|hazar\b|thousand\b)?))|"
            r"(?:(?:₹|rs\.?|inr)\s*(\d+(?:[.,]\d+)?\s*(?:lakh|lac|crore|cr|k\b|hazaar\b|hazar\b|thousand\b)?))|"
            r"(\d+(?:[.,]\d+)?\s*(?:lakh|lac|crore|cr|k\b|hazaar\b|hazar\b|thousand\b))|"
            r"\b(\d{4,}(?:[.,]\d+)?)\b",
            re.IGNORECASE,
        )
        for match in num_pat.finditer(text):
            val_str = match.group(1) or match.group(2) or match.group(3) or match.group(4)
            if not val_str:
                continue
            cleaned_val = val_str.lower().replace(",", "").strip()
            # Must contain at least one digit
            if any(c.isdigit() for c in cleaned_val):
                return val_str, match.group(0).strip(), match.span(), currency

        return None, "", (0, 0), currency

    @classmethod
    def _extract_risk_candidate(cls, text: str) -> Tuple[Optional[str], str, Tuple[int, int]]:
        # Moderate / Medium
        mod_pat = re.compile(
            r"\b(?:"
            r"moderate(?:\s*risk)?"
            r"|medium(?:\s*risk)?"
            r"|risk\s*(?:moderate|medium)"
            r"|thoda\s*moderate(?:\s*risk)?"
            r"|main\s*moderate\s*risk\s*(?:le\s*sakta\s*hoon)?"
            r"|beech\s*ka\s*risk"
            r"|balanced"
            r")\b",
            re.IGNORECASE,
        )
        m = mod_pat.search(text)
        if m:
            return m.group(0), m.group(0), m.span()

        # Conservative / Low
        cons_pat = re.compile(
            r"\b(?:"
            r"conservative(?:\s*risk)?"
            r"|low\s*risk"
            r"|risk\s*(?:conservative|low)"
            r"|kam\s*risk"
            r"|safe(?:\s*side)?"
            r"|surakshit"
            r")\b",
            re.IGNORECASE,
        )
        m2 = cons_pat.search(text)
        if m2:
            return m2.group(0), m2.group(0), m2.span()

        # Aggressive / High
        agg_pat = re.compile(
            r"\b(?:"
            r"aggressive(?:\s*risk)?"
            r"|high\s*risk"
            r"|risk\s*(?:aggressive|high)"
            r"|zyada\s*risk"
            r"|high\s*returns"
            r")\b",
            re.IGNORECASE,
        )
        m3 = agg_pat.search(text)
        if m3:
            return m3.group(0), m3.group(0), m3.span()

        return None, "", (0, 0)

    @classmethod
    def _extract_sector_candidate(cls, text: str) -> Tuple[Optional[str], str, Tuple[int, int]]:
        sec_pat = re.compile(
            r"\b(it|banking|auto|pharma|energy|fmcg|defence|metals?)\s*(?:sector)?\b",
            re.IGNORECASE,
        )
        m = sec_pat.search(text)
        if m:
            return m.group(1), m.group(0), m.span()
        return None, "", (0, 0)

    @classmethod
    def _extract_file_candidate(cls, text: str) -> Tuple[Optional[str], str, Tuple[int, int]]:
        cleaned = re.sub(r"\b(?:wali|wala|file|kholo|open|karo|please|excel|sheet)\b", "", text, flags=re.I).strip()
        if cleaned:
            return cleaned, cleaned, (0, len(text))
        return None, "", (0, 0)

    @classmethod
    def _extract_media_candidate(cls, text: str) -> Tuple[Optional[str], str, Tuple[int, int]]:
        cleaned = re.sub(r"\b(?:gaana|song|video|chalao|play|karo|sunna|hai|movie|please)\b", "", text, flags=re.I).strip()
        if cleaned:
            return cleaned, cleaned, (0, len(text))
        return None, "", (0, 0)
