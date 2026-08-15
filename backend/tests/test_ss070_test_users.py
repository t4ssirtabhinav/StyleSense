"""Tests for backend/scripts/ss070_test_users.py (SS-070).

Per docs/tickets/SS-070-design.md's test plan: the Supabase Admin client is
faked throughout -- NO live calls (AC #9). Fakes are hand-rolled (not
MagicMock) so pagination/table-filtering behaviour is actually exercised,
mirroring test_occasion_repository.py / test_app_config_repository.py's
fake-builder style.

Covers the guard rails specifically, per the design note's test plan and
the raw ticket's AC #7/#9:
  - every subcommand blocked without STYLESENSE_ALLOW_TEST_USER_ADMIN
  - delete refuses a non-prefixed email (delete_user never called)
  - delete refuses a prefixed-but-unmarked account (the both-not-either rule)
  - create refuses an existing label
  - list filters a mixed page to zero false positives
  - list unions multiple pages, not just page 1
  - delete's four-tables-then-users-then-auth call order
  - the service_role key never appears in captured stdout/stderr or any
    raised exception's text, across the whole suite (autouse leak guard)
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest

from scripts import ss070_test_users as sut

SECRET_SERVICE_ROLE_KEY = "sk-live-SUPER-SECRET-service-role-value-do-not-print"


# ------------------------------------------------------------------
# Fakes
# ------------------------------------------------------------------


@dataclass
class FakeUser:
    id: str
    email: str
    app_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = "2026-01-01T00:00:00+00:00"


class FakeUserResponse:
    def __init__(self, user: FakeUser) -> None:
        self.user = user


class FakeAdmin:
    """Fakes ``Client.auth.admin`` -- ``create_user``/``list_users``/
    ``delete_user``/``get_user_by_id``, per the surface verified against the
    installed supabase-py 2.31.0 source (design note's ground-check)."""

    def __init__(self, users: list[FakeUser] | None = None, log: list[str] | None = None) -> None:
        self.users: list[FakeUser] = list(users or [])
        self.log: list[str] = log if log is not None else []
        self.calls: list[str] = []
        self.create_error: Exception | None = None

    def create_user(self, attributes: dict[str, Any]) -> FakeUserResponse:
        self.calls.append("create_user")
        self.log.append("auth.create_user")
        if self.create_error is not None:
            raise self.create_error
        new_user = FakeUser(
            id=f"auth-{len(self.users) + 1}",
            email=attributes["email"],
            app_metadata=dict(attributes.get("app_metadata") or {}),
        )
        self.users.append(new_user)
        return FakeUserResponse(new_user)

    def list_users(self, page: int | None = None, per_page: int | None = None) -> list[FakeUser]:
        self.calls.append("list_users")
        page = page or 1
        per_page = per_page or len(self.users) or 1
        start = (page - 1) * per_page
        return self.users[start : start + per_page]

    def delete_user(self, id: str, should_soft_delete: bool = False) -> None:
        self.calls.append("delete_user")
        self.log.append(f"auth.delete_user({id})")
        self.users = [u for u in self.users if u.id != id]

    def get_user_by_id(self, uid: str) -> FakeUserResponse:
        self.calls.append("get_user_by_id")
        self.log.append(f"auth.get_user_by_id({uid})")
        for u in self.users:
            if u.id == uid:
                return FakeUserResponse(u)
        raise sut.AuthApiError("user not found", 404, None)

    def generate_link(self, params: dict[str, Any]) -> Any:  # pragma: no cover -- fallback path
        raise NotImplementedError("not exercised by this test suite")


class FakeQueryResult:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class FakeQueryBuilder:
    def __init__(
        self, table_name: str, tables: dict[str, list[dict[str, Any]]], log: list[str]
    ) -> None:
        self.table_name = table_name
        self.tables = tables
        self.log = log
        self._op: str | None = None
        self._insert_rows: list[dict[str, Any]] = []
        self._update_values: dict[str, Any] = {}
        self._filters: dict[str, Any] = {}

    def select(self, *args: Any, **kwargs: Any) -> FakeQueryBuilder:
        self._op = "select"
        return self

    def insert(self, rows: Any) -> FakeQueryBuilder:
        self._op = "insert"
        self._insert_rows = rows if isinstance(rows, list) else [rows]
        return self

    def update(self, values: dict[str, Any]) -> FakeQueryBuilder:
        self._op = "update"
        self._update_values = values
        return self

    def delete(self) -> FakeQueryBuilder:
        self._op = "delete"
        return self

    def eq(self, column: str, value: Any) -> FakeQueryBuilder:
        self._filters[column] = value
        return self

    def execute(self) -> FakeQueryResult:
        self.log.append(f"{self.table_name}.{self._op}({self._filters})")
        rows = self.tables.setdefault(self.table_name, [])

        if self._op == "select":
            matched = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
            return FakeQueryResult(matched)
        if self._op == "insert":
            for row in self._insert_rows:
                rows.append(dict(row))
            return FakeQueryResult(list(self._insert_rows))
        if self._op == "update":
            matched = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
            for r in matched:
                r.update(self._update_values)
            return FakeQueryResult(matched)
        if self._op == "delete":
            matched = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]
            self.tables[self.table_name] = [r for r in rows if r not in matched]
            if self.table_name == "users":
                # Emulate 001_initial.sql:46's real ON DELETE CASCADE
                # (wardrobe_items.user_id -> users(id)) so this fake can
                # exercise AC #6's post-delete verification without a live
                # DB. The four NO_ACTION_FK_TABLES deliberately do NOT
                # cascade here either -- same as production -- which is
                # exactly why the script must clear them first.
                deleted_ids = {r.get("id") for r in matched}
                items = self.tables.get("wardrobe_items", [])
                self.tables["wardrobe_items"] = [
                    r for r in items if r.get("user_id") not in deleted_ids
                ]
            return FakeQueryResult(matched)
        raise AssertionError(f"unsupported fake op {self._op!r}")


class FakeAuth:
    def __init__(self, admin: FakeAdmin) -> None:
        self.admin = admin
        self.sign_in_calls: list[dict[str, Any]] = []
        self.sign_in_result: Any = None
        self.sign_in_error: Exception | None = None

    def sign_in_with_password(self, credentials: dict[str, Any]) -> Any:
        self.sign_in_calls.append(credentials)
        if self.sign_in_error is not None:
            raise self.sign_in_error
        return self.sign_in_result

    def verify_otp(self, params: dict[str, Any]) -> Any:  # pragma: no cover -- fallback path
        raise NotImplementedError("not exercised by this test suite")


class FakeClient:
    def __init__(self, admin: FakeAdmin | None = None, log: list[str] | None = None) -> None:
        self.log: list[str] = log if log is not None else []
        self.admin = admin or FakeAdmin(log=self.log)
        self.auth = FakeAuth(self.admin)
        self.tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> FakeQueryBuilder:
        return FakeQueryBuilder(name, self.tables, self.log)


def _never_confirm(prompt: str) -> bool:
    raise AssertionError(f"confirm() should not have been reached: {prompt!r}")


def _always_confirm(prompt: str) -> bool:
    return True


def _marked_user(label: str, *, prefixed: bool = True, marked: bool = True) -> FakeUser:
    email = sut._email_for_label(label) if prefixed else f"real.user+{label}@gmail.com"
    app_metadata = {sut.APP_METADATA_MARKER_KEY: True} if marked else {}
    return FakeUser(id=f"auth-{label}", email=email, app_metadata=app_metadata)


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _env_and_leak_guard(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> Iterator[None]:
    """Baseline env for every test, PLUS the service_role-key leak guard
    (guard rail #6) -- asserted after every single test in this module, not
    just the ones that explicitly exercise a failure path. Tests that need
    STYLESENSE_ALLOW_TEST_USER_ADMIN unset must monkeypatch.delenv it
    themselves (delenv inside the test body runs after this fixture)."""
    monkeypatch.setenv("SUPABASE_URL", "https://exampleproj.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", SECRET_SERVICE_ROLE_KEY)
    monkeypatch.setenv(sut.ENV_OPT_IN, "1")
    yield
    captured = capsys.readouterr()
    assert SECRET_SERVICE_ROLE_KEY not in captured.out
    assert SECRET_SERVICE_ROLE_KEY not in captured.err


# ------------------------------------------------------------------
# Guard rail #1: opt-in env var blocks every subcommand.
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["create", "--label", "demo"],
        ["seed", "--label", "demo", "--items", "1"],
        ["session", "--label", "demo"],
        ["list"],
        ["delete", "--label", "demo"],
    ],
    ids=["create", "seed", "session", "list", "delete"],
)
def test_missing_opt_in_env_var_blocks_every_subcommand(
    monkeypatch: pytest.MonkeyPatch, argv: list[str]
) -> None:
    monkeypatch.delenv(sut.ENV_OPT_IN, raising=False)

    def _admin_client_should_not_be_called() -> Any:
        raise AssertionError("_admin_client() must not be called when the opt-in var is missing")

    monkeypatch.setattr(sut, "_admin_client", _admin_client_should_not_be_called)

    exit_code = sut.main(argv)

    assert exit_code == 1


# ------------------------------------------------------------------
# delete: both-not-either rule (guard rail #2).
# ------------------------------------------------------------------


def test_delete_refuses_non_prefixed_email(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_user = _marked_user("realacct", prefixed=False, marked=True)
    monkeypatch.setattr(sut, "_find_by_label", lambda admin, label: fake_user)
    admin = FakeAdmin(users=[fake_user])
    client = FakeClient(admin=admin)

    with pytest.raises(sut.TestUserAdminError) as exc_info:
        sut.cmd_delete(client, "realacct", confirm=_never_confirm)

    assert "prefix" in str(exc_info.value).lower()
    assert "delete_user" not in admin.calls
    assert SECRET_SERVICE_ROLE_KEY not in str(exc_info.value)


def test_delete_refuses_prefixed_but_unmarked_account(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_user = _marked_user("unmarked", prefixed=True, marked=False)
    monkeypatch.setattr(sut, "_find_by_label", lambda admin, label: fake_user)
    admin = FakeAdmin(users=[fake_user])
    client = FakeClient(admin=admin)

    with pytest.raises(sut.TestUserAdminError) as exc_info:
        sut.cmd_delete(client, "unmarked", confirm=_never_confirm)

    assert "app_metadata" in str(exc_info.value) or "marker" in str(exc_info.value).lower()
    assert "delete_user" not in admin.calls


def test_delete_refusal_message_is_clear_and_specific(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC #7: 'a clear refusal message', asserted directly rather than only
    inferred from the absence of a delete_user call."""
    fake_user = _marked_user("clearmsg", prefixed=False, marked=False)
    monkeypatch.setattr(sut, "_find_by_label", lambda admin, label: fake_user)
    client = FakeClient()

    with pytest.raises(sut.TestUserAdminError) as exc_info:
        sut.cmd_delete(client, "clearmsg", confirm=_never_confirm)

    message = str(exc_info.value)
    assert "Refusing to delete" in message
    assert fake_user.email in message


# ------------------------------------------------------------------
# Boundary sweep: empty label, and delete is safely re-runnable after a
# simulated mid-operation crash (Risk: high -- §C6 boundary sweep).
# ------------------------------------------------------------------


@pytest.mark.parametrize("label", ["", "-leadinghyphen", "UPPERCASE", "a" * 49])
def test_invalid_labels_are_rejected_before_any_admin_call(label: str) -> None:
    admin = FakeAdmin()
    client = FakeClient(admin=admin)

    with pytest.raises(sut.TestUserAdminError):
        sut.cmd_create(client, label, confirm=_never_confirm)

    assert admin.calls == []


def test_delete_is_safely_re_runnable_after_a_simulated_mid_operation_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates a process kill between clearing the four no-action-FK
    tables and deleting public.users -- the state a real crash would leave
    behind. Re-running delete must finish the job cleanly, not error out on
    the already-empty tables."""
    label = "crashmidway"
    fake_user = _marked_user(label)
    monkeypatch.setattr(sut, "_find_by_label", lambda admin, label_: fake_user)

    admin = FakeAdmin(users=[fake_user])
    client = FakeClient(admin=admin)
    client.tables["users"] = [{"id": fake_user.id}]
    client.tables["wardrobe_items"] = [{"id": "item-1", "user_id": fake_user.id}]
    # Pre-clear the four no-action-FK tables, as if a first run got exactly
    # that far before being killed.
    for table in sut.NO_ACTION_FK_TABLES:
        client.tables[table] = []

    result = sut.cmd_delete(client, label, confirm=_always_confirm)

    assert result.verification.fully_deleted is True


# ------------------------------------------------------------------
# create: duplicate label refused (BL-169 landmine, guard rail #5).
# ------------------------------------------------------------------


def test_create_refuses_existing_label() -> None:
    label = "dupe"
    existing = _marked_user(label)
    admin = FakeAdmin(users=[existing])
    client = FakeClient(admin=admin)

    with pytest.raises(sut.TestUserAdminError) as exc_info:
        sut.cmd_create(client, label, confirm=_never_confirm)

    assert "already" in str(exc_info.value).lower()
    assert "create_user" not in admin.calls


def test_create_pre_checks_public_users_row_before_admin_api_call() -> None:
    """Guard rail #5: even if no ss070 auth account exists for the label,
    a pre-existing public.users row for the same email must refuse BEFORE
    create_user is ever called (the BL-169 landmine)."""
    label = "landmine"
    email = sut._email_for_label(label)
    admin = FakeAdmin()
    client = FakeClient(admin=admin)
    client.tables["users"] = [{"id": "some-other-uuid", "email": email}]

    with pytest.raises(sut.TestUserAdminError) as exc_info:
        sut.cmd_create(client, label, confirm=_never_confirm)

    assert "BL-169" in str(exc_info.value) or "public.users" in str(exc_info.value)
    assert "create_user" not in admin.calls


def test_create_succeeds_and_verifies_public_users_row_by_query() -> None:
    """AC #1/#2: the public.users row is confirmed by an actual query, and
    the generated password is >=16 chars from a CSPRNG."""
    label = "freshlabel"
    admin = FakeAdmin()
    client = FakeClient(admin=admin)

    # Simulate the handle_new_auth_user trigger firing, exactly like
    # 002_onboarding_completed.sql -- but this is OUR fake's job to emulate,
    # not the script's; the script only ever queries for it.
    real_create_user = admin.create_user

    def _create_user_and_provision_profile(attributes: dict[str, Any]) -> FakeUserResponse:
        response = real_create_user(attributes)
        client.tables.setdefault("users", []).append(
            {"id": response.user.id, "email": response.user.email}
        )
        return response

    admin.create_user = _create_user_and_provision_profile  # type: ignore[method-assign]

    result = sut.cmd_create(client, label, confirm=_always_confirm)

    assert result.profile_row_verified is True
    assert len(result.password) >= 16
    assert result.email == sut._email_for_label(label)


# ------------------------------------------------------------------
# seed: boundary sweep (empty / max / duplicate-is-additive).
# ------------------------------------------------------------------


def test_seed_refuses_zero_items(monkeypatch: pytest.MonkeyPatch) -> None:
    label = "zeroitems"
    fake_user = _marked_user(label)
    monkeypatch.setattr(sut, "_find_by_label", lambda admin, label_: fake_user)
    client = FakeClient()

    with pytest.raises(sut.TestUserAdminError):
        sut.cmd_seed(client, label, items=0, confirm=_never_confirm)


def test_seed_refuses_items_over_the_typo_guard_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    label = "toomany"
    fake_user = _marked_user(label)
    monkeypatch.setattr(sut, "_find_by_label", lambda admin, label_: fake_user)
    client = FakeClient()

    with pytest.raises(sut.TestUserAdminError) as exc_info:
        sut.cmd_seed(client, label, items=sut.MAX_SEED_ITEMS + 1, confirm=_never_confirm)

    assert str(sut.MAX_SEED_ITEMS) in str(exc_info.value)
    assert client.tables.get("wardrobe_items", []) == []


def test_seed_re_run_is_additive_not_replacing(monkeypatch: pytest.MonkeyPatch) -> None:
    label = "reseed"
    fake_user = _marked_user(label)
    monkeypatch.setattr(sut, "_find_by_label", lambda admin, label_: fake_user)
    client = FakeClient()

    first = sut.cmd_seed(client, label, items=3, confirm=_always_confirm)
    second = sut.cmd_seed(client, label, items=2, confirm=_always_confirm)

    assert first.total == 3
    assert second.total == 5
    assert len(client.tables["wardrobe_items"]) == 5
    assert all(row["user_id"] == fake_user.id for row in client.tables["wardrobe_items"])
    # cost_per_wear is a GENERATED column -- the script must never insert it.
    assert all("cost_per_wear" not in row for row in client.tables["wardrobe_items"])


# ------------------------------------------------------------------
# list: filters a mixed page, and unions multiple pages.
# ------------------------------------------------------------------


def test_list_filters_mixed_page_with_zero_false_positives() -> None:
    test_account = _marked_user("realtest", prefixed=True, marked=True)
    real_developer_account = FakeUser(
        id="auth-real-dev", email="abhinav@realdomain.com", app_metadata={}
    )
    prefixed_but_unmarked = _marked_user("nomarker", prefixed=True, marked=False)

    admin = FakeAdmin(users=[test_account, real_developer_account, prefixed_but_unmarked])
    client = FakeClient(admin=admin)

    results = sut.cmd_list(client)

    assert [r.user_id for r in results] == [test_account.id]


def test_list_unions_multiple_pages_not_just_page_one() -> None:
    full_page = [
        _marked_user(f"page1-{i}", prefixed=True, marked=True) for i in range(sut.LIST_PAGE_SIZE)
    ]
    short_page = [_marked_user("page2-only", prefixed=True, marked=True)]

    admin = FakeAdmin(users=full_page + short_page)
    client = FakeClient(admin=admin)

    results = sut.cmd_list(client)

    assert len(results) == sut.LIST_PAGE_SIZE + 1
    result_ids = {r.user_id for r in results}
    assert short_page[0].id in result_ids
    assert all(u.id in result_ids for u in full_page)


# ------------------------------------------------------------------
# delete: four-tables-then-users-then-auth call order.
# ------------------------------------------------------------------


def test_delete_clears_four_no_action_fk_tables_before_users_before_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    label = "orderly"
    fake_user = _marked_user(label)
    monkeypatch.setattr(sut, "_find_by_label", lambda admin, label_: fake_user)

    log: list[str] = []
    admin = FakeAdmin(users=[fake_user], log=log)
    client = FakeClient(admin=admin, log=log)

    sut.cmd_delete(client, label, confirm=_always_confirm)

    fk_table_indices = [
        next(i for i, entry in enumerate(log) if entry.startswith(f"{table}.delete"))
        for table in sut.NO_ACTION_FK_TABLES
    ]
    users_delete_index = next(i for i, entry in enumerate(log) if entry.startswith("users.delete"))
    auth_delete_index = next(
        i for i, entry in enumerate(log) if entry.startswith(f"auth.delete_user({fake_user.id})")
    )

    assert max(fk_table_indices) < users_delete_index < auth_delete_index


def test_delete_verifies_zero_rows_across_all_three_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    label = "verified"
    fake_user = _marked_user(label)
    monkeypatch.setattr(sut, "_find_by_label", lambda admin, label_: fake_user)

    admin = FakeAdmin(users=[fake_user])
    client = FakeClient(admin=admin)
    client.tables["users"] = [{"id": fake_user.id}]
    client.tables["wardrobe_items"] = [{"id": "item-1", "user_id": fake_user.id}]

    result = sut.cmd_delete(client, label, confirm=_always_confirm)

    assert result.verification.fully_deleted is True
    assert result.verification.auth_user_present is False
    assert result.verification.public_user_present is False
    assert result.verification.wardrobe_items_remaining == 0


# ------------------------------------------------------------------
# Guard rail #6: service_role key never leaks, even on a failure path.
# ------------------------------------------------------------------


def test_service_role_key_scrubbed_from_create_failure() -> None:
    admin = FakeAdmin()
    admin.create_error = RuntimeError(
        f"upstream rejected request with apikey={SECRET_SERVICE_ROLE_KEY}"
    )
    client = FakeClient(admin=admin)

    with pytest.raises(sut.TestUserAdminError) as exc_info:
        sut.cmd_create(client, "leaktest", confirm=_always_confirm)

    assert SECRET_SERVICE_ROLE_KEY not in str(exc_info.value)
    assert "REDACTED" in str(exc_info.value)


def test_service_role_key_scrubbed_end_to_end_via_main(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = FakeAdmin()
    admin.create_error = RuntimeError(f"boom, key was {SECRET_SERVICE_ROLE_KEY}")
    client = FakeClient(admin=admin)

    monkeypatch.setattr(sut, "_admin_client", lambda: client)
    monkeypatch.setattr(sut, "_interactive_confirm", _always_confirm)

    exit_code = sut.main(["create", "--label", "e2eleak"])

    assert exit_code == 1
    # The autouse _env_and_leak_guard fixture asserts the secret is absent
    # from captured stdout/stderr after this test returns.
