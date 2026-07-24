# StyleSense — Architecture Amendments

`init documents/architecture-hld-lld.html` is the original HLD/LLD and is never edited in place — it stays the fixed Phase-1 source-of-record. This file is what gets edited instead: a dated, append-only log of every place reality has diverged from that original document, so "why does the code have X and the architecture doc doesn't mention it" always has a traceable answer.

**Logging:** any ticket created via `.claude/skills/new-feature/SKILL.md` (New-Scope Intake Mode) that changes or extends something the original architecture doc didn't cover gets one entry here, added during Stage 2 finalize. Entries are also fair game for the `/audit` skill's architecture-drift check to add, if it finds code that no longer matches the original doc and no amendment already explains why.

**Format** — one entry per amendment, oldest first, never edited after being written (if a later amendment supersedes an earlier one, say so in the new entry rather than rewriting the old one):

```
## AMEND-001 — <short title> (YYYY-MM-DD)

**What changed:** <what's true now that isn't in architecture-hld-lld.html>
**Introduced by:** <SS-XXX>
**Why the original doc didn't cover it:** <one line — genuinely new idea, scope grew, a wrong assumption at Phase 1, etc.>
**Original doc section this touches:** <e.g. "Database Schema", "AI Architecture" — so a reader knows what's now stale>
```

---

*(No amendments yet — this file is created empty. The first entry will be added the first time `.claude/skills/new-feature/SKILL.md` finalizes a ticket that requires one.)*
