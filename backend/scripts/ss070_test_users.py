"""SS-070 -- Test-User Seed & Teardown Script (Developer phase).

Standalone developer tooling. Ships no HTTP route, no mobile code, and is
not imported by ``app.main`` -- matches the existing ``backend/scripts/``
precedent (``ss015_verify_wear_history.py``, ``ss035_verify_wear_occasion.py``,
...), except this one is meant to be run repeatedly by hand rather than once.

Manages throwaway ``stylesense-test+<label>@stylesense-test.invalid``
accounts against the **live, shared Supabase project** through the
``supabase-py`` 2.31.0 Admin API. Subcommands: ``create``, ``seed``,
``session``, ``list``, ``delete``. See ``docs/tickets/SS-070-design.md`` for
the full ground-check and ``docs/tickets/raw/SS-070.md`` for the ACs.

SAFETY -- READ BEFORE EDITING
------------------------------
This script authenticates with ``SUPABASE_SERVICE_ROLE_KEY`` and performs
IRREVERSIBLE deletes on the one shared live Supabase project, which also
holds the developer's own real account and all real data. Every guard rail
below is load-bearing, not decorative:

  1. Every subcommand (including read-only ``list``) aborts unless
     ``STYLESENSE_ALLOW_TEST_USER_ADMIN=1`` is set in the environment.
  2. ``delete`` refuses any account whose email does not start with
     ``TEST_EMAIL_PREFIX`` **and** whose ``app_metadata`` is missing the
     ``APP_METADATA_MARKER_KEY`` marker -- BOTH conditions are required,
     not either. An email-prefix check alone can be defeated by a real user
     who happens to sign up with a similar address once SS-072 ships.
  3. No subcommand accepts a raw ``auth.users`` id as a delete target --
     every subcommand takes ``--label`` only; the id is resolved internally
     by paging ``list_users`` and matching the deterministic test email.
  4. ``create``/``seed``/``delete`` (the destructive subcommands) print the
     target project ref (parsed from ``SUPABASE_URL``) and require an
     interactive ``y`` confirmation before doing anything.
  5. ``create`` pre-checks ``public.users`` for the target email and
     refuses a duplicate label BEFORE calling the Admin API -- creating an
     ``auth.users`` row whose email already has a different ``public.users``
     row aborts inside a ``SECURITY DEFINER`` trigger with an opaque
     ``500 Database error saving new user`` (``BL-169``).
  6. ``TEST_EMAIL_PREFIX`` is a SAFETY DEVICE, not a configuration knob.
     Do not hand-edit it to point at a real account's address pattern --
     there is no code-level defense against that; it is a human discipline
     rule, stated here explicitly per the raw ticket's own edge case.

``public.users`` has NO foreign key to ``auth.users`` (verified against
every migration through ``020`` -- see the design note's ground-check).
Deleting only from ``auth.users`` therefore leaves ``public.users`` and its
children permanently orphaned. Four tables reference ``users(id)`` with NO
``ON DELETE`` action (``suggestion_sessions``, ``user_avatars``,
``social_posts``, ``shopping_wishlist``) and BLOCK a ``public.users`` delete
for any account that actually used the app. ``delete`` therefore runs, in
this exact order: (1) clear the four no-action-FK tables, (2) delete the
``public.users`` row (cascades ``wardrobe_items``, ``outfits``,
``ai_cost_ledger``, ``suggestion_impressions``), (3) ``auth.admin.delete_user``.
It then re-queries all three surfaces to VERIFY the deletion rather than
trusting that no exception means success.

Usage (from ``backend/``, with the venv active and
``SUPABASE_URL``/``SUPABASE_SERVICE_ROLE_KEY``/``SUPABASE_ANON_KEY`` set,
e.g. via ``set -a && source ../.env && set +a``)::

    export STYLESENSE_ALLOW_TEST_USER_ADMIN=1
    python -m scripts.ss070_test_users create --label demo1
    python -m scripts.ss070_test_users seed --label demo1 --items 8
    python -m scripts.ss070_test_users session --label demo1 --password '<from create>'
    python -m scripts.ss070_test_users list
    python -m scripts.ss070_test_users delete --label demo1

The generated password (AC #2) is printed exactly once by ``create`` and is
never written to any file -- copy it out of the terminal if you need it for
``session`` later. If you no longer have it, ``session`` falls back to a
magic-link redemption (no password required) automatically.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from supabase import AuthApiError, Client, create_client
from supabase_auth.types import Session, User

ENV_OPT_IN = "STYLESENSE_ALLOW_TEST_USER_ADMIN"

# SAFETY DEVICE -- see module docstring guard rail #6. Not a config knob.
TEST_EMAIL_PREFIX = "stylesense-test+"
# .invalid is reserved by RFC 2606 to never resolve -- these addresses are
# never actually sent mail (email_confirm=True skips confirmation), but a
# real, non-resolvable domain is one more layer against ever accidentally
# emailing someone.
TEST_EMAIL_DOMAIN = "stylesense-test.invalid"
APP_METADATA_MARKER_KEY = "ss070_test_user"

LABEL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,47}$")

# Tables that reference users(id) with NO ON DELETE action (verified against
# 001_initial.sql lines 99/111/121/136 -- docs/tickets/SS-070-design.md's
# ground-check). MUST be cleared before the public.users delete below, or
# the delete fails with a raw FK violation for any account that actually
# used the suggestion flow / avatar / social / wishlist features.
NO_ACTION_FK_TABLES: tuple[str, ...] = (
    "suggestion_sessions",
    "user_avatars",
    "social_posts",
    "shopping_wishlist",
)

# Never a real R2 object -- deleting a seeded user does not clean up R2
# (BL-068/SS-015's cleanup only runs via DELETE /wardrobe/items/{id}, which
# this script does not call). A placeholder URL that never touches R2 is
# the raw ticket's own preferred edge-case resolution.
PLACEHOLDER_IMAGE_URL = "https://placehold.co/600x800.png?text=SS-070+seed+item"

LIST_PAGE_SIZE = 200

# Boundary-sweep guard (not from the design note -- added defensively): a
# typo like an extra zero on --items should not be able to flood the one
# shared live project with rows. Re-run seed multiple times if more are
# genuinely needed.
MAX_SEED_ITEMS = 200


class TestUserAdminError(RuntimeError):
    """Raised for expected refusals/failures. Message is always safe to
    print -- constructed only from already-scrubbed text (see ``_scrub``)."""


ConfirmFn = Callable[[str], bool]


# ------------------------------------------------------------------
# Secret scrubbing (guard rail #6: the service_role key must never appear
# in stdout/stderr or a raised exception's message).
# ------------------------------------------------------------------


def _scrub(text: str, secret: str) -> str:
    if not secret:
        return text
    return text.replace(secret, "***REDACTED-SERVICE-ROLE-KEY***")


def _service_role_key() -> str:
    return os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _run_scrubbed(fn: Callable[[], Any]) -> Any:
    """Call ``fn`` with no args; on any exception, re-raise a
    ``TestUserAdminError`` whose message has the service_role key scrubbed
    out, dropping the original exception from the printed traceback
    (``from None``) so it can never be displayed with the key still in it."""
    try:
        return fn()
    except Exception as exc:
        raise TestUserAdminError(_scrub(str(exc), _service_role_key())) from None


# ------------------------------------------------------------------
# Guard rail #1: opt-in env var, every subcommand.
# ------------------------------------------------------------------


def _require_opt_in() -> None:
    if os.environ.get(ENV_OPT_IN) != "1":
        raise TestUserAdminError(
            f"Refusing to run: set {ENV_OPT_IN}=1 to confirm you intend to run "
            "test-user admin operations against the live Supabase project."
        )


# ------------------------------------------------------------------
# Project ref + interactive confirmation (guard rail #4).
# ------------------------------------------------------------------


def _project_ref(supabase_url: str) -> str:
    host = urlparse(supabase_url).hostname or ""
    return host.split(".")[0] if host else supabase_url


def _interactive_confirm(prompt: str) -> bool:
    answer = input(f"{prompt} [type 'y' to continue]: ").strip().lower()
    return answer == "y"


def _require_confirmation(action: str, supabase_url: str, confirm: ConfirmFn) -> None:
    ref = _project_ref(supabase_url)
    print(f"About to {action} against Supabase project '{ref}' ({supabase_url}).")
    if not confirm(f"Confirm: {action}"):
        raise TestUserAdminError(f"Aborted: confirmation declined for: {action}")


# ------------------------------------------------------------------
# Label / email helpers.
# ------------------------------------------------------------------


def _validate_label(label: str) -> str:
    if not LABEL_RE.match(label):
        raise TestUserAdminError(
            f"Invalid --label {label!r}: must match {LABEL_RE.pattern!r} "
            "(lowercase alphanumerics/hyphens, starting with an alphanumeric, <=48 chars)."
        )
    return label


def _email_for_label(label: str) -> str:
    return f"{TEST_EMAIL_PREFIX}{label}@{TEST_EMAIL_DOMAIN}"


def _generate_password() -> str:
    # CSPRNG, >=16 chars (AC #2). token_urlsafe(16) yields ~22 URL-safe
    # base64 characters from Python's `secrets` module.
    return secrets.token_urlsafe(16)


def _is_ss070_test_account(user: User) -> bool:
    email = user.email or ""
    app_metadata = user.app_metadata or {}
    return email.startswith(TEST_EMAIL_PREFIX) and bool(app_metadata.get(APP_METADATA_MARKER_KEY))


# ------------------------------------------------------------------
# Admin API paging (list_users has no server-side filter -- verified
# against the installed supabase-py source, see design note).
# ------------------------------------------------------------------


def _iter_all_users(admin: Any, page_size: int = LIST_PAGE_SIZE) -> list[User]:
    all_users: list[User] = []
    page = 1
    while True:
        users = admin.list_users(page=page, per_page=page_size)
        if not users:
            return all_users
        all_users.extend(users)
        if len(users) < page_size:
            return all_users
        page += 1


def _find_by_label(admin: Any, label: str) -> User | None:
    target_email = _email_for_label(label)
    for user in _iter_all_users(admin):
        if user.email == target_email:
            return user
    return None


def _select_users_by_email(client: Any, email: str) -> list[dict[str, Any]]:
    resp = client.table("users").select("id,email").eq("email", email).execute()
    return list(resp.data or [])


# ------------------------------------------------------------------
# Result types.
# ------------------------------------------------------------------


@dataclass(frozen=True)
class CreateResult:
    user_id: str
    email: str
    password: str
    profile_row_verified: bool


@dataclass(frozen=True)
class SeedResult:
    user_id: str
    inserted: int
    total: int


@dataclass(frozen=True)
class SessionResult:
    email: str
    access_token: str
    refresh_token: str
    storage_key: str


@dataclass(frozen=True)
class ListedUser:
    user_id: str
    email: str
    created_at: str


@dataclass(frozen=True)
class DeleteVerification:
    auth_user_present: bool
    public_user_present: bool
    wardrobe_items_remaining: int

    @property
    def fully_deleted(self) -> bool:
        return (
            not self.auth_user_present
            and not self.public_user_present
            and self.wardrobe_items_remaining == 0
        )


@dataclass(frozen=True)
class DeleteResult:
    user_id: str
    verification: DeleteVerification


# ------------------------------------------------------------------
# create
# ------------------------------------------------------------------


def cmd_create(client: Any, label: str, confirm: ConfirmFn = _interactive_confirm) -> CreateResult:
    label = _validate_label(label)
    supabase_url = os.environ["SUPABASE_URL"]
    email = _email_for_label(label)

    existing_auth = _find_by_label(client.auth.admin, label)
    if existing_auth is not None:
        raise TestUserAdminError(
            f"Refusing to create: label {label!r} already has a test account ({email})."
        )

    # Guard rail #5 -- the BL-169 landmine: pre-check public.users for the
    # email BEFORE calling the Admin API, so a collision produces a clear
    # message instead of an opaque 500 from inside the auth trigger.
    if _select_users_by_email(client, email):
        raise TestUserAdminError(
            f"Refusing to create: a public.users row already exists for {email} "
            "(BL-169 -- creating this auth.users row would raise an opaque "
            "'500 Database error saving new user' from the handle_new_auth_user trigger)."
        )

    _require_confirmation(f"create test user '{label}' ({email})", supabase_url, confirm)

    password = _generate_password()

    def _create() -> Any:
        return client.auth.admin.create_user(
            {
                "email": email,
                "password": password,
                "email_confirm": True,
                "app_metadata": {APP_METADATA_MARKER_KEY: True, "ss070_label": label},
            }
        )

    response = _run_scrubbed(_create)
    user = response.user

    # AC #1: confirm the public.users row by an ACTUAL query -- never
    # inferred from the trigger's existence.
    profile_rows = _select_users_by_email(client, email)
    profile_verified = bool(profile_rows) and profile_rows[0].get("id") == user.id

    print(f"Created auth user {user.id} ({email}).")
    print(f"Password (shown once, never stored by this script): {password}")
    if profile_verified:
        print(f"Verified: public.users row exists for {user.id}.")
    else:
        print(
            f"WARNING: no public.users row found for {user.id} -- the "
            "handle_new_auth_user trigger may not have fired (half-state account, "
            f"see the raw ticket's 'Partial create' edge case). Run "
            f"`delete --label {label}` to clean up, then retry."
        )

    return CreateResult(
        user_id=user.id, email=email, password=password, profile_row_verified=profile_verified
    )


# ------------------------------------------------------------------
# seed
# ------------------------------------------------------------------


def _seed_item_payload(user_id: str) -> dict[str, Any]:
    return {
        "user_id": user_id,
        "image_url": PLACEHOLDER_IMAGE_URL,
        "category": "western_top",
        "subcategory": "kurta",
        "color_primary": "navy_blue",
        "pattern": "solid",
        "fabric": "cotton",
        "occasion_tags": ["office"],
        "season_tags": ["summer"],
        "processing_status": "bg_removed",
        "purchase_price": 149900,  # paise -- INR 1,499
        # cost_per_wear is a GENERATED column -- NEVER insert it.
    }


def _count_wardrobe_items(client: Any, user_id: str) -> int:
    resp = client.table("wardrobe_items").select("id").eq("user_id", user_id).execute()
    return len(resp.data or [])


def cmd_seed(
    client: Any,
    label: str,
    items: int,
    complete_onboarding: bool = False,
    confirm: ConfirmFn = _interactive_confirm,
) -> SeedResult:
    label = _validate_label(label)
    if items < 1:
        raise TestUserAdminError("--items must be >= 1.")
    if items > MAX_SEED_ITEMS:
        raise TestUserAdminError(
            f"Refusing to seed {items} rows in one call (max {MAX_SEED_ITEMS}) -- likely a typo "
            "(e.g. an extra zero). Re-run seed multiple times if you really need more."
        )
    supabase_url = os.environ["SUPABASE_URL"]

    user = _find_by_label(client.auth.admin, label)
    if user is None or not _is_ss070_test_account(user):
        raise TestUserAdminError(
            f"Refusing to seed: no ss070 test account found for label {label!r}."
        )

    _require_confirmation(
        f"seed {items} wardrobe_items row(s) for '{label}' ({user.email})", supabase_url, confirm
    )

    rows = [_seed_item_payload(user.id) for _ in range(items)]

    def _insert() -> Any:
        return client.table("wardrobe_items").insert(rows).execute()

    _run_scrubbed(_insert)

    if complete_onboarding:

        def _update() -> Any:
            return (
                client.table("users")
                .update({"onboarding_completed": True})
                .eq("id", user.id)
                .execute()
            )

        _run_scrubbed(_update)

    total = _count_wardrobe_items(client, user.id)
    print(f"Seeded {items} wardrobe_items row(s) for '{label}' ({user.id}). New total: {total}.")
    return SeedResult(user_id=user.id, inserted=items, total=total)


# ------------------------------------------------------------------
# session
# ------------------------------------------------------------------


def _session_via_password(client: Any, email: str, password: str) -> Session:
    def _sign_in() -> Any:
        return client.auth.sign_in_with_password({"email": email, "password": password})

    auth_response = _run_scrubbed(_sign_in)
    return auth_response.session


def _session_via_magic_link(client: Any, email: str) -> Session:
    """Fallback path when the password isn't available (design note: "keep
    generate_link as fallback only"). No password required -- generates a
    magic-link token server-side then redeems it directly for a session."""

    def _generate() -> Any:
        return client.auth.admin.generate_link({"type": "magiclink", "email": email})

    link = _run_scrubbed(_generate)

    def _verify() -> Any:
        return client.auth.verify_otp(
            {"token_hash": link.properties.hashed_token, "type": "magiclink"}
        )

    auth_response = _run_scrubbed(_verify)
    return auth_response.session


def _print_session(session: Session, email: str, supabase_url: str) -> SessionResult:
    ref = _project_ref(supabase_url)
    storage_key = f"sb-{ref}-auth-token"
    user_dump = session.user.model_dump(mode="json") if hasattr(session.user, "model_dump") else {}
    payload = {
        "access_token": session.access_token,
        "token_type": session.token_type,
        "expires_in": session.expires_in,
        "expires_at": session.expires_at,
        "refresh_token": session.refresh_token,
        "user": user_dump,
    }
    payload_json = json.dumps(payload)

    print(f"Session for {email} (access token expires in {session.expires_in}s):")
    print(payload_json)
    print()
    print("Browser console one-liner for the running web build (no login UI used):")
    print(
        f"localStorage.setItem({json.dumps(storage_key)}, {json.dumps(payload_json)}); "
        "location.reload();"
    )
    print()
    print(
        "NOTE: the access token expires in ~1h; the refresh token outlives it. "
        "If the app rejects a previously-copied session as expired, re-run "
        "`session --label <label>` for a fresh one."
    )

    return SessionResult(
        email=email,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        storage_key=storage_key,
    )


def cmd_session(client: Any, label: str, password: str | None = None) -> SessionResult:
    label = _validate_label(label)
    supabase_url = os.environ["SUPABASE_URL"]

    user = _find_by_label(client.auth.admin, label)
    if user is None or not _is_ss070_test_account(user):
        raise TestUserAdminError(
            f"Refusing to sign in: no ss070 test account found for label {label!r}."
        )
    email = user.email or _email_for_label(label)

    if password:
        session = _session_via_password(client, email, password)
    else:
        print("No --password given -- falling back to magic-link redemption.")
        session = _session_via_magic_link(client, email)

    return _print_session(session, email, supabase_url)


# ------------------------------------------------------------------
# list
# ------------------------------------------------------------------


def cmd_list(client: Any) -> list[ListedUser]:
    admin = client.auth.admin
    results = [
        ListedUser(user_id=u.id, email=u.email or "", created_at=str(u.created_at))
        for u in _iter_all_users(admin)
        if _is_ss070_test_account(u)
    ]

    if not results:
        print("No ss070 test accounts found.")
    else:
        print(f"{len(results)} ss070 test account(s):")
        for r in results:
            print(f"  {r.user_id}  {r.email}  created {r.created_at}")

    return results


# ------------------------------------------------------------------
# delete
# ------------------------------------------------------------------


def _auth_user_exists(client: Any, user_id: str) -> bool:
    try:
        client.auth.admin.get_user_by_id(user_id)
        return True
    except AuthApiError as exc:
        if exc.status == 404:
            return False
        raise


def _verify_deleted(client: Any, user_id: str) -> DeleteVerification:
    auth_present = _auth_user_exists(client, user_id)
    profile_rows = client.table("users").select("id").eq("id", user_id).execute().data or []
    item_rows = (
        client.table("wardrobe_items").select("id").eq("user_id", user_id).execute().data or []
    )
    return DeleteVerification(
        auth_user_present=auth_present,
        public_user_present=bool(profile_rows),
        wardrobe_items_remaining=len(item_rows),
    )


def cmd_delete(client: Any, label: str, confirm: ConfirmFn = _interactive_confirm) -> DeleteResult:
    label = _validate_label(label)
    supabase_url = os.environ["SUPABASE_URL"]

    user = _find_by_label(client.auth.admin, label)
    if user is None:
        raise TestUserAdminError(f"Refusing to delete: no account found for label {label!r}.")

    # Guard rail #2 -- BOTH the email prefix AND the app_metadata marker are
    # required, not either. This is the single most important check in the
    # whole script; it is deliberately re-verified here against the record
    # actually returned by the Admin API, not merely inferred from how the
    # email was constructed.
    if not _is_ss070_test_account(user):
        email = user.email or "<no email>"
        raise TestUserAdminError(
            f"Refusing to delete {email!r}: must match the {TEST_EMAIL_PREFIX!r} prefix "
            f"AND carry a truthy {APP_METADATA_MARKER_KEY!r} app_metadata marker -- "
            "this account is missing at least one. Both are required, not either."
        )

    email = user.email or _email_for_label(label)
    _require_confirmation(
        f"PERMANENTLY DELETE test user '{label}' ({email})", supabase_url, confirm
    )

    user_id = user.id

    def _clear_and_delete() -> None:
        # Ordered delete (design note's ground-check correction of the raw
        # ticket's wrong cascade claim): the four no-action-FK tables FIRST,
        # then public.users (cascades wardrobe_items/outfits/ai_cost_ledger/
        # suggestion_impressions), THEN auth.users last.
        for table in NO_ACTION_FK_TABLES:
            client.table(table).delete().eq("user_id", user_id).execute()

        client.table("users").delete().eq("id", user_id).execute()

        client.auth.admin.delete_user(user_id, should_soft_delete=False)

    _run_scrubbed(_clear_and_delete)

    verification = _verify_deleted(client, user_id)
    print(f"Delete requested for '{label}' ({user_id}). Post-delete verification:")
    print(f"  auth.users row present:       {verification.auth_user_present}")
    print(f"  public.users row present:     {verification.public_user_present}")
    print(f"  wardrobe_items rows remaining: {verification.wardrobe_items_remaining}")

    if not verification.fully_deleted:
        raise TestUserAdminError(
            f"Delete verification FAILED for '{label}' ({user_id}): {verification}"
        )

    print("Verified: zero rows remain across auth.users, public.users, wardrobe_items.")
    return DeleteResult(user_id=user_id, verification=verification)


# ------------------------------------------------------------------
# CLI wiring
# ------------------------------------------------------------------


def _admin_client() -> Client:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    return _run_scrubbed(lambda: create_client(url, key))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ss070_test_users",
        description=(
            "SS-070 test-user seed/teardown tool. Manages throwaway "
            f"{TEST_EMAIL_PREFIX}<label>@{TEST_EMAIL_DOMAIN} accounts on the live "
            "Supabase project via the Admin API (service_role). No subcommand accepts "
            "a raw user id -- every destructive action is resolved from --label internally."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create", help="Create a new test account.")
    p_create.add_argument("--label", required=True)

    p_seed = sub.add_parser("seed", help="Seed wardrobe_items rows for a test account.")
    p_seed.add_argument("--label", required=True)
    p_seed.add_argument("--items", type=int, required=True)
    p_seed.add_argument(
        "--complete-onboarding", action="store_true", help="Also set onboarding_completed=true."
    )

    p_session = sub.add_parser("session", help="Print a redeemable session for a test account.")
    p_session.add_argument("--label", required=True)
    p_session.add_argument(
        "--password",
        default=None,
        help="Password from `create`'s one-time output. Omit to fall back to a "
        "magic-link redemption instead.",
    )

    sub.add_parser("list", help="List every ss070 test account (and no others).")

    p_delete = sub.add_parser("delete", help="Permanently delete a test account and all its data.")
    p_delete.add_argument("--label", required=True)

    return parser


def _dispatch(client: Any, args: argparse.Namespace) -> None:
    if args.command == "create":
        cmd_create(client, args.label)
    elif args.command == "seed":
        cmd_seed(client, args.label, args.items, args.complete_onboarding)
    elif args.command == "session":
        cmd_session(client, args.label, args.password)
    elif args.command == "list":
        cmd_list(client)
    elif args.command == "delete":
        cmd_delete(client, args.label)
    else:  # pragma: no cover -- argparse's `required=True` makes this unreachable.
        raise TestUserAdminError(f"Unknown command {args.command!r}.")


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        _require_opt_in()
        client = _admin_client()
        _dispatch(client, args)
    except TestUserAdminError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # last-resort scrub -- guard rail #6 is global.
        print(
            f"ERROR: unexpected failure: {_scrub(str(exc), _service_role_key())}", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
