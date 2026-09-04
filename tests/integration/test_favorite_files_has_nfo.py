"""
test_favorite_files_has_nfo.py - loadFavorite 流程端對端：has_nfo 正確傳遞

端對端驗證：filter-files 回傳 has_nfo 欄位，GET /favorite-files contract 不動。
"""
import pytest
from pathlib import Path
from unittest.mock import patch
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



class TestFavoriteFilesHasNfoE2E:
    """端對端：favorite-files → filter-files 流程，has_nfo 欄位正確傳遞"""

    def _make_mp4(self, tmp_path: Path, name: str) -> str:
        """建立假 mp4 檔，回傳字串路徑"""
        p = tmp_path / name
        p.write_bytes(b"fake video content")
        return str(p)

    def _make_nfo(self, tmp_path: Path, stem: str) -> Path:
        p = tmp_path / f"{stem}.nfo"
        p.write_text("<?xml version='1.0'?><movie/>", encoding="utf-8")
        return p

    def test_filter_files_has_nfo_propagated(self, client, tmp_path):
        """filter-files 回傳的 files 元素從 str 變成 {path, has_nfo}，前端能正確解析"""
        # 建立 2 個 mp4，1 個有 nfo
        mp4_organized = self._make_mp4(tmp_path, "ORGANIZED-001.mp4")
        mp4_new = self._make_mp4(tmp_path, "NEW-002.mp4")
        self._make_nfo(tmp_path, "ORGANIZED-001")

        resp = client.post("/api/search/filter-files", json={
            "paths": [mp4_organized, mp4_new]
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # Response element 必須是 dict，不是 str
        assert isinstance(data["files"], list)
        assert len(data["files"]) == 2

        files_by_path = {f["path"]: f for f in data["files"]}

        # 已整理（有 nfo）
        assert files_by_path[mp4_organized]["has_nfo"] is True
        # 新檔（無 nfo）
        assert files_by_path[mp4_new]["has_nfo"] is False

    def test_get_favorite_files_contract_unchanged(self, client, tmp_path):
        """GET /favorite-files 仍回傳 files: list[str]（contract 不動）"""
        # Mock favorite folder config
        mp4_path = self._make_mp4(tmp_path, "TEST-001.mp4")

        with patch("core.config.load_config") as mock_cfg:
            mock_cfg.return_value = {
                "search": {
                    "favorite_folder": str(tmp_path),
                },
                "gallery": {
                    "min_size_mb": 0,
                    "scan_subdirectories": False,
                    "video_extensions": [".mp4"],
                },
            }
            resp = client.get("/api/search/favorite-files")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True

        # files 必須是 list[str]，不是 list[dict]
        files = data.get("files", [])
        assert isinstance(files, list)
        for f in files:
            assert isinstance(f, str), f"favorite-files 應回傳 str，但得到 {type(f)}: {f}"
