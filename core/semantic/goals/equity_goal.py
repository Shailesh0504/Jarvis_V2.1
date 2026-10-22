# Auto-extracted domain goal mixin
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from core.capabilities import CapabilityDescriptor, get_capability_registry
from core.conversational_intent import ConversationalIntentClassifier, ConversationalIntentType
from core.semantic.hindi_vocab import HindiVocabEngine
from core.semantic.models import IntentName
from core.semantic.normalizer import HinglishNormalizer
from core.semantic.resolution import (
    MultiDimensionalConfidence,
    ResolutionDecision,
    SemanticResolution,
)
from core.semantic.goals.base import CanonicalGoal, CanonicalSpeechAct

logger = logging.getLogger("jarvis.semantic.goal_resolver")


class EquityResearchGoalMixin:
    RE_EQUITY_EXCLUSION = re.compile(
        r"\b(?:kya\s*hota\s*hai|kya\s*hoti\s*hai|kya\s*hote\s*hain|ka\s*matlab\s*kya|"
        r"what\s*is\s*(?:a\s*)?(?:stock|share|equity|nifty)|"
        r"what\s*are\s*(?:stocks|shares)|"
        r"meaning\s*of\s*(?:stock|share)|definition\s*of\s*(?:stock|share)|"
        r"stock\s*market\s*mein\s*aaj\s*kya\s*hua|aaj\s*kya\s*hua|today\s*news|market\s*news|"
        r"portfolio\s*(?:review|check|dekho))\b",
        re.IGNORECASE,
    )
    RE_EQUITY_RESEARCH_GENERAL = re.compile(
        r"\b(?:"
        # Optional leading conversational vocatives
        r"(?:(?:bhai|boss|dost|yaar|suno|sun|jarvis)\s+)?"
        r"(?:"
        # Form 1: [mujhe] [ek/koi/achha/best] [stock/share] [suggest/recommend/batao/bata/dhoondo/chahiye] [buy karne ke liye / investment ke liye]
        r"(?:(?:mujhe|mere\s*liye|humein|apne\s*liye)\s*)?"
        r"(?:(?:indian\s*)?market\s*mein\s*)?"
        r"(?:(?:koi|kuch|ek|best|top|accha|achha|achhe|acchi|good|(?:moderate|conservative|aggressive|low|high)\s*risk(?:\s*ke)?|(?:large|mid|small)\s*cap(?:\s*ke)?|(?:it|banking|auto|pharma|energy|fmcg|defence|metals?)\s*sector(?:\s*ke)?)\s+)?"
        r"(?:indian\s*)?"
        r"(?:stocks?|shares?|equit(?:y|ies)|opportunities|setups?|candidates|ideas?)"
        r"(?:\s+(?:koi|kuch|ek|best|top|accha|achha|achhe|acchi|good))?"
        r"(?:\s+(?:stocks?|shares?))?\s*"
        r"(?:suggest|recommend|select|pick|choose|batao|bataiye|batana|bata|bata\s*sakte\s*ho|dikhao|dikhana|dikhaye|shortlist|research|analyze|dhoondo|scan|chahiye)"
        r"(?:\s+(?:karo|kijiye|kar\s*do|kardo|kar\s*ke\s*do|karke\s*do|kar))?"
        r"(?:\s+(?:buy|kharidne|invest|investment|trade|trading)\s*(?:karne\s*)?ke\s*liye)?\b|"

        # Form 1b: [mujhe] [ek/koi] [stock/share] chahiye [investment/trading ke liye]
        r"(?:(?:mujhe|mere\s*liye)\s*)?(?:ek|koi)\s+(?:stocks?|shares?)\s+chahiye(?:\s+(?:buy|kharidne|invest|investment|trade|trading)\s*(?:karne\s*)?ke\s*liye)?\b|"

        # Form 2: [buy karne ke liye / investment ke liye] [koi/achha] [stock/share] [batao/suggest karo]
        r"(?:(?:buy|kharidne|invest|investment|trade|trading)\s*(?:karne\s*)?ke\s*liye\s*)"
        r"(?:(?:mujhe|mere\s*liye)\s*)?"
        r"(?:(?:koi|kuch|ek|best|top|accha|achha|achhe|acchi|good)\s*)?"
        r"(?:stocks?|shares?|setups?|ideas?)\s*"
        r"(?:(?:dekhna\s*hai|chahiye|batao|bata|bataiye|suggest\s*karo|suggest|select\s*karo|select|dikhao|research\s*karo|dhoondo))?\b|"

        # Form 3: suggest / recommend / shortlist first
        r"(?:suggest|recommend|select|pick|choose|shortlist|research|analyze)\s*(?:karo|kijiye|karna|kar\s*do|kardo|kar\s*ke\s*do|karke\s*do|kar)?\s*"
        r"(?:(?:mujhe|mere\s*liye)\s*)?"
        r"(?:(?:koi|kuch|ek|best|top|accha|achha|achhe|acchi)\s*)?"
        r"(?:indian\s*)?"
        r"(?:stocks?|shares?|equit(?:y|ies)|opportunities|setups?|candidates|ideas?)\b|"

        # Form 4: kaunsa stock lena/buy karna chahiye / buy kar sakta hoon
        r"(?:kaunsa|konsa|kis)\s+(?:stocks?|shares?)\s+(?:ko\s+)?(?:lena\s+chahiye|buy\s+karna\s+chahiye|kharidna\s+chahiye|dekhna\s+chahiye|buy\s+karun|kharidun|buy\s+karein|research\s+karun|analyze\s+karun|buy\s+kar\s+sakta\s+hoon|buy\s+kar\s+sakte\s+hain|kharid\s+sakta\s+hoon)\b|"

        # Form 5: investment ke liye koi stock
        r"(?:(?:(?:long|short)\s*term\s+)?(?:investment|invest\s*karne)|short\s*term|long\s*term|swing(?:\s*trading)?|(?:1|ek)\s*month)\s*ke\s*liye\s*"
        r"(?:(?:koi|kuch|ek|best|top|accha|achha|achhe|acchi)\s*)?"
        r"(?:stocks?|shares?|ideas?|setups?|candidates)\s*"
        r"(?:(?:dekhna\s*hai|chahiye|batao|bata|suggest\s*karo|suggest|dikhao|research\s*karo|dhoondo))?\b|"

        # Form 6: stock choose karne mein help karo
        r"(?:stocks?|shares?)\s+choose\s+karne\s+mein\s+(?:help|madad)\s+karo\b|"

        # Form 7: market opportunities
        r"(?:stock\s*market|(?:indian\s*)?market)\s+mein\s+(?:kuch\s+)?opportunities\s+(?:batao|scan\s*karo|dhoondo)\b|"

        # Form 8: standalone equity keywords
        r"(?:equity\s*research|stock\s*shortlist|swing\s*trading\s*ideas?)\b"
        r")"
        r")",
        re.IGNORECASE,
    )
    RE_MARKET_REGIME_QUERY = re.compile(
        r"\b(?:(?:aaj\s*)?(?:indian\s*)?market\s*kaisa\s*hai|(?:aaj\s*)?market\s*ka\s*(?:trend|mood|status)\s*kya\s*hai|market\s*regime\s*(?:kya\s*hai|batao)|nifty\s*trend\s*(?:kaisa\s*hai|batao))\b",
        re.IGNORECASE,
    )
    RE_SINGLE_STOCK_EQUITY = re.compile(
        r"\b([a-zA-Z0-9_]+)\s*(?:ka\s+|ko\s+)(?:(?:1|ek)\s*month\s*(?:ke\s*liye\s*)?)?(?:technical\s*setup|analyze|buy|technical\s*analysis)\b|"
        r"\b(?:analyze|analysis)\s+([a-zA-Z0-9_]+)(?:\s+(?:stock|share))?\b|"
        r"\b([a-zA-Z0-9_]+)\s*(?:stock|share)\s*(?:ka\s*)?(?:technical\s*setup|analysis)\b",
        re.IGNORECASE,
    )
    RE_MONITOR_STOCK = re.compile(
        r"\b(?:(?:is\s*stock|ise)\s*ko\s*monitor\s*(?:list\s*mein\s*add\s*karo|karna|karo)|monitor\s+(?:stock\s+)?([a-zA-Z0-9_]+)|([a-zA-Z0-9_]+)\s*ko\s*monitor\s*(?:karo|karna|kar\s*do)|monitor\s+list\s+mein\s+add\s+karo\s+([a-zA-Z0-9_]+))\b",
        re.IGNORECASE,
    )
    RE_EQUITY_PROFILE_UPDATE = re.compile(
        r"(?:(?:mera\s*)?(?:budget|capital|amount|investment)?\s*(?:hai\s*)?(?:₹|rs\.?|inr)?\s*(\d+(?:[.,]\d+)?\s*(?:lakh|lac|k|crore|cr)?)\s*(?:budget|capital|hai|rupaye|rs)?\s*(?:aur|and|,)?\s*(moderate|conservative|aggressive|low|high)\s*(?:risk)?)|"
        r"(?:(?:risk\s*(?:profile|level)?\s*(?:hai|is)?\s*)?(moderate|conservative|aggressive|low|high)\s*risk\s*(?:hai|aur|and|,)?\s*(?:budget|capital)?\s*(?:₹|rs\.?|inr)?\s*(\d+(?:[.,]\d+)?\s*(?:lakh|lac|k|crore|cr)?))|"
        r"((?:it|banking|auto|pharma|energy|fmcg|defence|metals?)\s*sector\s*(?:mein\s*stock\s*suggest\s*karo|mein\s*dekhna|mein\s*dikhao|only|mein|ke\s*liye)?)",
        re.IGNORECASE,
    )
    RE_STOCK_RECOMMENDATION_MEMORY = re.compile(
        r"\b(?:"
        r"(?:kaunsa|konsa|kya)\s+(?:stocks?|shares?)\s+(?:suggest|recommend|bataya|shortlist)\s+(?:kiya|the|tha)|"
        r"(?:latest|pichhl[aie]|last)\s+(?:stocks?|shares?|recommendation|suggestion)|"
        r"(?:us\s*time|us\s*waqt)\s+(?:price|bhav|rate)\s*kya\s*tha|"
        r"(?:target|t1|t2|first\s*target|second\s*target)\s*(?:kya\s*diya\s*tha|kya\s*tha|kya\s*hai|hit\s*hua|cross\s*hua)|"
        r"(?:exit|invalidation|stop\s*loss)\s*(?:kab\s*karna\s*tha|kya\s*tha|kya\s*hai)|"
        r"(?:abhi\s*)?(?:uska\s*)?status\s*kya\s*hai|"
        r"(?:\d{1,2}(?:st|nd|rd|th)?\s+(?:september|october|november|december|january|february|march|april|may|june|july|august|sep|oct|nov|dec|jan|feb|mar|apr|jun|jul|aug))\s*(?:ko|wala|wali)?\s*(?:kya\s*stock|recommendation|bataya|suggest)|"
        r"(?:pichhle\s*friday|last\s*friday|kal\s*wala|aaj\s*wala)\s*(?:stocks?|recommendation)|"
        r"[a-zA-Z0-9_]+\s*(?:ka\s+target|kitne\s*pe\s*suggest)"
        r")\b",
        re.IGNORECASE,
    )
    RE_STOCK_SCREENER_SUGGESTION = re.compile(
        r"\b(?:"
        r"(?:(?:intraday|swing(?:\s*trade|\s*trading)?)\s*(?:ke\s*liye\s*)?(?:stocks?|shares?)?\s*(?:suggest\s*karo|suggest|batao|bata|chahiye|recommend|dikhao|picks?))|"
        r"(?:(?:aaj\s*)?(?:intraday|swing)\s*(?:trading\s*)?(?:ke\s*liye\s*)?(?:kaunsa|konsa|best)\s*(?:stock|share))|"
        r"(?:stock\s*suggetions?|stock\s*suggestions?|stock\s*screener)"
        r")\b",
        re.IGNORECASE,
    )
    @classmethod
    def _is_equity_research_candidate(cls, effective_text: str, context: Optional[Any]) -> bool:
        """Determines if the utterance pertains to Indian equity research or multi-turn follow-ups."""
        if cls.RE_EQUITY_EXCLUSION.search(effective_text):
            return False

        if cls.RE_STOCK_SCREENER_SUGGESTION.search(effective_text):
            return True
        if cls.RE_EQUITY_RESEARCH_GENERAL.search(effective_text):
            return True
        if cls.RE_MARKET_REGIME_QUERY.search(effective_text):
            return True
        if cls.RE_SINGLE_STOCK_EQUITY.search(effective_text):
            return True
        if cls.RE_MONITOR_STOCK.search(effective_text):
            return True
        if cls.RE_EQUITY_PROFILE_UPDATE.search(effective_text):
            return True
        if cls.RE_STOCK_RECOMMENDATION_MEMORY.search(effective_text):
            return True

        # Multi-turn context
        if context:
            if hasattr(context, "active_variables") and context.active_variables.get("pending_equity_goal"):
                return True
            if hasattr(context, "pending_goal") and context.pending_goal in ("SHORT_TERM_INVESTMENT_RESEARCH", "FIND_OR_SUGGEST_EQUITY"):
                return True
            if getattr(context, "last_intent", None) == "EQUITY_RESEARCH":
                # Check for pronoun/ellipsis like "koi suggest karo", "aur batao", "shares dekho"
                if any(w in effective_text.lower() for w in ["suggest", "batao", "recommend", "dhoondo", "shortlist", "analyze"]):
                    return True

        return False
    @classmethod
    def _resolve_equity_research_goal(
        cls,
        raw_text: str,
        effective_text: str,
        context: Optional[Any],
    ) -> SemanticResolution:
        """
        Resolves Indian Equity 1-Month Research & Decision Support goals with multi-turn slot preservation.
        """
        from core.equity_research.manager import EquityResearchManager
        from core.equity_research.models import AdvisoryMode, OutputMode
        mgr = EquityResearchManager.get_instance()

        # 1. Market Regime Inquiry ("market kaisa hai?", "nifty trend batao")
        if cls.RE_MARKET_REGIME_QUERY.search(effective_text):
            index_data = mgr.data_provider.get_index_metrics()
            regime, rationale = mgr.regime_engine.evaluate_regime(index_data)
            resp = (
                f"📈 **Current Indian Market Regime**: **{regime.value}**\n"
                f"• {rationale}\n"
                f"• India VIX: {index_data.get('india_vix', 15.0)} | "
                f"Market Breadth (A/D): {index_data.get('market_breadth', {}).get('advance_decline_ratio', 1.0):.2f}\n"
                f"• Top Sectors (1M): {', '.join(index_data.get('top_sectors_1m', []))}"
            )
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Analyze current Indian market regime context",
                speech_act=CanonicalSpeechAct("STATUS_QUESTION"),
                goal="MARKET_REGIME_QUERY",
                intent=IntentName.EQUITY_RESEARCH,
                entities={"market": "INDIA", "asset_class": "EQUITY", "horizon": "1_MONTH", "domain": "EQUITY"},
                parameters={"scope": "MARKET_REGIME", "domain": "EQUITY"},
                context_dependencies=[],
                capability_required="finance.equity_research",
                capability_available=True,
                confidence=0.98,
                action_plan={
                    "service": "equity_research",
                    "action": "market_regime",
                    "parameters": {},
                },
                decision=ResolutionDecision.ANSWER,
                response_text=resp,
            )

        # 1b. Intraday / Swing Stock Screener Suggestions ("intraday ke liye stock suggest karo", "swing trade ke liye stock batao")
        if cls.RE_STOCK_SCREENER_SUGGESTION.search(effective_text):
            from core.equity_research.stock_screener import StockScreenerEngine
            lowered = effective_text.lower()
            if "intraday" in lowered and "swing" not in lowered:
                trade_type = "intraday"
                type_name = "Intraday"
            elif "swing" in lowered and "intraday" not in lowered:
                trade_type = "swing"
                type_name = "Swing"
            else:
                trade_type = "all"
                type_name = "Intraday aur Swing"

            screener = StockScreenerEngine.get_instance()
            if trade_type == "intraday":
                items = screener.scan_intraday_stocks()
            elif trade_type == "swing":
                items = screener.scan_swing_stocks()
            else:
                all_res = screener.get_all_suggestions()
                items = all_res.get("all", [])

            try:
                if context and hasattr(context, "event_bus") and context.event_bus:
                    context.event_bus.publish("gui.navigate", {"tab": "stock_suggestions", "filter": trade_type})
            except Exception:
                pass

            if items:
                top = items[0]
                lvl = top.levels
                resp_text = (
                    f"Boss, {type_name} trading ke liye top pick hai {top.name} ({top.symbol}). "
                    f"CMP hai ₹{lvl.cmp:.1f}. Entry zone: ₹{lvl.entry_min:.1f} - ₹{lvl.entry_max:.1f}, "
                    f"Target 1: ₹{lvl.target_1:.1f} (+{lvl.target_1_pct}%), "
                    f"aur Stop-Loss: ₹{lvl.stop_loss:.1f} (-{lvl.stop_loss_pct}%). "
                    f"Risk-to-Reward ratio {lvl.risk_reward} hai. "
                    f"Maine sidebar mein Stock Suggestions cockpit open kar diya hai."
                )
            else:
                resp_text = (
                    f"Boss, is samay koi high-confluence {type_name} setups nahi mile. "
                    f"Maine sidebar mein Stock Suggestions cockpit open kar diya hai."
                )

            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Suggest {type_name} stocks with technical confluence",
                speech_act=CanonicalSpeechAct("REQUEST"),
                goal=CanonicalGoal("SUGGEST_STOCK_TRADES"),
                intent=IntentName.EQUITY_RESEARCH,
                entities={"trade_type": trade_type, "market": "INDIA", "domain": "EQUITY"},
                parameters={"trade_type": trade_type, "domain": "EQUITY"},
                context_dependencies=[],
                capability_required="finance.equity_research",
                capability_available=True,
                confidence=0.98,
                action_plan={
                    "service": "equity_research",
                    "action": "suggest_stocks",
                    "parameters": {"trade_type": trade_type},
                },
                decision=ResolutionDecision.ANSWER,
                response_text=resp_text,
            )

        # 2. Historical Recommendation Memory Retrieval (e.g. "Jarvis kaunsa stock suggest kiya tha?")
        if cls.RE_STOCK_RECOMMENDATION_MEMORY.search(effective_text):
            try:
                from stock.stock_memory import StockMemoryEngine
                mem_engine = StockMemoryEngine.get_instance()
                handled, mem_resp = mem_engine.answer_recommendation_query(effective_text)
                if handled and mem_resp:
                    return SemanticResolution(
                        raw_input=raw_text,
                        meaning="Historical stock recommendation memory retrieval",
                        speech_act=CanonicalSpeechAct("QUESTION"),
                        goal="HISTORICAL_STOCK_RECOMMENDATION_QUERY",
                        intent=IntentName.EQUITY_RESEARCH,
                        entities={"domain": "EQUITY", "sub_intent": "RECOMMENDATION_MEMORY"},
                        parameters={"response_text": mem_resp, "domain": "EQUITY"},
                        context_dependencies=[],
                        capability_required="finance.equity_research",
                        capability_available=True,
                        confidence=0.99,
                        decision=ResolutionDecision.ANSWER,
                        response_text=mem_resp,
                    )
            except Exception as e:
                logger.debug("StockMemoryEngine lookup failed: %s", e)

        # 2. Monitor Stock ("is stock ko monitor karna", "TCS ko monitor karo")
        mon_match = cls.RE_MONITOR_STOCK.search(effective_text)
        if mon_match:
            sym = mon_match.group(1) or mon_match.group(2) or mon_match.group(3)
            if not sym or sym.lower() in ("stock", "ise", "is"):
                sym = "TCS"
                if context and getattr(context, "last_entities", None):
                    sym = context.last_entities.get("symbol", "TCS")
            sym = sym.upper().replace(".NS", "")
            ok, mon_resp = mgr.monitor_stock(sym)
            return SemanticResolution(
                raw_input=raw_text,
                meaning=f"Monitor 1-month equity thesis for {sym}",
                speech_act=CanonicalSpeechAct("REQUEST"),
                goal="MONITOR_EQUITY_THESIS",
                intent=IntentName.EQUITY_RESEARCH,
                entities={"symbol": sym, "market": "INDIA", "horizon": "1_MONTH", "domain": "EQUITY"},
                parameters={"symbol": sym, "action": "monitor", "domain": "EQUITY"},
                context_dependencies=[],
                capability_required="finance.equity_research",
                capability_available=True,
                confidence=0.98,
                action_plan={
                    "service": "equity_research",
                    "action": "monitor_stock",
                    "parameters": {"symbol": sym},
                },
                decision=ResolutionDecision.ANSWER,
                response_text=mon_resp,
            )

        # 3. Single Stock Analysis ("reliance ka 1 month technical setup kaisa hai")
        single_match = cls.RE_SINGLE_STOCK_EQUITY.search(effective_text)
        is_general_suggestion = bool(cls.RE_EQUITY_RESEARCH_GENERAL.search(effective_text))
        if single_match and not is_general_suggestion and not any(w in effective_text for w in ["short term ke liye stocks", "ideas dhoondo", "suggest karo", "best stock", "select kar", "select karo", "select karke do", "koi stock", "koi share", "kuch share", "kuch stock", "kuch shares", "kuch stocks"]):
            target_sym = single_match.group(1) or single_match.group(2) or single_match.group(3)
            stop_syms = (
                "short", "term", "swing", "stock", "stocks", "shares", "ideas",
                "koi", "kuch", "karo", "kijiye", "karna", "kar", "do", "kardo",
                "select", "choose", "pick",
                "mera", "mere", "liye", "mujhe", "ek", "help", "batao", "bataiye"
            )
            if target_sym and target_sym.lower() not in stop_syms:
                target_sym = target_sym.upper().replace(".NS", "")
                cand, single_report = mgr.analyze_single_stock(target_sym, output_mode=OutputMode.STANDARD)
                return SemanticResolution(
                    raw_input=raw_text,
                    meaning=f"Analyze Indian stock {target_sym} for 1-month horizon",
                    speech_act=CanonicalSpeechAct("REQUEST"),
                    goal="ANALYZE_STOCK_SETUP",
                    intent=IntentName.EQUITY_RESEARCH,
                    entities={"symbol": target_sym, "market": "INDIA", "horizon": "1_MONTH", "domain": "EQUITY"},
                    parameters={"symbol": target_sym, "domain": "EQUITY"},
                    context_dependencies=[],
                    capability_required="finance.equity_research",
                    capability_available=True,
                    confidence=0.98,
                    action_plan={
                        "service": "equity_research",
                        "action": "analyze_stock",
                        "parameters": {"symbol": target_sym},
                    },
                    decision=ResolutionDecision.ANSWER,
                    response_text=single_report,
                )

        # 4. Extract Inline Slots & Multi-Turn Profile Updates
        extracted_capital = None
        extracted_risk = None
        extracted_sector = None

        amt_m = re.search(r"(?:(?:budget|capital|amount|investment)\s*(?:hai\s*)?(?:is\s*)?(?:₹|rs\.?|inr)?\s*(\d+(?:[.,]\d+)?\s*(?:lakh|lac|k|crore|cr)?)|(?:₹|rs\.?|inr)\s*(\d+(?:[.,]\d+)?\s*(?:lakh|lac|k|crore|cr)?)|(\d+(?:[.,]\d+)?\s*(?:lakh|lac|crore|cr))\b)", effective_text, re.I)
        if amt_m:
            matched_val = amt_m.group(1) or amt_m.group(2) or amt_m.group(3)
            if matched_val:
                amt_s = matched_val.lower().replace(",", "").strip()
                mult = 1.0
                if "lakh" in amt_s or "lac" in amt_s:
                    mult = 100000.0
                    amt_s = amt_s.replace("lakh", "").replace("lac", "").strip()
                elif "cr" in amt_s or "crore" in amt_s:
                    mult = 10000000.0
                    amt_s = amt_s.replace("crore", "").replace("cr", "").strip()
                elif "k" in amt_s:
                    mult = 1000.0
                    amt_s = amt_s.replace("k", "").strip()
                try:
                    val = float(amt_s) * mult
                    if val > 0:
                        extracted_capital = val
                except ValueError:
                    pass

        risk_m = re.search(r"\b(moderate|conservative|aggressive|low|high)\s*(?:risk)?\b", effective_text, re.I)
        if risk_m:
            extracted_risk = risk_m.group(1).upper()
            if extracted_risk == "LOW":
                extracted_risk = "CONSERVATIVE"
            elif extracted_risk == "HIGH":
                extracted_risk = "AGGRESSIVE"

        sec_m = re.search(r"\b(it|banking|auto|pharma|energy|fmcg|defence|metals?)\s*sector\b", effective_text, re.I)
        if sec_m:
            extracted_sector = sec_m.group(1).upper()

        mcap_m = re.search(r"\b(large|mid|small)\s*cap\b", effective_text, re.I)
        extracted_mcap = None
        if mcap_m:
            extracted_mcap = f"{mcap_m.group(1).lower()}_cap"

        horiz_m = re.search(r"\b(intraday|short\s*term|swing|1\s*month|long\s*term)\b", effective_text, re.I)
        extracted_horizon = None
        if horiz_m:
            h = horiz_m.group(1).lower()
            if "short" in h or "swing" in h or "1" in h:
                extracted_horizon = "swing_short_term"
            elif "long" in h:
                extracted_horizon = "3_plus_years"
            elif "intra" in h:
                extracted_horizon = "intraday"

        updates = {}
        if extracted_capital is not None:
            updates["investment_amount"] = extracted_capital
        if extracted_risk is not None:
            updates["risk_tolerance"] = extracted_risk
        if extracted_sector is not None:
            updates["sector_preference"] = extracted_sector
        if updates:
            mgr.update_profile(updates)

        active_prof = mgr.get_profile()
        final_capital = extracted_capital if extracted_capital is not None else active_prof.investment_amount
        final_risk = extracted_risk if extracted_risk is not None else (active_prof.risk_tolerance.value if active_prof.risk_tolerance else None)
        final_sector = extracted_sector if extracted_sector is not None else (active_prof.sector_preferences[0] if active_prof.sector_preferences else None)

        # 5. Missing Slot Clarification Check & Wizard Open Trigger
        is_vague_request = any(w in effective_text.lower() for w in [
            "mere liye", "suggest", "select", "select kar", "select kar ke do", "best stock", "batao", "bata", "idea", "koi stock", "koi share", "kuch stock", "kuch share", "kaunsa share", "kaunsa stock", "choose", "shortlist", "chahiye", "buy karne", "kharidne", "dikhao", "dikhaye"
        ])
        has_complete_profile = (final_capital is not None and final_capital > 0 and final_risk is not None)
        if not has_complete_profile or (is_vague_request and extracted_capital is None and extracted_risk is None and not active_prof.is_complete_for_personalized()):
            if context and hasattr(context, "active_variables"):
                context.active_variables["pending_equity_goal"] = "FIND_OR_SUGGEST_EQUITY"
            if context and hasattr(context, "missing_slots"):
                context.missing_slots = ["investment_amount", "risk_tolerance", "horizon"]
                context.pending_goal = "FIND_OR_SUGGEST_EQUITY"

            ask_text = (
                "Bilkul Boss. Main Indian equities ke technical setup aur market regime ke basis par candidates shortlist kar sakta hoon. "
                "Pehle ye confirm kar leta hoon ki aap short-term (1 month) ke liye dekh rahe hain ya long-term? "
                "Aur aapka budget/capital ya risk preference (moderate/conservative/aggressive) kya hai?"
            )
            return SemanticResolution(
                raw_input=raw_text,
                meaning="Request missing client profile information before personalized research",
                speech_act=CanonicalSpeechAct("REQUEST"),
                goal=CanonicalGoal("FIND_OR_SUGGEST_EQUITY"),
                intent=IntentName.EQUITY_RESEARCH,
                entities={
                    "horizon": extracted_horizon or "1_MONTH",
                    "market": "INDIA",
                    "asset_class": "EQUITY",
                    "domain": "EQUITY",
                    "sub_intent": "STOCK_SUGGESTION",
                    "sector": extracted_sector or final_sector,
                    "market_cap": extracted_mcap,
                    "capital": final_capital,
                    "risk": final_risk,
                },
                parameters={
                    "missing_slots": ["investment_amount", "risk_tolerance", "horizon"],
                    "domain": "EQUITY",
                    "sub_intent": "STOCK_SUGGESTION",
                    "open_wizard": True,
                    "sector": extracted_sector or final_sector,
                    "market_cap": extracted_mcap,
                    "horizon": extracted_horizon,
                    "risk": final_risk,
                    "capital": final_capital,
                },
                context_dependencies=[],
                capability_required="finance.equity_research",
                capability_available=True,
                confidence=0.98,
                needs_clarification=True,
                clarification_prompt=ask_text,
                decision=ResolutionDecision.ASK_PRECISE_CLARIFICATION,
                response_text=ask_text,
                action_plan={
                    "service": "equity_research",
                    "action": "research_shortlist",
                    "parameters": {
                        "domain": "EQUITY",
                        "sub_intent": "STOCK_SUGGESTION",
                        "open_wizard": True,
                        "sector": extracted_sector or final_sector,
                        "market_cap": extracted_mcap,
                        "horizon": extracted_horizon,
                        "risk": final_risk,
                        "capital": final_capital,
                    },
                },
            )

        # 6. Research Execution & Candidate Delivery
        report, report_text = mgr.research_shortlist(
            output_mode=OutputMode.STANDARD,
            advisory_mode=AdvisoryMode.PERSONALIZED_ADVISORY if (final_capital or final_risk) else AdvisoryMode.RESEARCH,
        )
        res_params: Dict[str, Any] = {
            "domain": "EQUITY",
            "sub_intent": "STOCK_SUGGESTION",
        }
        if final_capital is not None:
            res_params["capital"] = final_capital
        if final_risk is not None:
            res_params["risk_tolerance"] = final_risk
        if final_sector is not None:
            res_params["sector"] = final_sector

        return SemanticResolution(
            raw_input=raw_text,
            meaning="Indian equity 1-month technical research and decision-support shortlist",
            speech_act=CanonicalSpeechAct("REQUEST"),
            goal=CanonicalGoal("SHORT_TERM_INVESTMENT_RESEARCH"),
            intent=IntentName.EQUITY_RESEARCH,
            entities={
                "horizon": "1_MONTH",
                "market": "INDIA",
                "asset_class": "EQUITY",
                "domain": "EQUITY",
                "sub_intent": "STOCK_SUGGESTION",
            },
            parameters=res_params,
            context_dependencies=["client_profile"],
            capability_required="finance.equity_research",
            capability_available=True,
            confidence=0.98,
            action_plan={
                "service": "equity_research",
                "action": "research_shortlist",
                "parameters": res_params,
            },
            decision=ResolutionDecision.ANSWER,
            response_text=report_text,
        )
