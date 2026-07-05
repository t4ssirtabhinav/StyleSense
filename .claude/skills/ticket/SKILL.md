---
name: ticket
description: Run the next phase of the StyleSense 4-phase ticket pipeline (architect -> developer -> qa -> devops) for a given ticket ID, e.g. "/ticket SS-008". Use whenever the user asks to work a Section 10 sprint ticket end-to-end.
---

# Ticket pipeline runner

Given an argument like `SS-008`, do the following. This is a reference for a repeatable process — not a fully automated state machine. The pipeline **pauses between every phase** for the user's go-ahead; never chain phases automatically.

## 1. Determine current state

- Read `docs/worklog/SS-XXX.md` if it exists. If it doesn't, this ticket hasn't started — begin at Architect.
- The worklog file's phase sections tell you what's already done. Find the first phase that is missing or incomplete: Architect → Developer → QA → DevOps.
- If QA's last verdict was BLOCKED, the next phase is Developer again (a fix pass), not DevOps.
- If QA's last verdict was PASS PENDING MANUAL VERIFICATION, stop and ask the user to confirm they've run `/run` or `/verify` against the flagged visual/UX acceptance criteria. Do not invoke DevOps until they confirm — this state exists because QA's tools (Read/Bash/Grep only) cannot render a screen, so a human has to close that gap.

## 2. Run exactly one phase

Invoke the matching subagent via the `Agent` tool with `subagent_type` set to `architect`, `developer`, `qa`, or `devops` (defined in `.claude/agents/`). Give it the ticket ID and point it at `docs/tickets/raw/SS-XXX.md` (and the design doc / worklog, once they exist).

If `docs/worklog/SS-XXX.md` doesn't exist yet, create it first with a header (ticket title, branch name `feature/SS-XXX-slug`) before invoking the Architect.

## 3. Stop and report

After the phase completes:
- Make sure the phase's output got appended to `docs/worklog/SS-XXX.md`. If the subagent didn't do this itself, append a short summary yourself.
- Update the ticket's row in `docs/worklog/README.md`.
- Report to the user what happened in this phase and what the next phase would be — then **stop**. Do not automatically proceed to the next phase. The user re-invokes `/ticket SS-XXX` (or just says "continue") when ready.

## Notes

- Before starting Developer, make sure a human has actually looked at the Architect's design doc — don't rubber-stamp past it just because the file exists.
- Before starting DevOps, QA's verdict for this pass must be PASS (or PASS PENDING MANUAL VERIFICATION with the user's confirmation obtained). If it's BLOCKED, loop back to Developer instead, referencing QA's findings.
- DevOps commits and pushes to the feature branch without asking, but always stops and asks before opening the PR — this is a fixed rule in `.claude/agents/devops.md` and `.claude/CLAUDE.md`'s Git Autonomy Contract, not something to renegotiate per ticket.

## Running independent tickets in parallel

The pause-between-phases rule is per ticket, not global — it does not require the whole sprint to run serially. Check `docs/worklog/README.md`'s dependency note before assuming tickets must queue behind each other. If two tickets have no file/folder overlap and no dependency relationship (e.g. SS-002's DB verification pass vs. the SS-008 design-system chain), it's safe to run their Architect (or even Developer) phases at the same time in separate git worktrees, each on its own `feature/SS-XXX-slug` branch, rather than waiting for one to fully finish. Still stop and report after each phase per ticket — parallelizing tickets doesn't change the per-phase human gate, it just lets independent tickets progress concurrently instead of queueing behind unrelated work.
