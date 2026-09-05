"""tests/integration/test_scrape_single_clears_memory.py — scrape-single 成功時清除失敗記憶測試（TASK-144-T6）。

覆蓋 DoD 8-9 與 mutation 點 M11。
"""
from contextlib import closing
from pathlib import Path

from core.database import organize_failures
from core.database.connection import init_db, get_connection


class TestScrapeSingleClearsMemory:
    """scrape_single 成功清除失敗記憶及例外保護測試"""

    def test_successful_organize_clears_not_found_memory(self, client, tmp_path, monkeypatch, mocker):
        """D8: 某番號被記成 not_found 後，手動 POST /api/scrape-single 整理成功 → organize_failures 裡那一列當場消失。"""
        db_path = tmp_path / "test_scrape_clears.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

        organize_failures.record_failure("not_found", "CAWD-500", "CAWD-500")
        assert organize_failures.should_skip("not_found", "CAWD-500") is True

        mocker.patch(
            "web.routers.scraper.organize_file",
            return_value={"success": True, "new_filename": "CAWD-500.mp4"},
        )
        mocker.patch("web.routers.scraper.try_inflow_upsert", return_value="not_linked")

        resp = client.post(
            "/api/scrape-single",
            json={
                "file_path": "/dummy/CAWD-500.mp4",
                "number": "CAWD-500",
                "metadata": {"number": "CAWD-500", "title": "Test Movie"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        with closing(get_connection(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM organize_failures WHERE reason='not_found' AND key='CAWD-500'"
            )
            count = cursor.fetchone()[0]
        assert count == 0

    def test_duplicate_early_return_does_not_clear_memory(self, client, tmp_path, monkeypatch, mocker):
        """D8 後半句: duplicate 早退的那條路徑不得清除記憶。"""
        db_path = tmp_path / "test_scrape_clears.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

        organize_failures.record_failure("not_found", "CAWD-500", "CAWD-500")

        mocker.patch(
            "web.routers.scraper.organize_file",
            return_value={"duplicate": True, "duplicate_target": "existing.mp4"},
        )

        resp = client.post(
            "/api/scrape-single",
            json={
                "file_path": "/dummy/CAWD-500.mp4",
                "number": "CAWD-500",
                "metadata": {"number": "CAWD-500", "title": "Test Movie"},
            },
        )
        assert resp.status_code == 200
        assert resp.json().get("duplicate") is True

        with closing(get_connection(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM organize_failures WHERE reason='not_found' AND key='CAWD-500'"
            )
            count = cursor.fetchone()[0]
        assert count == 1

    def test_organize_failure_does_not_clear_memory(self, client, tmp_path, monkeypatch, mocker):
        """D12: organize 失敗（非 duplicate）時**不得**清除記憶——spec §F3 是「成功入庫才清」。

        這條守的是 `scraper.py` 的 `if result.get('success'):`。拿掉它之後：
        呼叫端**自己帶 metadata** 進來（`scraper.py:220-222` 的分支，根本不走 `search_jav`）、
        `organize_file` 因為磁碟滿了回 `{"success": False}` → 記憶照樣被清掉。
        使用者流程：那部片其實**還是沒被整理進片庫**，但退避記錄不見了 ⇒ 下一輪自動整理
        又去把它重搜一次八個來源，24 小時退避形同沒有——正是這個功能存在的理由被抵銷。
        （T6 review：grok 用 probe 實測復現，推翻了「走到那行代表已經找到、清了也沒差」的原判。）
        """
        db_path = tmp_path / "test_scrape_clears.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

        organize_failures.record_failure("not_found", "CAWD-500", "CAWD-500")

        mocker.patch(
            "web.routers.scraper.organize_file",
            return_value={"success": False, "error": "磁碟空間不足"},
        )

        resp = client.post(
            "/api/scrape-single",
            json={
                "file_path": "/dummy/CAWD-500.mp4",
                "number": "CAWD-500",
                "metadata": {"number": "CAWD-500", "title": "Test Movie"},
            },
        )
        assert resp.status_code == 200
        assert resp.json().get("success") is False

        with closing(get_connection(db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM organize_failures WHERE reason='not_found' AND key='CAWD-500'"
            )
            count = cursor.fetchone()[0]
        assert count == 1, "整理失敗卻把退避記錄清掉了——下一輪會立刻再重搜八個來源"

    def test_clear_on_success_exception_does_not_break_response(self, client, tmp_path, monkeypatch, mocker):
        """D9: clear_on_success() 拋例外時，scrape-single 仍回原本的成功 JSON（HTTP 200、success: True），不變成 500。"""
        db_path = tmp_path / "test_scrape_clears.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

        mocker.patch(
            "web.routers.scraper.organize_file",
            return_value={"success": True, "new_filename": "CAWD-500.mp4"},
        )
        mocker.patch("web.routers.scraper.try_inflow_upsert", return_value="not_linked")

        def exploding_clear(number, *args, **kwargs):
            raise RuntimeError("Database connection suddenly dropped")

        monkeypatch.setattr("core.database.organize_failures.clear_on_success", exploding_clear)

        resp = client.post(
            "/api/scrape-single",
            json={
                "file_path": "/dummy/CAWD-500.mp4",
                "number": "CAWD-500",
                "metadata": {"number": "CAWD-500", "title": "Test Movie"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
