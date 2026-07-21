"""core.database.migrate — JSON cache → SQLite 遷移（spec-87 子模組）。"""
import json
from pathlib import Path

from core.logger import get_logger

from . import connection
from .video import Video, VideoRepository

logger = get_logger(__name__)


def migrate_json_to_sqlite(json_path: Path, db_path: Path = None,
                           delete_on_success: bool = True) -> dict:
    """遷移 JSON cache 到 SQLite

    Args:
        json_path: JSON 快取檔案路徑
        db_path: SQLite 資料庫路徑（預設為 output/openaver.db）
        delete_on_success: 成功後是否刪除 JSON 檔案

    Returns:
        dict: {'migrated': int, 'skipped': int, 'errors': int}
    """
    from core.gallery_scanner import VideoInfo

    result = {'migrated': 0, 'skipped': 0, 'errors': 0}

    if not Path(json_path).exists():
        return result

    # 確保資料庫已初始化
    if db_path is None:
        db_path = connection.get_db_path()
    connection.init_db(db_path)

    # 讀取 JSON
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
    except (json.JSONDecodeError, IOError):
        result['errors'] = 1
        return result

    repo = VideoRepository(db_path)
    videos_to_upsert = []

    for path_key, entry in cache_data.items():
        # 跳過 _metadata
        if path_key == '_metadata':
            result['skipped'] += 1
            continue

        try:
            # 取得 info 資料
            info_dict = entry.get('info', {})
            if not info_dict:
                result['skipped'] += 1
                continue

            # 建立 VideoInfo
            video_info = VideoInfo.from_dict(info_dict)

            # 轉換為 Video
            video = Video.from_video_info(video_info)

            # 設定 mtime 和 nfo_mtime（從 cache entry 取得，不是從 info 取得）
            video.mtime = entry.get('mtime', 0.0)
            video.nfo_mtime = entry.get('nfo_mtime', 0.0)

            videos_to_upsert.append(video)
        except Exception:
            result['errors'] += 1

    # 批次寫入
    if videos_to_upsert:
        inserted, updated = repo.upsert_batch(videos_to_upsert)
        result['migrated'] = inserted + updated

    # 成功後刪除 JSON
    if delete_on_success and result['errors'] == 0 and result['migrated'] > 0:
        try:
            Path(json_path).unlink()
        except IOError:
            pass

    return result


def backfill_readonly_nfo_mtime(db_path=None, path_mappings=None) -> int:
    """One-time heal for pre-0.12.6 readonly rows with a produced cover but a
    stale nfo_mtime<=0 (the v0.11.x/88b readonly produce hardcoded 0.0 while the
    .nfo was really written next to the cover in output_dir). showcase reads
    has_nfo from nfo_mtime, so those videos show a spurious enrich icon. This
    stats the sibling .nfo (derived from cover_path) and writes its real mtime.

    Idempotent + safe: only rows with cover_path set AND nfo_mtime<=0 (or NULL)
    are considered, and only when the sibling .nfo actually exists on disk; the
    UPDATE only SETS nfo_mtime, never clears it. Rows whose .nfo is missing are
    left untouched (they legitimately keep has_nfo=False). Returns the count healed.
    """
    from core.path_utils import uri_to_local_fs_path

    if db_path is None:
        db_path = connection.get_db_path()
    if path_mappings is None:
        path_mappings = {}

    conn = connection.get_connection(db_path)
    healed = 0
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT path, cover_path FROM videos "
            "WHERE cover_path IS NOT NULL AND cover_path != '' "
            "AND (nfo_mtime IS NULL OR nfo_mtime <= 0)"
        )
        rows = cursor.fetchall()

        for video_path, cover_path in rows:
            try:
                cover_fs = uri_to_local_fs_path(cover_path, path_mappings)
                nfo_path = Path(cover_fs).with_suffix('.nfo')
                if not nfo_path.exists():
                    continue
                nfo_mtime = nfo_path.stat().st_mtime
                cursor.execute(
                    "UPDATE videos SET nfo_mtime = ? WHERE path = ?",
                    (nfo_mtime, video_path),
                )
                healed += 1
            except Exception:
                logger.warning(
                    "backfill_readonly_nfo_mtime: failed to heal row path=%r cover_path=%r",
                    video_path, cover_path, exc_info=True
                )

        conn.commit()
    finally:
        conn.close()

    return healed
