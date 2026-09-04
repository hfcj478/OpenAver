"""core/auto_organize.py — 自動整理一輪的純同步本體（spec-144 T3 / plan CD-144-4..7）。

run_one_round() 全同步：列檔 → .nfo／記憶／番號過濾 → smart_search → 翻譯判斷
→ organize_file → 四類統計。不含排程、不含鎖——中止與宣告只透過 should_abort /
on_file_start 兩個 Callable 參數，本模組對它們的實作一無所知（T4a 的事）。
core 層，禁止 import 任何 web.* 符號（BE-LINT-01）。
"""
import asyncio
import os
from typing import Callable, Optional

from core.database import organize_failures
from core.favorite_scan import detect_nfo, list_favorite_video_files, resolve_favorite_folder
from core.organizer import extract_chinese_title, organize_file
from core.path_utils import coerce_to_file_uri
from core.readonly_source import is_path_readonly, readonly_source_prefixes, writable_source_prefixes
from core.scraper import smart_search
from core.scrapers.utils import extract_number, has_japanese
from core.translate_service import create_translate_service
from core.wishlist_reconcile import reconcile_wishlist


def run_one_round(
    config: dict,
    should_abort: Optional[Callable[[], bool]] = None,
    on_file_start: Optional[Callable[[str], None]] = None,
) -> dict:
    """跑一輪自動整理，回傳統計 dict（schema 見 plan T3 步驟 8，唯一定義）。"""
    added = []
    cover_missing = []
    failed = []
    skipped_has_nfo = 0
    skipped_memory_hit = 0
    skipped_duplicate = []
    newly_recorded = 0
    aborted_after = None

    gallery_config = config.get('gallery', {})
    path_mappings = gallery_config.get('path_mappings', {})  # 整輪只取一次（DoD-7）

    folder = resolve_favorite_folder(config)

    # 唯讀 guard：對「最愛資料夾」本身判一次，不逐檔判（CD-144-7）
    ro_prefixes = readonly_source_prefixes(gallery_config, path_mappings)
    wr_prefixes = writable_source_prefixes(gallery_config, path_mappings)
    if is_path_readonly(coerce_to_file_uri(folder, path_mappings), ro_prefixes, wr_prefixes):
        return {"readonly": True}

    files = list_favorite_video_files(folder, config)
    nfo_map = detect_nfo(files)

    proxy_url = config.get('search', {}).get('proxy_url', '')
    scraper_config = config.get('scraper', {})
    translate_config = config.get('translate', {})
    translate_enabled = translate_config.get('enabled', False)
    translate_service = create_translate_service(translate_config) if translate_enabled else None

    completed = 0
    for path in files:
        # ① should_abort → ② extract_number → ③ on_file_start，順序不可顛倒（DoD-5）
        if should_abort is not None and should_abort():
            aborted_after = completed
            break

        number = extract_number(path)
        if not number:
            continue  # 無番號跳過，不計數，不呼叫 on_file_start

        if on_file_start is not None:
            on_file_start(number)

        if nfo_map.get(path, False):
            skipped_has_nfo += 1
            completed += 1
            continue

        upper_number = number.upper()
        dup_key = organize_failures.duplicate_key(path, path_mappings)
        if organize_failures.should_skip('not_found', upper_number) or \
                organize_failures.should_skip('duplicate', dup_key):
            skipped_memory_hit += 1  # 記憶命中不算事件（DoD-9）
            completed += 1
            continue

        results = smart_search(number, proxy_url=proxy_url)  # CD-144-4：逐字同手動批次
        if not results:
            organize_failures.record_failure('not_found', upper_number, number)
            newly_recorded += 1
            failed.append(number)
            completed += 1
            continue

        metadata = dict(results[0])  # CD-144-5：原樣，不加不減（不覆蓋 number）

        filename = os.path.basename(path)
        chinese_title = extract_chinese_title(filename, number, metadata.get('actors'))
        if not chinese_title and translate_enabled and has_japanese(metadata.get('title', '')):
            try:
                translated = asyncio.run(translate_service.translate_single(metadata['title']))
            except Exception:
                translated = ""  # 翻譯失敗不擋，原標題入庫，不計 failed（DoD-8）
            if translated:
                metadata['translated_title'] = translated

        organize_result = organize_file(path, metadata, scraper_config)

        if organize_result.get('duplicate'):
            target = organize_result.get('duplicate_target', '')
            organize_failures.record_failure('duplicate', dup_key, number, duplicate_target=target)
            newly_recorded += 1
            skipped_duplicate.append({"number": number, "target": target})
        elif organize_result.get('success'):
            organize_failures.clear_on_success(number)
            if organize_result.get('cover_path'):
                added.append(number)
            else:
                cover_missing.append(number)
        else:
            failed.append(number)

        completed += 1

    wishlist_removed = reconcile_wishlist()  # 迴圈結束（含被中止的情況）跑一次

    return {
        "added": added,
        "cover_missing": cover_missing,
        "failed": failed,
        "skipped": {
            "has_nfo": skipped_has_nfo,
            "memory_hit": skipped_memory_hit,
            "duplicate": skipped_duplicate,
        },
        "newly_recorded": newly_recorded,
        "wishlist_removed": wishlist_removed,
        "aborted_after": aborted_after,
    }
