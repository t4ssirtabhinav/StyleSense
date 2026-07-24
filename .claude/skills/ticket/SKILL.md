---
name: ticket
description: Run the next phase of the StyleSense 4-phase ticket pipeline (architect -> developer -> qa -> devops) for a given ticket ID, e.g. "/ticket SS-008". Use whenever the user asks to work a Section 10 sprint ticket end-to-end.
---

# Ticket pipeline runner

Given an argument like `SS-008`, do the following. This is a reference for a repeatable process — not a fully automated state machine.

## Two lanes — gate by risk, not by habit

Every ticket carries a `Risk:` field (`low` | `med` | `high`), set by the Architect at the end of its design pass (or by `/new-feature` Stage 2 for new tickets). It decides how many human gates the pipeline pauses at — apply the rulebook's own risk-weighting (`docs/OPERATOR_RULEBOOK.md` §C6/§F5) to the *process*, not just the code.

- **Full lane (`Risk: high`)** — touches auth, payments, DB schema/migrations, RLS, secrets, or anything external-facing / irreversible. Pauses at **every** gate: after Architect (design review), after QA if it returns PASS PENDING MANUAL VERIFICATION (visual/UX check), and always at the PR. This is the original behavior, unchanged.
- **Fast lane (`Risk: low` / `Risk: med`)** — everything else (placeholder screens, token tweaks, analytics hooks, copy, additive UI with no security/schema/money surface). **Auto-chain Architect → Developer → QA with no human pause between them**, then **stop at the PR gate** — the one real one-way door. The human reviews the design doc + QA verdict *together, once, at the PR* instead of three separate times.

If the Architect hasn't tagged a ticket yet (first run, ticket predates this field), treat it as **Full lane** until the Architect assigns a Risk — never guess a ticket *down* into the fast lane. A QA verdict of **BLOCKED** stops both lanes and loops back to Developer regardless of risk; and a **PASS PENDING MANUAL VERIFICATION** always pauses both lanes for the human (fast lane doesn't skip a genuinely-needed visual check — it just doesn't add gates a low-risk ticket never needed).

## 1. Determine current state

- Read `docs/worklog/SS-XXX.md` if it exists. If it doesn't, this ticket hasn't started — begin at Architect.
- The worklog file's phase sections tell you what's already done. Find the first phase that is missing or incomplete: Architect → Developer → QA → DevOps.
- If QA's last verdict was BLOCKED, the next phase is Developer again (a fix pass), not DevOps.
- If QA's last verdict was PASS PENDING MANUAL VERIFICATION, stop and ask the user to confirm they've run `/run` or `/verify` against the flagged visual/UX acceptance criteria. Do not invoke DevOps until they confirm — this state exists because QA's tools (Read/Bash/Grep only) cannot render a screen, so a human has to close that gap.

## 2. Run exactly one phase

Invoke the matching subagent via the `Agent` tool with `subagent_type` set to `architect`, `developer`, `qa`, or `devops` (defined in `.claude/agents/`). Give it the ticket ID and point it at `docs/tickets/raw/SS-XXX.md` (and the design doc / worklog, once they exist).

If `docs/worklog/SS-XXX.md` doesn't exist yet, create it first with a header (ticket title, branch name `feature/SS-XXX-slug`) before invoking the Architect.

Before invoking, scan `docs/BACKLOG.md`'s **Active** table **once, up front** — grep it by the Tag(s) relevant to this ticket (`tokens`/`auth`/`schema`/`ci`/`ai`/`infra`/`test`) rather than reading every row — and pass the matching `BL-XXX` rows into the subagent's prompt as things it should check whether it now resolves. This once-per-ticket scan is the only backlog resurfacing the pipeline does: the Architect re-scans Active as part of its own pass, but Developer / QA / DevOps do **not** re-scan — they act only on the rows you (or the Architect) hand them, plus closing any row they actually resolve. Do **not** scan the **Parked** table here — it's owned by `/audit`, not the ticket pipeline.

## 3. Stop and report

After the phase completes:
- Make sure the phase's output got appended to `docs/worklog/SS-XXX.md`. If the subagent didn't do this itself, append a short summary yourself.
- Check whether the subagent logged anything new to `docs/BACKLOG.md` or moved any rows to **Resolved** — if it found something backlog-worthy but didn't log it (or the note in the subagent's report mentions a deferred item that never made it into the file), append it yourself rather than letting it evaporate.
- Update the ticket's row in `docs/worklog/README.md`.
- Report to the user what happened in this phase and what the next phase would be, then:
  - **Full lane (`Risk: high`)** — **stop**. The user re-invokes `/ticket SS-XXX` (or says "continue") when ready. (Also stop, in either lane, if the phase was Architect and the ticket had no Risk yet — the human should see the Risk classification before an auto-chain starts.)
  - **Fast lane (`Risk: low`/`med`)** — **continue automatically to the next phase** (Architect → Developer → QA), without waiting, until you reach the PR gate. Still write the worklog entry and README update after each phase, but don't pause. Stop only when: the next action is opening the PR, QA returns BLOCKED (loop to Developer), or QA returns PASS PENDING MANUAL VERIFICATION (pause for the human's visual check).

## Notes

- **Full lane only:** before starting Developer, make sure a human has actually looked at the Architect's design doc — don't rubber-stamp past it just because the file exists. On the **fast lane** this gate is deliberately skipped — the human reviews the design at the PR alongside the QA verdict; that's the whole point of the lane. Never fast-lane a ticket the Architect tagged (or should have tagged) `high`.
- Before opening the PR, QA's verdict for this pass must be PASS (or PASS PENDING MANUAL VERIFICATION with the user's confirmation obtained). If it's BLOCKED, loop back to Developer instead, referencing QA's findings — in either lane.
- DevOps commits and pushes to the feature branch without asking, but always stops and asks before opening the PR — this is a fixed rule in `.claude/agents/devops.md` and `.claude/CLAUDE.md`'s Git Autonomy Contract, not something to renegotiate per ticket.

## Backlog (cross-ticket open items)

`docs/BACKLOG.md` exists so a deferred decision (a missing design token, a business decision like MSG91 vs. Twilio, a CI gap) doesn't quietly disappear once its originating ticket ships and its worklog stops being read. The backlog is split into **Active** (scanned during ticket runs) and **Parked** (owned by `/audit`, not scanned here). All four agents log new items and close rows their phase resolves — both are scan-free (append / move-a-known-ID). Only *resurfacing* costs a scan, so the pipeline does it exactly once:

- **Once per ticket, up front (you) + the Architect pass:** scan **Active** by relevant Tag and hand matching rows to the subagent (see step 2). No other phase re-scans — Developer / QA / DevOps act only on rows handed to them, plus closing what they resolve.
- After any phase, confirm nothing backlog-worthy got dropped (see step 3) — but this is a check on the phase's *report*, not a re-scan of the table.
- If the user explicitly says to defer something ("let's think about X later"), log it yourself immediately (Active if a near ticket will hit it, else Parked) rather than assuming a future subagent will catch it.

## Running independent tickets in parallel — the default for a solo sprint

**Parallelize by default; serialize only true dependencies.** The gates are per ticket, not global — they never require the whole sprint to run serially, and for a solo dev running back-to-back tickets, concurrency is the actual throughput lever (this is how you get several tickets done in a day, not shaving tokens). Check `docs/worklog/README.md`'s dependency note first. If two tickets have no file/folder overlap and no dependency relationship (e.g. SS-005 Home Shell vs. SS-009 Error Monitoring), run them at the same time in separate git worktrees, each on its own `feature/SS-XXX-slug` branch, rather than finishing one before starting the next.

This composes with the two lanes: several **fast-lane** tickets in parallel worktrees, each auto-chaining Architect→Developer→QA and converging on their own PR gates, is the normal fast path. Parallelizing doesn't change a lane's gates — it just lets independent tickets progress concurrently instead of queueing. When in doubt about overlap, serialize.
