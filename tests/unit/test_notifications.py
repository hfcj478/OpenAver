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
    """DoD-3 (M1): 同 title_key 且同 message 在**還沒被看過**之前不重複寫入。"""
    from web.routers.notifications import emit_notification, _notifications, _read_ids
    emit_notification("info", "notif.update_available", message="v1.0.0")
    assert len(_notifications) == 1
    first_id = _notifications[0]["id"]
    first_time = _notifications[0]["timestamp"]

    # 連發相同 title_key 且相同 message（都還沒讀過）→ 合併，時間戳不動
    emit_notification("info", "notif.update_available", message="v1.0.0")
    assert len(_notifications) == 1
    assert _notifications[0]["id"] == first_id
    assert _notifications[0]["timestamp"] == first_time
    assert first_id not in _read_ids

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


def test_emit_notification_stays_memory_only_and_never_blocks(monkeypatch):
    """DoD-2: emit_notification 必須維持「純記憶體」——這條路徑上一次 DB 連線都不准發生。

    契約三件事，缺一不可：
    1. **零 DB 連線**：整個呼叫期間 `sqlite3.connect` 的呼叫次數必須是 0。
    2. **不卡**：呼叫耗時 < 0.1 秒。
    3. **真的做了事**：那筆通知確實進了記憶體那一份。

    ⚠️ **為什麼第 1 條是計數而不是「patch 成會拋、然後斷言沒拋」**（T8 review，grok 實測）：
    `emit_notification()` 本身根本不碰 DB（寫入在背景 thread），所以把 `sqlite3.connect`
    patch 成拋例外時，**那個 patch 在受測路徑上是死碼**——實測呼叫次數 0 ⇒
    「沒有拋出來」是恆真的，什麼都沒證明。更糟的是它會誤導：把同步 `insert_notification`
    搬回這條路徑的 mutation 之所以轉紅，是因為那個 patch **讓它拋了**，
    不是因為耗時斷言——沒有 patch 時同步寫入只花約 40ms，`< 0.1s` 抓不住它。
    而只要有人把同步寫入包進 `try/except` 吞掉，三條舊斷言就會**全綠**。

    改成計數之後，「裸的同步寫入」與「包 try/except 吞掉的同步寫入」**兩種都擋得住**，
    而且不依賴任何時間門檻。DB 真的鎖住時的存活由
    `test_writer_thread_survives_db_locked_exception`（背景 thread 那條）負責，不在這裡重複。
    """
    import time
    import uuid
    from web.routers.notifications import emit_notification, _notifications

    connect_calls = []
    real_connect = sqlite3.connect

    def _counting_connect(*args, **kwargs):
        connect_calls.append(args[0] if args else None)
        return real_connect(*args, **kwargs)

    monkeypatch.setattr("sqlite3.connect", _counting_connect)

    # 去重早退防呆（邊界條件②）：emit_notification() 對「同 title_key ＋ 同 message」
    # 會提早 return，不走 appendleft／put_nowait。用唯一值確保走完整條路徑，
    # 否則下面三條斷言都會在一個根本沒執行的路徑上假綠。
    unique_key = f"notif.test_unique_{uuid.uuid4()}"
    unique_msg = f"msg_{uuid.uuid4()}"

    t0 = time.perf_counter()
    emit_notification("info", unique_key, message=unique_msg)
    elapsed = time.perf_counter() - t0

    assert connect_calls == [], (
        f"emit_notification 在呼叫端開了 DB 連線：{connect_calls!r}。"
        "這條路徑必須維持純記憶體（appendleft ＋ put_nowait）——"
        "一旦有人把同步 DB 寫入搬回來，批次補完 SSE 那條熱路徑會被 DB 鎖卡住。"
    )
    assert elapsed < 0.1, f"emit_notification 呼叫耗時過長：{elapsed:.4f}s >= 0.1s"
    assert any(
        n["title_key"] == unique_key and n["message"] == unique_msg
        for n in _notifications
    ), "通知沒有真的進到記憶體那一份（前兩條斷言在空操作上也會綠）"


def test_app_shutdown_drains_notification_writer_queue(tmp_path, monkeypatch):
    """v0.15.13 P2-1 回歸：關閉 App 時，還在佇列裡的通知不能被 daemon writer
    thread 直接砍掉。

    重現方式：真的跑一次 `web.app` 完整 lifespan（`TestClient(app)` 進出就是
    startup ＋ shutdown），startup 完成後立刻 emit 一筆通知，**不**手動呼叫
    `stop_notification_persistence()`、也不手動 `queue.join()`——完全依賴
    shutdown 自己把佇列排空。斷言那筆通知真的落到 DB：若 shutdown 沒有 join
    writer thread，process（測試裡是 `with` block 結束）就會在 thread 還沒消化
    完佇列前繼續往下，這筆通知永遠不會被寫進去。
    """
    import asyncio
    import uuid
    from unittest.mock import AsyncMock, patch

    from fastapi.testclient import TestClient

    import web.routers.notifications as notif_mod
    from core.database.connection import get_connection, init_db

    test_db = tmp_path / "shutdown_test.db"
    init_db(test_db)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: test_db)
    monkeypatch.setattr("core.access_auth.get_db_path", lambda: tmp_path / "access.db")

    from web.app import app

    async def _hang_forever():
        await asyncio.Event().wait()

    with patch("web.app.auto_organize_loop", _hang_forever), \
         patch("web.app.startup_reconnect", return_value=None), \
         patch("web.app.source_reachability") as mock_sr:
        mock_sr.schedule_reprobe_if_stale = AsyncMock(return_value=None)
        unique_key = f"notif.test_shutdown_drain_{uuid.uuid4()}"
        with TestClient(app):
            notif_mod.emit_notification("info", unique_key)
        # `with` 區塊結束＝TestClient.__exit__ 已經跑完 lifespan shutdown。

    conn = get_connection(test_db)
    try:
        rows = conn.execute(
            "SELECT title_key FROM notifications WHERE title_key = ?", (unique_key,)
        ).fetchall()
    finally:
        conn.close()
    assert rows, (
        "shutdown 沒有把 writer 佇列排空——關閉 App 時最後那筆通知遺失了"
    )


def test_items_queued_after_sentinel_are_still_written(tmp_path, monkeypatch):
    """v0.15.13：排在**哨兵後面**的通知也要落地——由 writer 自己在退出前排空。

    真實來源：run-now 那一輪的 detached task、掃描頁的縮圖預熱 daemon thread
    （`web/routers/scanner.py:1535`）、scanner 的 `_work` daemon thread（`:283`）。
    它們在「哨兵已入列、writer 還沒讀到」的空隙 emit 的東西會排在哨兵後面。

    ⚠️ **順序用兩個 Event 釘死，不靠時序碰運氣**（Codex 五審 P3）：
    先前的寫法是「emit 第一筆 → 馬上呼叫 stop()」，靠「writer 醒來＋寫一筆 SQLite
    比主執行緒下一行 put_nowait 慢」來讓哨兵先入列。實務上幾乎必定成立（實測單筆約
    18ms），但**不保證**——若 OS 剛好先排到 writer，late 那筆會排在哨兵**前面**，
    於是就算把 `_drain_before_exit()` 拿掉測試照樣綠，mutation 收據就是假的。

    這裡改成明確構造：writer 寫完第一筆後**卡住**，主執行緒此時才放哨兵，
    放完再放行讓它 emit late——late 保證在哨兵之後。
    """
    import threading
    import uuid
    from contextlib import closing

    import web.routers.notifications as notif_mod
    from core.database.connection import get_connection, init_db

    test_db = tmp_path / "after_sentinel.db"
    init_db(test_db)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: test_db)

    late_key = f"notif.test_late_{uuid.uuid4()}"
    first_key = f"notif.test_first_{uuid.uuid4()}"

    first_written = threading.Event()   # writer：第一筆寫完了
    sentinel_queued = threading.Event()  # 主執行緒：哨兵已入列，你可以 emit late 了

    real_apply = notif_mod._apply_write
    fired = []

    def apply_then_wait_then_emit_late(item, db_path):
        real_apply(item, db_path)
        if fired:
            return
        fired.append(True)
        first_written.set()
        assert sentinel_queued.wait(timeout=5), "主執行緒沒有在時限內放哨兵"
        notif_mod.emit_notification("info", late_key)

    notif_mod.start_notification_persistence()
    writer = notif_mod._writer_thread
    assert writer is not None, "前提不成立：writer 沒起來"
    monkeypatch.setattr(notif_mod, "_apply_write", apply_then_wait_then_emit_late)

    notif_mod.emit_notification("info", first_key)
    assert first_written.wait(timeout=5), "writer 沒有處理第一筆"

    notif_mod._write_queue.put_nowait(None)  # 哨兵：明確排在 late 之前
    sentinel_queued.set()
    writer.join(timeout=5)
    assert not writer.is_alive(), "writer 沒有在時限內退出"
    notif_mod.stop_notification_persistence()  # 清掉 module-level 指標

    with closing(get_connection(test_db)) as conn:
        keys = {r[0] for r in conn.execute("SELECT title_key FROM notifications").fetchall()}
    assert first_key in keys
    assert late_key in keys, (
        "排在哨兵後面的通知沒被寫出去——writer 退出前沒有把佇列排空"
    )


def test_stop_notification_persistence_is_bounded_by_its_timeout(tmp_path, monkeypatch):
    """`stop_notification_persistence()` 的牆鐘 ≤ timeout ＋ ε，**不管佇列裡有什麼**。

    這一條是為了把一個我先前用散文宣稱、卻沒有任何測試量過的東西釘死。
    先前兩版都由 shutdown 那一側在 join 之後再去消費佇列，於是關閉時間會被
    **單筆 SQLite 寫入**拖長（`get_connection()` 用 sqlite 預設鎖等待，約 5 秒），
    「2 秒上限」那句話是假的。單一消費者形狀下 stop() 只做「放哨兵 ＋ join(timeout)」，
    上限由 join 自己保證，與 DB 快慢完全解耦。

    使用者流程：關掉 App 時畫面卡住不消失。
    """
    import threading
    import time

    import web.routers.notifications as notif_mod

    notif_mod.stop_notification_persistence()  # 清場

    # 佇列裡塞東西，並讓「寫一筆」非常慢——若 stop() 自己去消費就會被拖住
    notif_mod._write_queue.put_nowait({"op": "insert", "id": "x", "timestamp": 0,
                                       "level": "info", "title_key": "k",
                                       "message": "", "task_type": None})
    monkeypatch.setattr(notif_mod, "_apply_write",
                        lambda item, db_path: time.sleep(3.0))

    release = threading.Event()
    stuck = threading.Thread(target=lambda: release.wait(timeout=10),
                             name="StuckWriter", daemon=True)
    stuck.start()
    monkeypatch.setattr(notif_mod, "_writer_thread", stuck)

    try:
        t0 = time.perf_counter()
        notif_mod.stop_notification_persistence(timeout=0.1)
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, (
            f"stop() 花了 {elapsed:.2f}s，遠超它自己的 timeout=0.1s"
            "——關閉時間被 DB 寫入拖住了"
        )
    finally:
        release.set()
        stuck.join(timeout=2)
        with notif_mod._write_queue.mutex:
            notif_mod._write_queue.queue.clear()


def test_read_notification_does_not_silence_the_next_occurrence():
    """pre-merge SA-pre-9 P2-2：使用者看過之後，同一件事再發生要重新出聲。

    使用者流程：開著定時整理 → 第一次失敗，側欄出現一則紅色「定時整理失敗」→
    使用者打開通知抽屜（`base.html` 的 toggleDrawer 會 POST /notifications/read
    把當下全部標讀）→ 之後每 12 小時又失敗一次，但去重只比對記憶體 deque
    ⇒ **側欄再也不出現任何東西、未讀角標也不亮**，使用者以為排程在跑，
    其實幾週來一部片都沒整理到。

    這支釘的就是「已讀之後不再被去重吃掉」。
    """
    from web.routers.notifications import emit_notification, _notifications, _read_ids

    emit_notification("error", "notif.auto_organize_failed", message="")
    assert len(_notifications) == 1
    first_id = _notifications[0]["id"]

    # 使用者打開抽屜 → 全部標讀
    _read_ids.add(first_id)

    # 12 小時後同一件事再發生
    emit_notification("error", "notif.auto_organize_failed", message="")

    assert len(_notifications) == 2, (
        "已讀之後同內容再發生必須新增一筆，否則背景失敗會永遠靜默"
    )
    newest = _notifications[0]
    assert newest["id"] != first_id
    assert newest["id"] not in _read_ids, "新那筆必須是未讀，未讀角標才會亮"


def test_dedup_still_applies_when_an_unread_copy_exists_among_read_ones():
    """反向鎖：deque 裡同時有已讀與未讀的同內容時，仍然不得再新增。

    只寫上面那支的話，把去重整段刪掉也會綠。這支保證「未讀清單裡恆為一則」
    ——spec §F5「連續相同狀況只發一次」那半沒有被這次修改弄壞。
    """
    from web.routers.notifications import emit_notification, _notifications, _read_ids

    emit_notification("error", "notif.auto_organize_failed", message="")
    _read_ids.add(_notifications[0]["id"])          # 第一則：已讀
    emit_notification("error", "notif.auto_organize_failed", message="")   # 第二則：未讀
    assert len(_notifications) == 2

    emit_notification("error", "notif.auto_organize_failed", message="")   # 第三次
    assert len(_notifications) == 2, (
        "已經有一則未讀的同內容通知在了，不得再堆第二則未讀"
    )
