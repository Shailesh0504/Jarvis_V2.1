# CODE CLEANUP & HEALTH RULES

See full specification in [CODEBASE_HEALTH_RULES.md](file:///c:/Users/Admin/Documents/Jarvis_V2.1/CODEBASE_HEALTH_RULES.md).

## Quick Reference Summary

1. **Golden Rule**: Never leave the codebase worse than you found it. `CHANGE → CHECK → CLEAN → TEST → VERIFY`.
2. **No Code Duplication**: Search existing code → Find reusable implementation → Reuse/Extend → Only then create new code.
3. **Dead Code Prevention**: Continuously identify and remove unused functions, classes, variables, imports, modules, configuration, and debug code.
4. **Complexity Control**: Simple → Clear → Reusable → Maintainable. Avoid multiple wrappers, multiple fallbacks, multiple managers.
5. **Architecture Health**: Maintain strict separation across Perception → Normalization → Intent → Context → Router → Plugin/Skill → Universal Verification → Response/TTS.
6. **Error Handling Health**: Never silently catch errors with empty `except: pass`. Detect → Log → Handle → Recover → Inform.
7. **Health-First Development**: Feature development and codebase health must happen together. Small continuous cleanup is preferred over massive cleanup later.
8. **Definition of Done**: A task is DONE only when feature works, existing functionality still works, no duplicate logic, no dead code, dependencies are healthy, tests pass, and documentation is accurate.
