"""core.database — 永久 re-export facade（spec-87 D0）。

所有呼叫方繼續使用 `from core.database import X`，無需感知子模組。
"""
from .connection import (
    get_db_path,
    get_connection,
    init_db,
    _migrate_old_aliases,
)
from .video import Video, VideoRepository
from .alias import AliasRecord, AliasRepository
from .tag_alias import TagAliasRecord, TagAliasRepository
from .actress import Actress, ActressRepository
from .migrate import migrate_json_to_sqlite, backfill_readonly_nfo_mtime

__all__ = [
    "get_db_path",
    "get_connection",
    "init_db",
    "_migrate_old_aliases",
    "Video",
    "VideoRepository",
    "AliasRecord",
    "AliasRepository",
    "TagAliasRecord",
    "TagAliasRepository",
    "Actress",
    "ActressRepository",
    "migrate_json_to_sqlite",
    "backfill_readonly_nfo_mtime",
]
