"""enrich_contract.py — enrich 記帳合約的中性原子（無 side-effect、無網路、無寫檔）。

依賴僅 `core.database` / `core.path_utils` / `os` / `dataclasses`。
**不 import** `core.enricher` / `core.readonly_producer`（避免循環依賴；本模組是被它們共用的底層）。

存在理由（feature/105）：enrich「寫完後記帳 has_servable_cover」的判斷原本被手抄多份，
enricher 那份含磁碟複驗（正確），唯讀那份漏了（Bug 1 破圖）。把單一原子收斂於此，
三呼叫點物理共用同一份磁碟真相，消除鏡射漂移。
"""

import os
from dataclasses import dataclass
from typing import List, Optional

from core.path_utils import uri_to_local_fs_path


@dataclass
class EnrichResult:
    success: bool
    nfo_written: bool
    cover_written: bool
    extrafanart_written: int
    fields_filled: List[str]
    source_used: str
    error: Optional[str]
    reason: Optional[str] = None


def cover_uri_is_servable(cover_uri, path_mappings) -> bool:
    """封面 URI 是否「前端 /thumb 真的服務得到」的最小磁碟真相原子。

    `bool(cover_uri)`（DB 有記 cover_path）**且** 該封面實體檔在磁碟上實際存在
    （uri_to_local_fs_path 反解後 os.path.exists）。cover_uri 為空 → 短路 False，
    不呼叫 os.path.exists。
    """
    return bool(cover_uri) and os.path.exists(uri_to_local_fs_path(cover_uri, path_mappings))


def compute_has_servable_cover(repo, path_uri, path_mappings) -> bool:
    """寫完 + commit 後重讀 DB 最終 cover_path，再確認實體封面檔是否服務得到。

    reason=hit 必須是「前端 /thumb 真的服務得到」。/thumb（scanner.py get_thumb）
    有兩道 gate，兩道都過才服務得到，reason=hit 必須同時鏡射：
      gate 1（scanner.py:1276-1277）：DB cover_path 非空，否則 404。
      gate 2（scanner.py:1290/1300/1332-1333）：cache miss 或 disabled 時要讀
        實體封面檔（uri_to_local_fs_path 反解後 generate / fallback FileResponse），
        檔不在 → 404。（cache hit 於 :1263 直接 serve WebP 不碰實體檔，見下方 false-negative）
    故不能只查 DB cover_path 非空（只鏡射 gate 1，Codex PR #98 P2）：DB 有記
    cover_path、但該實體封面檔已被刪/移／path_mapping 失效解不到時，/thumb 於
    cache miss/disabled 會 404 → 飛入破圖，卻誤計 hit。
    亦不能用磁碟 sidecar 真相（Path(fs_path).with_suffix('.jpg')）判：磁碟有 .jpg
    但 DB cover_path 空（散落 sidecar 未入 DB／db·nfo-sourced 命中跳過 :514
    _db_upsert）會漏 gate 1（Codex P1，v0.11.9）。故重讀 DB 最終 cover_path，
    並用 /thumb 同一組解析（uri_to_local_fs_path + 同 path_mappings）確認實體檔存在。
    此重讀應在所有寫檔 + _db_upsert + nfo_mtime UPDATE 之後（同步、已 commit），
    故看到的是最終 DB 狀態。
    已知並接受的 false-negative（安全方向）：cache hit（stale WebP 已快取）但實體
    封面檔已刪時，/thumb 仍能從快取 serve（:1263），此處卻判 no_cover。代價是「服務
    得到的封面不飛入」（不破圖）；反向 false-positive（判 hit 卻 404 破圖）代價更高，
    故偏保守。

    Args:
        repo: VideoRepository（呼叫端建構、已完成寫入/upsert）。
        path_uri: DB row 的 key（canonical file:/// URI），必須與 upsert 寫入時同一 key。
        path_mappings: WSL 反解用；與 /thumb 同一組解析。
    """
    row = repo.get_by_path(path_uri)
    return cover_uri_is_servable(row.cover_path if row else "", path_mappings)
