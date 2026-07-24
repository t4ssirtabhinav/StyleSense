---
name: new-feature
description: Take a feature idea that isn't covered by the original architecture (init documents/architecture-hld-lld.html) or epics doc, run impact analysis on it, and — only after explicit user sign-off — turn it into a properly prioritized SS-XXX ticket ready for the normal /ticket pipeline. Use whenever the user has a new idea that doesn't already have a ticket, e.g. "/new-feature add a stylist chat feature".
---

# New-feature intake runner

Given a free-text feature idea, run Architect's **New-Scope Intake Mode** (see `.claude/agents/architect.md`) as a two-stage, human-gated process. This is not a fully automated state machine — like `.claude/skills/ticket/SKILL.md`, it **always pauses** for the user between the two stages.

This formalizes a pattern that already happened organically once: SS-006 and SS-007 were both surfaced mid-review on SS-004 and turned into real tickets with a `## Source note (this repo)` section. Use this skill for anything that doesn't already have a home in an existing ticket; if the idea is really just a small addition to a ticket already in `docs/tickets/raw/`, edit that ticket instead — don't route it through here.

## 1. Stage 1 — Impact analysis

Invoke the `architect` subagent via the `Agent` tool with the feature idea (verbatim, don't paraphrase it down before handing it over) and tell it explicitly this is **New-Scope Intake Mode, Stage 1** — no ticket file exists yet.

Before invoking, skim `docs/BACKLOG.md`'s **Active** and **Parked** tables yourself for anything that looks like this exact idea already sitting there (e.g. BL-026 in Active, BL-027 in Parked) and mention it in the prompt — same reason `.claude/skills/ticket/SKILL.md` does this for regular tickets: it saves the subagent a blind search. Intake is the one flow that reads Parked too (a "new" idea is often a parked one whose moment has come), unlike the ticket pipeline which never scans Parked.

## 2. Stop and report

Architect's Stage 1 output is a report, not a file — nothing gets written yet. Relay the impact analysis to the user in full: what it touches, breaking-change risk, proposed Priority/Sprint, draft Acceptance Criteria, and whether the architecture doc would need an amendment. **Stop here.** Do not proceed to Stage 2 without the user explicitly confirming (or adjusting) the proposal — this is not optional, it's the whole point of this skill: accountability for adding scope the original architecture never covered has to sit with the user, not get rubber-stamped by an agent.

**If the user declines the idea (or defers it),** don't let the analysis evaporate into chat (`docs/OPERATOR_RULEBOOK.md` §A6 — chat is not storage). Log a one-line **Parked** row in `docs/BACKLOG.md` (next `BL-XXX` ID, a Tag, `new-feature intake` as source, today's date) capturing the idea and a pointer to why it was declined/deferred, so a future `/audit` or intake can pick it up instead of re-deriving it from nothing. A ticket that *is* accepted needs no such row — its `## Source note` is the durable record.

## 3. Stage 2 — Finalize (only after confirmation)

Once the user confirms — with whatever adjustments they made to priority, sprint, or scope — invoke `architect` again (or continue the same invocation, if still live) for **Stage 2**, passing along the confirmed impact analysis and any adjustments. Architect will:
- Create `docs/tickets/raw/SS-XXX.md` with a `## Source note (this repo)` section **and a `Risk: low|med|high` header field** (high = auth/payments/schema/RLS/secrets/external-facing/irreversible; else low/med) so the ticket enters `/ticket` on the correct lane from its first run.
- Update `docs/worklog/README.md`'s table and sprint-ordering paragraph.
- Append to `docs/ARCHITECTURE_AMENDMENTS.md` if applicable.
- Resolve the matching `docs/BACKLOG.md` **Active** or **Parked** row if this closes one.

Confirm all of that actually happened (same drop-check spirit as `.claude/skills/ticket/SKILL.md` step 3 — if Architect's report mentions something it didn't actually write, don't let it evaporate). Report the new ticket ID to the user and tell them it's now ready for `/ticket SS-XXX` whenever they want to start it — but **do not** auto-invoke `/ticket` yourself. Intake ending in an accepted ticket is where this skill's job ends.

## Rules

- Never skip Stage 1's pause, even if the idea seems obviously good or small — "obviously fine" is exactly the feeling `docs/OPERATOR_RULEBOOK.md` §D8 warns isn't trustworthy.
- If Stage 1 finds the idea already exists (as a backlog row, an existing ticket, or an already-planned-but-unscheduled item in the original epics doc), say so plainly and don't manufacture a duplicate ticket just to have something to show for the invocation.
- If the idea turns out to be a small addition rather than new scope, say so and point the user at editing the existing ticket instead of continuing to Stage 2.
