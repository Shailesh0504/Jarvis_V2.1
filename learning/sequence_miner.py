# learning/sequence_miner.py
"""Proactive Sequential Action Chain Miner & Workflow Synthesizer for Jarvis V2."""

from dataclasses import dataclass, field
import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("jarvis.learning.miner")


@dataclass
class ActionStep:
    plugin: str
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    timestamp: float = field(default_factory=time.time)

    def to_key(self) -> str:
        # Normalize parameters to detect structural repetition
        p_keys = sorted(list(self.parameters.keys()))
        return f"{self.plugin}:{self.action}:{','.join(p_keys)}"


@dataclass
class WorkflowProposal:
    name: str # e.g. "prepare_sales_report"
    display_title: str # e.g. "Prepare Sales Report"
    trigger_phrases: List[str] # e.g. ["sales report prepare karo", "prepare sales report", "sales report banao"]
    steps: List[Dict[str, Any]]
    frequency: int = 2
    prompt_text: str = ""


class SequenceMiner:
    """Detects repeated sequences of actions and generates proactive workflow proposals."""

    def __init__(self, min_chain_length: int = 3, min_frequency: int = 2):
        self.min_chain_length = min_chain_length
        self.min_frequency = min_frequency
        self._history: List[ActionStep] = []
        self._chain_counts: Dict[str, int] = {}
        self._chain_samples: Dict[str, List[ActionStep]] = {}
        self._proposed_chains: set = set()

    def record_step(
        self,
        plugin: str,
        action: str,
        parameters: Optional[Dict[str, Any]] = None,
        description: str = ""
    ) -> None:
        """Records an executed action step and scans for repeated chains."""
        step = ActionStep(
            plugin=plugin,
            action=action,
            parameters=parameters or {},
            description=description or f"{plugin}.{action}"
        )
        self._history.append(step)
        if len(self._history) > 100:
            self._history.pop(0)

        # Scan multi-step chains of lengths 3, 4, 5
        self._update_chain_frequencies()

    def _update_chain_frequencies(self) -> None:
        n = len(self._history)
        for chain_len in range(self.min_chain_length, min(6, n + 1)):
            chain = self._history[n - chain_len : n]
            chain_sig = "|".join(s.to_key() for s in chain)
            self._chain_counts[chain_sig] = self._chain_counts.get(chain_sig, 0) + 1
            self._chain_samples[chain_sig] = chain

    def detect_proposal(self) -> Optional[WorkflowProposal]:
        """Returns a proactive workflow proposal if a repeated sequence is found."""
        for sig, count in list(self._chain_counts.items()):
            if count >= self.min_frequency and sig not in self._proposed_chains:
                chain = self._chain_samples.get(sig, [])
                if len(chain) >= self.min_chain_length:
                    # Mark this and related signatures as proposed
                    self._proposed_chains.add(sig)
                    for k in list(self._chain_counts.keys()):
                        if k in sig or sig in k:
                            self._proposed_chains.add(k)
                    return self._synthesize_proposal(chain, count)
        return None

    def _synthesize_proposal(self, chain: List[ActionStep], frequency: int) -> WorkflowProposal:
        """Derives clean workflow name, trigger keywords, and executable steps."""
        actions_str = " ".join(f"{s.plugin} {s.action}" for s in chain).lower()

        if "excel" in actions_str or "sales" in actions_str:
            title = "Prepare Sales Report"
            name = "prepare_sales_report"
            triggers = ["sales report prepare karo", "prepare sales report", "sales report banao", "sales report", "generate sales report"]
        elif "downloads" in actions_str or "duplicate" in actions_str or "organize" in actions_str:
            title = "Organize Downloads"
            name = "organize_downloads"
            triggers = ["downloads organize karo", "organize downloads", "downloads report"]
        elif "vlc" in actions_str or "media" in actions_str:
            title = "Media Session"
            name = "media_session"
            triggers = ["start media session", "movie night", "media chalao"]
        else:
            title = f"Automated Workflow {chain[0].plugin.capitalize()}"
            name = f"auto_{chain[0].plugin}_{chain[0].action}"
            triggers = [f"{name.replace('_', ' ')}", f"{title.lower()}"]

        steps = []
        for s in chain:
            steps.append({
                "plugin": s.plugin,
                "action": s.action,
                "parameters": s.parameters,
                "description": s.description
            })

        prompt = (
            f"Aap ye workflow frequently repeat kar rahe hain ({frequency} baar). "
            f"Kya main ise '{title}' naam se automate kar du?"
        )

        return WorkflowProposal(
            name=name,
            display_title=title,
            trigger_phrases=triggers,
            steps=steps,
            frequency=frequency,
            prompt_text=prompt
        )

    def clear(self) -> None:
        self._history.clear()
        self._chain_counts.clear()
        self._chain_samples.clear()
        self._proposed_chains.clear()
