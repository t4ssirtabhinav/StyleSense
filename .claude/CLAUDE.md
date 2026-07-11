# StyleSense — Claude Code Standards

You are helping build StyleSense, an India-first AI fashion app.

**Stack:** Expo React Native (web-first) + TypeScript · Supabase · Python FastAPI

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
- Every phase appends to `docs/worklog/SS-XXX.md` — this is the audit trail for what each agent did and why.
- Deferred items that aren't this ticket's blocker but might matter later (a product decision, a design-token gap, a CI issue) go in `docs/BACKLOG.md`, not just the worklog — worklogs stop being read once a ticket ships, the backlog doesn't.

## Git Autonomy Contract

- Subagents may `git add <named files>`, `git commit`, and `git push` on `feature/*` branches without asking each time.
- Opening a PR (`gh pr create`) always pauses for explicit user confirmation first.
- `main` is never touched directly by any agent. No `--no-verify`, no force-push, no `git add -A`.
