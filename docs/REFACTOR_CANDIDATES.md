# Refactor Candidates & Dead Code Review Log

Per Section 9 & 31 of project governance rules:
> **"DO NOT DELETE CODE ONLY BECAUSE IDE SEARCH SAYS 'NO REFERENCES'. Before deleting anything, prove that it is genuinely obsolete. If uncertain: MARK IT FOR REVIEW. Do not delete it."**

This document tracks all candidates identified during the project audit, evaluating confidence, risk, and recommended action.

---

| File | Item | Why It Appears Unused / Candidate | Confidence | Risk | Recommendation |
|---|---|---|---|---|---|
| `gui/chat.py` | `ChatWidget` (5 lines) | Early prototyping stub. Modern active chat UI is fully implemented in `gui/views/chat_view.py` (`ChatView`). | HIGH | LOW | **RETAIN AS BACKWARD-COMPATIBLE STUB**. Mark as deprecated; do not delete to avoid breaking external plugin/reflection imports. |
| `gui/settings.py` | `SettingsWidget` (5 lines) | Early prototyping stub. Modern active settings UI is implemented in `gui/views/settings_view.py` (`SettingsView`). | HIGH | LOW | **RETAIN AS BACKWARD-COMPATIBLE STUB**. Mark as deprecated. |
| `gui/plugins.py` | `PluginsWidget` (5 lines) | Early prototyping stub. Active plugin management UI is in `gui/views/plugins_view.py` (`PluginsView`). | HIGH | LOW | **RETAIN AS BACKWARD-COMPATIBLE STUB**. Mark as deprecated. |
| `gui/status.py` | `StatusWidget` (5 lines) | Early prototyping stub. Telemetry is handled by `gui/components/status_bar.py` and metric cards. | HIGH | LOW | **RETAIN AS BACKWARD-COMPATIBLE STUB**. Mark as deprecated. |
| `gui/voice.py` | `VoiceWidget` (5 lines) | Early prototyping stub. Modern voice visualizer is in `gui/components/voice_visualizer.py`. | HIGH | LOW | **RETAIN AS BACKWARD-COMPATIBLE STUB**. Mark as deprecated. |
| `voice/wakeword.py` | Full file (16 lines) | Facade module re-exporting `WakeWordDetector`, `WakeWordMatchResult`, etc. from `voice.wake_word`. | HIGH | HIGH | **DO NOT DELETE**. Active facade preserving backward compatibility for external callers expecting `from voice.wakeword import ...`. |
| `memory/preferences.py` | Full file | Facade re-exporting preference operations to `memory.database`. | HIGH | MEDIUM | **DO NOT DELETE**. Preserves public API contract for `memory.preferences`. |
| `memory/semantic.py` | Full file | Facade re-exporting semantic memory functions to `memory.database`. | HIGH | MEDIUM | **DO NOT DELETE**. Preserves public API contract for `memory.semantic`. |
| `learning/corrections.py` | Full file | Facade re-exporting corrections logic to `learning.corrections_layer`. | HIGH | MEDIUM | **DO NOT DELETE**. Preserves public API contract for `learning.corrections`. |
| `learning/suggestions.py` | Full file | Facade re-exporting suggestion data models. | HIGH | MEDIUM | **DO NOT DELETE**. Preserves public API contract for `learning.suggestions`. |
| `core/semantic/lexicon.py:normalize_text` | Function | One of 4 duplicate definitions of `normalize_text` across the codebase. | MEDIUM | HIGH | **DO NOT DELETE**. Keep as domain-specific lexical normalizer while consolidating shared core normalizer in `core.semantic.normalizer`. |
| `learning/communication_normalizer.py:normalize_text` | Function | One of 4 duplicate definitions of `normalize_text`. | MEDIUM | HIGH | **DO NOT DELETE**. Keep as communication-layer normalizer. |
