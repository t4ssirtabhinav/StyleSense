"""SS-040 -- proves "nothing reads render_transform yet" (design §"Files to
create", modelled on test_garment_registry_purely_additive.py's pattern).

migration 023_item_lifecycle_columns.sql adds `wardrobe_items.render_transform`
as a bare nullable JSONB column with no shape enforced -- SS-055 owns the
eventual `{x, y, scale, rotation, z}` shape and its readers. This test locks
in that the column ships genuinely inert: no backend or mobile source
references the identifier outside tests/scripts/docs/migrations/the
generated types file.

**Whoever builds SS-055: this test is EXPECTED to start failing once you add
a real reader. Narrow its exclusions/allowlist the way SS-038 narrowed
test_garment_registry_purely_additive.py's -- do not delete this test.**

Pure filesystem/text-search, no live Postgres connection -- must run in
every CI invocation, unlike test_db_schema.py's live-gated assertions.
"""

from __future__ import annotations

import re
from pathlib import Path

RENDER_TRANSFORM_IDENTIFIER = "render_transform"

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
MOBILE_DIR = REPO_ROOT / "mobile"
MIGRATION_FILE = REPO_ROOT / "supabase" / "migrations" / "023_item_lifecycle_columns.sql"


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


def test_render_transform_has_no_backend_or_mobile_readers() -> None:
    """SS-055 is the ticket that will legitimately break this test -- when
    it adds a real reader, narrow the exclusion/allowlist the way SS-038
    narrowed test_garment_registry_purely_additive.py, don't delete this
    test."""
    assert BACKEND_DIR.is_dir(), f"expected backend/ at {BACKEND_DIR}"
    assert MOBILE_DIR.is_dir(), f"expected mobile/ at {MOBILE_DIR}"

    offenders: list[str] = []

    for path in _iter_source_files(
        BACKEND_DIR,
        suffixes=(".py",),
        excluded_dirs=("tests", "scripts"),
    ):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if RENDER_TRANSFORM_IDENTIFIER in text:
            offenders.append(f"{path.relative_to(REPO_ROOT)}")

    for path in _iter_source_files(
        MOBILE_DIR,
        suffixes=(".ts", ".tsx"),
        excluded_dirs=("__tests__",),
        excluded_files=(MOBILE_DIR / "types" / "supabase.ts",),
    ):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if RENDER_TRANSFORM_IDENTIFIER in text:
            offenders.append(f"{path.relative_to(REPO_ROOT)}")

    assert not offenders, (
        "render_transform must not appear in any backend/ or mobile/ source file "
        f"outside tests/scripts/__tests__/the generated types file yet (SS-055 owns "
        f"the first real reader): {offenders}"
    )


def test_render_transform_column_exists_in_migration_023() -> None:
    """Cross-checks the identifier against the migration file itself, so a
    future rename fails THIS test loudly instead of the grep above silently
    checking a stale name forever (test_garment_registry_purely_additive.py's
    exact guard)."""
    assert MIGRATION_FILE.is_file(), f"expected migration file at {MIGRATION_FILE}"
    sql = MIGRATION_FILE.read_text(encoding="utf-8")

    added_columns = set(re.findall(r"ADD COLUMN IF NOT EXISTS (\w+)", sql))

    assert RENDER_TRANSFORM_IDENTIFIER in added_columns, (
        "expected 'render_transform' among migration 023's ADD COLUMN statements -- "
        f"found {added_columns}"
    )
