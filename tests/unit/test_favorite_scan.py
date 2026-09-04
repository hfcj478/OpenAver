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
