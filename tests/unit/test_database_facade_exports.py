"""Regression guard: core.database facade must export all public names.

If someone accidentally removes an entry from core/database/__init__.py
(once the module is split into a package in 87a-T2), this test catches it
immediately. Each name is asserted independently so the failure message
identifies exactly which export went missing.

This guard is intentionally added BEFORE the split (87a-T1): it passes on the
current single-file core/database.py and turns RED the moment the split-out
facade omits any re-export.
"""
from pathlib import Path

import pytest

import core.database as db

# spec-87 §A public surface — all 13 names the facade must re-export.
# Includes the underscore-prefixed _migrate_old_aliases because
# tests/unit/test_alias_repository.py:81 imports it directly.
EXPECTED_NAMES = [
    # connection.py
    "get_db_path",
    "get_connection",
    "init_db",
    "_migrate_old_aliases",
    # migrate.py
    "migrate_json_to_sqlite",
    # video.py
    "Video",
    "VideoRepository",
    # alias.py
    "AliasRecord",
    "AliasRepository",
    # tag_alias.py
    "TagAliasRecord",
    "TagAliasRepository",
    # actress.py
    "Actress",
    "ActressRepository",
]


@pytest.mark.parametrize("name", EXPECTED_NAMES)
def test_facade_exports_public_name(name):
    assert hasattr(db, name), (
        f"core.database is missing '{name}' — "
        f"check core/database/__init__.py __all__ and its import list"
    )


def test_default_db_path_resolves_to_repo_root_output():
    """get_db_path() must resolve to <repo-root>/output/openaver.db.

    Regression guard for the 87a split: get_db_path lives in the deeper
    core/database/connection.py, so its Path(__file__).parent chain must walk
    up one extra level. A byte-exact copy from the old monolith silently
    pointed the default DB at core/output/ — empty DB / apparent data loss for
    every no-arg caller. The rest of the suite never catches this because it
    always uses tmp_path / explicit db_path / patched get_db_path.
    """
    # this test file is tests/unit/<f>.py → parents[2] is the repo root
    repo_root = Path(__file__).resolve().parents[2]
    expected = repo_root / "output" / "openaver.db"
    assert db.get_db_path().resolve() == expected.resolve(), (
        f"get_db_path() = {db.get_db_path()}, expected {expected}"
    )
