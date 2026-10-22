# CODEBASE HEALTH RULES

## Primary Objective

The Jarvis codebase MUST ALWAYS remain healthy, clean, maintainable, understandable, testable, and production-ready.

Codebase health is a **continuous responsibility**, not a one-time cleanup activity.

Every code change MUST leave the project in an equal or better state than before the change.

---

# 1. Golden Rule

> **Never leave the codebase worse than you found it.**

After every modification:

```text
CHANGE
  ↓
CHECK
  ↓
CLEAN
  ↓
TEST
  ↓
VERIFY
```

Do not consider a task complete until the codebase is healthy.

---

# 2. Healthy Codebase Definition

A healthy codebase should have:

* No unnecessary dead code
* No known duplicate logic
* No unused imports
* No unnecessary dependencies
* No broken imports
* No unresolved references
* No obvious circular dependencies
* No unnecessary complexity
* No abandoned experimental code
* No obsolete configuration
* No duplicate configuration
* No unexplained hacks
* No unnecessary TODO/FIXME accumulation
* Clear module ownership
* Clear architecture
* Predictable data flow
* Testable components
* Working startup
* Working core functionality
* Updated documentation

---

# 3. Every Change Must Preserve Health

Whenever code is added, modified, or deleted, check:

```text
Did this introduce duplication?
Did this introduce unnecessary complexity?
Did this make another component obsolete?
Did this create dead code?
Did this break an existing dependency?
Did this create a circular dependency?
Did this make testing harder?
Did this make the architecture harder to understand?
```

If yes, fix it before completing the task.

---

# 4. No Code Duplication

Before writing new logic:

```text
SEARCH EXISTING CODE
        ↓
FIND REUSABLE IMPLEMENTATION
        ↓
REUSE / EXTEND
        ↓
ONLY THEN CREATE NEW CODE
```

Never create a second implementation of an existing responsibility.

Prefer:

```text
ONE RESPONSIBILITY
        ↓
ONE CANONICAL IMPLEMENTATION
        ↓
MANY CALLERS
```

---

# 5. Dead Code Prevention

Continuously identify and remove:

* Unused functions
* Unused classes
* Unused variables
* Unused imports
* Unused modules
* Unused components
* Unused configuration
* Unused dependencies
* Obsolete handlers
* Old fallback logic
* Temporary code
* Commented-out implementations
* Debug code

Before deleting anything, verify references and dynamic usage.

---

# 6. Complexity Control

Every new solution must be evaluated for unnecessary complexity.

Prefer:

```text
Simple
→ Clear
→ Reusable
→ Maintainable
```

Avoid:

```text
Complex
→ Multiple wrappers
→ Multiple fallbacks
→ Multiple managers
→ Difficult debugging
```

Do not introduce an abstraction unless it provides a real architectural benefit.

---

# 7. Architecture Health

Maintain clear responsibility boundaries.

For Jarvis:

```text
Voice Input
     ↓
Listener
     ↓
Normalization / Translation
     ↓
Intent Detection
     ↓
Context / Conversation
     ↓
Command Router
     ↓
Skill
     ↓
System Action
     ↓
Response Generation
     ↓
Speaker
```

Do not allow unrelated responsibilities to leak between layers.

For example:

* Listener should not launch applications.
* Speaker should not detect intents.
* Intent detection should not directly manipulate the OS.
* GUI should not contain core business logic.
* Skills should not duplicate routing logic.
* Context Manager should not become a command executor.

---

# 8. Dependency Health

Regularly check:

```text
Imports
Dependencies
Module relationships
Circular dependencies
Unused packages
Broken references
```

Remove dependencies that are no longer required.

Do not add a package when existing project functionality can solve the problem adequately.

---

# 9. Configuration Health

Maintain a single source of truth.

Avoid multiple files defining the same configuration.

Check for:

* Duplicate settings
* Conflicting values
* Obsolete settings
* Unused environment variables
* Hardcoded paths
* Hardcoded credentials
* Temporary development settings

Secrets MUST NEVER be hardcoded into source code.

---

# 10. Error Handling Health

Do not hide errors with broad exception handling.

Avoid:

```python
try:
    ...
except:
    pass
```

Prefer meaningful error handling:

```text
Detect
→ Log
→ Handle
→ Recover when possible
→ Inform user when necessary
```

Errors should help debugging instead of silently disappearing.

---

# 11. Logging Health

Logging should be:

* Useful
* Structured
* Consistent
* Debuggable
* Configurable

Remove unnecessary:

```text
print()
temporary debug messages
duplicate logs
```

Do not flood the console with repeated messages during normal operation.

---

# 12. Performance Health

The codebase should remain responsive.

Do not introduce unnecessary:

* Blocking operations
* Repeated disk scans
* Repeated database queries
* Duplicate model loading
* Duplicate initialization
* Unnecessary network requests
* Excessive thread creation
* Excessive process creation
* Memory-heavy operations

Performance optimization should be based on evidence, not assumptions.

---

# 13. Startup Health

Jarvis startup must remain reliable.

After architectural changes, verify:

```text
Configuration
↓
Dependencies
↓
Database
↓
Core modules
↓
Listener
↓
Conversation system
↓
GUI
↓
Speaker
```

A new feature MUST NOT unnecessarily slow down or destabilize startup.

---

# 14. Runtime Health

Verify that Jarvis can:

* Start
* Listen
* Understand commands
* Handle normal conversation
* Maintain context
* Execute commands
* Handle errors
* Give natural feedback
* Continue after failures
* Shut down cleanly

One failed command should not unnecessarily crash the entire assistant.

---

# 15. Regression Protection

Existing working functionality MUST remain protected.

Whenever a bug is fixed, create or update a regression test where practical.

Example:

```text
User:
"Brave open karo"

Expected:
Brave launches.
```

```text
User:
"YouTube ko Brave me open karo"

Expected:
YouTube opens specifically in Brave.
```

```text
User:
"Excel Chrome Brave Word open karo"

Expected:
All requested applications are correctly identified.
```

---

# 16. Before Creating New Files

Before creating a new file, ask:

```text
Can an existing file own this responsibility?
Can an existing module be extended?
Is this genuinely a separate concern?
Will this reduce or increase complexity?
```

Do not create files merely because a feature is small.

---

# 17. Before Creating New Functions

Search the project first.

Ask:

```text
Does this function already exist?
Does another function perform almost the same task?
Can the existing function be generalized safely?
```

If duplicate functionality exists, refactor instead of duplicating it.

---

# 18. Before Removing Files

Never blindly delete a file.

Check:

```text
Imports
References
Registrations
Dynamic imports
Configuration
Tests
GUI references
Skill registration
Startup code
```

Then remove only when confirmed unnecessary.

---

# 19. Documentation Health

Documentation must match the actual codebase.

If architecture changes, update relevant documentation:

```text
README.md
AGENTS.md
ARCHITECTURE.md
DESIGN.md
PRD.md
RULES.md
FEATURES.md
CODE_CLEANUP_RULES.md
```

Never allow documentation to describe deleted or renamed components as if they still exist.

---

# 20. TODO / FIXME Health

TODOs should not become permanent garbage.

Each TODO should have a reason.

Periodically classify:

```text
KEEP
FIX
IMPLEMENT
REMOVE
```

Remove obsolete TODOs.

---

# 21. Refactoring Rule

Refactoring should improve at least one of:

* Readability
* Maintainability
* Reusability
* Testability
* Performance
* Reliability
* Architecture

Do not refactor merely to make code look different.

---

# 22. AI Coding Agent Rule

Every AI coding agent MUST follow:

```text
UNDERSTAND
    ↓
SEARCH
    ↓
TRACE DEPENDENCIES
    ↓
REUSE
    ↓
IMPLEMENT
    ↓
CLEAN
    ↓
TEST
    ↓
VERIFY
```

Never:

```text
WRITE NEW CODE
    ↓
IGNORE EXISTING CODE
    ↓
CREATE DUPLICATION
    ↓
ADD PATCHES
    ↓
LEAVE PROJECT MESSY
```

---

# 23. Automatic Health Check After Every Significant Change

After significant modifications, check:

```text
[ ] Imports work
[ ] No obvious dead code introduced
[ ] No duplicate logic introduced
[ ] No unused files introduced
[ ] No unused dependencies introduced
[ ] No circular dependency introduced
[ ] No unnecessary complexity introduced
[ ] Error handling works
[ ] Logging works
[ ] Startup works
[ ] Existing functionality works
[ ] Tests pass
[ ] Documentation is accurate
```

---

# 24. Health Score

When performing a major refactor, evaluate the codebase using:

```text
Architecture       → Healthy / Needs Attention
Dependencies       → Healthy / Needs Attention
Dead Code          → Healthy / Needs Attention
Duplication        → Healthy / Needs Attention
Complexity         → Healthy / Needs Attention
Error Handling     → Healthy / Needs Attention
Performance        → Healthy / Needs Attention
Testing            → Healthy / Needs Attention
Documentation      → Healthy / Needs Attention
Runtime Stability  → Healthy / Needs Attention
```

Do not claim the codebase is healthy without verification.

---

# 25. Cleanup Trigger Conditions

A cleanup/refactor should be considered when:

* The same bug appears in multiple places.
* The same logic exists in multiple modules.
* A file has too many unrelated responsibilities.
* A function becomes difficult to understand.
* A feature requires excessive special cases.
* A module is no longer used.
* A dependency is obsolete.
* Configuration has become duplicated.
* Tests are becoming difficult to maintain.
* Adding a small feature requires changing many unrelated files.

---

# 26. Never Hide Technical Debt

Do not solve technical debt by:

* Adding another workaround
* Adding another fallback
* Copying existing code
* Suppressing errors
* Ignoring warnings
* Adding unnecessary conditions
* Increasing abstraction without purpose

When technical debt is discovered:

```text
IDENTIFY
→ UNDERSTAND
→ DOCUMENT IF NECESSARY
→ FIX WHEN SAFE
→ VERIFY
```

---

# 27. Health-First Development Rule

Feature development and codebase health must happen together.

Do NOT think:

```text
First build everything.
Then clean everything.
```

Instead:

```text
Build
 ↓
Keep clean
 ↓
Test
 ↓
Refactor when necessary
 ↓
Continue
```

Small continuous cleanup is preferred over massive cleanup later.

---

# 28. Definition of Done

A task is NOT DONE simply because the requested feature works.

A task is DONE only when:

```text
Feature works
AND
Existing functionality still works
AND
No unnecessary duplication exists
AND
No obvious dead code remains
AND
No unnecessary complexity was introduced
AND
Dependencies are healthy
AND
Architecture remains understandable
AND
Tests pass
AND
Documentation remains accurate
```

---

# 29. Final Rule

The Jarvis project should continuously move toward:

```text
                    HEALTHY CODEBASE

                         ▲
                         │
                 Continuous Review
                         │
          ┌──────────────┼──────────────┐
          │              │              │
       Clean Code    Clear Design    Testing
          │              │              │
          └──────────────┼──────────────┘
                         │
                  Simple Architecture
                         │
                  Reliable Jarvis
```

### Absolute Principle

> **Every change must leave the Jarvis codebase cleaner, safer, simpler, and more maintainable than before.**

Never intentionally leave known dead code, duplicate logic, broken references, unnecessary complexity, or obsolete components behind.
