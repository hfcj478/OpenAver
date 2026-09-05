"""
test_filter_files_has_nfo.py - filter-files endpoint has_nfo 欄位測試

後端 TDD-lite：5 個邊界 case
"""
import pytest
import stat
from pathlib import Path
from core.database.connection import init_db


@pytest.fixture(autouse=True)
def _t6_isolated_failure_db(tmp_path, monkeypatch):
    """TASK-144-T6：這支檔案裡的測試現在會間接碰到 organize_failures 這張表。

    `POST /api/search/filter-files` 會查失敗記憶、`scrape_single()` 成功時會清失敗記憶，
    兩者都開 sqlite 連線——而這些測試原本完全不碰 DB，於是被 repo-write 守衛（G1，
    `tests/conftest.py:250`）擋成 `RepoWriteGuardViolation`（繼承 `BaseException`，
    產品碼的 `except Exception` 攔不到，整個請求變 500）。

    **這不是放寬守衛**：守衛擋的是「寫進真實 output/openaver.db」，把預設 db_path 指到
    tmp 正是它訊息裡列的四種修法第一種。形狀照 `tests/unit/test_auto_organize.py::isolated_db`
    的既有慣例（T3 建立）。
    """
    db_path = tmp_path / "t6_organize_failures.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
    return db_path



class TestFilterFilesHasNfo:
    """filter-files endpoint has_nfo 欄位邊界測試"""

    def _make_mp4(self, tmp_path: Path, name: str) -> Path:
        """建立一個大小足夠的假 mp4 檔（>= 1 bytes，設定 min_size_mb=0 時通過）"""
        p = tmp_path / name
        p.write_bytes(b"fake video content")
        return p

    def _make_nfo(self, tmp_path: Path, stem: str, suffix: str = ".nfo") -> Path:
        """建立 sidecar NFO 檔"""
        p = tmp_path / f"{stem}{suffix}"
        p.write_text("<?xml version='1.0'?><movie/>", encoding="utf-8")
        return p

    def test_basic_has_nfo_and_not(self, client, tmp_path):
        """Case 1: 兩個 mp4，一個有同名 nfo → has_nfo 正確"""
        mp4_with = self._make_mp4(tmp_path, "ABC-001.mp4")
        mp4_without = self._make_mp4(tmp_path, "ABC-002.mp4")
        self._make_nfo(tmp_path, "ABC-001")

        resp = client.post("/api/search/filter-files", json={
            "paths": [str(mp4_with), str(mp4_without)]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        files = {f["path"]: f["has_nfo"] for f in data["files"]}
        assert files[str(mp4_with)] is True
        assert files[str(mp4_without)] is False

    def test_uppercase_nfo_extension(self, client, tmp_path):
        """Case 2: sidecar 副檔名大寫 .NFO → has_nfo === True（Linux ext4 大小寫敏感，必須用 suffix.lower()）"""
        mp4 = self._make_mp4(tmp_path, "FOO.mp4")
        self._make_nfo(tmp_path, "FOO", suffix=".NFO")

        resp = client.post("/api/search/filter-files", json={
            "paths": [str(mp4)]
        })
        assert resp.status_code == 200
        data = resp.json()
        file_entry = data["files"][0]
        assert file_entry["has_nfo"] is True

    def test_stem_case_insensitive(self, client, tmp_path):
        """Case 3: mp4 stem 小寫 'foo'，sidecar 'FOO.nfo' → case-insensitive → has_nfo === True"""
        mp4 = self._make_mp4(tmp_path, "foo.mp4")
        self._make_nfo(tmp_path, "FOO", suffix=".nfo")

        resp = client.post("/api/search/filter-files", json={
            "paths": [str(mp4)]
        })
        assert resp.status_code == 200
        data = resp.json()
        file_entry = data["files"][0]
        assert file_entry["has_nfo"] is True

    def test_empty_paths(self, client):
        """Case 4: paths = [] → files = []，不 crash，total_rejected = 0"""
        resp = client.post("/api/search/filter-files", json={"paths": []})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["files"] == []
        assert data["total_rejected"] == 0

    def test_nfo_directory_not_counted_as_nfo(self, client, tmp_path):
        """Case 6: 同 stem 的 .nfo 是目錄（非檔）→ has_nfo === False（is_file() guard）"""
        mp4 = self._make_mp4(tmp_path, "foo.mp4")
        nfo_dir = tmp_path / "foo.nfo"
        nfo_dir.mkdir()  # 建資料夾，不是檔案

        resp = client.post("/api/search/filter-files", json={
            "paths": [str(mp4)]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        file_entry = data["files"][0]
        assert file_entry["has_nfo"] is False

    def test_permission_error_on_iterdir(self, client, tmp_path, monkeypatch):
        """Case 5: 父目錄 iterdir() 引發 PermissionError → has_nfo === False，不回 500"""
        mp4 = self._make_mp4(tmp_path, "PERM.mp4")

        # Monkeypatch Path.iterdir to raise PermissionError for this directory
        original_iterdir = Path.iterdir

        def mock_iterdir(self_path):
            if self_path == tmp_path:
                raise PermissionError("Permission denied")
            return original_iterdir(self_path)

        monkeypatch.setattr(Path, "iterdir", mock_iterdir)

        resp = client.post("/api/search/filter-files", json={
            "paths": [str(mp4)]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        file_entry = data["files"][0]
        assert file_entry["has_nfo"] is False
