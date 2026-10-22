# stock/stock_memory.py
"""
Stock Recommendation Memory and NLP Historical Query Engine for Jarvis V2.1.
Resolves natural-language questions regarding past stock recommendations,
derives exact IST calendar dates, and handles multi-turn context follow-ups.
"""

from datetime import datetime, timedelta
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from core.timezone_manager import get_timezone_manager

from .stock_history import StockHistoryDatabase
from .stock_models import RecommendationRecord
from .stock_tracker import StockTracker

logger = logging.getLogger("jarvis.stock.memory")

IST_TZ = get_timezone_manager().get_ist_timezone()

MONTH_MAP = {
    "january": 1, "jan": 1, "janvary": 1,
    "february": 2, "feb": 2, "farvari": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5, "mai": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8, "agast": 8,
    "september": 9, "sep": 9, "sept": 9, "sitambar": 9,
    "october": 10, "oct": 10, "aktubar": 10,
    "november": 11, "nov": 11, "navambar": 11,
    "december": 12, "dec": 12, "disambar": 12,
}

WEEKDAY_MAP = {
    "monday": 0, "somwar": 0,
    "tuesday": 1, "mangalwar": 1,
    "wednesday": 2, "budhwar": 2,
    "thursday": 3, "guruwar": 3, "veervar": 3,
    "friday": 4, "shukrawar": 4,
    "saturday": 5, "shaniwar": 5,
    "sunday": 6, "ravivar": 6, "itwar": 6,
}


class StockMemoryEngine:
    """Answers conversational questions about historical stock recommendations."""

    _instance: Optional["StockMemoryEngine"] = None

    def __init__(self, db: Optional[StockHistoryDatabase] = None):
        self.db = db or StockHistoryDatabase.get_instance()
        self.tracker = StockTracker(db=self.db)
        self.last_referenced_rec: Optional[RecommendationRecord] = None

    @classmethod
    def get_instance(cls, db: Optional[StockHistoryDatabase] = None) -> "StockMemoryEngine":
        if cls._instance is None:
            cls._instance = cls(db=db)
        return cls._instance

    # -------------------------------------------------------------------------
    # Date Resolution
    # -------------------------------------------------------------------------

    def resolve_date_expression(self, text: str, ref_date: Optional[datetime] = None) -> Optional[str]:
        """
        Interprets natural Hindi/English date references to an exact YYYY-MM-DD string in Asia/Kolkata.
        """
        now = ref_date or datetime.now(IST_TZ)
        low = text.lower().strip()

        # 1. aaj / today
        if re.search(r"\b(?:aaj|today)\b", low):
            return now.strftime("%Y-%m-%d")

        # 2. kal / yesterday (note: in recommendation query, kal refers to past yesterday)
        if re.search(r"\b(?:kal|yesterday|kal\s*wala)\b", low):
            return (now - timedelta(days=1)).strftime("%Y-%m-%d")

        # 3. parso / day before yesterday
        if re.search(r"\b(?:parso|parson|day\s*before\s*yesterday)\b", low):
            return (now - timedelta(days=2)).strftime("%Y-%m-%d")

        # 4. Specific weekday ("pichhle Friday", "last Friday", "shukrawar")
        for day_name, day_num in WEEKDAY_MAP.items():
            if day_name in low:
                # Find last occurrence of this weekday
                days_behind = (now.weekday() - day_num) % 7
                if days_behind == 0:
                    days_behind = 7  # Last week's day
                target_dt = now - timedelta(days=days_behind)
                return target_dt.strftime("%Y-%m-%d")

        # 5. DD/MM/YYYY or DD-MM-YYYY
        slash_match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", low)
        if slash_match:
            d, m, y = int(slash_match.group(1)), int(slash_match.group(2)), int(slash_match.group(3))
            return f"{y:04d}-{m:02d}-{d:02d}"

        # 6. "18 September" or "18 Sep 2026" or "September 18"
        for m_name, m_val in MONTH_MAP.items():
            # e.g. "18 september" or "18th september"
            m1 = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+" + re.escape(m_name) + r"(?:\s+(\d{4}))?\b", low)
            if m1:
                day = int(m1.group(1))
                year = int(m1.group(2)) if m1.group(2) else now.year
                return f"{year:04d}-{m_val:02d}-{day:02d}"
            # e.g. "september 18"
            m2 = re.search(r"\b" + re.escape(m_name) + r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s+(\d{4}))?\b", low)
            if m2:
                day = int(m2.group(1))
                year = int(m2.group(2)) if m2.group(2) else now.year
                return f"{year:04d}-{m_val:02d}-{day:02d}"

        return None

    # -------------------------------------------------------------------------
    # Natural Language Query Handling
    # -------------------------------------------------------------------------

    def answer_recommendation_query(self, user_text: str) -> Tuple[bool, str]:
        """
        Parses incoming question and retrieves accurate historical recommendation memory.
        Returns (handled: bool, natural_response: str).
        """
        low = user_text.lower().strip()

        # Prospective search/monitor/action queries must NEVER be hijacked by recommendation memory
        if any(p in low for p in ["dekhna chahiye", "kharidna chahiye", "buy karna", "nifty trend", "market kaisa", "monitor karo", "monitor karna"]):
            return False, ""

        # 1. Extract Symbol if explicitly mentioned (e.g. "ABC ka target kya hai?", "TCS kitne pe suggest kiya?")
        rec: Optional[RecommendationRecord] = None
        has_symbol_inquiry = any(p in low for p in ["target", "suggest", "bataya", "price", "bhav", "rate", "exit", "invalidation", "status", "kitne"])

        if has_symbol_inquiry:
            words = re.findall(r"\b[A-Za-z0-9_]+\b", user_text)
            all_recs = self.db.get_all_recommendations(limit=20)
            all_symbols = {r.symbol.upper().replace(".NS", ""): r for r in all_recs}
            all_names = {r.company_name.lower(): r for r in all_recs}

            for w in words:
                up_w = w.upper().replace(".NS", "")
                if up_w in all_symbols:
                    rec = all_symbols[up_w]
                    break
                if w.lower() in all_names:
                    rec = all_names[w.lower()]
                    break

        # 2. Date-based retrieval (e.g. "18 September ko kya stock bataya tha?", "last Friday wala stock")
        if not rec:
            is_date_rec_query = any(p in low for p in [
                "suggest kiya", "suggest kiye", "bataya tha", "bataye the", "recommend kiya", "shortlist kiya",
                "kya stock", "kaunsa stock", "konsa stock", "wala stock", "wali recommendation", "ki recommendation",
                "wala share", "kya recommend"
            ])
            if is_date_rec_query:
                resolved_date = self.resolve_date_expression(low)
                if resolved_date:
                    date_recs = self.db.get_recommendations_by_date(resolved_date)
                    if date_recs:
                        rec = date_recs[0]
                    else:
                        return True, f"{resolved_date} ko koi stock recommendation record nahi mila, Boss."

        # 3. Contextual Ellipsis / Turn N+1 Follow-up
        if not rec:
            is_followup = any(p in low for p in [
                "us time", "price kya tha", "target kya", "first target", "second target",
                "exit kab", "kab exit", "invalidation", "status kya", "target 1 hit", "target 2 hit",
                "wahi wala", "uska"
            ])
            if is_followup and self.last_referenced_rec:
                rec = self.last_referenced_rec

        # 4. Latest Recommendation query ("kaunsa stock suggest kiya tha", "latest stock recommendation")
        if not rec:
            is_latest = any(p in low for p in [
                "kaunsa stock suggest", "konsa stock suggest", "kya stock bataya", "kya stock suggest",
                "latest recommendation", "pichhli recommendation", "pichhla stock", "latest stock",
                "stocks shortlist kiye the"
            ])
            if is_latest:
                rec = self.db.get_latest_recommendation()
                if not rec:
                    return True, "Abhi tak koi historical stock recommendation save nahi hui hai, Boss."

        if not rec:
            return False, ""

        # Update last referenced record for subsequent turns
        self.last_referenced_rec = rec
        sym_clean = rec.symbol.replace(".NS", "")
        company = rec.company_name
        ref_p = rec.reference_price
        t1 = rec.target_1
        t2 = rec.target_2
        inv_p = rec.invalidation_price
        date_str = rec.recommendation_date

        # Format Indian Date Display (e.g. "18 September 2026")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            display_date = f"{dt.day} {dt.strftime('%B')} {dt.year}"
        except Exception:
            display_date = date_str

        # Specific Question Sub-Intent Handlers

        # A. Target questions ("target kya diya tha?", "ABC ka target kya hai?", "first target?")
        if any(w in low for w in ["target 1", "first target", "pehla target"]):
            return True, f"{company} ({sym_clean}) ka Target 1 ₹{t1:.2f} tha (Reference price: ₹{ref_p:.2f})."

        if any(w in low for w in ["target 2", "second target", "dusra target"]):
            return True, f"{company} ({sym_clean}) ka Target 2 ₹{t2:.2f} tha (Reference price: ₹{ref_p:.2f})."

        if "target" in low and not any(w in low for w in ["hit", "cross", "reach"]):
            return True, f"{display_date} ko {company} ({sym_clean}) ke liye Target 1 ₹{t1:.2f} aur Target 2 ₹{t2:.2f} set kiya gaya tha."

        # B. Price at suggestion ("us time price kya tha?", "ABC kitne pe suggest kiya tha?")
        if any(w in low for w in ["price kya tha", "kitne pe", "kis price pe", "reference price", "us time"]):
            return True, f"{display_date} ko recommendation ke waqt {company} ({sym_clean}) ka reference price ₹{ref_p:.2f} tha."

        # C. Exit / Invalidation ("exit kab karna tha?", "invalidation kya tha?")
        if any(w in low for w in ["exit", "stop", "invalidation", "kab nikalna", "kab exit"]):
            hold_msg = f" Original setup ka maximum holding period {rec.maximum_holding_period_days} days tha." if rec.maximum_holding_period_days else ""
            return True, f"{company} ({sym_clean}) ke original setup ka predefined invalidation level ₹{inv_p:.2f} tha.{hold_msg}"

        # D. Status check ("abhi status kya hai?", "target 1 hit hua?", "target 2 hit hua?")
        if any(w in low for w in ["status", "hit hua", "reach hua", "cross hua", "kya hua"]):
            # Get latest price snapshot or reference
            snaps = self.db.get_price_snapshots(rec.id)
            curr_p = snaps[-1].price if snaps else ref_p
            perf = self.tracker.calculate_performance(rec, curr_p)
            return True, (
                f"{company} ({sym_clean}) ka current status '{perf.tracking_status}' hai. "
                f"Reference price ₹{ref_p:.2f} tha aur current market price ₹{curr_p:.2f} hai "
                f"({perf.percentage_change:+.2f}%). Predefined invalidation level ₹{inv_p:.2f} hai."
            )

        # E. General Recommendation Summary ("kaunsa stock suggest kiya tha?", "18 September ko kya stock bataya?")
        return True, (
            f"Maine {display_date} ko {company} ({sym_clean}) suggest kiya tha. "
            f"Us waqt reference price ₹{ref_p:.2f} tha, Target 1 ₹{t1:.2f}, Target 2 ₹{t2:.2f} "
            f"aur predefined invalidation level ₹{inv_p:.2f} tha."
        )
