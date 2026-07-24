# The Operating Manual

> **Status: Frozen — reference only.** This is background reasoning, not a per-ticket document. Read it when a rule meets a case it didn't anticipate; don't cite it mid-ticket and don't grow it as routine process evolves (that goes in the rulebook, the agents, or CLAUDE.md). The setup is deliberately kept lighter than this manual's ambition — see the two-lane / tight-worklog / Active-Parked backlog trims in CLAUDE.md and `.claude/skills/ticket/SKILL.md`.

*What this is: the reasoning behind `docs/OPERATOR_RULEBOOK.md`. Read this only when a rule meets a case it didn't anticipate — the rulebook is the checklist; this is the why, for the cases the checklist can't cover. A senior operator's handoff, written for whoever (human or agent) runs this pipeline next. Not a checklist to satisfy — a way of working to inhabit. This manual wins over the rulebook on conflict.*

---

## The thesis, before anything else

Most of the gap between a stronger model and a weaker one, on real work, is not raw reasoning capacity. It's process discipline. The failures that actually cost time on this project are almost never "the reasoning was too hard." They are: a ticket read literally instead of actually; a claim shipped because it sounded right; a stale fact about a third-party platform delivered at the same confidence as a fresh one; a design decision never attacked before it shipped; effort spent evenly across a diff instead of where the real risk concentrates. Every one of those is a process failure, and process is copyable. Follow this manual honestly and you close most of that distance. Follow it performatively — going through the motions so the worklog *looks* diligent — and you close none of it.

Every incident referenced below is real and happened in this repo. When this manual says "we caught X," you can open `docs/BACKLOG.md` and read it.

---

## 1. Reading what a ticket or request is actually asking for

The literal words are the surface. Underneath is a job — extract the job before the first tool call.

**Identify the deliverable species.** Every request resolves to one or more of: a decision, a diagnosis, a diff, an artifact, a plan, a teaching. A ticket's Acceptance Criteria section is usually a *diff* request wrapped in a *decision* about interpretation — when an AC is genuinely ambiguous, `.claude/agents/qa.md` already instructs saying so explicitly rather than silently picking one reading. That instinct — flag the ambiguity instead of resolving it invisibly — is the read doing its job, and it should apply to Architect and Developer too, not just QA.

**Detect the question behind the question.** SS-003's phone-OTP work looked, on its surface, like "wire up Supabase Auth's phone provider." The real question underneath was "can we actually deliver an OTP to an Indian phone number in this environment" — and the honest answer required correcting the premise: MSG91 isn't a native Supabase Auth provider, Twilio doesn't bypass India's TRAI DLT registration either (DLT applies to the destination carrier, not the sending vendor), and the only channel that sidesteps DLT for testing is WhatsApp's sandbox or Supabase's built-in Test OTP feature. Answering the literal question ("configure the SMS provider") would have been responsive and wrong for a shipping timeline. Answering the real question meant surfacing a business decision (BL-001) instead of quietly picking a vendor. Premise-correction is the highest-value read available — deliver it as the headline, not buried three paragraphs into a design doc.

**Read scope words as contracts.** "Every acceptance criterion," "the whole flow," "end-to-end" are completeness contracts: they mean coverage will be judged, so enumerate the space and show the enumeration is grounded — QA's own instruction to check each AC individually, citing the specific file or test that satisfies it, is this same discipline already codified for one phase. Extend the instinct to the others: a narrow ask ("fix this one type error") gets a narrow answer, not an unsolicited refactor.

**Read the verbs for mode.** "Verify," "audit," "check" → adversarial mode: find what's wrong, deliver a disposition, not reassurance. "Compare, take inspiration from" (as when adopting patterns from another project's `.claude/` setup) → comparative synthesis: judge, adopt selectively, and say explicitly what you rejected and why — selective rejection is proof of judgment, wholesale copying is proof of none. "Recommend / decide" → make the call and justify it; don't hand back an option menu when judgment was asked for.

**The move that operationalizes all of this:** before executing, restate the request to yourself as a numbered deliverable list with species labels. If the restatement surprises you — if it contains work the literal words didn't mention — the read worked.

---

## 2. Breaking a ticket into independently checkable pieces

Decomposition is not organization. Organizing by topic (all the auth items together, all the UI items together) produces tidy sections; decomposing by *verification boundary* produces pieces that can each be proven done without trusting the others. The ticket template already forces this for Acceptance Criteria — "inserting a duplicate OTP request within N seconds is rejected (asserted in a test)" names its own proof. Apply the same discipline to anything that isn't a ticket: a research task decomposes into claims that each carry a source; an audit decomposes into findings that each carry a disposition.

**Decompose decisions apart from tasks.** They are different species and mixing them breaks sequencing. BL-018 (`public.users` auto-provisioning) is exactly this shape: it reads like a minor implementation detail sitting inside SS-003's scope, but it's actually a decision — DB trigger vs. application-level insert during SS-004's onboarding — that gates SS-004's own implementation. Filed by ticket number, it looks like SS-003 business; filed by dependency, it's a decision SS-004's Architect phase needs resolved before writing a design doc. When decomposing, ask of each piece: is this a task (produces an artifact) or a decision (unblocks other pieces)? Decisions float to the front regardless of where a ticket list puts them.

**Externalize the state.** Working memory — yours and the user's — is the first casualty of a long session or a ticket that spans multiple pipeline phases. Every decomposition lives in a file: the session's todo list, `docs/BACKLOG.md` for cross-ticket deferrals, `docs/worklog/SS-XXX.md` for the audit trail. The backlog discipline matters more than it looks — *logging* a deferred item is half the job; *resurfacing* (checking the Open table before every new piece of work, already wired into `SKILL.md`) is what keeps a growing backlog from silently dropping threads. A backlog nobody re-checks is a graveyard with a nice table format.

**Decompose your own uncertainty too.** SS-003's design phase separated: (a) claims checkable against the repo (does `public.users` have the columns the design assumes — grep the migration), (b) claims requiring current external research (is MSG91 actually a native Supabase provider — it wasn't, and only checking the docs directly caught it), (c) pure judgment calls needing no lookup (is a DB trigger or an app-level insert the right shape for BL-018). Each bucket has a different verification method; mixing them forces the most expensive method (research) onto things that were actually just a grep away, or worse, lets a grep-checkable claim get "verified" by memory instead.

---

## 3. Deciding where the real risk lives

Effort is finite. Spent evenly across a diff, it's spent wrong. Risk-weight everything: **probability of being wrong × cost of being wrong × silence of the failure.** The third factor is the one that gets forgotten — a loud failure (a `tsc` error, a failing test) self-corrects; a silent one compounds.

**One-way doors get the deepest scrutiny.** In this project: a Supabase migration applied against the live/staging project (only one project ref exists in the repo today — see BL-003 — so there's no disposable scratch environment to experiment against), a push to `main`, a Razorpay webhook accepted without HMAC verification, a `service_role` key that leaks into anything client-reachable, any DLT/SMS vendor commitment (BL-001 — choosing MSG91 vs. Twilio has real lead-time and cost consequences that aren't easily undone). Before any of these, ask "what does undoing this cost?" — if the answer is "a support incident," "a re-registration with a telecom regulator," or "you can't," that item gets ten times the verification of its neighbors.

**Knowledge-cutoff boundaries are standing risk.** Anything platform-versioned, priced, or deprecated rots between training and now, and it looks exactly as confident stale as fresh. BL-011 is the canonical instance: `react-native-worklets@0.8.3` was pinned in the repo, looked fine, and threw `WorkletsError` at import time the moment `react-native-reanimated@^4.5.0` actually needed `0.10.x` — a peer-dependency fact that no amount of re-reading the existing code would have surfaced, only checking the current package's actual peer range did. The countermeasure is categorical: Supabase Auth's supported providers, Expo SDK API surface, RN library peer ranges, Razorpay webhook behavior, TRAI DLT rules — researched or labeled, never recited from memory.

**Failures that ship to `develop`/`main` outrank failures caught locally.** BL-014/015/016/017/020 are the sharpest example of this project's own version of that lesson, run in reverse: a real fix (`secureStoreAdapter`, the `crlf`→`lf` biome setting, the arrow-function lint fix) existed *only* in an uncommitted local working tree, invisible to CI because CI checks out clean blobs. Every ticket's DevOps phase correctly treated those files as out of scope for its own diff — and so the fix silently never made it into a commit, passing locally and breaking on the next PR that happened to touch the same files. Rank risk by where it detonates: local dev loop (cheap, loud, self-correcting) < CI (cheap, loud) < `develop`/staging (costs a blocked PR) < `main`/production (existential, often silent until a user hits it). Local-only fixes are a standing risk precisely because "it works on my machine" and "it works in CI" are different claims, and the gap between them is invisible until something explicitly checks it — which is exactly the pattern DevOps eventually caught by diffing working-tree state against `HEAD`.

**Risk concentrates at seams.** The Supabase client boundary (`features/<domain>/*.queries.ts` — the *only* place Supabase gets called per `.claude/CLAUDE.md`), the FastAPI JWT dependency, the AI provider adapter interfaces (`ai/ports/interfaces.py`), the Razorpay webhook handler, the phone-OTP request/verify round-trip. When reviewing anything — a design doc, a diff, another agent's report — read the seams first and the straight-line component logic last.

**Where to spend effort, concretely:** 80% of verification on the ~20% of surface that's irreversible, external-facing, security-relevant, money-gating, or cutoff-exposed. The rest gets structural checks — does it typecheck, does it cross-reference, does it contradict the design doc — and no more. Uniform diligence starves the lines that actually needed it.

---

## 4. Verifying a claim by re-deriving it

Fluency is not truth. Output sounds right at a constant rate regardless of whether it *is* right — don't trust the feeling that a claim is "obviously fine." Re-derive it.

**The moves, by claim type:**

- **"X exists / is referenced correctly"** → grep the repo, glob the directory, open the file. Cross-reference integrity (does this design doc's cited component actually exist, does this ticket's dependency actually resolve) is always mechanically checkable; never certify it from memory.
- **"This is current Supabase/Expo/Razorpay behavior"** → fetch the primary source now, quote it. The MSG91 finding (BL-001) came from checking Supabase's actual documentation for natively-supported SMS providers, not from recalling what seemed plausible.
- **"This number is right"** → recompute. ₹ pricing, rate limits, coverage percentages, token/latency budgets logged per `.claude/CLAUDE.md`'s AI-call logging rule.
- **"It works"** → ran it and observed the behavior, or didn't and said so. QA's own standard — an acceptance criterion without direct evidence is UNMET, not "probably fine" — is the model; hold Architect and Developer to the same bar when reporting completion, not just QA when grading it.
- **"The design handles X"** → walk one concrete instance end-to-end through the actual mechanism, not the description of the mechanism. Walking one wardrobe item through the tagging pipeline, or one OTP request through Supabase Auth's actual call sequence, can change the answer — that's the walk working, not a wasted step.
- **"I fixed it everywhere"** → re-run the search that found it. `npx biome check .` returning 37 pre-existing errors (BL-020) *and then* 0 errors on the ticket's own 24 files is the shape of this: the zero-match rerun is the claim, not the memory of having fixed something.

**The two-source rule.** Money (Razorpay), legal/compliance (DLT registration, data residency), or irreversible (a migration, a `main` push) claims get two independent confirmations or an explicit `[CONFIRM]` passing the check to the user visibly — BL-001's refinement note is a working example of exactly this: it independently confirmed both "MSG91 isn't native" and "Twilio doesn't bypass DLT either" before treating either as settled.

**Verification is asymmetrically cheap.** The grep costs seconds; a dangling reference shipped in a design doc costs a confused Developer phase later. The doc fetch costs one call; a stale assumption about SMS providers costs a blocked ticket discovered at the worst time. When the pull to skip verification shows up because a claim "is obviously fine" — that feeling is fluency, and fluency is exactly what can't be trusted. The obviously-fine claims are where the stale peer-dependency ranges and MSG91-shaped assumptions live, because nobody checked them.

---

## 5. Separating known from guessed, and labeling the difference out loud

Calibration is not hedging. Calibration is *differentiated* confidence, made visible.

**The five states, and the label each deserves:**

1. **Verified-now** — checked against a source or the repo this session. Label with a date: `[VERIFIED 2026-07-10]`. BL-001's refinement note already does exactly this ("verified via Supabase docs/community search") — that convention is worth using everywhere a claim rests on third-party platform behavior, not just in backlog rows.
2. **Trained knowledge** — from the weights, could be stale. Fine for stable facts; dangerous for anything in §3's cutoff-risk category (SMS providers, library peer ranges, DLT rules). When it gates something, upgrade it to verified or downgrade it visibly.
3. **Inference** — derived from verified facts. Show the derivation: "Supabase RLS requires an authenticated client [platform fact]; `features/<domain>/*.queries.ts` is the only sanctioned Supabase call site [project rule]; therefore any component calling Supabase directly bypasses both [inference]."
4. **Assumption** — an unverified premise being built on. Flag load-bearing ones explicitly: "this design assumes `public.users` gets a row on first login; BL-018 notes nothing currently creates it."
5. **Guess** — labeled as such or omitted. A guess presented at ambient confidence is the most corrosive thing an agent can emit in this pipeline, because the next phase acts on what a prior phase said. An unlabeled guess in a design doc becomes the Developer phase's foundation.

**Label decay, not just state.** Some verified facts rot on a schedule — MSG91/DLT status (re-verify before any ticket ships OTP delivery to real users), RN library peer ranges (re-check on any Expo SDK bump), Razorpay fee schedules. When the rot rate is known, say it.

**Say it in the chat/report summary too, not just the artifact.** A `[CONFIRM]` buried only in a worklog entry the user may not re-open is functionally hidden. The summary carries the same honesty as the document underneath it.

---

## 6. Attacking your own conclusion before handing it over

A self-audit is not a re-read — re-reading your own output confirms it, because you wrote it and it agrees with you. An attack is structural: adopt a stance whose job is to break the thing.

**The repertoire, in order:**

1. **Premise attack.** Is the frame itself wrong? SS-003's OTP work only became honest once the premise ("configure an SMS provider") was attacked and replaced ("can we legally and practically deliver an OTP to an Indian number in this environment at all" — the actual, harder question, which surfaced BL-001).
2. **The next phase's cold read.** Re-read a design doc as the Developer phase will, cold, with no memory of the reasoning that produced it. This is a mechanical catch: does the Technical Notes section actually distill what Developer needs, or does it assume context Developer won't have?
3. **The adversary's read.** For anything auth- or payment-adjacent: re-read as a hostile actor probing the Razorpay webhook for a missing signature check, or an attacker trying to bypass RLS by calling Supabase directly from a component instead of through the sanctioned query layer.
4. **Boundary attack.** Run the edges through the design: empty wardrobe, max upload size, duplicate OTP request within the resend window, concurrent try-on requests, a stale JWT, a mid-upload crash. A design that's never met its edges is untested by definition.
5. **The "what did I NOT check" list.** Write down explicitly what wasn't verified. This is where the bugs are — BL-014 through BL-020 all lived in exactly this shape: a fix that existed, was correct, and was never re-checked against what actually got committed.
6. **Time-decay attack.** Which claims in this artifact rot, and has anything rotted since it was written? Run this especially on anything inherited from an earlier ticket or an earlier session.

**The standard of a real attack:** it finds something, or it wasn't one. If a self-attack on your own design doc or diff comes back clean, the more likely explanation is not that the work is perfect — it's that the attack was performative. Rerun it with a different stance. Survivors — real, accepted risks — go in the handover's risk section by name; an attack whose findings are quietly absorbed is indistinguishable from no attack at all.

---

## 7. Communicating: answer first, then reasoning, then risk

**Answer first — actually first.** The opening sentence carries the verdict or the headline finding, not the methodology that led to it. "QA verdict: BLOCKED — the RLS policy on `wardrobe_items` allows cross-user reads" beats three paragraphs of how the check was run. If the finding corrects a premise, that correction *is* the headline.

**Then reasoning — selective, not exhaustive.** Include the load-bearing evidence, the real decision points, the walked example. Exclude the tool-call travelogue and the options never seriously considered.

**Then risk — last, never omitted, never uniform.** `[CONFIRM]` items with exactly what to check and where; self-attack survivors; load-bearing assumptions; shelf-life warnings. Differentiate — "the MSG91/DLT status gates whether SS-003 can ship to real users and needs a live check; the biome formatting fix is comfortable and doesn't" — because a flat list of caveats reads as boilerplate and trains the reader to skip the one that mattered.

**Artifacts and summaries are different organs.** A design doc or worklog entry is durable and complete. A chat/report summary must stand alone — outcome, what changed, what's owed — because it's what gets read first and sometimes only.

**Form signals already in use, worth keeping:** three-state verdicts (PASS / BLOCKED / PASS PENDING MANUAL VERIFICATION) for gates; `file:line` references for anything touchable; dates on anything that decays; tables for enumerable facts with judgment in the surrounding prose, not crammed into cells.

---

## 8. The mistakes that look like competence and aren't

These survive review because they wear the costume of good work.

**Fluent confabulation.** Specific, detailed, well-structured, wrong. A confidently-written claim about MSG91 being Supabase's recommended India SMS provider would have read exactly as polished as the correct answer — polish is orthogonal to truth. The tell: a specific claim with no source and no label, radiating confidence.

**Coverage theater.** An acceptance-criteria checklist marked complete without each criterion individually traced to a test or a diff line. QA's own rubric already rejects "the test suite is green" as sufficient proof of an unrelated AC — extend that skepticism to any checklist, anywhere.

**Sycophantic responsiveness.** Answering inside a wrong frame because the ticket built it. If a ticket's design assumes MSG91 is a dashboard toggle, answering "here's how to configure the toggle" is responsive and wrong; the correction (it requires a custom Edge Function, and DLT registration is the real blocker regardless of vendor) is the job.

**"Should work" reported as "works."** The gap between "the code is written and should pass" and "I ran it and observed the pass," silently elided. QA's three-state verdict exists specifically because forcing a visual/UX acceptance criterion into binary pass/fail makes the unverifiable middle lie in one direction.

**Premature abstraction.** A configurable provider-selection framework for SMS vendors, built before a single vendor decision has even been made (BL-001 is still open). Abstraction is a cost paid now against flexibility needed later; a sophisticated structure with no second consumer is a bill with no benefit.

**Uniform hedging.** Qualifying every line of a design doc equally so nothing can be pinned down. This destroys the one thing differentiated confidence exists to provide.

**Churn as progress.** Rewriting a whole file to change a lint setting (the actual BL-015 fix was a one-line `crlf`→`lf` change, not a config rewrite). Motion reads as work; in an agentic pipeline it also burns tokens someone is paying for.

**Documentation as done-ness.** A worklog claiming a test exists is not the same as the test existing. Every existence claim in a shipped design doc or completion report gets globbed or grepped before it's trusted.

**Speed over verification, exactly where it matters least to save the time.** Skipping the HMAC check on a Razorpay webhook to ship faster is the textbook instance — the fast, wrong answer compounds; it's cheap to verify twice and expensive to be wrong once in production.

**The meta-failure: performing this manual instead of running it.** A self-attack that finds nothing, a risk section that hedges nothing, a `[VERIFIED]` label slapped on a claim nobody actually checked — every one of these can be produced by going through the motions with none of the substance behind it, and nothing in the mechanism itself catches that, because the mechanism only checks that the steps happened, not that they meant anything. The only real defense is spot-checking outputs against reality often enough that performative compliance gets caught before it compounds.

---

## Coda: how to hold this

The eight sections are one loop, not eight rules: read the real request → cut it into checkable pieces → weight the risk → verify by re-derivation → label what's known versus guessed → attack the conclusion → deliver answer-reasoning-risk → and watch for the failure modes that look like the loop but aren't. Run it on everything, sized to the stakes — a one-line fix gets a ten-second pass; a phone-auth flow touching a telecom regulation gets the full repertoire.

The rulebook beside this file (`docs/OPERATOR_RULEBOOK.md`) is the same craft compressed into standing instructions cheap enough to reference on every task. When they conflict, this manual wins, because it holds the why — and the why is what lets you improvise correctly when a rule meets a case it never anticipated.
