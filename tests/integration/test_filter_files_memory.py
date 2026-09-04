"""tests/integration/test_filter_files_memory.py — filter-files endpoint 記憶回填測試（TASK-144-T6）。

覆蓋 DoD 1-4 與 mutation 點 M1-M4。
"""
from pathlib import Path

from core.database import organize_failures
from core.database.connection import init_db
from core.scrapers.utils import extract_number as real_extract_number


class TestFilterFilesMemory:
    """filter-files endpoint 失敗記憶回填測試"""

    def _make_mp4(self, directory: Path, name: str) -> Path:
        p = directory / name
        p.write_bytes(b"fake video content for testing")
        return p

    def test_all_files_have_skip_reason_and_duplicate_target_keys(self, client, tmp_path, monkeypatch):
        """D1: POST /api/search/filter-files 回的 files 每一筆恆含 skip_reason 與 duplicate_target 兩個 key；
        記憶全空時兩者皆為 ''。"""
        db_path = tmp_path / "test_filter_files_memory.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

        mp4 = self._make_mp4(tmp_path, "TEST-001.mp4")
        resp = client.post("/api/search/filter-files", json={"paths": [str(mp4)]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["files"]) == 1
        file_entry = data["files"][0]
        assert set(file_entry.keys()) == {"path", "has_nfo", "skip_reason", "duplicate_target"}
        assert file_entry["skip_reason"] == ""
        assert file_entry["duplicate_target"] == ""
        assert file_entry["path"] == str(mp4)
        assert file_entry["has_nfo"] is False

    def test_not_found_skip_reason_set_when_memory_hit(self, client, tmp_path, monkeypatch):
        """D2: organize_failures 有 not_found 記憶 → filter-files 回 skip_reason == 'not_found'。"""
        db_path = tmp_path / "test_filter_files_memory.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

        organize_failures.record_failure("not_found", "CAWD-500", "CAWD-500")

        mp4 = self._make_mp4(tmp_path, "CAWD-500.mp4")
        resp = client.post("/api/search/filter-files", json={"paths": [str(mp4)]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["files"]) == 1
        file_entry = data["files"][0]
        assert file_entry["skip_reason"] == "not_found"
        assert file_entry["duplicate_target"] == ""

    def test_duplicate_skip_reason_and_target_set_when_memory_hit(self, client, tmp_path, monkeypatch):
        """D3: organize_failures 有 duplicate 記憶且帶 path_mappings → filter-files 回 skip_reason == 'duplicate' 且 duplicate_target 帶值。"""
        db_path = tmp_path / "test_filter_files_memory.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

        test_mappings = {str(tmp_path): "file:///mapped_media"}
        monkeypatch.setattr("core.config.load_config", lambda: {
            "scraper": {"video_extensions": [".mp4"]},
            "gallery": {"min_size_mb": 0, "path_mappings": test_mappings},
        })

        mp4 = self._make_mp4(tmp_path, "ABC-123.mp4")
        dup_key = organize_failures.duplicate_key(str(mp4), test_mappings)
        organize_failures.record_failure(
            "duplicate", dup_key, "ABC-123", duplicate_target="ABC-123 [4K].mp4"
        )

        resp = client.post("/api/search/filter-files", json={"paths": [str(mp4)]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["files"]) == 1
        file_entry = data["files"][0]
        assert file_entry["skip_reason"] == "duplicate"
        assert file_entry["duplicate_target"] == "ABC-123 [4K].mp4"

    def test_unparseable_filename_skips_memory_lookup_without_crashing(self, client, tmp_path, monkeypatch):
        """D11: 檔名解不出番號時不查 not_found 記憶，整批不因此變成 500。

        `extract_number()` 解不出來時回的是 **None**，不是空字串——所以 `if number:` 這道閘
        一旦被拿掉，`number.upper()` 會拋 `AttributeError`，而 `_filter_files_sync()` 沒有包
        try/except ⇒ **整個 /api/search/filter-files 變成 500**，不是只跳過那一個檔。
        使用者流程：你把一個資料夾整包拖進搜尋頁，裡面夾了一支 `trailer.mp4` 之類解不出番號
        的檔（拖整夾時非常常見）→ 整份清單load 不出來，畫面上什麼都沒有。
        """
        db_path = tmp_path / "test_filter_files_memory.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

        assert real_extract_number("trailer.mp4") is None, "前提變了：extract_number 不再回 None"

        no_number = self._make_mp4(tmp_path, "trailer.mp4")
        with_number = self._make_mp4(tmp_path, "CAWD-500.mp4")

        resp = client.post(
            "/api/search/filter-files",
            json={"paths": [str(no_number), str(with_number)]},
        )
        assert resp.status_code == 200, "解不出番號的檔把整批打成 500"
        data = resp.json()
        assert data["success"] is True
        by_path = {f["path"]: f for f in data["files"]}
        assert by_path[str(no_number)]["skip_reason"] == ""
        assert by_path[str(no_number)]["duplicate_target"] == ""
        # 同一批裡有番號的那個仍要正常走完記憶查詢
        assert by_path[str(with_number)]["skip_reason"] == ""

    def test_number_extracted_from_basename_not_full_path(self, client, tmp_path, monkeypatch):
        """D4: extract_number 來源為 basename，父目錄番號不干擾。"""
        db_path = tmp_path / "test_filter_files_memory.db"
        init_db(db_path)
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

        sub_dir = tmp_path / "ABP-100"
        sub_dir.mkdir()
        mp4 = self._make_mp4(sub_dir, "CAWD-500.mp4")

        # 真正的 oracle：extract_number **收到的參數**必須是 basename。
        # 不可改用「假的 extract_number 對含分隔符的字串回父目錄番號」——那是把斷言建在
        # 自己編的行為上：真的 extract_number 在 POSIX 路徑上對整條路徑與對 basename 回同一個值
        # （`/tmp/x/ABP-100/CAWD-500.mp4` → `CAWD-500`），所以在 Linux 測試機上**回傳值分不出**
        # M2 有沒有被引入，唯一分得出來的是「傳進去的是什麼」。這裡委派真函式、只記錄參數。
        seen_args = []

        def recording_extract(name_or_path):
            seen_args.append(str(name_or_path))
            return real_extract_number(name_or_path)

        monkeypatch.setattr("core.scrapers.utils.extract_number", recording_extract)

        # 情況 1: 記憶裡只有 ABP-100 → filter-files 回 skip_reason == ''
        organize_failures.record_failure("not_found", "ABP-100", "ABP-100")
        resp = client.post("/api/search/filter-files", json={"paths": [str(mp4)]})
        assert resp.status_code == 200
        data = resp.json()
        assert data["files"][0]["skip_reason"] == ""

        # 情況 2: 記憶裡有 CAWD-500 → filter-files 回 skip_reason == 'not_found'
        organize_failures.record_failure("not_found", "CAWD-500", "CAWD-500")
        resp2 = client.post("/api/search/filter-files", json={"paths": [str(mp4)]})
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["files"][0]["skip_reason"] == "not_found"

        # M2 的正向鎖：兩次請求各呼叫一次，收到的都必須是純檔名。
        assert seen_args, "extract_number 完全沒被呼叫——記憶查詢那一段根本沒跑到"
        assert seen_args == ["CAWD-500.mp4", "CAWD-500.mp4"], (
            f"extract_number 收到的不是 basename：{seen_args!r}。"
            "傳整條路徑會讓父目錄名（MDCX／Jellyfin 的每片一夾佈局）被誤當番號。"
        )
