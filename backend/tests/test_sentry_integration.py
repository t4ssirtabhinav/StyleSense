"""Tests for backend Sentry initialisation (SS-009).

Proves the AC "Backend: Sentry initialised in FastAPI; unhandled exceptions
captured" -- not just that `sentry_sdk.init()` is called, but that an actual
unhandled exception raised inside a route reaches Sentry's capture path.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Iterator

import pytest
import sentry_sdk
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sentry_sdk.client import NonRecordingClient
from sentry_sdk.envelope import Envelope
from sentry_sdk.transport import Transport
from sentry_sdk.types import Event


def _reset_sentry_client() -> None:
    # `sentry_sdk.init(dsn=None)` is NOT a real reset -- sentry_sdk 2.x's
    # `_Client.is_active()` always returns True once any real Client
    # instance has been constructed, regardless of dsn. Only swapping the
    # global scope's client back to the library's own pre-init
    # NonRecordingClient (which reports is_active() == False) actually
    # isolates each test from whatever the previous test (or main.py's own
    # module-level init, if a real SENTRY_DSN_BACKEND happens to be set in
    # this environment's .env) left behind.
    sentry_sdk.get_global_scope().set_client(NonRecordingClient())


@pytest.fixture(autouse=True)
def _isolated_sentry_client() -> Iterator[None]:
    _reset_sentry_client()
    yield
    _reset_sentry_client()


def test_sentry_initializes_when_dsn_env_var_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_dsn = "https://examplepublickey@o0.ingest.sentry.io/0"
    monkeypatch.setenv("SENTRY_DSN_BACKEND", fake_dsn)

    sys.modules.pop("main", None)
    main = importlib.import_module("main")
    try:
        client = sentry_sdk.get_client()
        assert client.is_active() is True
        assert client.dsn == fake_dsn
    finally:
        sys.modules.pop("main", None)
        del main


def test_sentry_skips_init_when_dsn_env_var_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Set to an explicit empty string rather than delenv(): main.py's own
    # `load_dotenv()` call (default `override=False`) only fills in a var if
    # it is NOT already present in os.environ -- deleting it would let a
    # real, non-empty SENTRY_DSN_BACKEND from the repo's actual root .env
    # (confirmed present by this ticket's Architect phase) silently repopulate
    # it on reload, defeating this test's "absent" premise. An explicit
    # empty string is already-present (falsy, so main.py's `if sentry_dsn:`
    # guard still skips init) and can't be overridden by load_dotenv().
    monkeypatch.setenv("SENTRY_DSN_BACKEND", "")

    sys.modules.pop("main", None)
    main = importlib.import_module("main")
    try:
        # main.py's `if sentry_dsn:` guard means sentry_sdk.init() is never
        # called -- the global client stays the isolated-fixture's
        # NonRecordingClient, which reports itself inactive.
        client = sentry_sdk.get_client()
        assert client.is_active() is False
        assert client.dsn is None
    finally:
        sys.modules.pop("main", None)
        del main


class _CapturingTransport(Transport):
    """A real Sentry Transport that records envelopes instead of sending them."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[Event] = []

    def capture_envelope(self, envelope: Envelope) -> None:
        event = envelope.get_event()
        if event is not None:
            self.events.append(event)


def test_unhandled_exception_captured_by_sentry_integration() -> None:
    # An isolated FastAPI app (not main.app) with its own sentry_sdk.init()
    # pointed at a capturing test transport -- proves unhandled exceptions
    # actually reach Sentry's capture path, not just that init() was called.
    transport = _CapturingTransport()
    sentry_sdk.init(
        dsn="https://examplepublickey@o0.ingest.sentry.io/0",
        transport=transport,
        traces_sample_rate=0.1,
    )

    app = FastAPI()

    @app.get("/boom")
    def boom() -> None:
        raise ValueError("kaboom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    assert len(transport.events) >= 1
    captured_exception = transport.events[0]["exception"]
    assert captured_exception["values"][0]["type"] == "ValueError"
    assert captured_exception["values"][0]["value"] == "kaboom"
