"""feature/90 Finding 2 guard：core/generate_state 純模組單元測試。

登記表讓設定頁 mode-switch 在 generate SSE 進行中拒絕切換（避免 purge 後背景
producer 補回離線來源卡）。這裡只驗純登記表語意（mark/done/is_active、idempotent、
多 token）；handler 生命週期（正常完成 + 斷線兩路徑都清 token）見
test_scanner_generate_disconnect.py。
"""
import core.generate_state as gs


def _reset():
    with gs._lock:
        gs._active_tokens.clear()


def test_empty_registry_not_in_progress():
    _reset()
    assert gs.is_generate_in_progress() is False


def test_mark_active_then_in_progress():
    _reset()
    tok = object()
    gs.mark_generate_active(tok)
    assert gs.is_generate_in_progress() is True
    gs.mark_generate_done(tok)
    assert gs.is_generate_in_progress() is False


def test_mark_done_idempotent_on_absent_token():
    _reset()
    # 對未登記 token discard 不得拋錯（斷線/正常兩路徑可能重複清）。
    gs.mark_generate_done(object())
    assert gs.is_generate_in_progress() is False


def test_multiple_tokens_active_until_all_cleared():
    _reset()
    a, b = object(), object()
    gs.mark_generate_active(a)
    gs.mark_generate_active(b)
    assert gs.is_generate_in_progress() is True
    gs.mark_generate_done(a)
    # 仍有 b 在跑 → 仍算進行中（不可因清掉一個就放行切換）。
    assert gs.is_generate_in_progress() is True
    gs.mark_generate_done(b)
    assert gs.is_generate_in_progress() is False
    _reset()


def test_same_token_marked_twice_single_clear_removes():
    _reset()
    tok = object()
    gs.mark_generate_active(tok)
    gs.mark_generate_active(tok)  # set 冪等
    assert gs.is_generate_in_progress() is True
    gs.mark_generate_done(tok)
    assert gs.is_generate_in_progress() is False
