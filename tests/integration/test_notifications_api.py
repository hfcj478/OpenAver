"""
tests/integration/test_notifications_api.py — 通知中心 API 端點測試（53b）

用 FastAPI TestClient 打 GET / POST / DELETE。依 CLAUDE.md 測試分層：API 端點 → integration/。
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def reset_buffer(monkeypatch, tmp_path):
    import web.routers.notifications as notif_mod
    from core.database.connection import init_db

    test_db = tmp_path / "integ_test.db"
    init_db(test_db)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: test_db)

    with notif_mod._lock:
        notif_mod._notifications.clear()
        notif_mod._read_ids.clear()
    while not notif_mod._write_queue.empty():
        try:
            notif_mod._write_queue.get_nowait()
            notif_mod._write_queue.task_done()
        except Exception:
            break

    yield

    with notif_mod._lock:
        notif_mod._notifications.clear()
        notif_mod._read_ids.clear()
    notif_mod.stop_notification_persistence()
    while not notif_mod._write_queue.empty():
        try:
            notif_mod._write_queue.get_nowait()
            notif_mod._write_queue.task_done()
        except Exception:
            break



@pytest.fixture
def client():
    from web.app import app
    return TestClient(app)


def test_get_empty(client):
    """無 emit 時 GET 回空 buffer + 0 unread + null highest。"""
    res = client.get("/api/notifications")
    body = res.json()
    assert body["items"] == []
    assert body["unread_count"] == 0
    assert body["highest_unread_level"] is None


def test_get_with_items(client):
    """emit 2 筆後 GET 回最新在前 + 全部未讀。"""
    from web.routers.notifications import emit_notification
    emit_notification("info", "notif.scanner_started")
    emit_notification("warn", "notif.scanner_done_with_errors")
    body = client.get("/api/notifications").json()
    assert len(body["items"]) == 2
    assert body["items"][0]["title_key"] == "notif.scanner_done_with_errors"
    assert body["unread_count"] == 2
    assert body["highest_unread_level"] == "warn"


def test_post_read_marks_all(client):
    """POST /read 後 GET 顯示全部已讀。"""
    from web.routers.notifications import emit_notification
    emit_notification("info", "notif.scanner_started")
    emit_notification("warn", "notif.batch_enrich_done_with_errors")

    res = client.post("/api/notifications/read")
    assert res.json() == {"ok": True, "marked_count": 2}

    body = client.get("/api/notifications").json()
    assert body["unread_count"] == 0
    assert all(item["is_read"] is True for item in body["items"])


def test_delete_clears_all(client):
    """DELETE 後 buffer 跟 _read_ids 都清空。"""
    from web.routers.notifications import emit_notification, _read_ids
    emit_notification("info", "notif.scanner_started")
    client.post("/api/notifications/read")
    assert len(_read_ids) > 0

    res = client.delete("/api/notifications")
    assert res.json()["ok"] is True
    assert res.json()["cleared_count"] >= 1

    body = client.get("/api/notifications").json()
    assert body["items"] == []
    assert len(_read_ids) == 0


def test_highest_unread_level_priority(client):
    """info + error 未讀 → highest = error；標已讀後新 warn → highest = warn。"""
    from web.routers.notifications import emit_notification
    emit_notification("info", "notif.scanner_started")
    emit_notification("error", "notif.scanner_failed")
    assert client.get("/api/notifications").json()["highest_unread_level"] == "error"

    client.post("/api/notifications/read")
    emit_notification("warn", "notif.scanner_done_with_errors")
    assert client.get("/api/notifications").json()["highest_unread_level"] == "warn"


def test_scanner_no_directory_emits_no_started(client):
    """scanner_started 在無 directories 時不應 emit（P2-2 regression guard）。

    沒有 scannerRouter 可以直接呼叫 scanner_generate，用 mock config 驗證 emit 邏輯：
    當 directories 為空時，emit_notification 不應被呼叫（不殘留 scanner_started）。
    """
    import unittest.mock as mock
    from web.routers.notifications import _notifications

    # 模擬 directories 為空的 config
    empty_config = {"gallery": {"directories": [], "output_dir": "output", "output_filename": "gallery_output.html", "path_mappings": {}, "min_size_mb": 0, "default_mode": "image", "default_sort": "date", "default_order": "descending", "items_per_page": 90}, "general": {"theme": "light"}}

    with mock.patch("web.routers.scanner.load_config", return_value=empty_config):
        from web.routers.scanner import generate_avlist
        # 消費完 generator（否則 yield 不執行）
        events = list(generate_avlist())

    # 驗證：沒有 scanner_started 通知（early return path 不應 emit started）
    notif_keys = [n["title_key"] for n in _notifications]
    assert "notif.scanner_started" not in notif_keys, f"scanner_started 不應在 no-directory 路徑出現，但找到：{notif_keys}"
    # 驗證：SSE stream 包含 error 事件
    assert any("error" in e for e in events), "no-directory 路徑應產生 SSE error 事件"


def test_notification_persists_across_restart(client, tmp_path, monkeypatch):
    """DoD-1 (M3): 發通知落 DB，模擬重啟後 GET /api/notifications 仍看得到它，且已讀狀態不變。"""
    from core.database.connection import init_db
    import web.routers.notifications as notif_mod
    from web.routers.notifications import emit_notification, start_notification_persistence, _write_queue

    test_db = tmp_path / "persist_test.db"
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: test_db)
    init_db(test_db)

    # 啟動持久化
    start_notification_persistence()

    emit_notification("info", "notif.persist_key", message="persisted message")
    _write_queue.join()

    # 模擬 process 重啟：清空記憶體緩衝
    # 先**真的**停掉舊 writer（哨兵 ＋ join），不要只把指標設成 None：
    # 那會留下一條仍活著、仍在消費同一個 module-level 佇列、而且綁著**舊 db_path**
    # 的孤兒 thread，把接下來該寫進新庫的通知寫到舊庫去。
    notif_mod.stop_notification_persistence()
    with notif_mod._lock:
        notif_mod._notifications.clear()
        notif_mod._read_ids.clear()

    # 重啟開機：呼叫 start_notification_persistence()
    start_notification_persistence()

    body = client.get("/api/notifications").json()
    assert len(body["items"]) == 1
    assert body["items"][0]["title_key"] == "notif.persist_key"
    assert body["items"][0]["message"] == "persisted message"
    assert body["items"][0]["is_read"] is False
    assert body["unread_count"] == 1


def test_notification_clear_persists_across_restart(client, tmp_path, monkeypatch):
    """DoD-6 (M6): DELETE /api/notifications 清空後重啟，抽屜仍為空，不得從 DB 復活。"""
    from core.database.connection import init_db
    import web.routers.notifications as notif_mod
    from web.routers.notifications import emit_notification, start_notification_persistence, _write_queue

    test_db = tmp_path / "clear_persist_test.db"
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: test_db)
    init_db(test_db)

    start_notification_persistence()

    emit_notification("info", "notif.to_be_cleared")
    _write_queue.join()

    # 清空
    res = client.delete("/api/notifications")
    assert res.json()["ok"] is True
    _write_queue.join()

    # 模擬 process 重啟
    # 先**真的**停掉舊 writer（哨兵 ＋ join），不要只把指標設成 None：
    # 那會留下一條仍活著、仍在消費同一個 module-level 佇列、而且綁著**舊 db_path**
    # 的孤兒 thread，把接下來該寫進新庫的通知寫到舊庫去。
    notif_mod.stop_notification_persistence()
    with notif_mod._lock:
        notif_mod._notifications.clear()
        notif_mod._read_ids.clear()

    start_notification_persistence()

    body = client.get("/api/notifications").json()
    assert body["items"] == []
    assert body["unread_count"] == 0


def test_notification_read_persists_across_restart(client, tmp_path, monkeypatch):
    """DoD-6: POST /api/notifications/read 標記已讀後重啟，重啟後通知仍是已讀。"""
    from core.database.connection import init_db
    import web.routers.notifications as notif_mod
    from web.routers.notifications import emit_notification, start_notification_persistence, _write_queue

    test_db = tmp_path / "read_persist_test.db"
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: test_db)
    init_db(test_db)

    start_notification_persistence()

    emit_notification("info", "notif.to_be_read")
    _write_queue.join()

    res = client.post("/api/notifications/read")
    assert res.json()["ok"] is True
    _write_queue.join()

    # 模擬 process 重啟
    # 先**真的**停掉舊 writer（哨兵 ＋ join），不要只把指標設成 None：
    # 那會留下一條仍活著、仍在消費同一個 module-level 佇列、而且綁著**舊 db_path**
    # 的孤兒 thread，把接下來該寫進新庫的通知寫到舊庫去。
    notif_mod.stop_notification_persistence()
    with notif_mod._lock:
        notif_mod._notifications.clear()
        notif_mod._read_ids.clear()

    start_notification_persistence()

    body = client.get("/api/notifications").json()
    assert len(body["items"]) == 1
    assert body["items"][0]["is_read"] is True
    assert body["unread_count"] == 0


def test_loadback_order_preserves_newest_first(client, tmp_path, monkeypatch):
    """DoD-7: DB 裡有 N 筆時間戳不同的通知，重啟後 GET 回傳的順序與重啟前逐筆相同（最新的在最前面）。"""
    import time
    from core.database.connection import init_db
    import web.routers.notifications as notif_mod
    from web.routers.notifications import emit_notification, start_notification_persistence, _write_queue

    test_db = tmp_path / "order_test.db"
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: test_db)
    init_db(test_db)

    start_notification_persistence()

    for i in range(5):
        emit_notification("info", f"notif.item_{i}", message=f"msg_{i}")
        time.sleep(0.01)  # 確保 timestamp 嚴格遞增
    _write_queue.join()

    before_body = client.get("/api/notifications").json()
    before_ids = [item["id"] for item in before_body["items"]]
    assert len(before_ids) == 5

    # 模擬 process 重啟
    # 先**真的**停掉舊 writer（哨兵 ＋ join），不要只把指標設成 None：
    # 那會留下一條仍活著、仍在消費同一個 module-level 佇列、而且綁著**舊 db_path**
    # 的孤兒 thread，把接下來該寫進新庫的通知寫到舊庫去。
    notif_mod.stop_notification_persistence()
    with notif_mod._lock:
        notif_mod._notifications.clear()
        notif_mod._read_ids.clear()

    start_notification_persistence()

    after_body = client.get("/api/notifications").json()
    after_ids = [item["id"] for item in after_body["items"]]
    assert after_ids == before_ids


def test_start_persistence_idempotent(tmp_path, monkeypatch):
    """DoD-9: 重複呼叫 start_notification_persistence() 不啟動兩條 thread，不使 deque 出現重複通知。"""
    from core.database.connection import init_db
    import web.routers.notifications as notif_mod
    from web.routers.notifications import emit_notification, start_notification_persistence, _write_queue

    test_db = tmp_path / "idempotent_test.db"
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: test_db)
    init_db(test_db)

    start_notification_persistence()
    first_thread = notif_mod._writer_thread

    emit_notification("info", "notif.idem_key", message="idem msg")
    _write_queue.join()

    assert len(notif_mod._notifications) == 1

    # 第二次呼叫
    start_notification_persistence()
    assert notif_mod._writer_thread is first_thread
    assert len(notif_mod._notifications) == 1

