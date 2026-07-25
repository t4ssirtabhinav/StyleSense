"""Real JWT-verification FastAPI dependency (SS-011, resolves ``BL-033``).

Replaces the pattern of ``routers/outfit_suggestions.py``'s explicitly
NON-PRODUCTION ``get_current_user_id_stub`` (reads the ``sub`` claim WITHOUT
verifying the token's signature). This dependency instead calls
``supabase-py``'s ``auth.get_user(token)``, which validates the token's
signature server-side against Supabase's hosted Auth API -- the first real
auth boundary in this backend. ``outfit_suggestions.py``'s stub is
deliberately left untouched by this ticket (tracked as ``BL-052``).

**Call-shape verification note** (design doc's Open Questions #3, "verify,
don't recite" per docs/OPERATOR_RULEBOOK.md): confirmed 2026-07-24 against
this repo's actually-installed ``supabase==2.31.0`` /
``supabase-auth==2.31.0``:

- ``create_client(url, key) -> Client`` (sync). ``Client.auth`` resolves (via
  MRO) to ``supabase_auth._sync.gotrue_client.SyncGoTrueClient``.
- ``SyncGoTrueClient.get_user(jwt: str | None = None) -> UserResponse | None``
  is a **synchronous** method (not a coroutine) -- the design doc's own
  sketch already called it without ``await``, so no change was needed there,
  but this is flagged explicitly since a sync, network-bound call inside an
  ``async def`` dependency blocks the event loop for its duration. Accepted
  as-is for this ticket (matches the design's own sketch, and this endpoint
  is not yet under meaningful concurrent load) -- worth revisiting if this
  dependency becomes a hot path.
- On an invalid/expired token, the underlying ``_request`` call raises
  ``supabase_auth.errors.AuthApiError`` (a subclass of ``Exception``) rather
  than returning ``None`` -- caught here via a broad ``except Exception``,
  consistent with the design's own sketch.
- ``UserResponse.user`` is a required (non-Optional) field once a
  ``UserResponse`` is successfully constructed, but ``get_user`` can also
  return ``None`` outright per its own signature (e.g. an unexpected empty
  response) -- both cases are guarded below.
"""

from __future__ import annotations

import os

from fastapi import Header, HTTPException
from supabase import create_client


async def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing bearer token")

    client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])
    try:
        response = client.auth.get_user(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user = getattr(response, "user", None)
    user_id = getattr(user, "id", None)
    if user is None or not user_id:
        raise HTTPException(status_code=401, detail="Token did not resolve to a valid user")

    return str(user_id)
