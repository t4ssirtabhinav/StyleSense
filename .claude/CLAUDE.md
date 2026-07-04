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
- No direct Supabase calls in components — through query hooks only
- No hardcoded URLs — use `constants/api.ts`
