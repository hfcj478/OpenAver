"""core/favorite_scan.py — 我的最愛資料夾列檔邏輯（spec-144 T3）。

從 web/routers/search.py 的 get_favorite_files()（733-747 平台分支、762-786
列檔迴圈）與 _filter_files_sync()（880-885 NFO 快取）搬出的純函式，供 web 層
與 core/auto_organize.py 共用——core 不可 import web，方向只能是「web 呼叫
core」（BE-LINT-01）。兩個既有呼叫點都改呼叫這裡，回應形狀與行為零改動。
"""
from pathlib import Path

from core.path_utils import expand_env_vars, get_environment
from core.video_extensions import ZERO_SIZE_EXTENSIONS, get_video_extensions


def resolve_favorite_folder(config: dict) -> str:
    """算出最愛資料夾的實際路徑（純計算，對應原 733-747）。"""
    original_folder = config.get('search', {}).get('favorite_folder', '').strip()
    if not original_folder:
        if get_environment() == 'wsl':
            return expand_env_vars('%USERPROFILE%\\Downloads')
        return str(Path.home() / "Downloads")
    return expand_env_vars(original_folder)


def list_favorite_video_files(folder: str, config: dict) -> list:
    """列出資料夾第一層符合副檔名白名單與 min_size_mb 的檔案路徑（對應原 762-786）。

    PermissionError 原樣往外拋，不在此吞掉——呼叫端（get_favorite_files()）
    要拿它組出既有的「無權限讀取資料夾」錯誤回應，吞掉會讓那個錯誤訊息消失。
    """
    folder_path = Path(folder)
    video_exts = get_video_extensions(config)
    min_size_mb = config.get("gallery", {}).get("min_size_mb", 0)
    min_size_bytes = min_size_mb * 1024 * 1024

    files = []
    for f in folder_path.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in video_exts:
            continue
        suffix = f.suffix.lower()
        if min_size_bytes > 0 and suffix not in ZERO_SIZE_EXTENSIONS and f.stat().st_size < min_size_bytes:
            continue
        files.append(str(f))
    return files


def detect_nfo(paths: list) -> dict:
    """對每個路徑判斷旁邊有沒有同 stem 的 .nfo（對應原 880-885 nfo_stem_cache）。

    paths 是呼叫端已經正規化好的路徑字串；回傳 dict 用同一個字串當 key，
    呼叫端逐一 `nfo_map[path]` 取值。
    """
    nfo_stem_cache = {}
    result = {}
    for path_str in paths:
        p = Path(path_str)
        parent = p.parent
        if parent not in nfo_stem_cache:
            try:
                nfo_stem_cache[parent] = {
                    s.stem.lower()
                    for s in parent.iterdir()
                    if s.suffix.lower() == ".nfo" and s.is_file()
                }
            except (OSError, PermissionError):
                nfo_stem_cache[parent] = set()
        result[path_str] = p.stem.lower() in nfo_stem_cache[parent]
    return result
