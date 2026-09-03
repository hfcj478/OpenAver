"""Integration test for TASK-143-T5: Readonly tags survive rescrape.

Two-stage real request integration test (spec §3.2 AC2-3):
1. POST /api/user-tags adds a tag to a readonly source video.
2. POST /api/enrich-single triggers rescrape.
Assert: Rescraped output NFO retains the tag, and DB user_tags is unchanged.
"""
from pathlib import Path

import pytest
from core.database import VideoRepository as RealRepo, init_db
from core.path_utils import uri_to_local_fs_path
from tests.integration.test_user_tags_api import TestT4ReadonlyUserTags

# Prevent pytest from collecting tests from the imported helper class
TestT4ReadonlyUserTags.__test__ = False


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary test database."""
    db_path = tmp_path / "test_user_tags.db"
    init_db(db_path)
    return db_path


class TestReadonlyTagsSurviveRescrape:
    def test_readonly_tags_survive_rescrape(self, tmp_db, tmp_path, monkeypatch):
        client, src_dir, out_dir, file_uri = TestT4ReadonlyUserTags()._setup_readonly(
            tmp_db, tmp_path, monkeypatch, with_source_nfo=False, with_output_nfo=True
        )

        fake_config = {
            "gallery": {
                "directories": [{"path": str(src_dir), "readonly": True, "output_path": ""}],
                "path_mappings": {},
            },
            "scraper": {},
        }
        monkeypatch.setattr("web.routers.scraper.load_config", lambda: fake_config)
        monkeypatch.setattr("web.routers.collection.load_config", lambda: fake_config)
        monkeypatch.setattr(
            "web.routers.scraper.VideoRepository",
            lambda *a, **kw: RealRepo(tmp_db),
        )
        monkeypatch.setattr("core.readonly_producer.get_db_path", lambda: tmp_db)
        monkeypatch.setattr("core.readonly_producer.download_image", lambda *a, **kw: False)
        # /api/enrich-single 成功後會呼叫 _reconcile_wishlist_after_write() → reconcile_wishlist()，
        # 而 WishlistRepository() 不帶參數時走 connection.get_db_path()（模組屬性、呼叫當下才解析）。
        # 不 patch 它 → 這支測試會去開**使用者真實的 output/openaver.db**，被 repo_write_guard G1 擋下。
        # ⚠️ 這條在 git worktree 裡不會紅（G1 只認真 repo 路徑），只有在主工作樹跑才看得到。
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: tmp_db)
        # 同一個陷阱的姊妹案例（T5 sonnet review P2）：`core/thumbnail_cache.py:22` 是
        # `from core.database import get_db_path`——**import 當下就複製了參照**，
        # 所以 patch `core.database.connection.get_db_path` 對它完全無效
        # （實測：patch 後 `thumbnail_cache.get_db_path()` 仍回真實 repo 路徑）。
        # 不 patch 它 → enrich 成功後的 `thumbnail_cache.invalidate()` 會對專案真實的
        # `output/thumb/` 做 unlink。目前因為檔名是 sha1(合成 tmp 路徑) 且 missing_ok=True
        # 所以靜默 no-op、測試照樣綠——**這正是它危險的地方**，必須顯式擋掉。
        monkeypatch.setattr("core.thumbnail_cache.get_db_path", lambda: tmp_db)

        # ① 加標籤
        resp1 = client.post("/api/user-tags", json={"file_path": file_uri, "add": ["SURVIVE"]})
        assert resp1.status_code == 200
        assert resp1.json()["success"] is True

        repo = RealRepo(tmp_db)
        assert repo.get_by_path(file_uri).user_tags == ["SURVIVE"]

        # ② 觸發重刮
        resp2 = client.post(
            "/api/enrich-single",
            json={
                "file_path": file_uri,
                "number": "TEST-001",
                "readonly_action": "rescrape",
                "mode": "refresh_full",
                "overwrite_existing": True,
                "metadata": {"number": "TEST-001", "title": "Rescraped Title"},
            },
        )
        assert resp2.status_code == 200
        assert resp2.json()["success"] is True

        # 斷言：從 DB 讀出 output_dir，找到重刮後的 NFO
        row = repo.get_by_path(file_uri)
        assert row is not None
        output_dir_fs = Path(uri_to_local_fs_path(row.output_dir, {}))
        nfo_files = list(output_dir_fs.glob("*.nfo"))
        assert len(nfo_files) >= 1
        nfo_content = nfo_files[0].read_text(encoding="utf-8")
        assert "<user_tag>SURVIVE</user_tag>" in nfo_content

        # DB 值沒有被這次重刮改變（維持保留語意）
        assert repo.get_by_path(file_uri).user_tags == ["SURVIVE"]
