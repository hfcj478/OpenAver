"""
tests/unit/test_notifications.py — 通知 buffer 純函式邏輯測試（53b）

全 mock，不啟動 FastAPI。依 CLAUDE.md 測試分層：純邏輯 → unit/。
"""
import sqlite3
import pytest


@pytest.fixture(autouse=True)
def reset_buffer(monkeypatch, tmp_path):
    """每個 test 前後清空 buffer 與佇列，確保 DB 隔離，防止狀態污染。"""
    import web.routers.notifications as notif_mod
    from core.database.connection import init_db

    test_db = tmp_path / "unit_test.db"
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



def test_emit_notification_basic():
    from web.routers.notifications import emit_notification, _notifications
    emit_notification("info", "notif.scanner_started", task_type="scanner_generate")
    assert len(_notifications) == 1
    assert _notifications[0]["level"] == "info"
    assert _notifications[0]["title_key"] == "notif.scanner_started"
    assert _notifications[0]["task_type"] == "scanner_generate"
    assert "id" in _notifications[0]
    assert "timestamp" in _notifications[0]


def test_buffer_max_50():
    from web.routers.notifications import emit_notification, _notifications
    for i in range(55):
        emit_notification("info", f"notif.test_{i}")
    assert len(_notifications) == 50
    assert _notifications[0]["title_key"] == "notif.test_54"
    keys = [n["title_key"] for n in _notifications]
    assert "notif.test_0" not in keys


def test_newest_first():
    from web.routers.notifications import emit_notification, _notifications
    emit_notification("info", "notif.first")
    emit_notification("error", "notif.second")
    assert _notifications[0]["title_key"] == "notif.second"
    assert _notifications[1]["title_key"] == "notif.first"


def test_emit_evicts_orphan_read_id():
    """F2 設計驗證：buffer 滿時 emit 新筆，被擠出筆的 read_id 同步從 _read_ids 清掉。"""
    from web.routers.notifications import emit_notification, _notifications, _read_ids
    for i in range(50):
        emit_notification("info", f"notif.test_{i}")
    oldest_id = _notifications[-1]["id"]
    _read_ids.add(oldest_id)
    emit_notification("info", "notif.test_50")
    assert oldest_id not in _read_ids


def test_emit_notification_dedup_same_title_and_message():
    """DoD-3 (M1): 同 title_key 且同 message 不重複寫入，時間戳與已讀狀態維持原樣。"""
    from web.routers.notifications import emit_notification, _notifications, _read_ids
    emit_notification("info", "notif.update_available", message="v1.0.0")
    assert len(_notifications) == 1
    first_id = _notifications[0]["id"]
    first_time = _notifications[0]["timestamp"]

    # 標記為已讀
    _read_ids.add(first_id)

    # 連發相同 title_key 且相同 message
    emit_notification("info", "notif.update_available", message="v1.0.0")
    assert len(_notifications) == 1
    assert _notifications[0]["id"] == first_id
    assert _notifications[0]["timestamp"] == first_time
    assert first_id in _read_ids

    # 同 title_key 但不同 message → 應新增第二筆
    emit_notification("info", "notif.update_available", message="v1.0.1")
    assert len(_notifications) == 2
    assert _notifications[0]["message"] == "v1.0.1"


def test_emit_notification_non_blocking_zero_db_calls():
    """DoD-2: emit_notification 絕不阻塞，函式體內零 DB 呼叫。"""
    from unittest.mock import patch
    from web.routers.notifications import emit_notification

    with patch("core.database.connection.get_connection") as mock_conn:
        emit_notification("info", "notif.noblock_test", message="no db")
        assert mock_conn.call_count == 0


def test_writer_thread_survives_db_locked_exception(monkeypatch):
    """DoD-2 (M4): DB 發生異常（如 database is locked）時，writer thread 不死且後續通知仍能寫入。"""
    import time
    import sqlite3
    import web.routers.notifications as notif_mod

    # 啟動持久化
    notif_mod.start_notification_persistence()

    processed = []
    real_insert = notif_mod.insert_notification
    call_count = 0

    def faulty_insert(item, db_path=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise sqlite3.OperationalError("database is locked")
        processed.append(item["title_key"])
        return real_insert(item, db_path=db_path)

    monkeypatch.setattr(notif_mod, "insert_notification", faulty_insert)

    notif_mod.emit_notification("warn", "notif.faulty", message="fail")
    notif_mod.emit_notification("info", "notif.healthy", message="ok")

    # 等待 writer 處理（至多 1 秒）
    deadline = time.time() + 1.0
    while time.time() < deadline:
        if "notif.healthy" in processed:
            break
        time.sleep(0.02)

    assert "notif.healthy" in processed, "Writer thread 應在第一次例外後存活並成功寫入第二筆通知"



def test_insert_notification_trims_db_to_50_rows(tmp_path):
    """DoD-5 (M5): 每次 insert 後，notifications 表修剪至最新 50 列。"""
    import time
    from core.database.connection import init_db, get_connection
    from core.database.notifications import insert_notification

    test_db = tmp_path / "trim_test.db"
    init_db(test_db)

    base_time = time.time()
    for i in range(60):
        row = {
            "id": f"id_{i}",
            "timestamp": base_time + i,
            "level": "info",
            "title_key": f"notif_{i}",
            "message": f"msg_{i}",
            "task_type": None,
        }
        insert_notification(row, db_path=test_db)

    with get_connection(test_db) as conn:
        cursor = conn.cursor()
        count = cursor.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]
        assert count == 50

        # 確認保留的是最新的 50 筆（id_10 到 id_59），最舊的 10 筆（id_0 到 id_9）已被刪除
        rows = cursor.execute("SELECT id FROM notifications ORDER BY timestamp ASC").fetchall()
        retained_ids = [r[0] for r in rows]
        assert "id_0" not in retained_ids
        assert "id_9" not in retained_ids
        assert "id_10" in retained_ids
        assert "id_59" in retained_ids

def test_insert_notification_trim_keeps_newest_when_timestamps_tie(tmp_path):
    """修剪在 timestamp **並列**時仍必須留下最新的那 50 筆（PR review 實測復現的洞）。

    `timestamp` 是 REAL。上面那支 `..._trims_db_to_50_rows` 用 `base_time + i`，
    每一筆的時間戳都不同，所以 `ORDER BY timestamp DESC` 單獨就夠用——它**測不到**
    並列的情況。真的並列時 SQLite 的排序不穩定：只用 timestamp 排序會留下最先插入
    的 50 筆，而剛寫進去的那筆在**它自己這次 insert 之後立刻被刪掉**，與「保留最新
    50 筆」完全相反。決勝靠 `rowid DESC`（隨插入單調遞增）。

    這支測試的來源：本卡 PR review 用相同 SQL 在沙盒裡復現 55 筆同 timestamp 的行為。
    """
    from core.database.connection import init_db, get_connection
    from core.database.notifications import insert_notification, load_recent_notifications

    test_db = tmp_path / "trim_tie_test.db"
    init_db(test_db)

    tied = 1_700_000_000.0  # 60 筆逐位元組相同的 timestamp
    for i in range(60):
        insert_notification(
            {
                "id": f"tie_{i:02d}",
                "timestamp": tied,
                "level": "info",
                "title_key": f"notif_tie_{i}",
                "message": f"msg_{i}",
                "task_type": None,
            },
            db_path=test_db,
        )

    with get_connection(test_db) as conn:
        ids = {r[0] for r in conn.execute("SELECT id FROM notifications").fetchall()}

    assert len(ids) == 50
    # 留下的必須是**後**插入的 tie_10..tie_59，不是先插入的 tie_00..tie_49
    assert ids == {f"tie_{i:02d}" for i in range(10, 60)}
    assert "tie_59" in ids, "最後插入的那筆不得在它自己這次 insert 之後被刪掉"
    assert "tie_00" not in ids

    # loadback 的排序也要用同一個決勝規則，否則重啟後順序與記憶體不一致
    loaded = load_recent_notifications(limit=50, db_path=test_db)
    assert [r["id"] for r in loaded][:3] == ["tie_59", "tie_58", "tie_57"]


def test_calc_highest_unread_level_priority():
    """直接 unit-test helper 函式，不經 API。"""
    from web.routers.notifications import _calc_highest_unread_level
    items = [
        {"id": "a", "level": "info"},
        {"id": "b", "level": "error"},
        {"id": "c", "level": "warn"},
    ]
    assert _calc_highest_unread_level(items, set()) == "error"
    assert _calc_highest_unread_level(items, {"b"}) == "warn"
    assert _calc_highest_unread_level(items, {"a", "b", "c"}) is None


def test_writer_db_path_frozen_at_start_not_resolved_per_item(tmp_path, monkeypatch):
    """writer 要寫哪個 DB，在啟動那一刻就定死，不在消費的當下才去問 `get_db_path()`。

    這條不是防禦性寫法，是 144-T1 開發期實測到的回歸的直接守衛：
    「入列」與「真的寫下去」之間隔著不確定的時間。若寫入端在消費的當下才解析目標，
    那筆通知會落到「那一刻」的 DB 而不是「產生它時」的 DB——實測後果是測試 A 啟動的
    writer 在測試 B 執行期間醒來，拿著已經還原成真實 `output/openaver.db` 的路徑去連，
    被 repo-write 守衛擋下（`RepoWriteGuardViolation` 繼承 `BaseException`，
    writer 的 `except Exception` 接不住）⇒ thread 靜默死亡、佇列只增不減，
    而 `GET` 只讀記憶體所以表面完全正常。

    做法：啟動後把 `get_db_path` 改指向另一個庫，斷言通知仍落在**啟動時**那一個。
    """
    import web.routers.notifications as notif_mod
    from core.database.connection import init_db
    from core.database.notifications import load_recent_notifications

    started_db = tmp_path / "started.db"
    swapped_db = tmp_path / "swapped.db"
    init_db(started_db)
    init_db(swapped_db)

    monkeypatch.setattr("core.database.connection.get_db_path", lambda: started_db)
    notif_mod.stop_notification_persistence()
    notif_mod.start_notification_persistence()
    try:
        # 啟動之後才把路徑換掉——凍結成立的話，下面這筆仍該落在 started_db
        monkeypatch.setattr("core.database.connection.get_db_path", lambda: swapped_db)

        notif_mod.emit_notification("info", "notif.frozen_path_probe", message="frozen")
        notif_mod._write_queue.join()

        landed = [r["title_key"] for r in load_recent_notifications(db_path=started_db)]
        strayed = [r["title_key"] for r in load_recent_notifications(db_path=swapped_db)]
        assert "notif.frozen_path_probe" in landed, (
            "通知沒有落在 writer 啟動時的那個庫——db_path 沒有被凍結"
        )
        assert strayed == [], "通知落到了啟動之後才換上的那個庫——db_path 是在消費當下解析的"
    finally:
        notif_mod.stop_notification_persistence()


def test_start_notification_persistence_is_fail_soft(tmp_path, monkeypatch):
    """讀不到通知歷史時不得拋——App 啟動不能被側欄的歷史通知拖垮。

    lifespan 裡的鄰居（`backfill_readonly_nfo_mtime`、`source_reachability`）都是
    try/except 包起來的，而「側欄的歷史通知」比那兩者都不重要。載不回來就不啟動
    writer（讀不到的庫多半也寫不進去），以純記憶體模式運作。
    """
    import web.routers.notifications as notif_mod

    notif_mod.stop_notification_persistence()

    def _boom():
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr("core.database.connection.get_db_path", _boom)

    notif_mod.start_notification_persistence()  # 不得拋
    assert notif_mod._writer_thread is None, "載不回來時不該啟動 writer thread"

    # 純記憶體模式下 emit 照常可用
    notif_mod.emit_notification("info", "notif.fail_soft_probe", message="still works")
    assert any(
        n["title_key"] == "notif.fail_soft_probe" for n in notif_mod._notifications
    )
