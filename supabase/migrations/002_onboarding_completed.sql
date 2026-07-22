-- ============================================================
-- SS-004 — onboarding completion tracking + auto-provisioning
-- ============================================================

-- 1. Track onboarding completion explicitly (do not overload full_name
--    nullability as the signal — see docs/tickets/SS-004-design.md).
ALTER TABLE users
  ADD COLUMN onboarding_completed BOOLEAN NOT NULL DEFAULT false;

-- 2. Auto-provision a public.users row whenever a new Supabase Auth user is
--    created (phone OTP signup creates an auth.users row on first
--    signInWithOtp/verifyOtp) — closes the gap SS-003's Architect flagged
--    (BL-018): nothing previously created this row, so SS-003's row-existence
--    heuristic never actually detected a "returning" user correctly.
CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  INSERT INTO public.users (id, phone, email)
  VALUES (NEW.id, NEW.phone, NEW.email)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_auth_user();
