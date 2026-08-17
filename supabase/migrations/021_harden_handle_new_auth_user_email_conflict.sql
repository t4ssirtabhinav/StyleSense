-- ============================================================
-- SS-072 -- harden handle_new_auth_user against a duplicate-email
-- signup (BL-169). Replaces ONE function, nothing else -- no ALTER
-- TABLE, no new constraint, no new index, no trigger re-creation (the
-- on_auth_user_created trigger binds to this function BY NAME, so
-- CREATE OR REPLACE FUNCTION alone is sufficient and its AFTER INSERT
-- timing is preserved unchanged).
-- ============================================================
--
-- Three-layer defence -- only THIS layer (layer 2) is new. Read this
-- before touching the WHERE clause below:
--
--   Layer 1 (UX, client-side)   -- features/auth/auth.service.ts's
--     toEmailAuthError() maps Supabase's OWN user_already_exists /
--     email_exists error to a specific, actionable message before this
--     trigger is ever reached. Covers the common (non-racing) case --
--     [LIVE-VERIFIED 2026-08-17, see docs/worklog/SS-072.md] a literal
--     duplicate email is in fact already rejected by GoTrue itself,
--     cleanly, before an auth.users row is even inserted, so this
--     trigger does not run at all for that case.
--
--   Layer 2 (THIS migration)    -- a lower(email) pre-check that
--     RAISE EXCEPTIONs with a recognizable, deterministic token instead
--     of letting users.email's UNIQUE constraint fire from inside this
--     SECURITY DEFINER body as an opaque "Database error
--     saving/creating new user" (BL-169). NOT atomic on its own: two
--     exactly-concurrent signups for the same never-before-seen email
--     can both pass this SELECT and both reach the INSERT below --
--     layer 3 is what actually prevents two rows from committing in
--     that race. This layer only makes the FAILURE MESSAGE legible; it
--     does not by itself close the race.
--
--   Layer 3 (pre-existing, correctness backstop) -- users.email UNIQUE
--     from 001_initial.sql:26. Whichever of the two racing inserts
--     loses hits this constraint and aborts -- this is what actually
--     guarantees "rejected outright, never merged" even under a
--     perfectly-timed race. This migration does not add it; it was
--     already there.
--
-- [LIVE-VERIFIED 2026-08-17 against the shared project, pre-021, see
-- docs/worklog/SS-072.md] The actual reachable shape of BL-169 today is
-- an ORPHANED public.users row (no FK/cascade to auth.users -- BL-184):
-- delete an auth user, its public.users row survives and permanently
-- blocks a NEW auth.users insert with that email, because GoTrue's own
-- duplicate-email check has nothing left to match against. That insert
-- reaches this trigger, which (pre-021) blind-inserts and collides with
-- the UNIQUE constraint, surfacing to the client as a generic wrapped
-- 500 (observed message: "Database error creating new user" via the
-- Admin API -- note "creating", not "saving" as originally assumed;
-- features/auth/auth.service.ts's regex matches both). Also confirmed
-- live, pre-021: the transaction already rolls back correctly (zero
-- orphaned auth.users rows after the failed insert, the existing
-- public.users row unchanged) -- that correctness property comes from
-- Postgres's own trigger-exception-aborts-transaction semantics plus
-- layer 3, independent of this migration's own code.
--
-- Case-insensitive: auth.users normalises email case on signup, but
-- public.users' UNIQUE constraint does not -- lower() on both sides is
-- what makes the two agree, and is what catches a case-variant
-- duplicate the plain UNIQUE constraint alone would miss.
--
-- Deliberately NOT in this migration (see docs/tickets/SS-072-design.md
-- and docs/BACKLOG.md BL-184/BL-185 for the full reasoning):
--   * No case-insensitive functional unique index on email -- unreachable
--     from GoTrue (which already normalises case), reachable only via a
--     direct admin insert; not worth a migration that can fail mid-flight
--     on live case-variant rows without first proving there are none.
--   * No symmetric guard on phone -- would change the phone path's
--     behaviour in the exact migration whose AC #5 demands that path be
--     PROVABLY unaffected. Phone shares this landmine identically but is
--     deferred to BL-185.
--   * No FK from public.users.id to auth.users.id -- a genuinely
--     irreversible schema change on live data, well outside this ticket.
--     Deferred to BL-184.
--
-- Rollback: re-run 002_onboarding_completed.sql's function body verbatim
-- (CREATE OR REPLACE FUNCTION public.handle_new_auth_user() with just the
-- ON CONFLICT (id) DO NOTHING insert, no email pre-check). The trigger
-- binding, the table, and every row are untouched by this migration, so
-- reverting the function is a complete revert -- no reconstruction needed.

CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- SS-072 (BL-169): reject a signup whose email is already owned by a
  -- DIFFERENT public.users row, with a recognizable error, instead of
  -- letting users.email's UNIQUE constraint fire from inside this
  -- SECURITY DEFINER body as an opaque "Database error saving new user".
  -- Gated on NEW.email IS NOT NULL so a phone-only signup (email NULL)
  -- short-circuits this IF on its first term and falls straight through
  -- to the identical INSERT below -- AC #5, the phone path must be
  -- provably unaffected by this migration.
  IF NEW.email IS NOT NULL AND EXISTS (
    SELECT 1 FROM public.users u
    WHERE u.id <> NEW.id AND lower(u.email) = lower(NEW.email)
  ) THEN
    RAISE EXCEPTION 'stylesense_email_conflict'
      USING ERRCODE = 'P0001',
            DETAIL  = 'email already registered to a different account',
            HINT    = 'sign in instead, or link the identity while authenticated';
  END IF;

  -- Unchanged from 002_onboarding_completed.sql. ON CONFLICT (id) DO
  -- NOTHING preserves re-entrancy for the id case.
  INSERT INTO public.users (id, phone, email)
  VALUES (NEW.id, NEW.phone, NEW.email)
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

-- No trigger re-creation needed -- on_auth_user_created (002) already
-- binds to public.handle_new_auth_user() by name and AFTER INSERT timing
-- is unaffected by CREATE OR REPLACE FUNCTION.
