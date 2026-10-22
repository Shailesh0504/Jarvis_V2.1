# plugins/equity_research/plugin.py
"""Equity Research Plugin wrapping EquityResearchManager."""

import logging
import re
from typing import Any, Dict, Optional

from plugins.base import BasePlugin
from plugins.manifest import PluginManifest, PluginResult
from core.equity_research.manager import get_equity_research_manager
from core.equity_research.models import RiskTolerance, OutputMode, UserInvestmentProfile
from .commands import ACTIONS
from .permissions import PERMISSIONS_REQUIRED

logger = logging.getLogger("jarvis.plugins.equity_research")


class EquityResearchPlugin(BasePlugin):
    """Production Indian Equity 1-Month Research Plugin for Jarvis V2.1."""

    def __init__(
        self,
        manifest: Optional[PluginManifest] = None,
        config: Optional[Dict[str, Any]] = None,
        event_bus: Optional[Any] = None,
        **kwargs: Any,
    ):
        super().__init__(manifest=manifest, config=config, event_bus=event_bus, **kwargs)
        self.manager = get_equity_research_manager()

    def get_manifest(self) -> PluginManifest:
        return PluginManifest(
            name="equity_research",
            version="1.0.0",
            description="Professional Indian Equity 1-Month Investment Research & Decision-Support Engine.",
            author="Jarvis Team",
            permissions=PERMISSIONS_REQUIRED,
            actions=ACTIONS,
        )

    @staticmethod
    def _parse_capital(val: Any) -> float:
        """Safely parse capital to float with robust fallbacks and zero crash guarantee."""
        if val is None:
            return 100000.0
        if isinstance(val, (int, float)):
            return float(val) if val > 0 else 100000.0
        try:
            from core.semantic.slot_extractor import SlotNormalizer
            norm, _ = SlotNormalizer.normalize_capital(str(val))
            if norm is not None and norm > 0:
                return float(norm)
        except Exception:
            pass
        # Direct regex search for numbers
        m = re.search(r'(\d[\d,]*(?:\.\d+)?)', str(val))
        if m:
            clean_num = m.group(1).replace(',', '')
            try:
                num = float(clean_num)
                return num if num > 0 else 100000.0
            except Exception:
                pass
        return 100000.0

    @staticmethod
    def _parse_risk_tolerance(val: Any) -> RiskTolerance:
        """Safely parse risk tolerance string/enum to RiskTolerance."""
        if isinstance(val, RiskTolerance):
            return val
        s = str(val or "").upper()
        if "CONSERVATIVE" in s or "LOW" in s or "KAM" in s:
            return RiskTolerance.CONSERVATIVE
        if "AGGRESSIVE" in s or "HIGH" in s or "ZYADA" in s or "JYADA" in s:
            return RiskTolerance.AGGRESSIVE
        return RiskTolerance.MODERATE

    def execute(self, action_name: str, parameters: Optional[Dict[str, Any]] = None) -> PluginResult:
        parameters = parameters or {}

        try:
            if action_name == "research_shortlist":
                profile = None
                capital = parameters.get("capital") or parameters.get("investment_amount")
                risk_str = parameters.get("risk_tolerance") or parameters.get("risk_profile")
                sector = parameters.get("sector_preference") or parameters.get("sector")
                mode_str = parameters.get("output_mode", "STANDARD").upper()
                output_mode = getattr(OutputMode, mode_str, OutputMode.STANDARD)

                if capital is not None or risk_str is not None:
                    risk = self._parse_risk_tolerance(risk_str)
                    profile = UserInvestmentProfile(
                        investment_amount=self._parse_capital(capital),
                        risk_tolerance=risk,
                        sector_preferences=[sector] if sector else [],
                    )

                report, formatted_text = self.manager.research_shortlist(
                    profile=profile,
                    sector_filter=sector,
                    output_mode=output_mode,
                )
                return PluginResult(
                    success=True,
                    data={
                        "report_text": formatted_text,
                        "candidate_count": len(report.candidates),
                        "regime": report.market_regime.value if report.market_regime else "UNKNOWN",
                        "market_status": report.market_status.value,
                    },
                )

            elif action_name == "analyze_stock":
                symbol = parameters.get("symbol", "").strip().upper()
                if not symbol:
                    return PluginResult(success=False, error="Stock symbol is required.")

                mode_str = parameters.get("output_mode", "STANDARD").upper()
                output_mode = getattr(OutputMode, mode_str, OutputMode.STANDARD)

                candidate, formatted_text = self.manager.analyze_single_stock(symbol, output_mode=output_mode)
                if not candidate:
                    return PluginResult(
                        success=False,
                        error=f"Could not find or analyze stock symbol '{symbol}'. Ensure it is a liquid NSE ticker.",
                    )

                return PluginResult(
                    success=True,
                    data={
                        "symbol": symbol,
                        "report_text": formatted_text,
                        "score": candidate.multi_factor_score,
                        "evidence_tier": candidate.evidence_tier.value,
                        "strategy": candidate.strategy_matched,
                    },
                )

            elif action_name == "market_regime":
                index_data = self.manager.data_provider.get_index_metrics()
                regime, rationale = self.manager.regime_engine.evaluate_regime(index_data)
                status, last_session = self.manager.data_provider.get_market_status()
                summary_text = (
                    f"Market Status: {status.value} (Last session: {last_session}). "
                    f"Current Indian Market Regime: {regime.value}.\n"
                    f"{rationale}"
                )
                return PluginResult(
                    success=True,
                    data={
                        "summary_text": summary_text,
                        "regime": regime.value,
                        "market_status": status.value,
                        "index_data": index_data,
                    },
                )

            elif action_name == "monitor_stock":
                action_type = parameters.get("action_type", "list").lower()
                symbol = parameters.get("symbol", "").strip().upper()

                if action_type == "add":
                    if not symbol:
                        return PluginResult(success=False, error="Symbol is required to monitor.")
                    ok, msg = self.manager.monitor_stock(symbol)
                    return PluginResult(
                        success=ok,
                        data={"message": msg},
                        error=None if ok else msg,
                    )

                elif action_type == "check":
                    expired = self.manager.monitor.check_expirations()
                    return PluginResult(success=True, data={"expired": expired})

                else:
                    theses = self.manager.monitor.list_active_theses()
                    return PluginResult(
                        success=True,
                        data={"active_theses": [t.to_dict() for t in theses], "count": len(theses)},
                    )

            elif action_name == "update_profile":
                updates = {}
                if "capital" in parameters or "investment_amount" in parameters:
                    cap_val = parameters.get("capital") or parameters.get("investment_amount")
                    updates["investment_amount"] = self._parse_capital(cap_val)
                if "risk_tolerance" in parameters or "risk_profile" in parameters:
                    risk_val = parameters.get("risk_tolerance") or parameters.get("risk_profile")
                    updates["risk_tolerance"] = self._parse_risk_tolerance(risk_val).value
                if "sector_preference" in parameters or "sector" in parameters:
                    updates["sector_preference"] = parameters.get("sector_preference") or parameters.get("sector")

                updated = self.manager.update_profile(updates)
                return PluginResult(
                    success=True,
                    data={
                        "message": f"Profile updated: Capital ₹{updated.investment_amount:,.0f}, Risk: {updated.risk_tolerance.value}.",
                        "profile": updated.to_dict(),
                    },
                )

            elif action_name == "open_wizard":
                from stock.stock_router import StockWebServer
                from stock.stock_service import StockService
                import webbrowser

                stock_server = StockWebServer.get_instance()
                wizard_url = stock_server.start()
                stock_service = StockService.get_instance()
                stock_service.initialize_workflow(initial_params=parameters)
                webbrowser.open(wizard_url)
                return PluginResult(
                    success=True,
                    data={
                        "wizard_url": wizard_url,
                        "message": "Bilkul. Main stock selection ke liye kuch details chahunga. Maine selection window open kar di hai.",
                    },
                )

            elif action_name == "suggest_stocks":
                from core.equity_research.stock_screener import StockScreenerEngine
                trade_type = str(parameters.get("trade_type", "all")).lower()
                screener = StockScreenerEngine.get_instance()

                # Emit navigation event so GUI opens the sidebar view
                if hasattr(self, "event_bus") and self.event_bus:
                    self.event_bus.publish("gui.navigate", {"tab": "stock_suggestions", "filter": trade_type})

                if "intraday" in trade_type:
                    suggestions = screener.scan_intraday_stocks()
                    type_str = "Intraday"
                elif "swing" in trade_type:
                    suggestions = screener.scan_swing_stocks()
                    type_str = "Swing"
                else:
                    all_dict = screener.get_all_suggestions()
                    suggestions = all_dict.get("all", [])
                    type_str = "Intraday & Swing"

                if not suggestions:
                    spoken = f"Boss, is samay koi high-confluence {type_str} setups nahi mile. Market data update hone par dobara check karein."
                    return PluginResult(success=True, data={"message": spoken})

                top = suggestions[0]
                lvl = top.levels
                spoken = (
                    f"Boss, {type_str} ke liye top pick hai {top.name} ({top.symbol}). "
                    f"CMP hai ₹{lvl.cmp:.1f}. Entry zone ₹{lvl.entry_min:.1f} se ₹{lvl.entry_max:.1f}, "
                    f"Target ₹{lvl.target_1:.1f} (+{lvl.target_1_pct}%), "
                    f"aur Stop-Loss ₹{lvl.stop_loss:.1f} (-{lvl.stop_loss_pct}%). "
                    f"Maine sidebar mein poora trade setup cockpit open kar diya hai."
                )
                return PluginResult(
                    success=True,
                    data={
                        "message": spoken,
                        "top_pick": top.to_dict(),
                        "total_count": len(suggestions),
                        "trade_type": type_str,
                    },
                )

            else:
                return PluginResult(success=False, error=f"Unknown action '{action_name}'")

        except Exception as e:
            logger.error("EquityResearchPlugin error on %s: %s", action_name, e, exc_info=True)
            return PluginResult(
                success=False,
                error="Stock research request process karte samay takneeki samasya aayi. Kripya thodi der baad try karein.",
            )
