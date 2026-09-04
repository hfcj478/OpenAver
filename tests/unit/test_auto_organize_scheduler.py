"""tests/unit/test_auto_organize_scheduler.py — 排程 loop 單元測試（TASK-144-T5）。

覆蓋 DoD 1–11 與 mutation 點 M1/M2/M5/M6/M7。
"""
from __future__ import annotations

import contextlib
import os

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from core import auto_organize_state
from web import auto_organize_scheduler as sched


def _empty_result(**overrides):
    base = {
        "added": [],
        "cover_missing": [],
        "failed": [],
        "skipped": {"has_nfo": 0, "memory_hit": 0, "duplicate": []},
        "newly_recorded": 0,
        "wishlist_removed": [],
        "aborted_after": None,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def reset_scheduler_and_state():
    """每個測試前後重置 scheduler 與 auto_organize_state 的模組狀態。"""
    with auto_organize_state._lock:
        auto_organize_state._running = False
        auto_organize_state._current_number = None
        auto_organize_state._abort_requested = False
        auto_organize_state._last_manual_at = float("-inf")
    sched._next_due_at = 0.0
    sched._round_task = None
    yield
    with auto_organize_state._lock:
        auto_organize_state._running = False
        auto_organize_state._current_number = None
        auto_organize_state._abort_requested = False
        auto_organize_state._last_manual_at = float("-inf")
    if sched._round_task is not None and not sched._round_task.done():
        sched._round_task.cancel()
    sched._next_due_at = 0.0
    sched._round_task = None


# ---------------------------------------------------------------------------
# DoD-1：開關與計時
# ---------------------------------------------------------------------------

def test_is_due_first_wake_resets_without_running():
    """DoD-1 / D9：重啟後 _next_due_at==0 → 從零計時、不補跑。"""
    assert sched._next_due_at == 0.0
    assert sched._is_due() is False
    assert sched._next_due_at > time.time()


def test_is_due_true_after_deadline():
    """DoD-1：到期後 _is_due() 為 True。"""
    sched._next_due_at = time.time() - 1.0
    assert sched._is_due() is True


def test_reset_due_time_pushes_interval_forward():
    """DoD-1：reset_due_time 把到期時間推到現在 + 12h。"""
    before = time.time()
    sched.reset_due_time()
    expected = before + sched.AUTO_ORGANIZE_INTERVAL_HOURS * 3600
    assert sched._next_due_at >= expected - 1.0
    assert sched._next_due_at <= expected + 2.0


async def test_loop_skips_when_disabled(monkeypatch):
    """DoD-1：enabled=False → loop 醒來也不跑。"""
    wake_count = {"n": 0}

    async def fake_sleep(_s):
        wake_count["n"] += 1
        if wake_count["n"] >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(sched.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        sched, "load_config",
        lambda: {"search": {"auto_organize": {"enabled": False}}},
    )
    enter_spy = MagicMock(wraps=auto_organize_state.enter_cron)
    monkeypatch.setattr(sched.auto_organize_state, "enter_cron", enter_spy)

    with pytest.raises(asyncio.CancelledError):
        await sched.auto_organize_loop()

    enter_spy.assert_not_called()


async def test_loop_runs_when_enabled_and_due(monkeypatch):
    """DoD-1：enabled=True 且到期 → 跑一輪。"""
    wake_count = {"n": 0}
    sched._next_due_at = time.time() - 1.0

    async def fake_sleep(_s):
        wake_count["n"] += 1
        if wake_count["n"] >= 2:
            raise asyncio.CancelledError()

    run_body = AsyncMock()
    monkeypatch.setattr(sched.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(
        sched, "load_config",
        lambda: {"search": {"auto_organize": {"enabled": True}}},
    )
    monkeypatch.setattr(sched, "_run_round_body", run_body)
    # enter_cron 成功後 _run_round_body 負責 exit；這裡 body 是 mock，手動釋放
    real_enter = auto_organize_state.enter_cron

    def enter_then_release(trigger, now=None):
        ok = real_enter(trigger, now=now)
        if ok:
            auto_organize_state.exit_cron()
        return ok

    monkeypatch.setattr(sched.auto_organize_state, "enter_cron", enter_then_release)

    with pytest.raises(asyncio.CancelledError):
        await sched.auto_organize_loop()

    run_body.assert_awaited()
    assert run_body.await_args.args[0] == "schedule"


# ---------------------------------------------------------------------------
# DoD-2 / DoD-3：enter_and_start（毫秒返回 ＋ trigger 原樣）
# ---------------------------------------------------------------------------

async def test_enter_and_start_returns_immediately_while_round_runs(monkeypatch):
    """DoD-2：enter_and_start 立刻返回，整輪在背景跑。"""
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_body(trigger):
        started.set()
        await release.wait()
        auto_organize_state.exit_cron()

    monkeypatch.setattr(sched, "_run_round_body", slow_body)

    t0 = time.perf_counter()
    result = sched.enter_and_start("run_now")
    elapsed = time.perf_counter() - t0

    assert result == {"success": True, "reason": None}
    assert elapsed < 0.1
    await asyncio.wait_for(started.wait(), timeout=1.0)
    release.set()
    await asyncio.wait_for(sched._round_task, timeout=1.0)


async def test_enter_and_start_already_running():
    """DoD-2：另一輪在跑 → success=False, reason=already_running。"""
    assert auto_organize_state.enter_cron("schedule") is True
    result = sched.enter_and_start("run_now")
    assert result == {"success": False, "reason": "already_running"}


async def test_run_now_succeeds_right_after_manual_activity(monkeypatch):
    """DoD-3 / M1：剛動過手動仍能 run-now（trigger 不得寫死成 schedule）。"""
    auto_organize_state.mark_manual_activity()

    async def noop_body(trigger):
        auto_organize_state.exit_cron()

    monkeypatch.setattr(sched, "_run_round_body", noop_body)

    result = sched.enter_and_start("run_now")
    assert result == {"success": True, "reason": None}
    await asyncio.wait_for(sched._round_task, timeout=1.0)


# ---------------------------------------------------------------------------
# DoD-5 / M7：探測例外仍釋放 running
# ---------------------------------------------------------------------------

async def test_prepare_exception_still_releases_running(monkeypatch):
    """DoD-5 / M7：探測階段拋例外 → running 不得卡住。"""
    assert auto_organize_state.enter_cron("run_now") is True

    def boom(_config):
        raise RuntimeError("probe boom")

    monkeypatch.setattr(sched, "resolve_favorite_folder", boom)
    monkeypatch.setattr(sched, "load_config", lambda: {"search": {}})

    with pytest.raises(RuntimeError, match="probe boom"):
        await sched._run_round_body("run_now")

    assert auto_organize_state.get_status()["running"] is False


# ---------------------------------------------------------------------------
# DoD-4：enter_cron 在探測之前（順序）
# ---------------------------------------------------------------------------

async def test_enter_cron_before_folder_probe_in_enter_and_start(monkeypatch):
    """DoD-4：enter_cron 是第一步；探測排在它之後。"""
    order = []

    real_enter = auto_organize_state.enter_cron

    def tracking_enter(trigger, now=None):
        order.append(("enter_cron", trigger))
        return real_enter(trigger, now=now)

    async def tracking_prepare(trigger):
        order.append(("prepare", trigger))
        auto_organize_state.exit_cron()
        return _empty_result()

    monkeypatch.setattr(sched.auto_organize_state, "enter_cron", tracking_enter)
    monkeypatch.setattr(sched, "_prepare_and_run", tracking_prepare)
    # _run_round_body 會再 exit；prepare 已 exit，再包 round_guard 會 double-exit（無害）
    # 改成直接測 enter_and_start 順序：enter 後才 create_task(prepare)
    monkeypatch.setattr(sched, "_run_round_body", tracking_prepare)

    result = sched.enter_and_start("run_now")
    assert result["success"] is True
    await asyncio.wait_for(sched._round_task, timeout=1.0)

    assert order[0] == ("enter_cron", "run_now")
    assert order[1] == ("prepare", "run_now")


# ---------------------------------------------------------------------------
# DoD-6 / M2：零事件不發通知
# ---------------------------------------------------------------------------

def test_zero_events_does_not_emit(monkeypatch):
    """DoD-6 / M2：事件數 0 → 不發通知。"""
    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)

    sched._emit_round_summary(_empty_result())
    emit.assert_not_called()


def test_nonzero_events_emits_summary(monkeypatch):
    """DoD-6：有新增／失敗 → 發 summary。"""
    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)

    sched._emit_round_summary(_empty_result(added=["ABC-123"], failed=["XYZ-456"]))
    emit.assert_called_once()
    assert emit.call_args.args[0] == "warn"
    assert emit.call_args.args[1] == "notif.auto_organize_summary"
    assert "新增 1 部" in emit.call_args.kwargs["message"]
    assert "失敗 1 部" in emit.call_args.kwargs["message"]


# ---------------------------------------------------------------------------
# DoD-7 / M5：aborted_after 分支
# ---------------------------------------------------------------------------

def test_aborted_after_positive_emits_aborted(monkeypatch):
    """DoD-7：aborted_after > 0 → 發 aborted 通知。"""
    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)

    sched._emit_round_summary(_empty_result(aborted_after=3, added=["A-1"]))
    emit.assert_called_once()
    assert emit.call_args.args[1] == "notif.auto_organize_aborted"
    assert "處理 3 部後因手動操作中止" in emit.call_args.kwargs["message"]


def test_aborted_after_zero_does_not_emit(monkeypatch):
    """DoD-7 / M5：aborted_after == 0 → 不發通知。"""
    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)

    sched._emit_round_summary(_empty_result(aborted_after=0))
    emit.assert_not_called()


def test_aborted_after_none_falls_through_to_event_threshold(monkeypatch):
    """DoD-7：aborted_after is None → 走事件數門檻（零事件不發）。"""
    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)

    sched._emit_round_summary(_empty_result(aborted_after=None))
    emit.assert_not_called()


# ---------------------------------------------------------------------------
# DoD-8 / M6：資料夾探測逾時
# ---------------------------------------------------------------------------

async def test_folder_probe_respects_timeout(monkeypatch):
    """DoD-8 / M6：exists 探測必須有 wait_for 上限；逾時 → folder_unreachable。"""
    monkeypatch.setattr(sched, "_FOLDER_EXISTS_TIMEOUT_S", 0.05)
    monkeypatch.setattr(sched, "load_config", lambda: {"search": {"favorite_folder": "/nas/fav"}})
    monkeypatch.setattr(sched, "resolve_favorite_folder", lambda _c: "/nas/fav")

    def slow_exists(_path):
        time.sleep(0.5)
        return True

    monkeypatch.setattr(sched.os.path, "exists", slow_exists)

    t0 = time.perf_counter()
    result = await sched._prepare_and_run("schedule")
    elapsed = time.perf_counter() - t0

    assert result.get("folder_unreachable") is True
    assert result["folder"] == "/nas/fav"
    assert elapsed < 0.3  # 遠小於 slow_exists 的 0.5s


async def test_folder_unreachable_emits_warn_and_resets(monkeypatch):
    """DoD-8：連不到 → 黃色通知 ＋ reset_due_time。"""
    emit = MagicMock()
    reset = MagicMock(wraps=sched.reset_due_time)
    monkeypatch.setattr(sched, "emit_notification", emit)
    monkeypatch.setattr(sched, "reset_due_time", reset)

    async def fake_prepare(_trigger):
        return {"folder_unreachable": True, "folder": "/gone"}

    monkeypatch.setattr(sched, "_prepare_and_run", fake_prepare)
    assert auto_organize_state.enter_cron("schedule") is True

    await sched._run_round_body("schedule")

    emit.assert_called_once_with(
        "warn", "notif.auto_organize_folder_unreachable",
        message="/gone", task_type="auto_organize",
    )
    reset.assert_called()
    assert auto_organize_state.get_status()["running"] is False


# ---------------------------------------------------------------------------
# DoD-9：唯讀資料夾
# ---------------------------------------------------------------------------

async def test_readonly_emits_warn_and_resets(monkeypatch):
    """DoD-9：readonly → 黃色通知 ＋ reset_due_time。"""
    emit = MagicMock()
    reset = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)
    monkeypatch.setattr(sched, "reset_due_time", reset)

    async def fake_prepare(_trigger):
        return {"readonly": True, "folder": "/ro"}

    monkeypatch.setattr(sched, "_prepare_and_run", fake_prepare)
    assert auto_organize_state.enter_cron("schedule") is True

    await sched._run_round_body("schedule")

    emit.assert_called_once_with(
        "warn", "notif.auto_organize_readonly",
        message="/ro", task_type="auto_organize",
    )
    reset.assert_called()


# ---------------------------------------------------------------------------
# DoD-10：書籤對帳通知（只讀 wishlist_removed，不再呼叫 reconcile）
# ---------------------------------------------------------------------------

async def test_wishlist_removed_emits_formatted_message(monkeypatch):
    """DoD-10：wishlist_removed 非空 → format ＋ emit；不呼叫 reconcile_wishlist。"""
    emit = MagicMock()
    monkeypatch.setattr(sched, "emit_notification", emit)

    reconcile = MagicMock()
    monkeypatch.setattr("core.wishlist_reconcile.reconcile_wishlist", reconcile, raising=False)

    async def fake_prepare(_trigger):
        return _empty_result(
            added=["ABC-123"],
            failed=["XYZ-456"],
            wishlist_removed=["ABC-123"],
        )

    monkeypatch.setattr(sched, "_prepare_and_run", fake_prepare)
    assert auto_organize_state.enter_cron("run_now") is True

    await sched._run_round_body("run_now")

    title_keys = [c.args[1] for c in emit.call_args_list]
    assert "notif.auto_organize_summary" in title_keys
    assert "notif.wishlist_auto_removed" in title_keys
    wishlist_call = next(
        c for c in emit.call_args_list if c.args[1] == "notif.wishlist_auto_removed"
    )
    assert "ABC-123" in wishlist_call.kwargs["message"]
    reconcile.assert_not_called()


# ---------------------------------------------------------------------------
# DoD-11：舊 config 缺 auto_organize key 不得炸
# ---------------------------------------------------------------------------

async def test_missing_auto_organize_key_treated_as_disabled(monkeypatch):
    """DoD-11：缺整個 search.auto_organize → 視為關閉、不拋例外。"""
    wake_count = {"n": 0}

    async def fake_sleep(_s):
        wake_count["n"] += 1
        if wake_count["n"] >= 2:
            raise asyncio.CancelledError()

    monkeypatch.setattr(sched.asyncio, "sleep", fake_sleep)
    # 完全沒有 auto_organize key
    monkeypatch.setattr(sched, "load_config", lambda: {"search": {"favorite_folder": "/x"}})
    enter_spy = MagicMock(wraps=auto_organize_state.enter_cron)
    monkeypatch.setattr(sched.auto_organize_state, "enter_cron", enter_spy)

    with pytest.raises(asyncio.CancelledError):
        await sched.auto_organize_loop()

    enter_spy.assert_not_called()


def test_auto_organize_interval_constant():
    """設計決策 4：間隔寫死 12 小時，與 config 共用同一常數。"""
    from core.config import AUTO_ORGANIZE_INTERVAL_HOURS
    assert AUTO_ORGANIZE_INTERVAL_HOURS == 12
    assert sched.AUTO_ORGANIZE_INTERVAL_HOURS == 12


# ===========================================================================
# Opus 於 review 階段補的兩支守衛（實作交件時這兩條都沒有測試守著）
# ===========================================================================

class TestProbeTimeoutAndLoopSurvival:
    def test_folder_probe_has_a_timeout(self, monkeypatch):
        """資料夾探測必須有逾時上限，否則 NAS 睡著時整條排程會掛住。

        🔴 `asyncio.to_thread()` 自己**永遠不會**拋 `TimeoutError`——少了
        `asyncio.wait_for` 那一層，`except asyncio.TimeoutError` 是死碼，
        而 `os.path.exists()` 會卡在 worker thread 上幾十秒到幾分鐘。
        spec §F6 明文要避免的就是這件事（「否則 NAS 睡著時一次 exists() 卡幾十秒，
        整個網頁介面跟著沒反應，使用者以為當掉去砍程序」）。

        做法：讓探測永遠不返回（模擬睡著的 NAS），斷言 `_prepare_and_run`
        仍在**遠小於**那個 sleep 的時間內回到「連不到」的結論。
        """
        import asyncio as _asyncio
        import time as _time
        from web import auto_organize_scheduler as aos

        monkeypatch.setattr(aos, "_FOLDER_EXISTS_TIMEOUT_S", 0.2)
        monkeypatch.setattr(aos, "load_config", lambda: {})
        monkeypatch.setattr(aos, "resolve_favorite_folder", lambda _cfg: "/nas/asleep")

        # 🔴 只對「我們這一條路徑」變慢：`aos.os` 就是全域 `os` 模組，
        # 無差別 patch 會讓 pytest 自己的每一次 `os.path.exists` 也睡 3 秒，整支測試掛住
        # （第一版就是這樣寫的，當場掛給我看）。
        _real_exists = os.path.exists

        def _slow_only_for_target(path):
            if path == "/nas/asleep":
                # 3 秒（不是 30）：`asyncio.to_thread` 開的 thread **無法被取消**，
                # `asyncio.run()` 收尾時會等 executor 關閉——sleep 多久這支測試就慢多久。
                # 3 秒足以與 0.2 秒的逾時拉開一個數量級。
                _time.sleep(3)
                return True
            return _real_exists(path)

        monkeypatch.setattr(aos.os.path, "exists", _slow_only_for_target)
        # 逾時被拿掉時（mutation）探測會回 True 並往下走到 run_one_round——
        # 那支必須也被擋住，否則 mutation 那一輪會跑進真實刮削而掛住，
        # gate 就看不到「逾時測試轉紅」而是看到逾時。
        monkeypatch.setattr(aos, "run_one_round", lambda *a, **kw: {
            "added": [], "cover_missing": [], "failed": [],
            "skipped": {"has_nfo": 0, "memory_hit": 0, "duplicate": []},
            "newly_recorded": 0, "wishlist_removed": [], "aborted_after": None,
        })

        # 🔴 必須在 coroutine **裡面**量：`asyncio.run()` 收尾時會 join 那條
        # 還在 sleep 的 executor thread（`to_thread` 開的 thread 無法取消），
        # 所以量在 `asyncio.run(...)` 外面會把那 3 秒也算進去——那不是排程被卡住，
        # 是測試自己量錯了地方（第一版就是這樣，量到 3.0s 卻誤判實作有問題）。
        measured = {}

        async def _timed():
            t0 = _time.perf_counter()
            res = await aos._prepare_and_run("schedule")
            measured["elapsed"] = _time.perf_counter() - t0
            return res

        result = _asyncio.run(_timed())

        assert result.get("folder_unreachable") is True
        assert measured["elapsed"] < 1.0, (
            f"探測花了 {measured['elapsed']:.1f}s——沒有逾時上限，NAS 睡著時整條排程會被卡住"
        )

    def test_loop_survives_an_exception_from_one_round(self, monkeypatch):
        """單輪的例外絕不能殺掉 loop。

        `while True` 外沒有 try/except 的話，一次未預期的例外就會讓整條排程
        **靜默停止**——App 還開著、開關還亮著、側欄什麼都不會說，使用者要好幾天
        後才會發現「它怎麼都沒動」。

        做法：讓第一輪拋例外，斷言 loop 仍能跑到第二輪。
        """
        import asyncio as _asyncio
        from core import auto_organize_state
        from web import auto_organize_scheduler as aos

        auto_organize_state.exit_cron()
        auto_organize_state._last_manual_at = float("-inf")

        calls = {"n": 0}

        # 🔴 讓 `_prepare_and_run` 拋，**不要**整支 mock 掉 `_run_round_body`：
        # 釋放 `running` 的 `exit_cron()` 就住在 `_run_round_body` 的 `_round_guard()` 裡，
        # 把它換掉等於連釋放一起拿掉 ⇒ 第二輪會被 `enter_cron()` 正確地擋下，
        # 測試就會誤判成「loop 被例外殺掉了」（第一版就是這樣自己騙自己）。
        async def _boom(trigger):
            calls["n"] += 1
            raise RuntimeError("這一輪炸了")

        monkeypatch.setattr(aos, "_prepare_and_run", _boom)
        monkeypatch.setattr(aos, "_LOOP_POLL_INTERVAL_S", 0)
        monkeypatch.setattr(aos, "_is_due", lambda: True)
        monkeypatch.setattr(
            aos, "load_config",
            lambda: {"search": {"auto_organize": {"enabled": True}}},
        )

        async def _drive():
            task = _asyncio.create_task(aos.auto_organize_loop())
            # 用真的 sleep 而不是 `sleep(0)`：loop 內有 `await asyncio.to_thread(load_config)`，
            # 那需要真的把控制權交回 event loop 才輪得到 worker thread 完成。
            for _ in range(200):
                await _asyncio.sleep(0.01)
                if calls["n"] >= 2:
                    break
            task.cancel()
            with contextlib.suppress(_asyncio.CancelledError):
                await task

        _asyncio.run(_drive())
        auto_organize_state.exit_cron()

        assert calls["n"] >= 2, (
            "第一輪拋例外之後 loop 就沒有再跑第二輪——排程被單輪的例外殺掉了"
        )


    def test_loop_survives_an_exception_from_load_config(self, monkeypatch):
        """讀 config 拋例外也不能殺掉 loop（PR review 指出第一版的 try 漏掉這一行）。

        `config.json` 被外部程序改壞、或磁碟一時 I/O 錯誤，都會從
        `await asyncio.to_thread(load_config)` 拋出來——那跟「一輪炸了」是同一類洞，
        只是觸發點不同。使用者看到的症狀一模一樣：**排程靜默停止，開關還亮著、
        側欄什麼都不說，只有重啟 App 才救得回來。**
        """
        import asyncio as _asyncio
        from core import auto_organize_state
        from web import auto_organize_scheduler as aos

        auto_organize_state.exit_cron()
        auto_organize_state._last_manual_at = float("-inf")

        calls = {"n": 0}

        def _boom_config():
            calls["n"] += 1
            raise OSError("config.json 讀不動")

        monkeypatch.setattr(aos, "load_config", _boom_config)
        monkeypatch.setattr(aos, "_LOOP_POLL_INTERVAL_S", 0)

        async def _drive():
            task = _asyncio.create_task(aos.auto_organize_loop())
            for _ in range(200):
                await _asyncio.sleep(0.01)
                if calls["n"] >= 2:
                    break
            task.cancel()
            with contextlib.suppress(_asyncio.CancelledError):
                await task

        _asyncio.run(_drive())
        auto_organize_state.exit_cron()

        assert calls["n"] >= 2, (
            "讀 config 拋例外之後 loop 就沒有再醒來——排程被它殺掉了"
        )


    def test_load_config_failure_does_not_push_the_schedule_out(self, monkeypatch):
        """讀不到設定時**不得**重置到期時間（PR review 指出第一版重置得太重）。

        「一輪炸了」重置是對的——否則每 5 分鐘重試一次，把一次失敗放大成連續轟炸。
        但「連設定都讀不到」是另一回事：那個到期窗**根本沒被消耗**，下一次 5 分鐘
        輪詢本來就會重試。在那裡重置等於**因為一次磁碟抖動就把排程整整推走 12 小時**，
        恢復之後使用者還要再等半天才會看到它動。
        """
        import asyncio as _asyncio
        from core import auto_organize_state
        from web import auto_organize_scheduler as aos

        auto_organize_state.exit_cron()
        aos._next_due_at = 1.0  # 遠古＝早就到期

        def _boom_config():
            raise OSError("config.json 讀不動")

        monkeypatch.setattr(aos, "load_config", _boom_config)
        monkeypatch.setattr(aos, "_LOOP_POLL_INTERVAL_S", 0)

        async def _drive():
            task = _asyncio.create_task(aos.auto_organize_loop())
            for _ in range(50):
                await _asyncio.sleep(0.01)
            task.cancel()
            with contextlib.suppress(_asyncio.CancelledError):
                await task

        _asyncio.run(_drive())

        assert aos._next_due_at == 1.0, (
            "讀設定失敗把到期時間往後推了——那個窗根本沒被消耗，"
            "這樣一次磁碟抖動就會讓排程停擺 12 小時"
        )

    def test_newly_recorded_alone_is_enough_to_emit(self, monkeypatch):
        """只有「本輪新寫進失敗記憶」也算事件，必須發通知（CD-144-3 公式第四項）。

        PR review 指出：把 `+ result["newly_recorded"]` 從事件數公式裡拿掉，
        原本的測試**全綠**——也就是那一項沒有任何守衛。
        使用者後果：一輪裡每一部都查無結果（只寫進失敗記憶、沒有新增／失敗／缺封面
        任何一項落在那三個清單裡）時，**側欄完全沉默**，使用者以為排程根本沒跑過。
        """
        from web import auto_organize_scheduler as aos

        emitted = []
        monkeypatch.setattr(
            aos, "emit_notification",
            lambda level, key, message="", task_type=None: emitted.append(key),
        )

        aos._emit_round_summary({
            "added": [], "cover_missing": [], "failed": [],
            "skipped": {"has_nfo": 0, "memory_hit": 0, "duplicate": []},
            "newly_recorded": 2,
            "wishlist_removed": [],
            "aborted_after": None,
        })

        assert "notif.auto_organize_summary" in emitted, (
            "只有 newly_recorded 非零時沒有發通知——事件數公式漏掉了第四項"
        )


# ---------------------------------------------------------------------------
# v0.15.13 P2-2：run-now 的 detached task 沒有自己的例外處理，使用者永遠等不到
# 任何結果（側欄一片安靜）。回歸鎖 enter_and_start() 真正 create_task 出去的
# 那個 coroutine（不是直接呼叫 _run_round_body），確保例外被攔下、不逃逸成
# asyncio 的 "Task exception was never retrieved"，且有一則固定文案的失敗通知。
# ---------------------------------------------------------------------------

async def test_enter_and_start_exception_is_caught_and_notified(monkeypatch):
    """run-now 背景例外必須被攔下：不吞掉、不裸露例外細節、running 要釋放。

    重現方式：讓 `_prepare_and_run`（資料夾解析／探測／`run_one_round()` 那一段，
    `_round_guard()` 真正保護的主體）拋一個帶內部細節的例外——**不**整支 mock 掉
    `_run_round_body`，否則 `_round_guard()` 的 finally 根本不會跑到，running
    永遠不會被釋放，會誤判成 wrapper 沒接住例外。透過 `enter_and_start()`
    （不是直接呼叫 `_run_round_body`）啟動，await 它真正建立的 `_round_task`，
    斷言：
    1. 例外沒有從 task 逃逸出去（`_round_task.exception()` 為 None，不是
       `_round_task` 本身 raise）——否則就是 "Task exception was never
       retrieved" 那個洞還在。
    2. 發出的通知是固定的 `notif.auto_organize_failed`，且訊息裡**不含**例外
       原文（不可把內部路徑／SQL 洩到畫面上）。
    3. `auto_organize_state` 的 running 有被釋放（`_round_guard()` 的 finally
       仍然跑到）。
    """
    from core import auto_organize_state

    secret_detail = "sqlite3.OperationalError: no such table: /internal/path/leak"

    async def boom(trigger):
        raise RuntimeError(secret_detail)

    monkeypatch.setattr(sched, "_prepare_and_run", boom)

    emitted = []
    monkeypatch.setattr(
        sched, "emit_notification",
        lambda level, key, message="", task_type=None: emitted.append(
            (level, key, message, task_type)
        ),
    )

    result = sched.enter_and_start("run_now")
    assert result == {"success": True, "reason": None}

    # 不能直接 `await sched._round_task` 期待它乾淨結束後再檢查——重點正是
    # 「即使 body 拋例外，這個 task 本身也不可以再往外拋」。用 wait_for 確保
    # 它會結束（不是掛住），再看它是否真的沒有帶著例外收尾。
    await asyncio.wait_for(sched._round_task, timeout=1.0)
    assert sched._round_task.exception() is None, (
        "detached task 帶著例外結束——沒人 await 它，會變成 "
        "'Task exception was never retrieved' 噪音，使用者側也看不到任何通知"
    )

    assert len(emitted) == 1, f"預期恰好一則失敗通知，實際：{emitted!r}"
    level, key, message, task_type = emitted[0]
    assert level == "error"
    assert key == "notif.auto_organize_failed"
    assert task_type == "auto_organize"
    assert secret_detail not in message, (
        "失敗通知的 message 洩漏了例外原文——內部路徑／SQL 不該出現在畫面上"
    )

    assert auto_organize_state.get_status()["running"] is False, (
        "背景例外之後 running 沒有被釋放——下一輪 run-now 會被永久卡在 already_running"
    )
