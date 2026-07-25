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

import pytest


@pytest.fixture(autouse=True)
def _baseline_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("CLOUDFLARE_R2_ACCOUNT_ID", "test-account-id")
    monkeypatch.setenv("CLOUDFLARE_R2_ACCESS_KEY", "test-access-key")
    monkeypatch.setenv("CLOUDFLARE_R2_SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("CLOUDFLARE_R2_BUCKET", "test-bucket")
