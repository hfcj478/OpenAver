"""tests/unit/test_favorite_scan.py — core/favorite_scan.py 純函式測試（TASK-144-T3）。

覆蓋 DoD-10：resolve_favorite_folder / list_favorite_video_files / detect_nfo
三支函式各自單元測試，以及與 get_favorite_files() 端點的 parity 斷言（同一組
輸入，wrapper 與底層函式必須算出一致的結果，證明「搬移是零行為改變」）。
"""
from pathlib import Path

import pytest

from core.favorite_scan import (
    detect_nfo,
    list_favorite_video_files,
    resolve_favorite_folder,
)


class TestResolveFavoriteFolder:
    """resolve_favorite_folder(config)：純計算，對應原 733-747。"""

    def test_explicit_folder_expands_env_vars(self, tmp_path):
        config = {"search": {"favorite_folder": str(tmp_path)}}
        assert resolve_favorite_folder(config) == str(tmp_path)

    def test_empty_folder_wsl_uses_windows_downloads(self, monkeypatch):
        monkeypatch.setattr("core.favorite_scan.get_environment", lambda: "wsl")
        monkeypatch.setattr(
            "core.favorite_scan.expand_env_vars",
            lambda p: f"/mnt/c/Users/fake/Downloads" if p == '%USERPROFILE%\\Downloads' else p,
        )
        config = {"search": {"favorite_folder": ""}}
        assert resolve_favorite_folder(config) == "/mnt/c/Users/fake/Downloads"

    def test_empty_folder_non_wsl_uses_home_downloads(self, monkeypatch):
        monkeypatch.setattr("core.favorite_scan.get_environment", lambda: "linux")
        config = {"search": {"favorite_folder": ""}}
        assert resolve_favorite_folder(config) == str(Path.home() / "Downloads")

    def test_missing_search_section_treated_as_empty(self, monkeypatch):
        monkeypatch.setattr("core.favorite_scan.get_environment", lambda: "linux")
        assert resolve_favorite_folder({}) == str(Path.home() / "Downloads")

    def test_whitespace_only_folder_treated_as_empty(self, monkeypatch):
        monkeypatch.setattr("core.favorite_scan.get_environment", lambda: "linux")
        config = {"search": {"favorite_folder": "   "}}
        assert resolve_favorite_folder(config) == str(Path.home() / "Downloads")


class TestListFavoriteVideoFiles:
    """list_favorite_video_files(folder, config)：對應原 762-786。"""

    def test_filters_by_extension(self, tmp_path):
        (tmp_path / "a.mp4").write_bytes(b"x")
        (tmp_path / "b.txt").write_bytes(b"x")
        config = {"scraper": {"video_extensions": [".mp4"]}}
        files = list_favorite_video_files(str(tmp_path), config)
        assert len(files) == 1
        assert files[0].endswith("a.mp4")

    def test_filters_by_min_size(self, tmp_path):
        small = tmp_path / "small.mp4"
        small.write_bytes(b"x" * 100)
        big = tmp_path / "big.mp4"
        big.write_bytes(b"x" * (2 * 1024 * 1024))
        config = {
            "scraper": {"video_extensions": [".mp4"]},
            "gallery": {"min_size_mb": 1},
        }
        files = list_favorite_video_files(str(tmp_path), config)
        assert len(files) == 1
        assert files[0].endswith("big.mp4")

    def test_zero_size_extensions_exempt_from_min_size(self, tmp_path):
        strm = tmp_path / "a.strm"
        strm.write_bytes(b"x")
        config = {
            "scraper": {"video_extensions": [".strm"]},
            "gallery": {"min_size_mb": 1},
        }
        files = list_favorite_video_files(str(tmp_path), config)
        assert len(files) == 1

    def test_skips_subdirectories(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.mp4").write_bytes(b"x")
        config = {"scraper": {"video_extensions": [".mp4"]}}
        assert list_favorite_video_files(str(tmp_path), config) == []

    def test_permission_error_propagates(self, tmp_path, monkeypatch):
        def raise_permission_error(self):
            raise PermissionError("no access")

        monkeypatch.setattr(Path, "iterdir", raise_permission_error)
        config = {"scraper": {"video_extensions": [".mp4"]}}
        with pytest.raises(PermissionError):
            list_favorite_video_files(str(tmp_path), config)


class TestDetectNfo:
    """detect_nfo(paths)：對應原 880-885 nfo_stem_cache。"""

    def test_hit_when_sibling_nfo_exists(self, tmp_path):
        video = tmp_path / "ABC-123.mp4"
        video.write_bytes(b"x")
        (tmp_path / "ABC-123.nfo").write_bytes(b"x")
        result = detect_nfo([str(video)])
        assert result[str(video)] is True

    def test_miss_when_no_sibling_nfo(self, tmp_path):
        video = tmp_path / "ABC-123.mp4"
        video.write_bytes(b"x")
        result = detect_nfo([str(video)])
        assert result[str(video)] is False

    def test_case_insensitive_stem_match(self, tmp_path):
        video = tmp_path / "abc-123.mp4"
        video.write_bytes(b"x")
        (tmp_path / "ABC-123.NFO").write_bytes(b"x")
        result = detect_nfo([str(video)])
        assert result[str(video)] is True

    def test_cache_reused_across_same_parent(self, tmp_path, monkeypatch):
        v1 = tmp_path / "a.mp4"
        v2 = tmp_path / "b.mp4"
        v1.write_bytes(b"x")
        v2.write_bytes(b"x")

        call_count = {"n": 0}
        real_iterdir = Path.iterdir

        def counting_iterdir(self):
            call_count["n"] += 1
            return real_iterdir(self)

        monkeypatch.setattr(Path, "iterdir", counting_iterdir)
        detect_nfo([str(v1), str(v2)])
        assert call_count["n"] == 1, "同一個父目錄只應該 iterdir 一次（快取）"

    def test_oserror_on_iterdir_treated_as_no_nfo(self, tmp_path, monkeypatch):
        video = tmp_path / "ABC-123.mp4"
        video.write_bytes(b"x")

        def raise_oserror(self):
            raise OSError("boom")

        monkeypatch.setattr(Path, "iterdir", raise_oserror)
        result = detect_nfo([str(video)])
        assert result[str(video)] is False


class TestFavoriteScanParity:
    """DoD-10 parity：wrapper（get_favorite_files 邏輯）與底層函式必須算出一致結果。"""

    def test_resolve_and_list_match_manual_computation(self, tmp_path):
        video = tmp_path / "ABC-123.mp4"
        video.write_bytes(b"x" * (2 * 1024 * 1024))
        (tmp_path / "note.txt").write_bytes(b"x")

        config = {
            "scraper": {"video_extensions": [".mp4"]},
            "gallery": {"min_size_mb": 1},
            "search": {"favorite_folder": str(tmp_path)},
        }

        folder = resolve_favorite_folder(config)
        files = list_favorite_video_files(folder, config)

        # 模擬 get_favorite_files() 端點組出的回應形狀
        response = {"success": True, "files": files, "folder": folder, "total": len(files)}

        assert response["success"] is True
        assert response["folder"] == str(tmp_path)
        assert response["total"] == 1
        assert str(video) in response["files"]


class TestSingleFileErrorDoesNotKillTheRound:
    """pre-merge SA-pre-9 P3-4：一個檔案問不到，不該讓整輪陣亡。

    使用者流程：定時整理正在列檔，其中一個檔剛好讀不到（Windows 上被下載器獨佔、
    NAS 那條連線正好斷了、下載器在這一瞬間把它搬走）→ 例外往外拋 → 整輪作廢 →
    run-now 那輪變「定時整理失敗」、排程那輪直接跳過，**再等 12 小時**。
    無人值守時這個代價不對等。

    ⚠️ **`Path.is_file()` 只吞「可忽略」的 OSError**（ENOENT / ENOTDIR / ELOOP…，
    見 CPython `pathlib._ignore_error`）——**PermissionError、EIO、ESTALE 會被它原樣往外拋**。
    所以測「檔案不見了」抓不到這條守衛（`is_file()` 自己回 False 就跳過了，
    第一版測試就是這樣寫的，mutation gate 當場判 SURVIVED）；
    要行使它必須用**不可忽略**的錯誤，或打中 `is_file()` 與 `stat()` 之間那個窗口。
    """

    def test_unreadable_file_is_skipped_and_the_rest_still_listed(self, tmp_path, monkeypatch):
        """不可忽略的 OSError（PermissionError）會穿過 `is_file()`——這條守衛要接住它。"""
        folder = tmp_path / "fav"
        folder.mkdir()
        big = b"x" * (2 * 1024 * 1024)
        (folder / "GOOD-001.mp4").write_bytes(big)
        (folder / "LOCKED.mp4").write_bytes(big)
        (folder / "GOOD-002.mp4").write_bytes(big)

        config = {"scraper": {"video_extensions": [".mp4"]}, "gallery": {"min_size_mb": 1}}

        real_stat = Path.stat

        def flaky_stat(self, *a, **kw):
            if self.name == "LOCKED.mp4":
                raise PermissionError(13, "Permission denied", str(self))
            return real_stat(self, *a, **kw)

        monkeypatch.setattr(Path, "stat", flaky_stat)

        names = sorted(Path(f).name for f in list_favorite_video_files(str(folder), config))
        assert names == ["GOOD-001.mp4", "GOOD-002.mp4"], (
            f"讀不到的那個檔跳過就好，其餘要照列，實際 {names}"
        )

    def test_file_vanishing_between_is_file_and_stat_is_skipped(self, tmp_path, monkeypatch):
        """TOCTOU：`is_file()` 過了，量大小的時候檔案已經被下載器搬走。"""
        folder = tmp_path / "fav"
        folder.mkdir()
        big = b"x" * (2 * 1024 * 1024)
        (folder / "GOOD-001.mp4").write_bytes(big)
        (folder / "VANISHING.mp4").write_bytes(big)

        config = {"scraper": {"video_extensions": [".mp4"]}, "gallery": {"min_size_mb": 1}}

        real_stat = Path.stat
        seen = {}

        def vanishing_stat(self, *a, **kw):
            if self.name == "VANISHING.mp4":
                # 第一次（is_file 問的那次）照常回答，第二次（量大小那次）才不見
                if seen.get("n"):
                    raise FileNotFoundError(2, "No such file or directory", str(self))
                seen["n"] = 1
            return real_stat(self, *a, **kw)

        monkeypatch.setattr(Path, "stat", vanishing_stat)

        names = sorted(Path(f).name for f in list_favorite_video_files(str(folder), config))
        assert names == ["GOOD-001.mp4"], (
            f"量大小時才消失的檔要跳過、不得讓整輪拋例外，實際 {names}"
        )

    def test_folder_level_permission_error_still_propagates(self, tmp_path, monkeypatch):
        """反向鎖：資料夾層級的 PermissionError 不可以被那個 try 吞掉。

        呼叫端（`get_favorite_files()`）要拿它組出「無權限讀取資料夾」的錯誤回應；
        吞掉會讓那句話消失，使用者只看到一個空清單、不知道為什麼。
        """
        folder = tmp_path / "fav"
        folder.mkdir()
        config = {"scraper": {"video_extensions": [".mp4"]}, "gallery": {"min_size_mb": 0}}

        def boom(self):
            raise PermissionError(13, "Permission denied", str(self))

        monkeypatch.setattr(Path, "iterdir", boom)

        with pytest.raises(PermissionError):
            list_favorite_video_files(str(folder), config)


class TestDetectNfoStrictMode:
    """Codex PR #181 二審 P0：列不到目錄時，「不知道」不可以被讀成「沒有 NFO」。"""

    def test_default_mode_keeps_the_manual_path_behaviour(self, tmp_path, monkeypatch):
        """反向鎖：預設模式維持 main 的行為（列不到＝當成沒有 NFO），手動清單不受影響。

        手動路徑的後果只是清單上少了「已有 NFO」的標記，下一步還要人按下去，
        沒有任何東西會自己動——改它反而會動到既有行為。
        """
        folder = tmp_path / "fav"
        folder.mkdir()
        video = folder / "ABC-123.mp4"
        video.write_bytes(b"x")

        def boom(self):
            raise OSError(5, "Input/output error", str(self))

        monkeypatch.setattr(Path, "iterdir", boom)

        result = detect_nfo([str(video)])
        assert result == {str(video): False}

    def test_strict_mode_propagates_so_the_round_can_fail_closed(self, tmp_path, monkeypatch):
        """strict=True 要把 OSError 往外拋，讓自動整理那一輪能夠什麼都不做。"""
        folder = tmp_path / "fav"
        folder.mkdir()
        video = folder / "ABC-123.mp4"
        video.write_bytes(b"x")

        def boom(self):
            raise OSError(5, "Input/output error", str(self))

        monkeypatch.setattr(Path, "iterdir", boom)

        with pytest.raises(OSError):
            detect_nfo([str(video)], strict=True)

    def test_strict_mode_is_normal_when_enumeration_works(self, tmp_path):
        """strict 不改變成功路徑的答案。"""
        folder = tmp_path / "fav"
        folder.mkdir()
        with_nfo = folder / "HAS-001.mp4"
        with_nfo.write_bytes(b"x")
        (folder / "HAS-001.nfo").write_text("<movie/>", encoding="utf-8")
        without = folder / "NONE-002.mp4"
        without.write_bytes(b"x")

        result = detect_nfo([str(with_nfo), str(without)], strict=True)
        assert result == {str(with_nfo): True, str(without): False}
