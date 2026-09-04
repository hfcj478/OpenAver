"""tests/unit/test_auto_organize.py — core/auto_organize.py run_one_round() 測試（TASK-144-T3）。

覆蓋 DoD 1-9、11 與 mutation 點 M1-M7。TDD-lite：mock smart_search / organize_file /
create_translate_service / reconcile_wishlist，DB 用 tmp db 隔離；唯讀 guard 不 mock
is_path_readonly 的回傳值，用真實唯讀前綴驗（見 DoD-3/4）。
"""
import hashlib
from unittest.mock import AsyncMock

import pytest

from core.auto_organize import run_one_round
from core.database import organize_failures
from core.database.connection import init_db, get_connection
from core.readonly_source import is_path_readonly as real_is_path_readonly


# ---------------------------------------------------------------------------
# 共用 fixture / helper
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """把 organize_failures 用到的預設 db_path 換成 tmp db，避免污染真實 output/openaver.db。"""
    db_path = tmp_path / "test_auto_organize.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)
    return db_path


def make_config(fav_dir, translate_enabled=False, path_mappings=None, directories=None):
    return {
        "search": {"favorite_folder": str(fav_dir)},
        "scraper": {"video_extensions": [".mp4"]},
        "gallery": {
            "min_size_mb": 0,
            "path_mappings": path_mappings or {},
            "directories": directories or [],
        },
        "translate": {"enabled": translate_enabled},
    }


def write_video(fav_dir, name, size=1024):
    p = fav_dir / name
    p.write_bytes(b"x" * size)
    return p


def default_organize_success(cover_path="/cover/x.jpg"):
    return {
        "success": True,
        "original_path": None,
        "new_folder": "/organized/x",
        "new_filename": "x.mp4",
        "cover_path": cover_path,
        "nfo_path": "/organized/x/x.nfo",
        "error": None,
        "used_fallbacks": [],
    }


# ===========================================================================
# DoD-1 / DoD-2：四部片統計 ＋ 回傳 schema 逐欄相符（含 M6）
# ===========================================================================

class TestFourFileRoundStatistics:
    def test_four_files_add_two_skip_nfo_one_skip_duplicate_one(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()

        dup_file = write_video(fav_dir, "DUP-001.mp4")
        dup4k_file = write_video(fav_dir, "DUP-001-4K.mp4")
        nfo_file = write_video(fav_dir, "NFO-001.mp4")
        write_video(fav_dir, "NFO-001.nfo", size=10)
        normal_file = write_video(fav_dir, "NORMAL-001.mp4")

        # BE-TEST-10：基準值必須在操作之前取得
        dup_hash_before = hashlib.sha256(dup_file.read_bytes()).hexdigest()

        config = make_config(fav_dir)

        def fake_smart_search(number, proxy_url=""):
            return [{"number": number, "title": f"title-{number}", "actors": []}]

        def fake_organize_file(file_path, metadata, cfg):
            if file_path == str(dup_file):
                return {"success": False, "duplicate": True, "duplicate_target": "/target/dup.mp4"}
            if file_path == str(dup4k_file):
                return default_organize_success("/cover/dup4k.jpg")
            if file_path == str(normal_file):
                return default_organize_success("/cover/normal.jpg")
            raise AssertionError(f"unexpected organize_file call for {file_path}")

        mocker.patch("core.auto_organize.smart_search", side_effect=fake_smart_search)
        mocker.patch("core.auto_organize.organize_file", side_effect=fake_organize_file)
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config)

        assert len(result["added"]) == 2
        assert set(result["added"]) == {"DUP-001", "NORMAL-001"}
        assert result["skipped"]["has_nfo"] == 1
        assert len(result["skipped"]["duplicate"]) == 1
        assert result["skipped"]["duplicate"][0]["number"] == "DUP-001"

        # ⚠️ 這裡**不**放「撞檔原片逐位元組不變」的雜湊斷言（PR review 抓到的空轉守衛）：
        # 本測試把 `organize_file` 整支 mock 掉了，雜湊在任何實作下都必然相等——
        # 就算有人把 `organize_file` 換成一支會就地改寫原檔的實作，這個斷言照樣綠。
        # 那條保證的**真守衛在 T0**（`tests/unit/test_organizer.py` 的
        # `test_organize_duplicate_detection` 與 `TestOrganizeAtomicReplace`），
        # 那裡跑的是真正的 `organize_file` ＋ 真檔案系統。
        # 本測試的職責是 `run_one_round` 的**編排**（哪些片進哪一桶），不是搬檔語意。
        assert dup_hash_before is not None  # 保留基準值取得的時機（BE-TEST-10 的形狀）


class TestReturnSchema:
    def test_return_schema_has_all_required_keys(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "SCHEMA-001.mp4")

        config = make_config(fav_dir)
        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": "SCHEMA-001", "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=["OWNED-001"])

        result = run_one_round(config)

        assert set(result.keys()) == {
            "added", "cover_missing", "failed", "skipped",
            "newly_recorded", "wishlist_removed", "aborted_after",
        }
        assert set(result["skipped"].keys()) == {"has_nfo", "memory_hit", "duplicate"}
        assert isinstance(result["added"], list)
        assert isinstance(result["cover_missing"], list)
        assert isinstance(result["failed"], list)
        assert isinstance(result["newly_recorded"], int)
        assert result["wishlist_removed"] == ["OWNED-001"]
        assert result["aborted_after"] is None


# ===========================================================================
# DoD-3 / DoD-4：唯讀 guard，真前綴（含 M1）
# ===========================================================================

class TestReadonlyGuard:
    def test_readonly_folder_skips_entire_round(self, tmp_path, isolated_db, mocker):
        ro_root = tmp_path / "ro_src"
        fav_dir = ro_root / "fav"
        fav_dir.mkdir(parents=True)
        write_video(fav_dir, "SHOULD-NOT-LIST.mp4")

        config = make_config(fav_dir, directories=[{"path": str(ro_root), "readonly": True}])

        spy = mocker.patch("core.auto_organize.is_path_readonly", wraps=real_is_path_readonly)
        list_spy = mocker.patch("core.auto_organize.list_favorite_video_files")
        search_spy = mocker.patch("core.auto_organize.smart_search")
        organize_spy = mocker.patch("core.auto_organize.organize_file")
        reconcile_spy = mocker.patch("core.auto_organize.reconcile_wishlist")

        result = run_one_round(config)

        assert result == {"readonly": True}
        list_spy.assert_not_called()
        search_spy.assert_not_called()
        organize_spy.assert_not_called()
        reconcile_spy.assert_not_called()

        # DoD-4：is_path_readonly 收到的第一個參數必須是 file:/// URI，不是裸原生路徑
        spy.assert_called_once()
        first_arg = spy.call_args[0][0]
        assert first_arg.startswith("file:///"), \
            f"is_path_readonly 收到裸路徑 {first_arg!r}，唯讀來源會靜默失去保護"

    def test_writable_folder_not_flagged_readonly(self, tmp_path, isolated_db, mocker):
        ro_root = tmp_path / "unrelated_ro_src"
        ro_root.mkdir()
        fav_dir = tmp_path / "writable_fav"
        fav_dir.mkdir()
        write_video(fav_dir, "NORMAL-001.mp4")

        config = make_config(fav_dir, directories=[{"path": str(ro_root), "readonly": True}])

        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": "NORMAL-001", "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config)

        assert result != {"readonly": True}
        assert "added" in result
        assert result["added"] == ["NORMAL-001"]


# ===========================================================================
# DoD-5 / DoD-6：中止順序、on_file_start 內容、None 參數等同永不中止（含 M2/M3）
# ===========================================================================

class TestAbortOrdering:
    def test_should_abort_stops_after_current_file(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        f1 = write_video(fav_dir, "FILE-001.mp4")
        f2 = write_video(fav_dir, "FILE-002.mp4")

        config = make_config(fav_dir)

        # 順序在這支測試裡是**承重的**（第 2 部才中止），而 `Path.iterdir()` 不保證順序
        # ——不釘死的話在某些檔案系統上會偶發紅燈，浪費排查時間（PR review 指出）。
        mocker.patch("core.auto_organize.list_favorite_video_files",
                      return_value=[str(f1), str(f2)])
        mocker.patch("core.auto_organize.smart_search",
                      side_effect=lambda number, proxy_url="": [{"number": number, "title": "t", "actors": []}])
        organize_mock = mocker.patch("core.auto_organize.organize_file",
                                      return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        call_count = {"n": 0}

        def should_abort():
            call_count["n"] += 1
            return call_count["n"] >= 2  # 第 2 次呼叫（第 2 部片）起回真

        result = run_one_round(config, should_abort=should_abort)

        assert organize_mock.call_count == 1
        assert organize_mock.call_args_list[0].args[0] == str(f1)
        assert result["aborted_after"] == 1
        assert str(f2) not in [c.args[0] for c in organize_mock.call_args_list]

    def test_on_file_start_excludes_aborted_file(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        f1 = write_video(fav_dir, "FILE-001.mp4")
        f2 = write_video(fav_dir, "FILE-002.mp4")

        config = make_config(fav_dir)

        # 順序在這支測試裡是承重的（理由同上一支）
        mocker.patch("core.auto_organize.list_favorite_video_files",
                      return_value=[str(f1), str(f2)])
        mocker.patch("core.auto_organize.smart_search",
                      side_effect=lambda number, proxy_url="": [{"number": number, "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        call_count = {"n": 0}

        def should_abort():
            call_count["n"] += 1
            return call_count["n"] >= 2

        started = []
        result = run_one_round(config, should_abort=should_abort, on_file_start=started.append)

        assert started == ["FILE-001"]
        assert "FILE-002" not in started
        assert result["aborted_after"] == 1

    def test_no_number_file_skipped_without_on_file_start(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "no_number_here.mp4")

        config = make_config(fav_dir)
        mocker.patch("core.auto_organize.smart_search")
        mocker.patch("core.auto_organize.organize_file")
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        started = []
        result = run_one_round(config, on_file_start=started.append)

        assert started == []
        assert result["added"] == []
        assert result["failed"] == []


class TestNoneCallablesMeanNeverAbort:
    def test_none_should_abort_and_on_file_start_process_all_files(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "FILE-001.mp4")
        write_video(fav_dir, "FILE-002.mp4")

        config = make_config(fav_dir)
        mocker.patch("core.auto_organize.smart_search",
                      side_effect=lambda number, proxy_url="": [{"number": number, "title": "t", "actors": []}])
        organize_mock = mocker.patch("core.auto_organize.organize_file",
                                      return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config, should_abort=None, on_file_start=None)

        assert organize_mock.call_count == 2
        assert result["aborted_after"] is None


# ===========================================================================
# DoD-7：path_mappings 整輪只取一次，duplicate 鍵一致（含 M4）
# ===========================================================================

class TestDuplicateKeyPathMappings:
    def test_duplicate_key_uses_path_mappings(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "MAP-001.mp4")

        path_mappings = {"/mnt/nas": "\\\\NAS\\share"}
        config = make_config(fav_dir, path_mappings=path_mappings)

        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": "MAP-001", "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        spy = mocker.spy(organize_failures, "duplicate_key")

        run_one_round(config)

        spy.assert_called_once()
        called_path_mappings = spy.call_args[0][1]
        assert called_path_mappings == path_mappings, \
            "duplicate 鍵必須帶上整輪只取一次的 path_mappings，不能退回裸 to_file_uri(path)"


# ===========================================================================
# DoD-8：翻譯三子句各有正反例（含 M5）
# ===========================================================================

class TestTranslationClauses:
    def _run_with_translation_mock(self, fav_dir, config, mocker, filename, title,
                                    translate_side_effect=None):
        write_video(fav_dir, filename)
        number = filename.rsplit(".", 1)[0].split(" ")[0]

        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": number, "title": title, "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        fake_service = mocker.MagicMock()
        if translate_side_effect is not None:
            fake_service.translate_single = AsyncMock(side_effect=translate_side_effect)
        else:
            fake_service.translate_single = AsyncMock(return_value="翻譯後標題")
        create_mock = mocker.patch("core.auto_organize.create_translate_service",
                                    return_value=fake_service)

        result = run_one_round(config)
        return result, fake_service, create_mock

    def test_translate_called_when_all_three_clauses_true(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        config = make_config(fav_dir, translate_enabled=True)

        result, fake_service, create_mock = self._run_with_translation_mock(
            fav_dir, config, mocker, "JP-001.mp4", "日本語タイトル"
        )

        create_mock.assert_called_once()
        fake_service.translate_single.assert_called_once_with("日本語タイトル")
        assert "JP-001" in result["added"]

    def test_translate_skipped_when_chinese_title_present(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        config = make_config(fav_dir, translate_enabled=True)

        result, fake_service, create_mock = self._run_with_translation_mock(
            fav_dir, config, mocker, "JP-002 我的中文標題.mp4", "日本語タイトル"
        )

        fake_service.translate_single.assert_not_called()

    def test_translate_skipped_when_title_not_japanese(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        config = make_config(fav_dir, translate_enabled=True)

        result, fake_service, create_mock = self._run_with_translation_mock(
            fav_dir, config, mocker, "JP-003.mp4", "English Title No Japanese"
        )

        fake_service.translate_single.assert_not_called()

    def test_translate_skipped_when_disabled(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        config = make_config(fav_dir, translate_enabled=False)

        result, fake_service, create_mock = self._run_with_translation_mock(
            fav_dir, config, mocker, "JP-004.mp4", "日本語タイトル"
        )

        create_mock.assert_not_called()
        fake_service.translate_single.assert_not_called()

    def test_translate_failure_does_not_block_or_count_as_failed(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        config = make_config(fav_dir, translate_enabled=True)

        result, fake_service, create_mock = self._run_with_translation_mock(
            fav_dir, config, mocker, "JP-005.mp4", "日本語タイトル",
            translate_side_effect=Exception("translation service down"),
        )

        fake_service.translate_single.assert_called_once()
        assert result["failed"] == []
        assert "JP-005" in result["added"]


# ===========================================================================
# DoD-9：記憶命中不算事件（含 M7）
# ===========================================================================

class TestMemoryHitNotAnEvent:
    def test_memory_hit_does_not_count_as_event(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "MEM-001.mp4")
        write_video(fav_dir, "NEW-001.mp4")

        # 事先寫入一筆 not_found 失敗記憶，讓 MEM-001 在本輪落入記憶命中分支
        organize_failures.record_failure("not_found", "MEM-001", "MEM-001")

        config = make_config(fav_dir)

        search_mock = mocker.patch(
            "core.auto_organize.smart_search",
            side_effect=lambda number, proxy_url="": [] if number == "NEW-001" else None,
        )
        organize_mock = mocker.patch("core.auto_organize.organize_file")
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        result = run_one_round(config)

        assert result["skipped"]["memory_hit"] == 1
        assert result["newly_recorded"] == 1  # 只有 NEW-001 的 not_found 是本輪新記錄
        assert "NEW-001" in result["failed"]
        # 記憶命中的檔案不應該再被拿去查詢或整理
        called_numbers = [c.args[0] for c in search_mock.call_args_list]
        assert "MEM-001" not in called_numbers
        organize_mock.assert_not_called()


# ===========================================================================
# 其他：reconcile_wishlist 被呼叫一次且回傳值原樣進了 wishlist_removed
# ===========================================================================

class TestWishlistReconcile:
    def test_reconcile_wishlist_called_once_and_flows_into_result(self, tmp_path, isolated_db, mocker):
        fav_dir = tmp_path / "fav"
        fav_dir.mkdir()
        write_video(fav_dir, "WL-001.mp4")

        config = make_config(fav_dir)
        mocker.patch("core.auto_organize.smart_search",
                      return_value=[{"number": "WL-001", "title": "t", "actors": []}])
        mocker.patch("core.auto_organize.organize_file", return_value=default_organize_success())
        reconcile_mock = mocker.patch("core.auto_organize.reconcile_wishlist",
                                       return_value=["OWNED-001", "OWNED-002"])

        result = run_one_round(config)

        reconcile_mock.assert_called_once()
        assert result["wishlist_removed"] == ["OWNED-001", "OWNED-002"]


class TestClearOnSuccess:
    """成功入庫必須清掉那部片的失敗記憶（CD-144-8 明文，Opus 獨立抽驗補的守衛）。

    這一格原本**沒有任何測試守著**：把 `organize_failures.clear_on_success(number)`
    整行拿掉，卡片定的 M1–M7 七格全部照樣 PASS。

    使用者流程（CD-144-8 逐字）：某片自動輪查無結果被記一筆 → 之後那部片成功入庫
    → 記憶沒清 → **最長 7 天內，「我的最愛」清單與自動輪都還把這部已經在片庫裡的片
    當成「查過沒結果」在跳過**，而使用者看不出為什麼。
    """

    def test_successful_organize_clears_not_found_memory(self, tmp_path, isolated_db, mocker):
        fav = tmp_path / "fav"
        fav.mkdir()
        write_video(fav, "ABC-123.mp4")
        config = make_config(fav)

        # 先讓這部片有一筆「查無結果」的記憶（模擬前幾輪的失敗）
        organize_failures.record_failure("not_found", "ABC-123", "ABC-123")
        assert organize_failures.should_skip("not_found", "ABC-123") is True, (
            "前置條件：這一輪開始前，記憶必須是命中的"
        )

        # 這一輪查得到、也整理成功了
        mocker.patch("core.auto_organize.smart_search",
                     return_value=[{"number": "ABC-123", "title": "Some Title"}])
        mocker.patch("core.auto_organize.organize_file",
                     return_value=default_organize_success())
        mocker.patch("core.auto_organize.reconcile_wishlist", return_value=[])

        # 記憶命中會讓這部片在步驟 3 就被跳過，所以要讓退避窗過期它這一輪才跑得到整理。
        mocker.patch("core.database.organize_failures._now",
                     return_value=organize_failures._now() + 8 * 86400)

        result = run_one_round(config)

        assert result["added"] == ["ABC-123"]

        # 🔴 斷言必須直接看**那一列在不在**，不能用 `should_skip()`：
        # 上面 patch 掉的時鐘已經讓退避窗過期，`should_skip()` 不論那列有沒有被刪都會回 False
        # ——用它斷言會是假綠（本測試第一版就是這樣，mutation 自驗當場抓到）。
        with get_connection(isolated_db) as conn:
            row = conn.cursor().execute(
                "SELECT 1 FROM organize_failures WHERE reason='not_found' AND key='ABC-123'"
            ).fetchone()
        assert row is None, (
            "成功入庫之後那筆『查無結果』的記憶必須被刪掉，"
            "否則接下來最長 7 天，這部已經在片庫裡的片還會被當成『查過沒結果』跳過"
        )
