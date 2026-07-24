# StyleSense — Audit Log

Append-only record of every `/audit` run (`.claude/skills/audit/SKILL.md` → `.claude/agents/auditor.md`), whether or not it found anything. This is what lets "when was this last checked" always have an answer — a clean run is still worth a line, per `docs/OPERATOR_RULEBOOK.md` §L3's append-only-state discipline. Never overwrite or delete an entry; if a later run corrects an earlier one, say so in the new entry.

**Format** — one entry per run, newest last:

```
## AUDIT-001 — YYYY-MM-DD

**Scopes run:** regression / security / platform-currency / architecture-drift (or a subset)
**Findings:** N total — X critical, Y warnings, Z clean
**Backlog rows touched:** BL-XXX (added), BL-YYY (resolved), ...
**/new-feature candidates flagged:** <none, or a short list>
**Notes:** <anything worth a human reading later — a scope skipped and why, a source that was inconclusive, etc.>
```

---

*(No runs yet — this file is created empty. The first entry will be added the first time `/audit` runs.)*
