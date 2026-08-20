"""SS-034 -- originally proved "nothing reads the garment types registry
yet" (design §6.2). **SS-038 is the first real consumer** of two of these
eight identifiers (``garment_types``, ``garment_type_aliases``, via
``services/garment_registry_adapter.py`` and
``adapters/garment_registry_repository.py``) -- this test now asserts the
NARROWER, still-true claim: the other SIX identifiers
(``garment_unknown_types``, ``garment_set_components``,
``garment_normalize_one``, ``garment_normalize_shape``, ``garment_is_known``,
``garment_log_unknown``) remain unreferenced by any backend/mobile source
outside tests/scripts -- SS-038 reads ``garment_types`` rows directly via
PostgREST, it never calls the SQL-side normalisation/logging functions or
touches the unknown-capture/set-component tables.

Unlike test_db_schema.py's SS-034 additions, this module needs no live
Postgres connection -- it is a pure filesystem/text-search test and must
run in every CI invocation. Do NOT gate it behind SUPABASE_DB_URL.

Scoped narrowly to the registry's own identifiers (table/function names),
deliberately NOT a generic word search -- "kurta", "saree", etc. already
appear legitimately as existing `wardrobe_category` ENUM values in shipped
code and would be false positives (design §6.2).

**SS-044 checked this file deliberately, per its own design doc's "Files to
modify" instruction, rather than leaving it silently stale.** SS-044
(migration 022_garment_category_resolution.sql) is what makes SS-038's
existing `garment_types`/`garment_type_aliases` reads genuinely RESOLVE
against live `wardrobe_items.category` values (they were a 100% miss
before -- BL-132) -- but it changes zero backend source files' READ SET.
Approach (a) (alias rows, not an ENUM->TEXT migration) needs no code
change on the resolution path (design finding 5): the two ALREADY-
allowlisted consumer files below still read exactly `garment_types`/
`garment_type_aliases` and nothing else; the other six identifiers
(`garment_unknown_types`, `garment_set_components`,
`garment_normalize_one`, `garment_normalize_shape`, `garment_is_known`,
`garment_log_unknown`) remain genuinely untouched by any backend/mobile
source outside tests/scripts -- SS-044 does not call any of the SQL-side
normalisation/logging functions either. Every assertion below is
STILL TRUE after SS-044 and needs no functional change; this comment
records that it was checked, not skipped.
"""

from __future__ import annotations

import re
from pathlib import Path

# The exact set of objects 014_garment_types_registry.sql creates. Kept
# here as the single source of truth this module tests against, and
# cross-checked against the migration file itself below so a future rename
# fails THIS test loudly instead of the grep silently checking a stale name
# forever (design §6.2, test_identifier_list_matches_the_migration_file).
GARMENT_REGISTRY_IDENTIFIERS = frozenset(
    {
        "garment_types",
        "garment_type_aliases",
        "garment_unknown_types",
        "garment_set_components",
        "garment_normalize_one",
        "garment_normalize_shape",
        "garment_is_known",
        "garment_log_unknown",
    }
)

# SS-038's real, legitimate consumers of `garment_types`/`garment_type_aliases`
# -- the two identifiers this test no longer asserts are unreferenced. Kept
# as an explicit allowlist (not a broad exclusion) so any OTHER file
# referencing these two identifiers still fails loudly.
_SS038_CONSUMER_IDENTIFIERS = frozenset({"garment_types", "garment_type_aliases"})
_STILL_PURELY_ADDITIVE_IDENTIFIERS = GARMENT_REGISTRY_IDENTIFIERS - _SS038_CONSUMER_IDENTIFIERS

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
MOBILE_DIR = REPO_ROOT / "mobile"
MIGRATION_FILE = REPO_ROOT / "supabase" / "migrations" / "014_garment_types_registry.sql"


def _iter_source_files(
    root: Path,
    suffixes: tuple[str, ...],
    excluded_dirs: tuple[str, ...],
    excluded_files: tuple[Path, ...] = (),
) -> list[Path]:
    excluded = {root / d for d in excluded_dirs}
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(excluded_dir in path.parents or path == excluded_dir for excluded_dir in excluded):
            continue
        if path in excluded_files:
            continue
        files.append(path)
    return files


def test_no_backend_source_references_garment_registry_identifiers() -> None:
    """Narrowed by SS-038 (see module docstring): only the SIX identifiers
    that are STILL genuinely unconsumed are asserted here.
    ``garment_types``/``garment_type_aliases`` now have real,
    allowlisted consumers -- see
    ``test_only_ss038_consumer_files_reference_garment_types_and_aliases``
    below for the positive-side assertion covering those two."""
    assert BACKEND_DIR.is_dir(), f"expected backend/ at {BACKEND_DIR}"

    offenders: list[str] = []
    for path in _iter_source_files(
        BACKEND_DIR,
        suffixes=(".py",),
        excluded_dirs=("tests", "scripts"),
    ):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for identifier in _STILL_PURELY_ADDITIVE_IDENTIFIERS:
            if identifier in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {identifier}")

    assert not offenders, (
        "these garment registry identifiers must still not appear in any backend/ "
        f"source file outside tests/ or scripts/ (still zero consumers): {offenders}"
    )


def test_no_mobile_source_references_garment_registry_identifiers() -> None:
    if not MOBILE_DIR.is_dir():
        # Defensive: this repo always ships mobile/, but do not hard-fail the
        # whole suite over a checkout-shape assumption in an unrelated area.
        return

    # mobile/types/supabase.ts is auto-generated by `supabase gen types` from
    # the live schema, not authored consumer code -- once garment_types exists
    # live, its row/column types legitimately appear there regardless of
    # whether any real feature code imports them. Excluding it here is the
    # same class of exclusion as __tests__/, just file- rather than dir-scoped.
    offenders: list[str] = []
    for path in _iter_source_files(
        MOBILE_DIR,
        suffixes=(".ts", ".tsx"),
        excluded_dirs=("__tests__",),
        excluded_files=(MOBILE_DIR / "types" / "supabase.ts",),
    ):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for identifier in GARMENT_REGISTRY_IDENTIFIERS:
            if identifier in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {identifier}")

    assert not offenders, (
        "garment registry identifiers must not appear in any mobile/ source file "
        f"outside __tests__/ or the generated types file yet "
        f"(SS-038 has no mobile-side consumer of the garment registry): {offenders}"
    )


_SS038_GARMENT_REGISTRY_CONSUMER_FILES = (
    "adapters/garment_registry_repository.py",
    "adapters/interfaces.py",
    "services/engine_v2.py",
    "services/engine_v2_types.py",
    "services/garment_registry_adapter.py",
    "services/styling_rules_defaults.py",
)


def test_only_ss038_consumer_files_reference_garment_types_and_aliases() -> None:
    """The positive-side assertion for SS-038's narrowing: `garment_types`/
    `garment_type_aliases` may now appear ONLY in this ticket's explicitly
    allowlisted consumer files (plus tests/scripts, already excluded by the
    sibling test above) -- any OTHER backend source file referencing these
    two identifiers still fails loudly, same discipline as before SS-038."""
    assert BACKEND_DIR.is_dir(), f"expected backend/ at {BACKEND_DIR}"

    allowlisted = {BACKEND_DIR / rel for rel in _SS038_GARMENT_REGISTRY_CONSUMER_FILES}
    for path in allowlisted:
        assert path.is_file(), f"expected SS-038 consumer file at {path}"

    offenders: list[str] = []
    for path in _iter_source_files(
        BACKEND_DIR,
        suffixes=(".py",),
        excluded_dirs=("tests", "scripts"),
    ):
        if path in allowlisted:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for identifier in _SS038_CONSUMER_IDENTIFIERS:
            if identifier in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {identifier}")

    assert not offenders, (
        "garment_types/garment_type_aliases must only appear in SS-038's allowlisted "
        f"consumer files outside tests/scripts: {offenders}"
    )


def test_identifier_list_matches_the_migration_file() -> None:
    """Sanity check the other way: every CREATE TABLE/CREATE FUNCTION name
    in 014_garment_types_registry.sql must be in GARMENT_REGISTRY_IDENTIFIERS
    above, so a future rename of one of these objects fails this test loudly
    instead of the grep above silently checking a stale name forever."""
    assert MIGRATION_FILE.is_file(), f"expected migration file at {MIGRATION_FILE}"
    sql = MIGRATION_FILE.read_text(encoding="utf-8")

    table_names = set(re.findall(r"CREATE TABLE (\w+)", sql))
    function_names = set(re.findall(r"CREATE OR REPLACE FUNCTION public\.(\w+)\(", sql))

    found_identifiers = table_names | function_names

    assert found_identifiers, "no CREATE TABLE/CREATE FUNCTION statements found in the migration"
    assert found_identifiers == set(GARMENT_REGISTRY_IDENTIFIERS), (
        "the migration file's actual object names diverged from this test's identifier "
        f"list -- found {found_identifiers}, expected {set(GARMENT_REGISTRY_IDENTIFIERS)}"
    )
