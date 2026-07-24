# The Solo Builder's Prompt Playbook (v2)

> **Status: Frozen — reference only.** Meta-process for *authoring* a new project's pipeline from scratch, not a document read during normal ticket execution. It's kept as a reusable template; it is not maintained per-ticket and no agent should cite it mid-ticket. StyleSense's live pipeline has since been trimmed lighter than what this playbook sets up (two-lane risk-gating, tight worklogs, Active/Parked backlog) — CLAUDE.md and `.claude/skills/ticket/SKILL.md` are the source of truth for how this repo actually runs.

### From a one-page idea to a self-auditing, cost-aware, multi-agent Claude Code pipeline

A serialized, fill-in-the-blank set of prompts for taking *any* product — not a specific one — from idea to a running, multi-agent, continuously-audited build pipeline, while keeping token cost near its floor. Copy this file into a new project's `docs/` folder, swap in your own placeholders, and follow it phase by phase.

This is v2: it keeps the original phase map and adds the patterns proven in real multi-session, multi-model builds — a craft layer (Phase 5.5), a platform-currency audit (Phase 8.5), and a cross-cutting context-economy discipline (Phase X). Together with the standards file (Phase 5), it ships as a set with two companions: `docs/OPERATOR_RULEBOOK.md` (rules) and `docs/OPERATING_MANUAL.md` (the reasoning behind them).

This is a generic handout, not a case study. No product, domain, or company is referenced anywhere in it on purpose — every prompt is written to be dropped into whatever you're building next.

---

## How to use this document

Each phase below follows the same shape: **Goal → What good output looks like → The prompt → Why it works → Context budget → Common pitfall.** The **Context budget** line is new in v2 and is the cost discipline — it names what a phase should load and, as importantly, what it shouldn't. Ignoring it is how a project with tens of thousands of tokens of docs turns every routine task into a needlessly expensive read.

- Placeholders are `ALL_CAPS` — replace them with your own project's specifics before you run the prompt.
- Run the phases in order the first time. Once you've done this once, you'll know which phases you can compress or skip for a smaller project.
- Phases 6 and 7 extend the pipeline itself once it exists — treat them as upgrades you bolt on, not one-shot setup you do once and forget.
- Phases 8–11 are prompts you run *on the pipeline itself*, not on the product — keep using them for the life of the project, not just once at the start.
- Phase X isn't a phase you run once — it's a discipline that applies to every task, from Phase 0 onward.
- A copy-paste appendix with all the prompts, stripped of commentary, is at the end — use it once you don't need the explanations anymore.

---

## Phase map

| # | Phase | What you produce | Where it typically lives |
|---|-------|-------------------|---------------------------|
| 0 | Ideation & feasibility | a market/ideation research doc | your planning notes |
| 1 | Architecture — HLD & LLD | a high/low-level design doc | your planning notes |
| 2 | Epics & tickets | an epics doc, then one file per ticket | `docs/tickets/raw/` |
| **2.5** | **Mid-project scope intake** | impact analysis + a new ticket, only after sign-off | `docs/tickets/raw/` |
| 3 | Build roadmap & environment plan | a setup guide + phased roadmap | your planning notes |
| 4 | Executing the setup, section by section | a scaffolded, deployable skeleton | your repo |
| 5 | The standards file | one binding conventions file | `.claude/CLAUDE.md` (or your tool's equivalent) |
| **5.5** | **The craft layer** | operator manual + rulebook | `docs/` |
| 6 | Multi-agent ticket pipeline | subagent definitions + an orchestrating skill | `.claude/agents/`, `.claude/skills/` |
| 7 | The cross-ticket backlog loop | a shared backlog doc + a logging/resurfacing step wired into every agent | `docs/BACKLOG.md` |
| 8 | Self-audit | a prioritized, evidence-based fix list | — |
| **8.5** | **Platform-currency audit** | dated deltas vs. the moving platform | `docs/` + backlog |
| 9 | Execute the fixes | a hardened, verified pipeline | — |
| 10 | Documentation / write-up | a shareable account of the build | — |
| 11 | Meta-audit of the prompting strategy | a document exactly like this one, for your own project | `docs/` |
| **X** | **Cross-cutting: context economy & session handoff** | cheaper every task | everywhere |

Bold rows are new: 5.5/8.5/X shipped as v2; 2.5 was added afterward, once a real mid-project scope gap actually showed up.

---

## Phase 0 — Ideation & feasibility

**Goal:** turn a raw idea into a feasibility study grounded in real numbers, before any architecture gets written.

**What good output looks like:** one document covering *why now*, how the target user actually behaves, why existing alternatives fail them, a monetization model with named revenue streams, infrastructure cost-per-user at a stated usage target, a feature architecture broken into named modules, a plainly-stated risk assessment, and a phased build roadmap.

**The prompt:**
```
Research the market opportunity for {PRODUCT_CATEGORY} in {TARGET_MARKET
OR SEGMENT}. Cover, as one document:
1. Why now — what changed that makes this viable today
2. Real user behavior for the target segment (not idealized personas)
3. Why comparable existing products underperform for this segment
4. A monetization model with named revenue streams
5. Infra cost-per-user at {TARGET_USAGE_LEVEL}, broken down by service
6. A feature architecture organized into named modules
7. A feasibility/risk assessment — name the real risks, don't soften them
8. A phased build roadmap
Everything built after this should be able to cite it as ground truth.
```

**Why it works:** forcing monetization and infra cost-per-user into the *same* document as feature scope stops the architecture phase from over-building features the unit economics can't support later. A feature list without a cost model is a wish list.

**Common pitfall:** treating this as a one-way document. Revisit it once real usage numbers exist — a feasibility study written before launch is a hypothesis, not a fact, and later phases should be allowed to contradict it.

---

## Phase 1 — Architecture: HLD & LLD

**Goal:** translate the ideation doc's feature modules into a concrete, buildable architecture — stack, data flow, contracts, and the abstractions that let any external provider (AI, payments, messaging, whatever you depend on) change later without touching business logic.

**What good output looks like:** system overview and architecture principles, an architecture diagram, a tech stack chosen against an explicit cost ceiling, each core user flow named individually (not lumped into one generic "main flow"), every external capability behind a named interface with one fully worked interface-and-adapter example (not just a signature), a complete data schema, at least one full API contract example, an explicit section on the design principles you're holding yourself to, a clean folder architecture, a hosting/CI-CD plan, an environment strategy (local/preview/prod), and a security architecture.

**The prompt:**
```
Turn {IDEATION_DOC} into a full HLD/LLD architecture document.
Constraints: {cost ceiling, e.g. "near-zero infra cost at launch" or
"under $X/month"}; every external capability (AI provider, payments,
messaging, storage — whatever applies) sits behind a named interface
(ports & adapters) so it can be swapped without touching business
logic — show one full worked interface + adapter pair, not just a
signature. Include: system overview & principles, architecture
diagram, tech stack, each core user flow named individually, the
complete data schema, one full API contract example, an explicit
design-principles section, a clean-architecture folder layout, a
hosting/CI-CD plan, an environment strategy (local/preview/prod), and
a security architecture.
```

**Why it works:** naming the interfaces at the architecture stage — not at first use — means every later ticket has one unambiguous place to put new adapter code, instead of each ticket re-deciding the abstraction from scratch. This is usually the single highest-leverage decision in the whole architecture phase.

**Common pitfall:** leaving the interface abstract. If you don't force one worked example into the document, "ports and adapters" stays a slide-ware idea that nobody actually follows once real deadlines hit.

---

## Phase 2 — Epics & tickets

**Goal:** break the architecture into dependency-ordered epics, then into individually buildable tickets small enough for one agent phase to implement in one sitting.

**What good output looks like:** epics ordered by real dependency — foundation and auth first, your core domain feature next, any AI/automation-driven feature after that, secondary features, community/social features if applicable, monetization, then launch prep — never ordered by which feature sounds most exciting. Within each epic, tickets small enough to finish in one sitting, using a fixed template.

**The ticket template to standardize on:**
```
# TICKET-ID — Title
`[Type]` `[Priority]` `[Sprint]` `[Points]` Est: Xh
Depends on: TICKET-ID

## Description
## Acceptance Criteria
## Technical Notes
## Edge Cases & Failure Modes
## Status note (this repo)
```

**The prompt:**
```
Break {ARCHITECTURE_DOC} into epics ordered by dependency, not by
feature glamour — foundation/auth first, core domain functionality
next, any AI-driven or automation-driven feature after that, secondary
features and monetization last. Within each epic, write tickets small
enough to implement in one sitting:
  Description / Acceptance Criteria / Technical Notes /
  Edge Cases & Failure Modes / Status note (what's already true in the
  current codebase vs. what's still open — check it, don't assume it)
```

**Why it works:** the **status note** field matters more than any other part of this template. Plans drift from reality within days. A ticket that doesn't say so out loud is a ticket that gets an agent re-building something that already exists, or silently skipping something that doesn't.

**Common pitfall:** writing the status note once, at ticket creation, and never updating it. It should be re-checked every time a ticket re-enters the pipeline after being blocked.

---

## Phase 2.5 — Mid-project scope intake (new)

**Goal:** give a feature idea that surfaces *after* Phase 2's epics/tickets doc was written — something the original architecture and epics doc genuinely never scoped — a repeatable path into the pipeline, instead of either hand-writing an ad hoc ticket or letting it live only in chat/memory.

**What good output looks like:** a two-stage, human-gated intake. Stage 1 is an impact-analysis report — what the idea touches, whether it's a breaking change to anything already shipped, whether it's actually already planned under a different ID, a proposed priority/sprint with dependency reasoning, and draft acceptance criteria — that stops and waits for explicit sign-off before anything is written. Stage 2, only after sign-off, creates the ticket using the same template as Phase 2, plus one addition: a "Source note" section (parallel to "Status note") stating why the idea exists and what gap it closes, since — unlike every other ticket — nothing in the original architecture doc explains its presence.

**The prompt:**
```
A new idea has come up that isn't in {ARCHITECTURE_DOC} or {EPICS_DOC}:
{IDEA}. Stage 1 — impact analysis only, do not create anything yet:
what does this touch; is it a breaking change to anything already
shipped (check existing tickets/worklogs); is it actually already
planned under a different ID; a proposed priority and sprint with
dependency reasoning; draft acceptance criteria. Stop and wait for my
explicit confirmation. Stage 2, only once I confirm: create the ticket
using the standard template plus a Source note section explaining why
it exists; update the ticket index; flag whether the architecture doc
is now out of date because of this (see Phase X's amendments pattern
below) rather than silently letting it drift.
```

**Why it works:** the two-stage split is the whole mechanism — collapsing impact analysis and ticket creation into one step means an agent either has to guess at priority/sprint (removing the human from a decision only they should own) or ask mid-stream in a way that's easy to skip under momentum. Forcing a stop between "here's what I found" and "here's what I built" makes the pause structural, not a matter of the agent remembering to ask.

**Context budget:** Stage 1 reads the same distilled sources Phase 2's ticket-writing already produced (the epics doc, the architecture doc — narrowly, for the relevant section, not in full) plus the ticket index and backlog, so it costs about one extra judgment-tier pass, only for genuinely ad hoc ideas — the steady-state ticket flow this phase doesn't touch is unaffected.

**Common pitfall:** routing something through this that's actually a small addition to an *existing* ticket's scope. That should just be an edit to that ticket — full intake is for things that don't have a home yet, not a default first move for every new thought.

---

## Phase 3 — Build roadmap & environment plan

**Goal:** turn the epics into a week-by-week build plan, plus a complete environment/account/repo setup checklist to follow *before* any feature code is written — and decide, up front, which recurring operational work you'll automate versus do by hand.

**What good output looks like:** a developer setup guide (every account/service needed, target repo structure), a phased build roadmap, and a short list of always-on operational agents — something that reviews every pull request automatically, something that scans dependencies and secrets, something that runs your test suite and reports coverage, something that emails a periodic health summary, something that watches spend on any metered API you depend on.

**The prompt:**
```
Turn {EPICS_DOC} into a phased, week-by-week build roadmap. Write a
developer setup guide: every account/service needed before writing
feature code, and the target repo structure. Separately, design
always-on operational agents for: PR review, dependency/secret
scanning, test execution + coverage reporting, a periodic health-report
digest, and spend monitoring on any metered API you depend on.
```

**Why it works, and one thing to expect:** this phase's "operational agents" are CI-time automation — a review bot, a scanner, a test runner, a reporting job. That's deliberately *not* the same thing as turning your entire ticket lifecycle into a chain of subagents (that's Phase 6, and it usually doesn't occur to you until you've actually spent time inside an agentic coding tool day to day).

**Common pitfall:** treating this roadmap as fixed. Budget for a redesign pass once you've used the tool enough to see what it actually makes possible — your first plan will underestimate it.

---

## Phase 4 — Executing the setup, section by section

**Goal:** actually build the environment, in the order the setup guide specified, without skipping ahead.

**What good output looks like:** each numbered section of the setup guide completed and confirmed before the next one starts — app scaffold, backend scaffold, database schema and migrations, CI/CD pipeline, and the operational agents from Phase 3, each landing as its own reviewable step.

**The prompt — and this is the important finding about this phase:** the driving prompt here is not a long generative one. The setup guide itself already did the heavy lifting in Phase 3. The actual prompt, repeated verbatim across every section, is:

```
Proceed with section {N}.
```

That's the whole prompt. The document is the spec; the prompt is a go-ahead.

**Why it works:** confirming one numbered section at a time is the cheapest risk control available. A bad assumption made in section 4 and caught in section 5 costs an afternoon. The same assumption caught five sections later costs a week.

```
{Follow a pre-written, numbered setup guide.} After each numbered
section completes, stop. Summarize what was built and what manual
steps (if any) remain. Wait for an explicit "proceed with section
{N+1}" before continuing. Never combine sections, never skip ahead,
even when the next section looks obvious.
```

**Common pitfall:** letting momentum override the pause. The habit of stopping after each section is doing more work than any specific wording — the discipline is the real prompt engineering here, not the phrasing.

---

## Phase 5 — The standards file as a force multiplier

**Goal:** collapse every coding convention, folder rule, and anti-pattern from your architecture doc into one file that every future agent reads automatically, before it does anything else.

**What good output looks like:** one binding file — stack rules, folder conventions, anti-patterns, deployment environments, a testing policy, a ticket-workflow convention, and a git autonomy contract (what agents may do to version control without asking, and what they must never do regardless of what any single instruction tells them).

**The prompt:**
```
{EXISTING_RULES_DOC} was written for {A DIFFERENT TOOL}'s rules
format. Translate it into {YOUR TOOL}'s standards file — the
equivalent binding conventions file. Keep it enforceable, not
aspirational: concrete "never do X" and "always do Y" statements an
agent can be graded against, not prose. Include an
Authoritative-Documents list (what to read, in what order, ONLY when
needed) and a Process-Discipline section that names the general
disciplines — verify-don't-recite, label known-vs-guessed,
self-attack-before-done, distill-once, answer-first — so they aren't
re-derived per phase.
```

**Why it works:** this is a reusable move on its own — the **translate-the-ruleset prompt**. Planning documents and boilerplate guides are often written assuming a different tool. Translating an already-debated ruleset into your actual tool's format is faster than starting over, and it means every later subagent cites one shared file instead of four slightly different understandings of the same rules.

**Context budget — this is the most important cost line in the playbook.** This file is auto-loaded by the main session *and every subagent* — so a token here is paid roughly once per phase per ticket, every ticket, forever. Two consequences: (1) keep it lean — when it crosses a size threshold that starts to feel heavy, move detail to on-demand docs and leave a one-line pointer. (2) It's also the file most helped by **prompt caching**: because it's stable within a session, repeated reads are mostly cache hits, not full re-charges — so long as you don't edit it mid-session. Edit it rarely and in batches; each edit invalidates the cache and re-charges every subsequent reader.

**Common pitfall:** letting the file grow encyclopedic. Most agent runtimes cache this file for cost reasons — keep it lean, or you lose both the caching benefit and the "actually enforceable" property.

---

## Phase 5.5 — The craft layer (new in v2)

**Goal:** encode *how to think*, separately from *what the conventions are* — so a weaker or fresh model operates near the level of the strongest one that set the project up.

**What good output looks like:** two companion files. An **operating manual** (the reasoning: how to read a request beneath its words, decompose by verification boundary, weight risk by irreversibility × silence, verify by re-derivation, label epistemic state, self-attack before handover, communicate answer-first, and the mistakes that look like competence). An **operator rulebook** (the same craft compressed into imperative, checkable rules — cheap enough to reference — plus a token-economy section and an agentic-loop section the manual doesn't carry).

**The prompt:**
```
Write two companion files for whoever operates this project next. (1)
An OPERATING MANUAL — a senior operator handing craft to a sharp
junior: how to read what a request actually asks; decompose into
independently checkable pieces; decide where the real risk lives;
verify by re-deriving, not trusting; separate known from guessed and
label it; attack your own conclusion before handoff; communicate
answer-then-reasoning-then-risk; and the specific mistakes that look
like competence. Ground each section in real decisions from this
project where you can. (2) An OPERATOR RULEBOOK — the same craft as
imperative, checkable rules, organized by phase of work (intake,
decompose, risk-weight, verify, label, self-attack, deliver,
anti-patterns), plus a TOKEN ECONOMY section and an AGENTIC LOOPS
section. Make the rulebook cheap enough to reference from the
standards file; summarize its highest-value rules INTO the standards
file so the full rulebook rarely needs loading. Manual wins on
conflict.
```

**Why it works:** most of the gap between a stronger and a weaker model on real work is process discipline, and process is copyable. The manual holds the *why* (for novel cases the rulebook didn't anticipate); the rulebook holds the *checklist* (for speed on the common case). Summarizing the rulebook's highest-value rules into the standards file means the standards file carries most of the value at a handful of lines, and the full rulebook loads only when a case genuinely needs it.

**Context budget:** both files are **on-demand, never auto-loaded** — this is deliberate. The manual should be read maybe once per novel situation; the rulebook only when the standards-file summary isn't enough. Auto-loading either would be the biggest self-inflicted cost mistake available in this whole playbook.

**Common pitfall:** re-pasting the craft into multiple files. It lives in exactly two, referenced by pointer everywhere else. Duplication here is the exact bloat the craft layer warns against.

---

## Phase 6 — Designing the multi-agent ticket pipeline

**Goal:** go beyond CI-time automation and turn the *entire ticket lifecycle* — design, implementation, verification, release — into a chain of subagents, each scoped to exactly one phase.

**What good output looks like:** one file per phase, each with its own tool grant and model tier, plus one orchestrating skill that reads a per-ticket record to determine the next phase, invokes exactly one subagent, and stops.

| Agent | Model tier | Tools | Job |
|---|---|---|---|
| Architect | Reasoning | Read, Glob, Grep, Write | Ticket → unambiguous design doc. Never touches app code. |
| Developer | Reasoning | Read, Write, Edit, Bash, Glob, Grep | Design doc → implementation + the tests it specifies. |
| QA | Fast | Read, Bash, Grep | Verifies each acceptance criterion individually. Never edits. |
| Releaser | Fast | Bash, Read | Branch, commit, push, PR — only after QA passes. |

**Three-state verdict (new in v2):** `PASS` / `BLOCKED` / `PASS PENDING MANUAL VERIFICATION`. The third exists because a read-only verifier genuinely cannot exercise a rendered screen, a live notification, or a real external round-trip — forcing those cases into binary pass/fail makes the agent lie in one direction (usually toward pass, since that's the less confrontational answer). On the third state, the orchestrator stops and asks the human to confirm before release proceeds.

**The prompt:**
```
Design a {N}-phase pipeline for taking one {UNIT_OF_WORK} from spec to
shipped, as {N} separate subagents — one per phase of your actual
SDLC (design / implement / verify / release, or your own equivalent).
For each: one file, an explicit tool grant, an explicit model tier
(stronger model for judgment-heavy phases, cheaper for mechanical
ones), and an explicit instruction not to re-read source material a
previous phase already distilled. Verification is read-only BY TOOL
GRANT, not by promise, and returns a three-state verdict (pass /
blocked / pass-pending-manual-verification), where the third pauses
the pipeline for a human on anything its tools can't exercise. State
lives in an append-only per-unit worklog that every phase appends to
(never overwrites), ending each entry in a Verdict line — the
orchestrator reads the last verdict to pick the next phase. Write one
orchestrating skill that runs exactly one phase, and always stops —
never chains phases automatically, even when the previous phase
clearly succeeded.
```

**Why it works:** context isolation. Each subagent gets a fresh context and is told explicitly what *not* to re-read. This single decision is usually the biggest cost lever in the whole system — bigger than model choice alone — and it only works if the pipeline is designed around isolated phases from the start. The append-only worklog matters for the same reason a mutable status field doesn't: a field that gets overwritten by every phase loses the history of *why* a decision was made the moment the next phase runs; an append-only log keeps the audit trail intact while still giving the orchestrator one place (the last verdict) to read for "what happens next."

**Context budget:** per phase, load: the agent's own definition (small) + the standards file (cached) + the ticket + the *relevant tail* of the worklog + the one distilled input that phase needs. Explicitly **not**: the architecture doc, the PRD, other tickets, sibling docs. As the worklog grows per ticket, instruct late phases (QA/release) to read the last Verdict plus the relevant section, not the entire history.

**Common pitfall:** letting a fast/cheap-tier agent make judgment calls it isn't equipped for. A verification agent on a cheap model is fine for mechanical checks; give it an explicit instruction to say "needs manual verification" instead of guessing on anything genuinely ambiguous or subjective (visual/UX judgment, for example) — otherwise it will quietly rubber-stamp things it can't actually evaluate.

---

## Phase 7 — The cross-ticket backlog loop

**Goal:** stop a deferred finding from any single phase — design, implementation, verification, or release — from quietly disappearing once the ticket that found it ships. A ticket's own design doc or worklog stops being read the moment that ticket is done; this phase adds a cross-ticket memory that doesn't.

**What good output looks like:** one shared backlog document — not per-ticket — with an **Open** table and a **Resolved** table. Every row records an ID, a title, a *source* (which ticket and which phase found it), a description, and when it was logged. A resolved row keeps all of that and adds who resolved it and a one-line note on how — nothing gets deleted, so the resolved table doubles as an audit trail. Every phase of the pipeline gets two new responsibilities threaded into its existing instructions, not bolted on as an afterthought:

- **Resurfacing** — before starting its own work, a phase checks the backlog's Open table for rows whose domain overlaps what it's about to do. If it can actually resolve one now, it does, and closes it out, instead of leaving it to ride further.
- **Logging** — whenever a phase finds or defers something that isn't its own hard blocker but might matter later or needs a human decision, it appends a new row rather than silently picking an answer just to avoid writing it down.

The orchestrator gets the same two responsibilities, one level up: it skims the backlog before invoking each phase and flags relevant rows in that phase's own prompt (matched loosely by domain, not just by exact ticket ID), and afterward it confirms nothing backlog-worthy got dropped — if a phase mentions something deferred that never made it into the file, the orchestrator appends it itself. If a human explicitly says "let's deal with that later," that gets logged immediately, on the spot, rather than trusted to a future phase's memory.

**The prompt** — field-tested, close to exact wording:
```
Add a new step, agnostic of any one ticket but applying to all of
them: create a separate backlog document for all the pending tasks
in each phase that need to be revisited later. Log the full detail
of the open task and which ticket and which phase (architect / dev /
qa / devops, or your own phase names) it stemmed from, and add this
as a step to every agent's own instructions — not just a note in this
one ticket's files.

If an open item can be resolved during any future ticket's phase, it
needs to be analyzed, worked, and closed out accordingly, not just
left sitting there.

Make sure this is actually handled: the backlog needs to resurface on
its own and must not get lost in the velocity of ongoing development.
```

**Why it works:**
- **"Agnostic of this ticket but for all tickets"** explicitly scopes the change as a pipeline-level edit, not a one-ticket fix — it tells the agent to go modify the shared agent definitions themselves, not just do something inside the current unit of work.
- **Naming the exact provenance to capture** (which ticket, which phase) up front means every resulting entry is traceable later, instead of degrading into a vague running list of TODOs nobody can trace back to a cause.
- **The explicit close-the-loop clause** — resolved items get analyzed, worked, and closed by whichever future phase can actually do it — is what turns this into a queue that gets worked down, instead of a one-way dumping ground.
- **"Should resurface and not get lost in the velocity of development"** is the actual design constraint, and it's the clause that matters most: it asks for an active resurfacing mechanism, not just a place to write things down. That single line is what forces the orchestrator-level responsibilities above — a backlog nobody re-reads is indistinguishable from a graveyard.

**Common pitfall:** shipping the logging half without the resurfacing half. Writing things down feels like progress, but a backlog that only grows and never gets checked before the next unit of work starts is just a slower way to lose the same information. Also worth guarding explicitly: give append-only tools (rather than full rewrite access) to any phase that's otherwise read-only or restricted — a shared file that every phase can freely rewrite is a merge-conflict waiting to happen, especially once you're running independent units of work in parallel.

**Creeping-cost control (new in v2):** the Open table gets re-scanned before every phase of every ticket, so its cost compounds as it grows — but the Resolved table only ever gets appended to and rarely re-read in full. Once Resolved passes roughly 30 rows, archive older entries to a separate file (e.g. `docs/BACKLOG_ARCHIVE.md`) rather than letting the live backlog grow indefinitely; keep the archive as the permanent audit trail, and keep the live file the size a phase can actually afford to scan.

---

## Phase 8 — Self-audit: "make this 10x"

From here on, these prompts run *on the pipeline itself* — use them repeatedly, not just once.

**The prompt** — field-tested, exact wording:
```
Act as an agentic AI implementation engineer using workflows as a
senior software engineer. Go through the agentic setup and entire
workflow using the tool itself. Find the issues and how the process
can be more optimized, cost-effective, and quicker for the entire
end-to-end lifecycle of product development. Research what the best
practices are around this — what 10x agentic-implementation
practitioners are doing to automate their workflows with high
efficiency and quality output.
```

**Why it works, broken into its actual ingredients:**
- **Role framing** ("act as a senior engineer doing an audit") sets an evaluative mode, not a generative one.
- **A named, concrete scope** — cost, speed, quality — turns the audit into something with a rubric instead of an open-ended "how's it looking."
- **An explicit research mandate**, separate from the audit itself, forces the answer to be checked against something outside the project's own assumptions.
- **No file list is given.** Trusting the agent to find its own surface area finds more than a pre-narrowed search would.

**Context budget:** this one legitimately ranges wide — it needs to read broadly to find its own surface area. Contain the *output*, not the input: require a disposition table, not a re-narration of the codebase, so an expensive read still produces a compact, actionable artifact.

**Common pitfall:** running this once and considering it done. Schedule it — a pipeline audit decays the same way code does if nobody looks at it again.

---

## Phase 8.5 — Platform-currency audit (new in v2)

**Goal:** catch the ground moving under you. Anything platform-versioned, priced, deprecated, or CLI/SDK-flagged rots between your training cutoff and now — and a stale fact looks exactly as confident as a fresh one, because confidence is a property of the writing, not of whatever checking did or didn't happen behind it.

**What good output looks like:** a dated deltas doc — what changed in the platforms/toolchains/dependencies since the design was written, each finding labeled `[VERIFIED <date>]`, with a disposition (fix now / backlog / doc-only) and every affected artifact actually updated, not just noted. Real examples this catches: a retired CLI command still referenced in CI, an auth mechanism being sunset, a changed default, a fee or quota that changed, an open upstream bug that breaks a documented happy path.

**The prompt:**
```
Audit this project against the CURRENT state of {PLATFORM/TOOLCHAIN/
DEPENDENCIES}. Research — don't recite — recent releases,
deprecations, retired commands, changed defaults, pricing/quota
changes, and known upstream bugs affecting anything we document or
depend on. For each finding: [VERIFIED <date>], the affected files,
and a disposition (fix now / backlog / doc-only). Fix the
correctness-breaking ones; backlog the rest with dates. Distrust
documentation freshness — check the primary source and the issue
tracker, not just a search-result summary or memory.
```

**Why it works:** it makes staleness a scheduled audit instead of a production surprise. The "distrust documentation freshness" instruction is what catches the case where even the official docs lag a known bug or a since-changed default.

**Context budget:** research-heavy by nature — that's inherent to the task, not a mistake to fix. Contain it by scope, not by skipping research: audit one platform-surface category at a time (auth providers, then CI tooling, then payments, …), and write findings to a doc as you go so the next session greps the findings instead of re-researching the same ground.

**Common pitfall:** trusting a search-result summary over the primary source when the detail is load-bearing (a fee, a deprecation date, a security-relevant default). Fetch the source for anything a real decision hangs on.

---

## Phase 9 — Execute the fixes

**The prompt** — field-tested, exact wording:
```
Prioritize and start with all the fixes. Let's make this 10x.
```

**Why it works:**
- **Short and decisive.** It delegates prioritization back to the agent that just finished the audit and already has full context on what matters most.
- **"10x" as an implicit quality bar**, not a literal instruction — communicates "don't do the minimum," without over-specifying what "properly" means for a list of unrelated fixes.
- **It works best paired with a standing rule, not written into the prompt itself:** when the agent finds more work than it was asked to do, it should surface a scoped choice, not silently expand the task on its own judgment.
- **Prove it, don't just claim it.** Anything fixable should be verified twice — once standalone, once triggered for real through the live system — before being reported as done.

**The fuller version worth keeping as a standing instruction, not a one-off prompt:**
```
Prioritize and start fixing all of it. Make it excellent, not just
adequate. When you find something outside the original scope (a
config drift, a broken assumption, a decision only I should make),
stop and ask — as a short, scoped choice, not an open question —
rather than deciding silently. Prove every fix actually works before
calling it done: test it standalone first, then trigger it for real
through the live system, not just by reading the code back.
```

**Context budget:** works from the disposition table produced by Phase 8/8.5, not a fresh re-audit. Don't re-read what the audit already found — the table is the distillate; treat it the same way a ticket's Technical Notes are treated by the pipeline's later phases.

**Common pitfall:** letting "10x" become an excuse for scope creep. It's a quality bar for the fixes already identified, not a license to invent new ones mid-flight without flagging them.

---

## Phase 10 — Turning the pipeline into a write-up

**Goal:** document the build in a form that's actually shareable — which forces the writing to be reusable rather than a one-off internal memo.

**The prompt:**
```
Act as a technical writer, an expert in agentic AI implementation in
multi-agent workflows, and an experienced senior software engineer.
Write a Medium-style blog post about the entire setup — ideation,
architecture (HLD/LLD), epics and tickets, the implementation agents,
the entire workflow run through the agentic tool, common mistakes,
major mistakes, fallbacks, human-intervention needs, efficiency, cost
and token optimization, gotchas, things to remember, environment
setup, the multi-agent setup, self-audit and optimizations, and
learnings. Add more sections if needed; serialize the sections based
on good document structure.

Constraint: the post must not reference the actual product or business
idea in any way. Make it idea-agnostic, using a generic placeholder
app, so the lessons are portable to any project.
```

**Why it works:**
- **A persona stack, not one role** (writer + domain expert + senior engineer) sets voice, credibility, and structural judgment all at once.
- **The content checklist doubles as the section outline** — listing every topic to cover is both scope and structure.
- **An explicit structural instruction** ("serialize based on good document structure") is what turns a topic dump into an actual narrative arc — keep this even when a checklist already exists, since checklist order and reading order are rarely the same thing.
- **The portability constraint is the real payload.** Anything that can only be published for one specific product is worth less than the same lessons written so any team could use them.

**Common pitfall:** skipping the portability constraint because "no one else will read this anyway." The constraint is what forces genuinely reusable writing — you get the portable version for free, and you can always re-add specifics later if you choose to.

---

## Phase 11 — Meta-audit of the prompting strategy

**Goal:** treat your own prompting strategy as an artifact worth documenting and revisiting — not just the product you're building.

**The prompt:**
```
I want to create a document of the prompts that helped me through this
entire process — every step, every phase, everything covered, each
part of the serialized prompting strategy from ideation to now.
```

**Why it works:** a prompt asking to document the prompting strategy is itself part of the prompting strategy, and that recursion is the point, not a flaw. It's the most reusable habit in this entire playbook — more reusable than any single template above:

> Periodically ask the system to document — and, before that, to audit — its own process. Not just the product it's building. The process itself is an artifact, and it decays the same way code does if nobody looks at it.

**The generic version, for your own project:**
```
Create a serialized document of the prompts driving this project,
phase by phase, from the first idea to right now. For each phase: the
goal, what it produces, the prompt that drives it, why it works, and
a genericized reusable version. Close with cross-cutting patterns and
a copy-paste template appendix.
Constraint: make it idea/product-agnostic — no specifics about what's
actually being built — so it works as a handout for any project.
```

**Common pitfall:** writing this once and letting it go stale. Treat it the way you'd treat a runbook — update it when a phase's prompt changes, not just when you remember to.

---

## Phase X — Cross-cutting: context economy & session handoff (new in v2)

Not a phase you run once — a discipline that runs on every task, and the answer to "how do I keep cost down once the project already has tens of thousands of tokens of docs."

**The core principle:** you pay tokens for what you *load*, not for what *exists*. A large doc set costs nothing until something reads it. The entire cost game is: **load the minimum, exactly once, and never re-load what's already been distilled.** Everything below serves that.

**Four signals to build into a project so every session loads cheaply:**

1. **The Authoritative-Documents list (in the standards file) is an inclusion map, not a table of contents.** It says *read X only when doing Y*, not just *X exists*. A session that needs to touch one domain reads the section for that domain, not the whole architecture doc. Make this explicit.
2. **Every reference doc opens with a 2-line "what this is / read-if" header**, so a session can decide from a handful of tokens whether it needs the rest at all. Cheap triage beats expensive reads.
3. **The distill-once rule is enforced, not hoped for:** tickets carry the design slice in their Technical Notes; agent definitions are told explicitly not to re-open the source doc a prior phase already distilled. The architecture doc is read in full exactly once and never again.
4. **The session-handoff prompt is a first-class artifact.** When you switch sessions or models to save cost — spinning up a fresh, cheaper session for a well-scoped task — don't paste a heavily-worded, context-dependent prompt built for a session that already knows the project. It will be read literally, trigger blind exploration of the whole doc set trying to reconstruct context you already had, and end up costing *more* than not switching at all. Instead hand the new session a scoped handoff prompt.

**The handoff-prompt template:**
```
Context: {PROJECT}. {STANDARDS_FILE} auto-loads; also read {README/
DOC-MAP} first for the file map. Read ONLY these, in order: {FILE
§section}, {FILE §section}. Do NOT read {explicitly-excluded files} —
not relevant to this task. Already decided (cite, don't re-derive):
{facts + where they live}. Apply {labeling + verification
conventions in force}. Task: {scoped ask}. Deliverables: {artifact +
location}. End with a standalone summary + anything [CONFIRM]-flagged
before I act on it.
```

**Prompt caching is your friend — don't fight it.** Stable, auto-loaded content (the standards file) is cached across a session, so its repeated reads by many agents are mostly cache hits, not full charges. The practical implication: keep that content stable *within* a session — batch edits rather than dribbling them out, because every edit invalidates the cache and re-charges every subsequent reader at full price. The variable, growing content — worklogs, the backlog, the specific docs a task pulls — is where real per-task cost actually lives, so that's where the minimization effort goes, not the cached baseline.

**Model-tier matching is cost matching:** judgment-heavy phases (architecture, audit, review) get the strong tier; mechanical phases (release chores, grep-audits, verification) get the cheap tier with an explicit "escalate, don't guess on ambiguity" instruction. Running everything on the strongest tier is the quiet, steady overspend — it never shows up as one big charge, only as a bill that's consistently higher than it needed to be.

---

## Cross-cutting patterns

These show up more than once, at different scales, which is what makes them worth keeping separate from any single phase:

- **Role + constraint + output-format framing.** Nearly every high-value prompt above names *who* the model should act as, *what axes* to optimize against, and *what shape* the output should take — in that order. Prompts that skip one of the three produce noticeably vaguer results.
- **Confirm before proceeding, at every scale.** Section by section in the setup guide. Phase by phase in the ticket pipeline. Before every PR, every single time, no matter how many prior tickets were auto-approved. Same instinct, three different granularities — build it in at all three.
- **Write down drift, everywhere.** A ticket-level status note. A pipeline-level audit trail. An environment-level handoff record. All three exist for the same reason: assume the plan and reality have already diverged, and make something say so explicitly rather than assume they still match.
- **A backlog that's write-only is a graveyard, not a backlog.** Logging a deferred item is half the job; the other half is something — a phase, an orchestrator, anyone — actually checking it again before the next relevant piece of work starts. Build the resurfacing check in at the same time as the logging step, not as a follow-up.
- **Ask, don't silently expand scope.** When an agent finds more to fix than it was asked to fix, the reusable move is a short, scoped question back to the human — not a unilateral judgment call, and not a return with an open-ended "what do you want me to do?"
- **Research before opinion.** Any time an agent is asked to judge prior work — especially its own team's — ask for external grounding before internal critique. It has no built-in reason to be harsher on itself than the room already was.
- **Translate, don't restart.** A standards file born from translating an existing, already-debated ruleset beats re-litigating every rule from a blank page.
- **Portability constraints force better writing.** Telling a writer their output has to work for an audience beyond the one obvious reader produces material that also happens to serve that one obvious reader better.
- **Prove it, don't just claim it.** Test every change twice — once in isolation, once live — before reporting it done. That's the difference between "should work now" and "just verified this actually happens."
- **Verify by re-deriving, label what's guessed, attack before handoff, answer-first.** The craft layer (Phase 5.5), applied to everything, not just the pipeline's own phases.
- **Load the minimum, once.** The cost layer (Phase X), applied to everything — every doc read, every session started, every subagent spun up.

---

## Appendix: copy-paste templates

All prompts, stripped of commentary, for reuse once you don't need the explanations anymore. New/changed in v2 are marked ★.

**0 — Ideation → feasibility doc**
```
Research the market opportunity for {PRODUCT_CATEGORY} in
{TARGET_MARKET}. Cover, as one document: why now; real user behavior
for the target segment; why comparable existing products underperform
here; a monetization model with named revenue streams; infra
cost-per-user at {TARGET_USAGE_LEVEL}; a feature architecture in named
modules; a feasibility assessment with real risks named plainly; a
phased build roadmap.
```

**1 — Architecture HLD/LLD**
```
Turn {IDEATION_DOC} into a full HLD/LLD. Constraints: {cost ceiling};
every external capability behind a named interface (ports & adapters),
with one worked interface+adapter example. Include: system overview,
architecture diagram, tech stack, each core flow named individually,
full data schema, one full API contract example, an explicit
design-principles section, clean-architecture folder layout,
hosting/CI-CD plan, environment strategy, security architecture.
```

**2 — Epics & tickets**
```
Break {ARCHITECTURE_DOC} into epics ordered by dependency. Within
each, write tickets small enough for one implementation pass:
Description / Acceptance Criteria / Technical Notes / Edge Cases &
Failure Modes / Status note (checked against actual current repo
state, not assumed).
```

**2.5 — Mid-project scope intake ★**
```
A new idea has come up that isn't in {ARCHITECTURE_DOC} or
{EPICS_DOC}: {IDEA}. Stage 1 — impact analysis only, do not create
anything yet: what does this touch; is it a breaking change to
anything already shipped; is it actually already planned under a
different ID; a proposed priority and sprint with dependency
reasoning; draft acceptance criteria. Stop and wait for explicit
confirmation. Stage 2, only once confirmed: create the ticket using
the standard template plus a Source note section explaining why it
exists; update the ticket index; flag architecture-doc drift instead
of letting it happen silently.
```

**3 — Build roadmap & environment plan**
```
Turn {EPICS_DOC} into a phased, week-by-week build roadmap. Write a
developer setup guide covering every account/service needed and the
target repo structure. Design always-on operational agents for: PR
review, dependency/secret scanning, test execution + coverage
reporting, a periodic health-report digest, and spend monitoring on
any metered API.
```

**4 — Section-gated execution**
```
Follow {SETUP_GUIDE} section by section. After each section, stop,
summarize what was built and what manual steps remain, and wait for
an explicit go-ahead before continuing. Never combine or skip
sections.
```

**5 — Translate-the-ruleset ★**
```
{EXISTING_RULES_DOC} targets {OTHER_TOOL}'s format. Translate it into
{YOUR_TOOL}'s standards file, keeping every rule enforceable (a
concrete never/always an agent can be graded against) rather than
aspirational prose. Include an Authoritative-Documents inclusion map
(read X only when doing Y) and a Process-Discipline section
summarizing the craft layer's highest-value rules inline.
```

**5.5 — The craft layer ★**
```
Write two companion files: (1) an OPERATING MANUAL — how to read a
request beneath its words, decompose by verification boundary, weight
risk by irreversibility × silence, verify by re-derivation, label
epistemic state, self-attack before handover, communicate
answer-then-reasoning-then-risk, and the mistakes that look like
competence, grounded in real decisions from this project where
possible. (2) an OPERATOR RULEBOOK — the same craft as imperative,
checkable rules by phase, plus a token-economy section and an
agentic-loops section. Summarize the rulebook's highest-value rules
into the standards file; the full files stay on-demand, never
auto-loaded. Manual wins on conflict.
```

**6 — Multi-agent pipeline design ★**
```
Design a {N}-phase pipeline for taking one {UNIT_OF_WORK} from spec to
shipped, as {N} subagents — one per phase. Each gets: one file, an
explicit tool grant, an explicit model tier, and an explicit
instruction not to re-read what a prior phase already distilled.
Verification is read-only by tool grant and returns a three-state
verdict (pass / blocked / pass-pending-manual-verification); state
lives in an append-only per-unit worklog ending each entry in a
Verdict line. One orchestrating skill reads the last verdict, runs
exactly one phase, and always stops.
```

**7 — The cross-ticket backlog loop**
```
Add a new step, agnostic of any one ticket but applying to all of
them: create a separate backlog document for all the pending tasks in
each phase that need to be revisited later. Log the full detail of
the open task and which ticket and which phase it stemmed from, and
add this as a step to every agent's own instructions. If an open item
can be resolved during any future ticket's phase, it needs to be
analyzed, worked, and closed out accordingly. Make sure this is
actually handled: the backlog needs to resurface on its own and must
not get lost in the velocity of ongoing development.
```

**8 — Self-audit**
```
Act as an agentic AI implementation engineer using workflows as a
senior software engineer. Go through the agentic setup and entire
workflow using the tool itself. Find the issues and how the process
can be more optimized, cost-effective, and quicker end to end.
Research what 10x agentic-implementation practitioners actually do.
```

**8.5 — Platform-currency audit ★**
```
Audit this project against the CURRENT state of {PLATFORM/TOOLCHAIN/
DEPENDENCIES}. Research — don't recite — recent releases,
deprecations, retired commands, changed defaults, pricing/quota
changes, and known upstream bugs. For each finding: [VERIFIED <date>],
affected files, and a disposition (fix now / backlog / doc-only). Fix
the correctness-breaking ones; backlog the rest with dates. Distrust
documentation freshness — check the primary source and issue tracker.
```

**9 — Execute the fixes**
```
Prioritize and start with all the fixes. Let's make this 10x. (Standing
rule: surface a scoped choice on anything outside original scope
rather than deciding silently; prove every fix works live before
calling it done.)
```

**10 — Documentation / write-up**
```
Act as a technical writer, an agentic AI expert, and a senior software
engineer. Write a Medium-style post covering: {full content
checklist}. Serialize sections by good document structure, not
checklist order. Constraint: idea/product-agnostic — generic
placeholder app only — so the lessons are portable.
```

**11 — Meta-audit of the prompting strategy**
```
Create a serialized document of the prompts driving this project,
phase by phase, from the first idea to now. For each: goal, output,
the driving prompt, why it works, and a genericized template. Close
with cross-cutting patterns and a copy-paste appendix. Constraint:
idea/product-agnostic, so it works as a handout for any project.
```

**X — Session-handoff prompt ★**
```
Context: {PROJECT}. {STANDARDS_FILE} auto-loads; also read {README/
DOC-MAP} first for the file map. Read ONLY these, in order: {FILE
§section}, {FILE §section}. Do NOT read {explicitly-excluded files} —
not relevant to this task. Already decided (cite, don't re-derive):
{facts + where they live}. Apply {labeling + verification conventions
in force}. Task: {scoped ask}. Deliverables: {artifact + location}.
End with a standalone summary + anything [CONFIRM]-flagged before I
act on it.
```
