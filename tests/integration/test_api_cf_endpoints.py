"""
tests/integration/test_api_cf_endpoints.py — TASK-70-T6
========================================================
Integration tests for /api/cf/status, /api/cf/abandon,
rescrape_preview CF exceptions, and mounting guard.

Uses FastAPI TestClient (client fixture from conftest.py).
"""
import pytest
from unittest.mock import MagicMock

from core.cf_transport import CfChallengeRequired, CfTransportUnavailable
from core.scrapers.javlibrary import JAVLIBRARY_ORIGIN


# ── /api/cf/status ────────────────────────────────────────────────────────────

class TestCfStatusEndpoint:
    """GET /api/cf/status — transport probe 端點。"""

    def test_status_no_transport_returns_not_ready(self, client, mocker):
        """transport is None → {ready: false, unavailable: true}，不 500。"""
        mocker.patch("web.routers.cf.get_cf_transport", return_value=None)
        resp = client.get("/api/cf/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is False
        assert data.get("unavailable") is True

    def test_status_with_transport_is_ready_true(self, client, mocker):
        """transport 存在，is_ready=True → {ready: true}。"""
        mock_t = MagicMock()
        mock_t.is_ready.return_value = True
        mocker.patch("web.routers.cf.get_cf_transport", return_value=mock_t)
        resp = client.get("/api/cf/status")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True

    def test_status_with_transport_is_ready_false(self, client, mocker):
        """transport 存在，is_ready=False → {ready: false}。"""
        mock_t = MagicMock()
        mock_t.is_ready.return_value = False
        mocker.patch("web.routers.cf.get_cf_transport", return_value=mock_t)
        resp = client.get("/api/cf/status")
        assert resp.status_code == 200
        assert resp.json()["ready"] is False

    def test_status_transport_is_ready_raises_returns_not_ready(self, client, mocker):
        """is_ready() 拋例外 → {ready: false}，不 500（try/except 守護）。"""
        mock_t = MagicMock()
        mock_t.is_ready.side_effect = RuntimeError("evaluate_js timeout")
        mocker.patch("web.routers.cf.get_cf_transport", return_value=mock_t)
        resp = client.get("/api/cf/status")
        assert resp.status_code == 200
        assert resp.json()["ready"] is False

    def test_status_dead_transport_returns_unavailable(self, client, mocker):
        """
        CD-70c-2/3: transport is_ready() raises CfTransportUnavailable (window dead)
        → {ready: false, unavailable: true}, not {ready: false}.
        This is distinct from the None-transport path (which also → unavailable:true)
        and from a transient JS error (RuntimeError → {ready:false} without unavailable).
        """
        mock_t = MagicMock()
        mock_t.is_ready.side_effect = CfTransportUnavailable("JL window destroyed")
        mocker.patch("web.routers.cf.get_cf_transport", return_value=mock_t)
        resp = client.get("/api/cf/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is False
        assert data.get("unavailable") is True, (
            f"Dead transport must return unavailable:true, got: {data!r}"
        )


# ── /api/cf/abandon ──────────────────────────────────────────────────────────

class TestCfAbandonEndpoint:
    """POST /api/cf/abandon — 逾時/取消通知端點。"""

    def test_abandon_returns_ok(self, client, mocker):
        """POST /api/cf/abandon → {ok: true}。"""
        mocker.patch("web.routers.cf.emit_notification")
        resp = client.post("/api/cf/abandon")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_abandon_emits_notification(self, client, mocker):
        """POST /api/cf/abandon → emit_notification 被呼叫，level='warn'，title_key='notif.jl_cf_timeout'。"""
        mock_emit = mocker.patch("web.routers.cf.emit_notification")
        client.post("/api/cf/abandon")
        assert mock_emit.called, "emit_notification 應被呼叫"
        call_kwargs = mock_emit.call_args
        # emit_notification(level, title_key, message, task_type)
        args = call_kwargs.args if call_kwargs.args else ()
        kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
        # 支援位置參數或關鍵字
        level = args[0] if len(args) > 0 else kwargs.get("level")
        title_key = args[1] if len(args) > 1 else kwargs.get("title_key")
        assert level == "warn", f"emit level 應為 'warn'，實際: {level!r}"
        assert title_key == "notif.jl_cf_timeout", \
            f"emit title_key 應為 'notif.jl_cf_timeout'，實際: {title_key!r}"


# ── /api/rescrape/preview CF 例外處理 ─────────────────────────────────────────

class TestRescrapePreviewCfExceptions:
    """rescrape_preview_endpoint 對 CF 例外的回應。"""

    def test_cf_challenge_required_returns_cf_needed(self, client, mocker):
        """CfChallengeRequired → {success:false, cf_needed:true}，begin_solve 被呼叫。"""
        # source=javlibrary 現在走 search_javlib_versions 分支（T2），不再走 search_jav_single_source
        mocker.patch(
            "web.routers.scraper.search_javlib_versions",
            side_effect=CfChallengeRequired("CF challenge"),
        )
        mock_transport = MagicMock()
        mocker.patch("web.routers.scraper.get_cf_transport", return_value=mock_transport)

        resp = client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
            "source": "javlibrary",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is False
        assert data.get("cf_needed") is True
        mock_transport.begin_solve.assert_called_once_with(JAVLIBRARY_ORIGIN, 'javlibrary')

    def test_cf_transport_unavailable_returns_cf_unavailable(self, client, mocker):
        """CfTransportUnavailable → {success:false, cf_unavailable:true}，begin_solve 不被呼叫。"""
        # source=javlibrary 現在走 search_javlib_versions 分支（T2），不再走 search_jav_single_source
        mocker.patch(
            "web.routers.scraper.search_javlib_versions",
            side_effect=CfTransportUnavailable("no transport"),
        )
        mock_transport = MagicMock()
        mocker.patch("web.routers.scraper.get_cf_transport", return_value=mock_transport)

        resp = client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
            "source": "javlibrary",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is False
        assert data.get("cf_unavailable") is True
        mock_transport.begin_solve.assert_not_called()  # CfTransportUnavailable 不應觸發 begin_solve

    def test_cf_challenge_no_transport_still_returns_cf_needed(self, client, mocker):
        """CfChallengeRequired + get_cf_transport → None → begin_solve 不呼叫，仍回 cf_needed:true。"""
        # source=javlibrary 現在走 search_javlib_versions 分支（T2），不再走 search_jav_single_source
        mocker.patch(
            "web.routers.scraper.search_javlib_versions",
            side_effect=CfChallengeRequired("CF challenge"),
        )
        mocker.patch("web.routers.scraper.get_cf_transport", return_value=None)

        resp = client.post("/api/rescrape/preview", json={
            "number": "SONE-205",
            "source": "javlibrary",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is False
        assert data.get("cf_needed") is True


# ── mounting guard ────────────────────────────────────────────────────────────

class TestCfMountingGuard:
    """mounting guard：確認 cf_router 已 include_router 進 app。"""

    def test_cf_status_endpoint_is_not_404(self, client):
        """/api/cf/status 非 404（include_router 確認）。"""
        resp = client.get("/api/cf/status")
        assert resp.status_code != 404, (
            "GET /api/cf/status 回 404 — web/app.py 可能漏了 app.include_router(cf_router.router)"
        )


# ── FIX-2: /api/search?source=javlibrary CfChallengeRequired → 非 500 ──────────

class TestSearchJavlibraryCfExceptions:
    """FIX-2: GET /api/search?source=javlibrary 觸發 CF 例外 → 結構化非 500 回應。"""

    def test_cf_challenge_required_returns_non_500(self, client, mocker):
        """CfChallengeRequired → 200 + success:false + error 欄位（非 500）。"""
        # search_jav_single_source 在 search() 函式內以 local import 引入，
        # patch target 為 core.scraper 模組的屬性（local import 路徑）。
        mocker.patch(
            "core.scraper.search_jav_single_source",
            side_effect=CfChallengeRequired("CF challenge"),
        )
        resp = client.get("/api/search", params={"q": "TCD-332", "mode": "exact", "source": "javlibrary"})
        assert resp.status_code == 200, (
            f"CfChallengeRequired 不應產生 500，got: {resp.status_code}"
        )
        data = resp.json()
        assert data.get("success") is False
        assert "error" in data
        assert data.get("data") == []
        assert data.get("total") == 0

    def test_cf_transport_unavailable_returns_non_500(self, client, mocker):
        """CfTransportUnavailable → 200 + success:false + error 欄位（非 500）。"""
        mocker.patch(
            "core.scraper.search_jav_single_source",
            side_effect=CfTransportUnavailable("no transport"),
        )
        resp = client.get("/api/search", params={"q": "TCD-332", "mode": "exact", "source": "javlibrary"})
        assert resp.status_code == 200, (
            f"CfTransportUnavailable 不應產生 500，got: {resp.status_code}"
        )
        data = resp.json()
        assert data.get("success") is False
        assert "error" in data
        assert data.get("data") == []


# ── FIX-3: begin_solve 拋例外 → cf_unavailable ───────────────────────────────

class TestRescrapePreviewBeginSolveFail:
    """FIX-3: begin_solve 拋例外 → {success:false, cf_unavailable:true}，非 500。"""

    def test_begin_solve_exception_returns_cf_unavailable(self, client, mocker):
        """begin_solve.side_effect=Exception → 200 + cf_unavailable:true（非 500）。"""
        mocker.patch(
            "web.routers.scraper.search_jav_single_source",
            side_effect=CfChallengeRequired("CF challenge"),
        )
        mock_transport = MagicMock()
        mock_transport.begin_solve.side_effect = Exception("window destroyed")
        mocker.patch("web.routers.scraper.get_cf_transport", return_value=mock_transport)

        resp = client.post("/api/rescrape/preview", json={
            "number": "TCD-332",
            "source": "javlibrary",
        })
        assert resp.status_code == 200, (
            f"begin_solve 失敗不應產生 500，got: {resp.status_code}"
        )
        data = resp.json()
        assert data.get("success") is False
        assert data.get("cf_unavailable") is True, (
            f"begin_solve 失敗應回 cf_unavailable:true，got: {data!r}"
        )
