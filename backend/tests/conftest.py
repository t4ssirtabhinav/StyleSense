"""Shared pytest fixtures for the backend test suite.

CI checks out a clean repo with no `.env` file (correctly gitignored) and
does not export SUPABASE_URL/SUPABASE_ANON_KEY/CLOUDFLARE_R2_* as workflow
env vars -- only a local dev machine with a real root `.env` (loaded via
`main.py`'s `load_dotenv()`) happens to have these ambient. A test that
exercises real adapter-construction code (`os.environ["..."]` bracket
access in `adapters/r2_storage.py`, `adapters/wardrobe_repository.py`,
`dependencies/auth.py`) without setting these itself will silently pass
locally and fail in CI with a `KeyError` -- exactly what happened with
`test_wardrobe_router.py::test_missing_or_invalid_auth_returns_401_via_real_dependency`
(missed the `monkeypatch.setenv` convention every other test in this suite
already follows correctly).

This autouse fixture sets baseline dummy values for every test, so no test
author needs to remember this individually going forward. A test that
specifically wants to exercise "env var missing" behavior can still
`monkeypatch.delenv(...)` within its own body to override these defaults
(see `test_r2_storage.py`'s existing missing-config test, unaffected by
this fixture since delenv runs after and simply removes whatever this
fixture set).
"""

from __future__ import annotations

import os

import pytest

# Blank out SENTRY_DSN_BACKEND before any test module is collected, not just
# before each test runs. `test_health.py`/`test_wardrobe_router.py`/
# `test_outfit_suggestions_router.py` all do `from main import app` at
# MODULE level, so main.py (and its unconditional `sentry_sdk.init()` when
# SENTRY_DSN_BACKEND is set) executes at pytest COLLECTION time -- before
# any fixture, even an autouse one, has a chance to run. On a dev machine
# with a real DSN in the root `.env`, that means a full `pytest tests/` run
# initialises a REAL Sentry client, a process-wide singleton that then
# stays active for the rest of the session: any later `logger.error()` or
# unhandled exception -- including AppConfigService's deliberate malformed-
# value log (SS-026 AC #4) and a real pre-existing bug in
# outfit_suggestion_service.py -- gets shipped to the live
# stylesense.sentry.io project as if it were production signal. That is
# exactly how PYTHON-FASTAPI-1 and PYTHON-FASTAPI-2 were created (both
# environment=development, 0 real users, sys.argv showing pytest).
# test_sentry_integration.py already isolates ITS OWN tests via a
# file-scoped autouse fixture, but that scope doesn't reach any other test
# file. Setting this here, at conftest module scope (which pytest always
# imports before collecting test files in this directory), wins the race:
# main.py's `load_dotenv()` (default `override=False`) only fills in a var
# that is NOT already present in os.environ, so this empty string survives
# and main.py's `if sentry_dsn:` guard skips init. Tests that explicitly
# want to exercise init (test_sentry_integration.py) still can --
# `monkeypatch.setenv(...)` inside a test function runs after collection
# and overrides this default same as any other env var.
os.environ.setdefault("SENTRY_DSN_BACKEND", "")


@pytest.fixture(autouse=True)
def _baseline_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    # (SS-026) AppConfigRepository is the first adapter needing this var --
    # its absence would KeyError in CI exactly per this file's own
    # documented gap.
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
    monkeypatch.setenv("CLOUDFLARE_R2_ACCOUNT_ID", "test-account-id")
    monkeypatch.setenv("CLOUDFLARE_R2_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("CLOUDFLARE_R2_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("CLOUDFLARE_R2_BUCKET", "test-bucket")
