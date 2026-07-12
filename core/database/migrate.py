"""core.database.migrate — JSON cache → SQLite 遷移（spec-87 子模組）。"""
import json
from pathlib import Path

from . import connection
from .video import Video, VideoRepository


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
