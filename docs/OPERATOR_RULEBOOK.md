# Operator Rulebook

*What this is: standing instructions for anyone (or any agent) operating on StyleSense. Read this when a phase needs the letter of a rule fast. Compressed from `docs/OPERATING_MANUAL.md` (which holds the why — read it once per novel situation; the manual wins on conflict). Every rule is imperative and checkable.*

---

## A. INTAKE — before any tool call

- A1. Restate the request as a numbered deliverable list, each tagged: decision | diagnosis | diff | artifact | plan | teaching. If restating changes the work, the read worked.
- A2. Scope words ("everything", "every acceptance criterion", "the whole flow") = completeness contract: enumerate the space, prove the enumeration is grounded. A narrow ask gets a narrow answer.
- A3. Verbs set mode: verify/audit → adversarial (find what's wrong, deliver a disposition per finding, not reassurance). compare/take-inspiration → adopt selectively, state what you rejected and why. recommend/decide → make the call, justify it, own it. Never return an option menu when asked for judgment.
- A4. Prosecute the premise before answering. If a ticket's acceptance criterion rests on a wrong assumption about a platform (see BL-001, BL-019 in `docs/BACKLOG.md`), the correction IS the deliverable, not a footnote.
- A5. Before writing a design doc, plan, or answer, validate the ground it stands on — do the referenced ticket, migration, component, or endpoint actually exist as described?
- A6. Findings that live only in chat or a worklog nobody re-reads are lost. Fold every finding into a repo artifact (`docs/BACKLOG.md`, a worklog entry, a ticket) — chat is not storage.
- A7. Compound requests: sequence deliverables by dependency, execute all of them; don't silently drop the trailing ones.

## B. DECOMPOSE

- B1. Cut by verification boundary, not topic. A piece is well-cut when one sentence names the evidence that proves it done — this is already the standard for acceptance criteria (see `docs/tickets/raw/SS-XXX.md`); apply it to everything, not just tickets.
- B2. Separate decisions from tasks. Decisions gate tasks → they run FIRST regardless of where a backlog or ticket list puts them by number or theme. Grouping by theme is not the same as ordering by time.
- B3. Externalize all state: the session's todo list, cross-ticket deferrals (`docs/BACKLOG.md`), the audit trail (`docs/worklog/SS-XXX.md`). Memory is not a storage medium.
- B4. Backlog protocol (already implemented — see `.claude/skills/ticket/SKILL.md` steps 2–3 and `docs/BACKLOG.md`'s split): log every deferral with source + date + Tag (scan-free append); resurface once per ticket at the Architect phase over the **Active** table only (Developer/QA/DevOps don't re-scan); close rows the current work resolves. **Parked** is owned by `/audit`, not the ticket hot path. A write-only backlog is a graveyard; a re-scanned-every-phase backlog is a tax.
- B5. Cut uncertainty into buckets first: repo-checkable (grep/glob it) | needs-current-research (fetch the primary source — Supabase docs, Expo release notes, Razorpay API docs) | pure-judgment. Each bucket gets its matching verification method.
- B6. Parallelize independent tickets across git worktrees when there's no file/folder overlap (already documented in `SKILL.md`'s "Running independent tickets in parallel"); serialize only true dependencies.

## C. RISK-WEIGHT — where effort goes

- C1. Risk = P(wrong) × cost(wrong) × silence(failure). A silent failure (a webhook signature check that's skipped, an RLS policy that's missing) outranks a loud one (a typecheck error).
- C2. One-way doors get 10x scrutiny: a Supabase migration applied to a live/staging project, a pushed `main`, a Razorpay webhook accepted without HMAC verification, a `service_role` key anywhere client-reachable, a DLT/SMS-provider commitment (see BL-001). Ask "what does undoing this cost?" before acting.
- C3. Cutoff-exposed categories are NEVER recited from memory: Supabase Auth's supported SMS providers, Expo SDK API surface, `expo-secure-store`'s method signatures, RN library peer-dependency ranges, Razorpay fee/webhook behavior, TRAI DLT rules. Research or label — no third option. (BL-001's MSG91/DLT investigation and BL-011's Reanimated/Worklets peer-range mismatch are both real instances of this category, already lived in this project.)
- C4. Rank by detonation site: local dev loop < CI < staging (`develop`) < production (`main`). Pull failures leftward by design — this is what the QA phase's deterministic gates (`tsc`, `biome`, `jest`, `ruff`, `mypy`, `pytest`) already exist to do.
- C5. Risk concentrates at seams: the Supabase client boundary (`features/<domain>/*.queries.ts`), the FastAPI JWT auth dependency, the AI provider adapter boundary (`ai/adapters/`), the Razorpay webhook handler, the phone-OTP flow. Review seams first, straight-line component logic last.
- C6. 80% of verification effort on the ~20% of surface that is irreversible / external-facing / security / money / cutoff-exposed. Uniform diligence across a diff starves the lines that actually needed it.

## D. VERIFY — re-derive, don't vibe

- D1. "This file/component/endpoint exists" → grep/glob it. Never certify a cross-reference (a ticket ID, an import path, a route) by memory.
- D2. "This is current Supabase/Expo/Razorpay behavior" → fetch the primary source now, quote it. A remembered summary is not the same as the current docs when the detail is load-bearing (see BL-001's MSG91-is/isn't-a-native-provider finding — this came from checking Supabase's docs directly, not from reciting).
- D3. Numbers (₹ pricing, rate limits, token budgets, coverage percentages) → recompute from inputs.
- D4. "It works" → ran it and observed the behavior (say what you saw), or didn't (say so plainly). No third phrasing. An acceptance criterion without direct evidence is UNMET, not "probably fine" — this is already QA's standard (`.claude/agents/qa.md`); hold yourself to it outside QA too.
- D5. Design claims → walk one concrete instance end-to-end through the actual mechanism (one wardrobe item through the tagging pipeline; one OTP request through Supabase Auth). The walk may change the answer — that's it working.
- D6. "Fixed everywhere" → re-run the search that found it (the same `biome check .` / grep / `tsc` pass). Zero matches is the claim, not the memory of having fixed it.
- D7. Two-source rule: money (Razorpay), legal/compliance (DLT, data residency), or irreversible (migrations, prod pushes) claims need two independent confirmations or an explicit `[CONFIRM]` handing the check to the user visibly.
- D8. Verification is asymmetrically cheap. The "this is obviously fine" feeling is fluency, not truth — the stale MSG91 assumption and the retired-command class of bug both look exactly as confident as the correct version.

## E. LABEL — known vs. guessed, out loud

- E1. Five states, distinct labels: `[VERIFIED <date>]` (checked this session, e.g. against Supabase/Expo/Razorpay docs) | trained-knowledge (date-stamp it, downgrade if load-bearing) | inference (show the derivation) | assumption (flag load-bearing ones explicitly) | guess (label it or omit it).
- E2. Unlabeled = will be read as verified. `docs/BACKLOG.md`'s BL-001 entry is the model to follow: it's explicitly dated and marked "(2026-07-10, verified via Supabase docs/community search)" — that convention should extend to any architect/developer claim resting on third-party platform behavior, not just backlog rows.
- E3. Label decay: facts with shelf lives get re-check triggers ("re-verify MSG91/DLT status before SS-003 ships to real users"; "re-check RN library peer ranges on any Expo SDK bump").
- E4. The chat/report summary carries the same uncertainty as the artifact. A `[CONFIRM]` buried only in a worklog file the user may not re-read is functionally hidden.
- E5. Calibration = CONTRAST. Differentiate confidence across findings; uniform hedging destroys the signal the same way uniform confidence does.

## F. SELF-ATTACK — before every handover

- F1. Run stances in order: premise attack → cold read as the next phase/executor → adversary personas (a malicious webhook sender, a hostile RLS bypass attempt, a reviewer) → boundary sweep (empty wardrobe, max upload size, duplicate OTP request, concurrent try-on requests, stale JWT, mid-upload crash) → "what did I NOT check" list → time-decay pass on any inherited/older claim.
- F2. The not-checked list is where the bugs are. A prior confident claim that's never been re-checked is the highest-yield hunting ground — this is exactly the shape of BL-014/015/016/017/020 (fixes that existed only in the working tree, correctly out-of-scope for every ticket that noticed them, and so never actually got committed until DevOps went looking).
- F3. An attack that finds nothing was performative — rerun with a different stance.
- F4. Survivors (real, accepted risks) go in the deliverable's risk section BY NAME — this is what QA's CRITICAL/WARNINGS split and the three-state verdict already do; extend the same discipline to Architect's design docs and Developer's completion reports.
- F5. Scale to stakes: a one-line fix gets a ten-second pass; an auth flow, a payment webhook, or a schema migration gets the full repertoire.

## G. DELIVER — answer, reasoning, risk

- G1. First sentence = verdict/deliverable/headline finding. A premise-correction leads; it is never paragraph six.
- G2. Reasoning is selective: load-bearing evidence, real decision points, the walked example. Cut the tool-call travelogue and the options never seriously considered.
- G3. Risk section: `[CONFIRM]` items with exactly where to check, self-attack survivors, load-bearing assumptions, shelf-life warnings — differentiated by what actually gates what. Never omitted, never boilerplate.
- G4. Artifact = durable + complete (a worklog entry, a design doc, a backlog row). Report/chat summary = stands alone (outcome, what changed, what's owed). The summary never claims more than was done and never says less than the risk section.
- G5. Forms: tables for enumerable facts; three-state verdicts (PASS | BLOCKED | PASS PENDING MANUAL VERIFICATION) for gates — already StyleSense's standard, keep it; `file:line` references for anything touchable; dates on anything that decays.
- G6. Everything the user needs is in the final message; mid-turn text scrolls away.

## H. ANTI-PATTERNS — competence costumes (reject on sight, in others' work and your own)

- H1. Fluent confabulation: specific + polished + sourceless. Detail is not evidence.
- H2. Coverage theater: an AC checklist without per-criterion verification; test coverage % without per-path assertions.
- H3. Sycophantic responsiveness: answering inside a wrong frame because the ticket or the user built it.
- H4. Answering the askable, not the asked — a status update when a fix was requested.
- H5. "Should work" dressed as "works." The gap between "the code is written and should pass" and "I ran it and observed the pass" is the entire reason QA's `PASS PENDING MANUAL VERIFICATION` state exists.
- H6. Premature abstraction: a configurable framework where a `features/<domain>/*.service.ts` function serves. No second consumer = no abstraction — this is already `.claude/CLAUDE.md`'s stance; the rulebook just names the failure mode explicitly.
- H7. Uniform hedging (see E5).
- H8. Churn as progress: rewriting a file to change one line; "cleanup" nobody asked for in the same diff as a bug fix.
- H9. Documentation as done-ness: every existence claim in a shipped design doc or worklog gets globbed/grepped, not assumed from having written it down.
- H10. Speed over verification on C-class risk (see C2/C6). Wrong-fast compounds; it's cheap to verify twice, expensive to ship wrong once.
- H11. Performing this rulebook — an empty self-attack pass, a decorative `[VERIFIED]` label with nothing behind it. Costume ≠ craft.

## T. TOKEN ECONOMY — near-operator results per token

- T1. Distill once, reference forever. A ticket's Technical Notes exist so the Developer phase never re-reads the full architecture doc; a design doc exists so QA never re-reads the ticket's raw prose from scratch.
- T2. Read targeted: grep/glob to locate, then read the section — not the whole file. Never re-read a doc for context already externalized into a ticket or worklog.
- T3. Batch independent tool calls in one message; serialize only true dependencies.
- T4. Edit > rewrite. Surgical diffs; never regenerate a file to change one line.
- T5. State lives in files, not context: the worklog, the backlog, ticket status notes. Context is cache; files are truth — sessions and models swap, files survive.
- T6. Match model to phase — already implemented (`architect`/`developer` on `sonnet`, `qa`/`devops` on `haiku`, with `qa.md`'s explicit "recommend a Sonnet re-run if genuinely unsure" escalation clause). Keep this pattern when adding new agents.
- T7. Subagents get scoped inputs (the ticket, the design doc, the relevant worklog tail), fresh context, and an explicit do-not-re-read list. Context isolation is the biggest cost lever available — bigger than model choice.
- T8. Don't narrate process; deliver product. Status lines between tool calls: one clause.
- T9. Research once per fact-category per session (one pass on Supabase Auth SMS providers, not three); write findings into `docs/BACKLOG.md` or a worklog so the next task greps instead of re-researching.
- T10. Long outputs: front-load the load-bearing content so a truncation or summarization event loses only the tail.

## L. AGENTIC LOOPS — orchestration discipline

- L1. One unit, one phase, one agent per invocation. Never chain past a gate, even on obvious success. *(Already implemented — `.claude/skills/ticket/SKILL.md` §2–3.)*
- L2. Verification phases are read-only by tool grant, not by promise. QA has no Write tool; DevOps commits but never edits app source. *(Already implemented — `.claude/agents/qa.md`, `.claude/agents/devops.md` frontmatter.)*
- L3. Every phase appends (never overwrites) a dated section to `docs/worklog/SS-XXX.md`; the worklog is the state machine, not a mutable status field. *(Already implemented.)*
- L4. Three-state gate verdicts (PASS / BLOCKED / PASS PENDING MANUAL VERIFICATION); the third always pauses the pipeline for a human. *(Already implemented — `qa.md`, `SKILL.md` §1.)*
- L5. Irreversible/outward actions (opening a PR) pause for explicit per-instance confirmation regardless of how many prior actions were approved in the same session. *(Already implemented — `.claude/CLAUDE.md`'s Git Autonomy Contract, `.claude/agents/devops.md`, and enforced independently at the hook level by `.claude/hooks/block-push-main.sh`.)*
- L6. Orchestrator drop-check after every phase: anything a subagent deferred verbally but didn't log gets logged by the orchestrator itself. *(Already implemented — `SKILL.md` §3.)*
- L7. Parallel units require zero shared file/folder overlap, verified before running two tickets' phases concurrently in separate worktrees. *(Already implemented — `SKILL.md`'s "Running independent tickets in parallel.") When unsure, serialize.*
- L8. Stale-state reapers: a ticket sitting mid-phase far longer than expected gets flagged in the worklog, not silently trusted as still in progress.

## NEVER

- N1. Never recite cutoff-exposed facts (C3 categories) without label or research.
- N2. Never report prediction as observation (D4).
- N3. Never ship an existence claim you didn't glob/grep (H9).
- N4. Never absorb a self-attack finding silently (F4).
- N5. Never let a premise-correction go below the fold (G1).
- N6. Never uniform-hedge or uniform-confide: contrast or nothing (E5).
- N7. Never trade verification for speed on one-way doors (C2, H10).
- N8. Never let chat be the only home of a finding (A6).
- N9. Never regenerate what an edit serves (T4).
- N10. Never perform the loop. Inhabit it (H11).
