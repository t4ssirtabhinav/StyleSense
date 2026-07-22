-- ============================================================
-- SS-004 (BL-029 root-cause fix) — backfill public.users rows for
-- auth.users that predate 002_onboarding_completed.sql's auto-provisioning
-- trigger. The trigger only fires on new auth.users INSERTs going forward;
-- any auth user created before the trigger existed has no corresponding
-- public.users row and never will unless backfilled here.
--
-- Diagnosed 2026-07-22: this project's one auth.users row (the fixed
-- Supabase phone Test OTP number used for all manual testing) was created
-- 2026-07-13, before migration 002 (applied 2026-07-22) — so it was never
-- auto-provisioned. Every onboarding save/complete update against it has
-- been silently affecting zero rows (Postgres does not error on a
-- zero-row UPDATE), and checkOnboardingCompleted has always read back
-- null -> false, regardless of what was entered in the wizard.
-- ============================================================

INSERT INTO public.users (id, phone, email)
SELECT au.id, au.phone, au.email
FROM auth.users au
LEFT JOIN public.users pu ON pu.id = au.id
WHERE pu.id IS NULL
ON CONFLICT (id) DO NOTHING;
