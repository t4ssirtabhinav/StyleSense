# StyleSense — Claude Code Standards

You are helping build StyleSense, an India-first AI fashion app.

**Stack:** Expo React Native (web-first) + TypeScript · Supabase · Python FastAPI

---

## Authoritative Documents

An inclusion map, not a table of contents — read the one line that applies, not the whole doc, unless the task actually needs it.

- `docs/tickets/raw/SS-XXX.md` — that ticket's acceptance criteria (ground truth for "done"). Read for the ticket at hand only.
- `docs/tickets/SS-XXX-design.md` — the Developer phase's spec. Read this instead of re-deriving from the architecture.
- `docs/worklog/SS-XXX.md` — that ticket's audit trail. Once it's long, read the last Verdict + relevant tail, not the full history.
- `docs/BACKLOG.md` — cross-ticket deferrals, split into **Active** (scanned once per ticket at the Architect phase, grep by Tag) and **Parked** (owned by `/audit`, never scanned during ticket runs). Log/close are scan-free appends; only the Architect + `/ticket` orchestrator resurface-scan, and Active only.
- `docs/ARCHITECTURE_AMENDMENTS.md` — dated deltas from the original HLD/LLD doc. Read when checking whether a ticket's assumptions are still current; append when `/new-feature` or `/audit` finds the architecture doc has fallen behind.
- `docs/AUDIT_LOG.md` — dated record of `/audit` runs. Read to see when the repo was last checked; not part of normal ticket work.
- `docs/OPERATOR_RULEBOOK.md` — dense, checkable rules by phase of work. Read when a phase needs the letter of a rule; Process Discipline below already covers the highest-value ones.
- `docs/OPERATING_MANUAL.md` — the reasoning behind the rulebook. Read only when a rule meets a case it didn't anticipate.
- `docs/PROMPT_PLAYBOOK.md` — meta-process for authoring new tickets/agents/audits. Not read during normal ticket execution.

## Process Discipline

Highest-value rules from `docs/OPERATOR_RULEBOOK.md`, inline so it rarely needs loading in full:

- Verify, don't recite: anything about a third-party platform (Supabase, Expo, Razorpay, DLT/SMS rules) gets checked against the current source, never asserted from memory.
- Label known vs. guessed: `[VERIFIED <date>]` / trained-knowledge / inference / assumption / guess — unlabeled is read as verified.
- "Should work" is not "works" — report only what was actually run and observed.
- Self-attack before handoff: on anything auth/payment/schema-adjacent, run the boundary sweep (empty/max/duplicate/concurrent/stale) before calling it done.
- Distill once, reference forever: a design doc or a ticket's Technical Notes is the next phase's spec — don't re-open the source it was distilled from.
- Risk-weight effort: spend it on what's irreversible, external-facing, security- or money-related — not evenly across a diff.

---

## React Native / Web

- NEVER use `StyleSheet.create` — use NativeWind `className` instead
- NEVER use `View`/`Text` directly — import from `components/ui/`
- NEVER use `FlatList` for large lists — use `FlashList`
- ALWAYS handle loading, error, and empty states in every component
- Navigate via Expo Router (`router.push`), never react-navigation directly
- Images: always use `expo-image`, not React Native `Image`
- All async ops: always wrap in `try/catch` with user-facing error handling

## TypeScript

- `strict: true` always — no `any` types
- Supabase types from auto-generated `types/supabase.ts` ONLY
- Zustand stores: always use typed selectors

## Backend (FastAPI)

- All endpoints: JWT auth dependency + Pydantic models + `try/except`
- Never call AI APIs synchronously — use background tasks
- All AI calls go through adapter interfaces (`IVisionProvider`, etc.)
- Rate limit checks via Upstash Redis BEFORE expensive AI calls
- Log all AI calls: `user_id`, `tokens_used`, `latency_ms`

## India-Specific

- Currency: ALWAYS format as ₹1,23,456 (Indian numbering system)
- Dates: use `'en-IN'` locale, IST timezone (`Asia/Kolkata`)
- Phone: default country code +91, validate 10-digit Indian mobile
- Ethnic wear categories are FIRST-CLASS — not edge cases
- Occasion rules: never suggest white for `wedding_guest`

## Security

- No secrets in code — use env vars only
- All user data queries MUST use authenticated Supabase client
- Never use `service_role` key in client-side code
- Razorpay webhooks: ALWAYS verify HMAC signature first

## Anti-Patterns

- No prop drilling more than 2 levels — use Zustand
- No inline styles in JSX — always NativeWind classes
- No `console.log` in production — use Sentry logging
- No direct Supabase calls in components — only through `features/<domain>/*.queries.ts` (React Query hooks)
- No hardcoded URLs — use `constants/api.ts`
- No `useEffect` for derived state — compute it directly during render
- Always use `useCallback` for event handlers passed to child components
- All API response types live in `types/` — never inline `any`-shaped objects

## Folder Structure (Clean Architecture / Modular Monolith)

Frontend (`mobile/`):
```
app/                          # Expo Router route groups
  (auth)/                     # login.tsx, onboarding.tsx
  (tabs)/                     # index.tsx, wardrobe.tsx, discover.tsx, profile.tsx
  outfit/[id].tsx
  tryon/[outfitId].tsx
features/<domain>/            # one folder per domain (wardrobe, outfit-ai, social, ...)
  <domain>.store.ts           # Zustand store (client state)
  <domain>.queries.ts         # React Query hooks (server state) — the ONLY place Supabase is called from
  <domain>.service.ts         # raw API calls used by queries.ts
  <domain>.types.ts
  components/                 # domain-specific components
components/ui/                # shared design system (Button, Card, Badge, ...) — see SS-008
lib/                          # supabase.ts, api.ts, storage.ts
hooks/                        # useAuth, useCamera, useLocation
```

Backend (`backend/`), hexagonal ports & adapters for every AI provider:
```
ai/ports/interfaces.py        # IVisionProvider, IStylingProvider, ISearchProvider (ABCs)
ai/adapters/                  # GeminiVisionAdapter, ClaudeStylingAdapter, PerplexitySearchAdapter
routers/                      # FastAPI route handlers — depend on ports via Depends(), never on adapters directly
services/                     # WardrobeImageService, WardrobeTaggingService, OutfitSuggestionService (single-responsibility)
adapters/                     # WardrobeRepository / IWardrobeRepository (DB access, separate from services)
```
Adding a new AI provider = a new adapter class implementing the existing port. Never modify a port to fit a new provider (Open/Closed).

## Deployment Environments

| Environment | Branch      | Backend               | Database                  |
|-------------|-------------|------------------------|----------------------------|
| Local       | `feature/*` | `localhost:8000`       | Supabase local (Docker)    |
| Preview     | `develop`   | Railway (preview env)  | Supabase staging project   |
| Production  | `main`      | Railway (prod)         | Supabase prod project      |

`main` requires CI pass + 1 review before merge; `develop` requires CI pass. Never push directly to `main`.

## Testing — Every User Story Ships With Tests

- Frontend: Jest (`jest-expo` preset) + React Native Testing Library for every new component/hook in `features/<domain>/` or `components/ui/`.
- Backend: Pytest (+ `pytest-asyncio`, `httpx`) for every new route/service in `routers/`/`services/`.
- A ticket is not done until its acceptance criteria are covered by a test or manually verified and noted as such in the ticket's worklog (see below).

## Ticket Workflow (Section 10 — Sprint Execution)

- One ticket = one branch: `feature/SS-XXX-slug`, cut from `develop`.
- Commit convention: `feat(SS-XXX): short description` (or `fix(SS-XXX): ...`, `chore(SS-XXX): ...`).
- Ticket source of truth lives in `docs/tickets/raw/SS-XXX.md`. Every ticket goes through four phases, each a Claude Code subagent in `.claude/agents/`: **architect** (writes `docs/tickets/SS-XXX-design.md`) → **developer** (implements + tests) → **qa** (verifies AC + runs lint/type/test) → **devops** (commit/push/PR). See `.claude/skills/ticket/SKILL.md`.
- **Two lanes, gated by the ticket's `Risk:` field** (set by the Architect / `/new-feature`): **full lane** (`Risk: high` — auth, payments, schema/migrations, RLS, secrets, external-facing/irreversible) keeps every human gate; **fast lane** (`Risk: low`/`med` — everything else) auto-chains architect→developer→qa and pauses only at the PR. Risk-weight the *process* the same way §C6/§F5 risk-weight the code — don't spend three gates on a placeholder screen. On the fence → classify up.
- **Parallelize the fast lane; serialize heavy tickets.** Independent `low`/`med` tickets (no file/folder overlap, no dependency) run concurrently in separate git worktrees, each on its own `feature/*` branch — the throughput lever for a solo sprint. `Risk: high` or large tickets run one at a time: parallelism burns the usage window several times faster, and a cutoff should strand at most one expensive phase.
- Every phase appends a **tight** entry to `docs/worklog/SS-XXX.md` (verdict + key decisions + backlog deltas — a pointer to the design doc/diff/PR, not a re-narration of them). This is the audit trail for what each agent did and why.
- **Phases checkpoint as they go** so a usage-limit cutoff doesn't cost the whole phase: Developer ticks a `### Developer — IN PROGRESS` block and commits `wip(SS-XXX)` per unit, QA records a `### QA — GATES` block with the HEAD sha before its AC pass, and the Architect grows the design doc behind an `<!-- IN PROGRESS -->` marker. A dangling marker means that phase was interrupted — `/ticket` resumes *within* it rather than restarting it. See `docs/worklog/README.md`.
- Deferred items that aren't this ticket's blocker but might matter later (a product decision, a design-token gap, a CI issue) go in `docs/BACKLOG.md`, not just the worklog — worklogs stop being read once a ticket ships, the backlog doesn't.
- A feature idea that isn't already an `SS-XXX` ticket and isn't in the original architecture/epics docs goes through `.claude/skills/new-feature/SKILL.md` first (impact analysis, always pauses for sign-off before a ticket is created) — don't hand-write a ticket for genuinely new scope without it. A repo-wide health check (not tied to any one ticket) is `.claude/skills/audit/SKILL.md`, run manually on your own cadence.

## Git Autonomy Contract

- Subagents may `git add <named files>`, `git commit`, and `git push` on `feature/*` branches without asking each time.
- **Developer checkpoints with `wip(SS-XXX): ...` commits** (one per unit of work, never pushed) so a phase interrupted by a usage-limit cutoff resumes instead of restarting. **DevOps squashes them** into the single clean `feat(SS-XXX): ...` commit — but only while the branch is still unpushed; once pushed, it adds a commit on top rather than rewriting history.
- Opening a PR (`gh pr create`) always pauses for explicit user confirmation first.
- `main` is never touched directly by any agent. No `--no-verify`, no force-push, no `git add -A`. The only permitted reset is DevOps' `git reset --soft` when squashing local `wip` commits — never `--hard`, never on a pushed branch.
