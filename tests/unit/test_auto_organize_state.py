"""tests/unit/test_auto_organize_state.py - 自動整理狀態模組單元測試

覆蓋 TASK-144-T4a DoD 1-5, 8, 10 與生命週期驗證。
"""

import pytest
from unittest.mock import patch
from core import auto_organize_state


@pytest.fixture(autouse=True)
def reset_state():
    """每個測試前後重置 auto_organize_state 的模組狀態。"""
    with auto_organize_state._lock:
        auto_organize_state._running = False
        auto_organize_state._current_number = None
        auto_organize_state._abort_requested = False
        auto_organize_state._last_manual_at = float("-inf")
    yield
    with auto_organize_state._lock:
        auto_organize_state._running = False
        auto_organize_state._current_number = None
        auto_organize_state._abort_requested = False
        auto_organize_state._last_manual_at = float("-inf")


def test_schedule_blocked_by_running_cron():
    """DoD-1: enter_cron('schedule') 另一輪在跑時拒絕。"""
    assert auto_organize_state.enter_cron("schedule", now=1000.0) is True
    # 另一輪已在跑，應拒絕
    assert auto_organize_state.enter_cron("schedule", now=2000.0) is False


def test_schedule_blocked_by_recent_manual_activity():
    """DoD-1 / mutation M2: enter_cron('schedule') 最近 10 分鐘有人動過時拒絕。"""
    auto_organize_state.mark_manual_activity(now=1000.0)
    # 500 秒 < 600 秒，應被擋下
    assert auto_organize_state.enter_cron("schedule", now=1500.0) is False
    # 邊界值：剛好 600 秒（1600 - 1000 == 600，not < 600），應成功進場
    assert auto_organize_state.enter_cron("schedule", now=1600.0) is True


def test_run_now_blocked_only_by_running_cron():
    """DoD-2: enter_cron('run_now') 另一輪在跑時拒絕。"""
    assert auto_organize_state.enter_cron("run_now", now=1000.0) is True
    assert auto_organize_state.enter_cron("run_now", now=2000.0) is False


def test_run_now_not_blocked_by_recent_manual_activity():
    """DoD-2 / mutation M1: enter_cron('run_now') 不受最近手動操作影響。"""
    auto_organize_state.mark_manual_activity(now=1000.0)
    # 10 秒前才剛動過手動操作，run_now 仍應成功進場
    assert auto_organize_state.enter_cron("run_now", now=1010.0) is True


def test_request_abort_sets_flag_when_running():
    """DoD-3: request_abort 在 running 為真時設旗標，且具冪等性。"""
    assert auto_organize_state.enter_cron("schedule") is True
    assert auto_organize_state.should_abort() is False

    auto_organize_state.request_abort()
    assert auto_organize_state.should_abort() is True

    # 冪等：連呼兩次結果相同
    auto_organize_state.request_abort()
    assert auto_organize_state.should_abort() is True


def test_request_abort_noop_when_not_running():
    """DoD-3 / mutation M3: request_abort 在沒在跑時不得設旗標。"""
    assert auto_organize_state.get_status()["running"] is False
    auto_organize_state.request_abort()
    assert auto_organize_state.should_abort() is False


def test_mark_manual_activity_does_not_touch_abort_requested():
    """DoD-4 / mutation M4: mark_manual_activity 只寫 _last_manual_at，不碰 abort_requested。"""
    assert auto_organize_state.should_abort() is False
    auto_organize_state.mark_manual_activity(now=1000.0)
    assert auto_organize_state.should_abort() is False
    assert auto_organize_state._last_manual_at == 1000.0


def test_get_status_is_read_only():
    """DoD-5 / mutation M5: get_status 純讀不改變任何狀態，回傳僅含 running 與 current_number。"""
    assert auto_organize_state.enter_cron("run_now") is True
    auto_organize_state.set_current_number("ABC-123")
    auto_organize_state.request_abort()
    auto_organize_state.mark_manual_activity(now=12345.0)

    # 驗證連續呼叫 100 次，四個 module-level 變數逐一不變
    for _ in range(100):
        status = auto_organize_state.get_status()
        assert set(status.keys()) == {"running", "current_number"}
        assert status["running"] is True
        assert status["current_number"] == "ABC-123"

        assert auto_organize_state._running is True
        assert auto_organize_state._current_number == "ABC-123"
        assert auto_organize_state._abort_requested is True
        assert auto_organize_state._last_manual_at == 12345.0


def test_enter_cron_now_injection():
    """DoD-8: 可注入時鐘 - enter_cron 未傳 now 時使用 _now() 且不拋出例外。"""
    with patch.object(auto_organize_state, "_now", return_value=5000.0):
        assert auto_organize_state.enter_cron("schedule") is True
    auto_organize_state.exit_cron()

    auto_organize_state.mark_manual_activity(now=4800.0)
    with patch.object(auto_organize_state, "_now", return_value=5000.0):
        # 5000 - 4800 = 200 < 600
        assert auto_organize_state.enter_cron("schedule") is False


def test_mark_manual_activity_now_injection():
    """DoD-8: 可注入時鐘 - mark_manual_activity 未傳 now 時使用 _now() 且不拋出例外。"""
    with patch.object(auto_organize_state, "_now", return_value=9999.0):
        auto_organize_state.mark_manual_activity()
    assert auto_organize_state._last_manual_at == 9999.0


def test_exit_cron_clears_all_fields():
    """DoD-10 / mutation M7: exit_cron 清場，三個 cron 側變數重設。"""
    assert auto_organize_state.enter_cron("run_now") is True
    auto_organize_state.set_current_number("ABC-123")
    auto_organize_state.request_abort()

    assert auto_organize_state._running is True
    assert auto_organize_state._current_number == "ABC-123"
    assert auto_organize_state._abort_requested is True

    auto_organize_state.exit_cron()

    assert auto_organize_state._running is False
    assert auto_organize_state._current_number is None
    assert auto_organize_state._abort_requested is False


def test_abort_lifecycle_end_to_end():
    """Oracle: 完整中止生命週期端到端驗證。"""
    assert auto_organize_state.enter_cron("schedule") is True
    auto_organize_state.set_current_number("ABC-123")
    assert auto_organize_state.get_status() == {"running": True, "current_number": "ABC-123"}

    # 模擬 favorite-files handler 觸發中止請求
    auto_organize_state.request_abort()
    assert auto_organize_state.should_abort() is True

    # cron 迴圈看到 abort 請求後退出
    auto_organize_state.exit_cron()
    assert auto_organize_state.get_status() == {"running": False, "current_number": None}
    assert auto_organize_state.should_abort() is False
