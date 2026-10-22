# brain/classifier.py
"""Intent and entity classifier combining rules, regex, plugin schemas, and LLM classification."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from core.intent import Intent, IntentResult, IntentType

logger = logging.getLogger("jarvis.brain.classifier")


class IntentClassifier:
    """Classifies user queries into structured Intents using rules and LLM fallback."""

    def __init__(self, llm_provider: Optional[Any] = None, plugin_manager: Optional[Any] = None, learning_manager: Optional[Any] = None):
        self.llm = llm_provider
        self.plugin_manager = plugin_manager
        self.learning_manager = learning_manager
        self._init_rules()

    def _init_rules(self) -> None:
        """Precompiled rules for high-speed deterministic matching."""
        self.system_patterns = [
            (re.compile(r"^(exit|quit|shutdown|goodbye|bye)$", re.IGNORECASE), "exit", IntentType.SYSTEM),
            (re.compile(r"^(status|health|system status|check status)$", re.IGNORECASE), "status", IntentType.SYSTEM),
            (re.compile(r"^(help|commands|what can you do)$", re.IGNORECASE), "help", IntentType.SYSTEM),
            (re.compile(r"^(?:plugins|plugin list|show plugins|list plugins)$", re.IGNORECASE), "plugins_list", IntentType.SYSTEM),
            (re.compile(r"^(?:plugin\s+enable|enable\s+plugin)\s+([a-zA-Z0-9_\-]+)$", re.IGNORECASE), "plugin_enable", IntentType.SYSTEM),
            (re.compile(r"^(?:plugin\s+disable|disable\s+plugin)\s+([a-zA-Z0-9_\-]+)$", re.IGNORECASE), "plugin_disable", IntentType.SYSTEM),
            (re.compile(r"^(?:plugin\s+reload|reload\s+plugin)\s+([a-zA-Z0-9_\-]+)$", re.IGNORECASE), "plugin_reload", IntentType.SYSTEM),
        ]

        self.memory_store_patterns = [
            re.compile(r"^(?:remember|note)\s+(?:that\s+)?my\s+([a-zA-Z0-9_\s]+?)\s+is\s+(.+)$", re.IGNORECASE),
            re.compile(r"^(?:remember|note)\s+(?:that\s+)?([a-zA-Z0-9_\s]+?)\s+is\s+(.+)$", re.IGNORECASE),
            re.compile(r"^my\s+([a-zA-Z0-9_\s]+?)\s+is\s+(.+)$", re.IGNORECASE),
        ]

        self.memory_query_patterns = [
            re.compile(r"^(?:what|who)\s+is\s+my\s+([a-zA-Z0-9_\s\?]+)$", re.IGNORECASE),
            re.compile(r"^(?:do you remember|tell me)\s+my\s+([a-zA-Z0-9_\s\?]+)$", re.IGNORECASE),
            re.compile(r"^what\s+did\s+i\s+say\s+about\s+([a-zA-Z0-9_\s\?]+)$", re.IGNORECASE),
        ]

    def classify(self, text: str, context: Optional[Any] = None) -> IntentResult:
        cleaned = text.strip()

        # Check Layer 4: Corrections first (e.g. "nahi, Chrome nahi Edge kholo")
        if self.learning_manager:
            corr = self.learning_manager.process_correction(cleaned)
            if corr.is_correction:
                return IntentResult(
                    primary_intent=Intent(
                        name="user_correction",
                        type=IntentType.CORRECTION,
                        entities={
                            "concept": corr.concept,
                            "old_value": corr.old_value,
                            "new_value": corr.new_value,
                            "explanation": corr.explanation
                        },
                        raw_query=cleaned
                    ),
                    confidence=1.0,
                    source="learning_layer_4"
                )

            # Check Layer 3: Composite Workflows (e.g. "Excel clean karo")
            workflow = self.learning_manager.check_workflow_match(cleaned)
            if workflow:
                return IntentResult(
                    primary_intent=Intent(
                        name=f"workflow_{workflow['name']}",
                        type=IntentType.COMMAND,
                        entities={"workflow_data": workflow},
                        is_multi_step=True,
                        raw_query=cleaned
                    ),
                    confidence=1.0,
                    source="learning_layer_3"
                )

            # Apply Layer 2: Vocabulary replacement (e.g. "browser" -> "edge")
            cleaned = self.learning_manager.resolve_vocabulary(cleaned)

        # 1. System rule check
        for pattern, name, itype in self.system_patterns:
            m = pattern.match(cleaned)
            if m:
                entities = {}
                if m.groups():
                    entities["plugin_name"] = m.group(1).strip()
                return IntentResult(
                    primary_intent=Intent(name=name, type=itype, entities=entities, raw_query=cleaned),
                    confidence=1.0,
                    source="rule"
                )

        # 2. Memory store check
        for pattern in self.memory_store_patterns:
            m = pattern.match(cleaned)
            if m:
                key = m.group(1).strip()
                val = m.group(2).strip().rstrip(".")
                return IntentResult(
                    primary_intent=Intent(
                        name="store_memory",
                        type=IntentType.MEMORY_STORE,
                        entities={"key": key, "value": val, "category": "facts"},
                        raw_query=cleaned
                    ),
                    confidence=0.98,
                    source="rule"
                )

        # 3. Memory query check
        for pattern in self.memory_query_patterns:
            m = pattern.match(cleaned)
            if m:
                query_key = m.group(1).strip().rstrip("?")
                return IntentResult(
                    primary_intent=Intent(
                        name="query_memory",
                        type=IntentType.MEMORY_QUERY,
                        entities={"query": query_key},
                        raw_query=cleaned
                    ),
                    confidence=0.98,
                    source="rule"
                )

        # 4. Fast Plugin Keyword / Grammar match
        if self.plugin_manager:
            plugin_match = self._match_plugin_direct(cleaned)
            if plugin_match:
                return plugin_match

        # 6. LLM-based classification if available and not Mock
        if self.llm and type(self.llm).__name__ != "MockLLMProvider":
            llm_result = self._classify_with_llm(cleaned)
            if llm_result:
                return llm_result

        # 7. Default to CHAT
        return IntentResult(
            primary_intent=Intent(
                name="chat",
                type=IntentType.CHAT,
                confidence=0.85,
                raw_query=cleaned
            ),
            confidence=0.85,
            source="fallback"
        )

    def _match_plugin_direct(self, text: str) -> Optional[IntentResult]:
        """Matches query directly against registered plugin actions and keywords."""
        indexed_match = self.plugin_manager.match_action(text)
        if indexed_match:
            plugin_name, action = indexed_match
            entities = self._extract_parameters(text, action.parameters)
            return IntentResult(
                primary_intent=Intent(
                    name=f"{plugin_name}_{action.name}", type=IntentType.COMMAND,
                    target_plugin=plugin_name, target_action=action.name,
                    entities=entities, raw_query=text
                ),
                confidence=0.92, source="plugin_rule"
            )
        return None

    def _extract_parameters(self, text: str, params: List[Any]) -> Dict[str, Any]:
        """Extract basic parameter arguments from text."""
        entities: Dict[str, Any] = {}
        for p in params:
            # If parameter has a name and text contains target information
            p_name = p.name if hasattr(p, "name") else p.get("name")
            if p_name == "app_name":
                # Look for 'open X' or 'launch X'
                m = re.search(r"(?:open|launch|start)\s+([a-zA-Z0-9_\-]+)", text, re.IGNORECASE)
                if m:
                    entities["app_name"] = m.group(1).strip()
            elif p_name == "path":
                m = re.search(r"(?:in|path|folder|directory)\s+([a-zA-Z0-9_\\\/\:\.\-]+)", text, re.IGNORECASE)
                if m:
                    entities["path"] = m.group(1).strip()
            elif p_name == "level":
                m = re.search(r"\b(\d{1,3})\b", text)
                if m:
                    entities["level"] = int(m.group(1))
        return entities

    def _classify_with_llm(self, text: str) -> Optional[IntentResult]:
        """Calls LLM with structured intent classification prompt."""
        try:
            from .prompts import INTENT_CLASSIFICATION_PROMPT
            plugin_schema = ""
            if self.plugin_manager:
                plugin_schema = self.plugin_manager.get_plugins_summary_json(query=text)

            prompt = INTENT_CLASSIFICATION_PROMPT.format(
                plugin_schema=plugin_schema,
                user_input=text
            )
            raw = self.llm.generate(prompt=prompt, system_prompt="You are a JSON-only intent extraction module.")
            # Extract JSON block
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(0))
                itype_str = parsed.get("type", "CHAT")
                itype = getattr(IntentType, itype_str, IntentType.CHAT)

                intent = Intent(
                    name=parsed.get("intent", "unnamed"),
                    type=itype,
                    confidence=parsed.get("confidence", 0.9),
                    target_plugin=parsed.get("target_plugin"),
                    target_action=parsed.get("target_action"),
                    entities=parsed.get("entities", {}),
                    is_multi_step=parsed.get("is_multi_step", False),
                    raw_query=text
                )
                return IntentResult(primary_intent=intent, confidence=intent.confidence, source="llm")
        except Exception as e:
            logger.error(f"LLM Classification failed: {e}")
        return None
