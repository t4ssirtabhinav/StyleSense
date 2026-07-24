---
name: audit
description: Manually trigger a repo-wide audit (regression + security + platform-currency + architecture-drift) via the auditor agent. Not part of the per-ticket pipeline — run this on your own cadence (weekly is the recommended default) to catch cross-ticket drift QA's per-ticket gate can't see. Use whenever the user asks to run a health check, self-audit, or "batman" pass on the whole repo.
---

# Repo-wide audit runner

Invoke the `auditor` subagent (`.claude/agents/auditor.md`) via the `Agent` tool to run all four scopes — regression, security, platform-currency, architecture-drift — in one pass, unless the user asks for a subset (e.g. "just run the platform-currency audit").

This is currently **manual-only by design** — there is no cron/`/schedule` wiring yet. The recommended cadence is weekly, all four scopes bundled; run it yourself when you want a checkpoint, or when it's been a while since `docs/AUDIT_LOG.md`'s last entry. If you later want this to run unattended on a schedule, that's a `/schedule` routine wrapping this same skill — a separate decision (execution environment, credentials, dependency installation in that environment) to make deliberately when you're ready, not something to bolt on silently.

## 1. Check when this last ran

Read `docs/AUDIT_LOG.md`. If it doesn't exist yet, this is the first run — the auditor will create it from its template. If it exists, note the date of the last entry so you can tell the user how long it's been (useful context even though nothing here blocks running again sooner).

## 2. Run it

Invoke `auditor` with the scope(s) requested (default: all four). Point it at `docs/BACKLOG.md` and `docs/ARCHITECTURE_AMENDMENTS.md` as inputs it should already know to check per its own definition — no need to pre-filter anything for it the way `.claude/skills/ticket/SKILL.md` does for per-ticket backlog rows; the auditor's whole job this run *is* the full-repo scan.

## 3. Report

Relay the auditor's summary table (scope → findings → severity) and the list of `BL-XXX` IDs it added or resolved. If it flagged anything as a `/new-feature` candidate, say so explicitly and let the user decide whether to act on it now — don't auto-invoke `/new-feature` yourself. If a regression-sweep failure is CRITICAL (not just a warning), say clearly that this should probably become a ticket soon rather than sit in the backlog — but still don't create one yourself; that's what `/new-feature` or a direct `docs/tickets/raw/` addition is for, with the same human sign-off `/new-feature` already requires.

## Rules

- Never let this skill or the auditor fix anything, commit anything, or create a ticket file directly — findings only, same boundary the auditor's own definition enforces.
- If the user asks to schedule this automatically, don't wire up `/schedule` without first confirming execution environment and cadence explicitly — those were deliberately deferred, not defaulted.
