"""TASK-144-T7: GET /api/search/auto-organize/status schema ＋ 唯讀性（D8 / M4）。"""

import core.auto_organize_state as aos
from core import auto_organize_state


EXPECTED_KEYS = {
    "running",
    "current_number",
    "enabled",
    "folder",
    "folder_is_set",
    "resolved_folder",
}


def test_get_auto_organize_status_schema(client):
    """D8：回 200，body 恰好是面板要的六個 key，型別各自正確。

    ⚠️ 這支端點在 2026-09-05 由兩個 key 擴成六個（主 session 修正）：原本面板為了拿到
    「還沒設資料夾時要顯示的候選路徑」得去打 `GET /api/search/favorite-files`，
    而那支會**把整個系統下載資料夾列完並逐檔 stat**，還帶著兩個副作用。
    這裡鎖 `== EXPECTED_KEYS`（不是 `>=`）是刻意的：多一個 key 也要有人來改這行，
    才不會有人又順手把整包 config 塞進來。
    """
    auto_organize_state.exit_cron()
    resp = client.get("/api/search/auto-organize/status")
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == EXPECTED_KEYS
    assert isinstance(data["running"], bool)
    assert data["current_number"] is None or isinstance(data["current_number"], str)
    assert isinstance(data["enabled"], bool)
    assert isinstance(data["folder"], str)
    assert isinstance(data["folder_is_set"], bool)
    assert isinstance(data["resolved_folder"], str)


def test_get_auto_organize_status_is_read_only(client):
    """D8：連續呼叫兩次回應相等，且**不留下任何副作用**。

    `_last_manual_at` 是這條斷言的重點，不是順帶：`mark_manual_activity()` 會寫它，
    而排程到期時會讀它來決定「最近 10 分鐘有人動過就跳過這一輪」。
    面板只是被打開來看一眼，若這支端點碰了它，**每開一次面板就把排程往後推 10 分鐘**。
    （這正是改掉 `favorite-files` 那條路的原因之一——那支的 handler 有這個副作用。）
    """
    auto_organize_state.exit_cron()
    before_manual = aos._last_manual_at
    before_abort = aos._abort_requested

    first = client.get("/api/search/auto-organize/status").json()
    second = client.get("/api/search/auto-organize/status").json()

    assert first == second
    assert aos._last_manual_at == before_manual, "status 端點動到了 _last_manual_at——排程會被往後推"
    assert aos._abort_requested == before_abort, "status 端點動到了中止旗標"


def test_get_auto_organize_status_reflects_real_running_state(client):
    """M4：回應如實反映 _running，防止恆真退化。"""
    auto_organize_state.exit_cron()
    idle = client.get("/api/search/auto-organize/status").json()
    assert idle["running"] is False
    assert idle["current_number"] is None

    assert auto_organize_state.enter_cron("run_now") is True
    try:
        auto_organize_state.set_current_number("ABC-123")
        busy = client.get("/api/search/auto-organize/status").json()
        assert busy["running"] is True
        assert busy["current_number"] == "ABC-123"
    finally:
        auto_organize_state.exit_cron()

    after = client.get("/api/search/auto-organize/status").json()
    assert after["running"] is False
    assert after["current_number"] is None


def test_resolved_folder_is_served_without_listing_files(client, monkeypatch):
    """未設最愛資料夾時，候選路徑照樣拿得到，而且**沒有任何檔案被列出**。

    使用者流程：還沒設過最愛資料夾的人打開「自動整理」面板 → 灰字要顯示
    「按下『就用這個資料夾』會變成哪個路徑」。舊做法是去列那個資料夾拿它的名字，
    下載夾大的人會看到面板卡著不出現。這裡直接證明沒有人去 iterdir。
    """
    monkeypatch.setattr(
        "web.routers.search.load_config",
        lambda: {"search": {"favorite_folder": "", "auto_organize": {"enabled": False}}},
    )

    called = []
    monkeypatch.setattr(
        "core.favorite_scan.list_favorite_video_files",
        lambda *a, **kw: called.append(a) or [],
    )

    data = client.get("/api/search/auto-organize/status").json()

    assert data["folder"] == ""
    assert data["folder_is_set"] is False
    assert data["resolved_folder"], "沒設資料夾時仍要給得出候選路徑"
    assert called == [], "為了顯示一個路徑字串就去列整個資料夾"
