"""TASK-61c-7: 進階搜尋 picker MVP — 後端契約測試

涵蓋：
1. `advanced_search_enabled` persist round-trip（GET 預設 false / PUT true → GET true）。
2. source override：`/api/search?source=<停用來源>&mode=exact` 仍回該來源資料
   （證明 override 路徑與 sources enabled 狀態無關，整包贏）。

長壓 / picker 互動 / OQ-3 軟提示 = MANUAL（見 TASK card checklist）。
"""
import json


class TestAdvancedSearchEnabledPersist:
    """advanced_search_enabled top-level bool persist round-trip"""

    def test_default_false(self, client, temp_config_path):
        """GET /api/config 預設 advanced_search_enabled = false"""
        resp = client.get("/api/config")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"].get("advanced_search_enabled") is False

    def test_put_true_persists(self, client, temp_config_path):
        """PUT advanced_search_enabled=true → GET 回 true（round-trip）"""
        cfg = client.get("/api/config").json()["data"]
        cfg["advanced_search_enabled"] = True

        put_resp = client.put("/api/config", json=cfg)
        assert put_resp.status_code == 200
        assert put_resp.json()["success"] is True

        # GET 再驗
        new_cfg = client.get("/api/config").json()["data"]
        assert new_cfg["advanced_search_enabled"] is True

        # 直接讀檔驗證持久化
        with open(temp_config_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["advanced_search_enabled"] is True


class TestAdvancedSearchSourceOverride:
    """picker 確定 → /api/search?source=<id>&mode=exact 覆寫契約（整包贏）"""

    def test_override_disabled_source_returns_that_source(self, client, temp_config_path, mocker):
        """選一個 enabled=false 的 builtin（javdb）→ 仍回該來源資料

        證明 source override 路徑與 sources enabled 狀態無關。
        """
        # 先停用 javdb（模擬 picker 顯示的「停用 builtin」）
        cfg = client.get("/api/config").json()["data"]
        for s in cfg["sources"]:
            if s["id"] == "javdb":
                s["enabled"] = False
        client.put("/api/config", json=cfg)

        # mock 單一來源搜尋（search.py 內 local import core.scraper.search_jav_single_source）
        mock_data = {"number": "SSIS-001", "title": "from-javdb", "source": "javdb"}
        mocker.patch("core.scraper.search_jav_single_source", return_value=mock_data)

        resp = client.get("/api/search", params={
            "q": "SSIS-001", "mode": "exact", "source": "javdb"
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]) == 1
        assert data["data"][0]["source"] == "javdb"
        assert data["data"][0]["title"] == "from-javdb"

    def test_override_calls_single_source(self, client, temp_config_path, mocker):
        """source override → 走 search_jav_single_source（非 smart_search）"""
        mock_single = mocker.patch(
            "core.scraper.search_jav_single_source",
            return_value={"number": "SSIS-002", "source": "javbus"},
        )
        resp = client.get("/api/search", params={
            "q": "SSIS-002", "mode": "exact", "source": "javbus"
        })
        assert resp.status_code == 200
        mock_single.assert_called_once()
        # 第一個位置參數為 query，第二個為 source
        args, kwargs = mock_single.call_args
        assert args[0] == "SSIS-002"
        assert args[1] == "javbus"
