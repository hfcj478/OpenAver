"""pre-merge SA-pre-9 P2：掃描頁「補完 NFO 欄位」不得寫回唯讀來源資料夾。

使用者流程：使用者有一個 MDCX／Jellyfin 整理過的唯讀來源（每部片旁邊都有 `.nfo`）
→ 唯讀入庫後某些欄位不齊 → 在掃描頁按「補完 NFO 欄位」→ 過去 OpenAver 會把
**來源資料夾**那份 `.nfo` 整份重新序列化寫回去（`update_videos_generator` 走的是
`get_nfo_path_from_video` ＝ 影片路徑 `.with_suffix('.nfo')`）→ 使用者叫它別碰的
資料夾被改了，原本手工整理的內容回不來。

唯讀列的 `nfo_mtime` 指的是**輸出夾**那份的 mtime、恆 > 0，所以不主動濾掉就一定會
入選 `check_cache_needs_update` —— 這是 spec-143 不變式（唯讀 ＝ 一般掃描 ＋ 產物落
輸出夾）在盤點時漏掉的第五格。

本檔鎖的是 `_build_nfo_update_cache`：`/api/gallery/update-check`（顯示數字）與
`/api/gallery/update`（真的寫檔）**共用同一個 helper**，兩邊各抄一份判定必然漂移，
而漂移的形狀是「按鈕說要更新 N 部、實際只更新 M 部」。
"""
from core.database import Video
from core.nfo_updater import check_cache_needs_update
from core.path_utils import to_file_uri
from web.routers.scanner import _build_nfo_update_cache

RO_DIR = "/srv/media/readonly-lib"
RW_DIR = "/srv/media/my-lib"


def _config(sources):
    return {"gallery": {"directories": sources, "path_mappings": {}}}


def _video(fs_path, number="ABC-123"):
    """一列「一定會入選」的影片：nfo_mtime > 0 ＋ 有番號 ＋ 欄位不齊（無 actor/genre）。

    path 一律用 to_file_uri() 建，**不可手寫 `file:///` 字面**——POSIX 絕對路徑在本專案
    是四斜線形式（`file:////srv/...`），手寫三斜線會讓前綴比對永遠不命中、測試假綠。
    """
    return Video(
        path=to_file_uri(fs_path, {}),  # db-ns-ok: 測試資料建構，非 DB-key 寫入路徑
        number=number,
        title="t",
        nfo_mtime=1234.0,
    )


class TestNfoUpdateSkipsReadonlySources:
    def test_readonly_row_excluded_writable_row_kept(self):
        cache, skipped, _ = _build_nfo_update_cache(
            [_video(f"{RO_DIR}/A/A.mp4"), _video(f"{RW_DIR}/B/B.mp4")],
            _config([
                {"path": RO_DIR, "readonly": True, "output_path": "/out"},
                {"path": RW_DIR, "readonly": False},
            ]),
        )

        assert skipped == 1
        assert list(cache) == [to_file_uri(f"{RW_DIR}/B/B.mp4", {})]  # db-ns-ok: 斷言期望值

    def test_readonly_row_really_would_have_been_written(self):
        """反向鎖接到**真正的傷害面**：`check_cache_needs_update` 回的 `paths`。

        那份清單正是交給 `update_videos_generator`（＝真的去寫來源 sidecar NFO）的輸入。
        只斷言「這列會進 cache」是在重述上面那支測試——它在兩顆 mutation 下都不會紅
        （delta review 實測）。改成走完下一層，這支才擋得住一類 t1 擋不到的迴歸：
        有人在 helper 裡加了別的過濾、讓某些列悄悄不進 cache。
        """
        row = _video(f"{RO_DIR}/A/A.mp4")
        writable_cfg = _config([{"path": RO_DIR, "readonly": False}])
        readonly_cfg = _config([{"path": RO_DIR, "readonly": True, "output_path": "/out"}])

        cache_wr, skipped_wr, _ = _build_nfo_update_cache([row], writable_cfg)
        cache_ro, skipped_ro, _ = _build_nfo_update_cache([row], readonly_cfg)

        # 可寫時：這列一路走到「要被寫檔的清單」裡
        assert skipped_wr == 0
        assert row.path in check_cache_needs_update(cache_wr)["paths"]

        # 唯讀時：同一列在同一條路上消失
        assert skipped_ro == 1
        assert row.path not in check_cache_needs_update(cache_ro)["paths"]

    def test_writable_source_nested_under_readonly_is_kept(self):
        """巢狀覆寫語意與 is_path_readonly 一致：最長匹配前綴決定歸屬。

        使用者把整個 NAS 掛成唯讀來源，底下某個子資料夾單獨設成可寫 → 那個子資料夾
        裡的片**不是**唯讀，補完 NFO 要照常寫。
        """
        nested = f"{RO_DIR}/writable-sub"

        cache, skipped, _ = _build_nfo_update_cache(
            [_video(f"{nested}/C/C.mp4")],
            _config([
                {"path": RO_DIR, "readonly": True, "output_path": "/out"},
                {"path": nested, "readonly": False},
            ]),
        )

        assert skipped == 0
        assert len(cache) == 1

    def test_no_readonly_sources_configured_skips_nothing(self):
        cache, skipped, _ = _build_nfo_update_cache(
            [_video(f"{RW_DIR}/B/B.mp4")],
            _config([{"path": RW_DIR, "readonly": False}]),
        )

        assert skipped == 0
        assert len(cache) == 1

    def test_cache_shape_unchanged_for_kept_rows(self):
        """濾掉唯讀不得改變留下來那些列的形狀（check_cache_needs_update 的輸入契約）。"""
        cache, _, _ = _build_nfo_update_cache(
            [_video(f"{RW_DIR}/B/B.mp4")],
            _config([{"path": RW_DIR, "readonly": False}]),
        )

        entry = next(iter(cache.values()))
        assert entry["nfo_mtime"] == 1234.0
        assert set(entry["info"]) == {
            "title", "date", "actor", "genre", "maker",
            "num", "director", "duration", "series", "label",
        }
        assert entry["info"]["num"] == "ABC-123"
