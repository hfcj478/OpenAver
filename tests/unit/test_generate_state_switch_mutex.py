"""test_generate_state_switch_mutex.py — 雙向互斥（PR #93 Codex P1）

switch 全窗口 vs generate 掛號的原子互斥：
- try_begin_switch(): generate 在飛 → 'generate_in_progress'；另一 switch 持窗口 →
  'switch_in_progress'（PR #93 P2 序列化）；否則佔窗口回 None
- try_mark_generate_active(): switch 進行中 → False（reverse guard）；否則登記回 True
- end_switch(): 釋放窗口

純記憶體、無 IO。每測前重置 module 全域避免跨測污染。
"""
import pytest

import core.generate_state as gs


@pytest.fixture(autouse=True)
def _reset_state():
    gs._active_tokens.clear()
    gs._switch_active = False
    gs._config_save_tokens.clear()
    yield
    gs._active_tokens.clear()
    gs._switch_active = False
    gs._config_save_tokens.clear()


class TestSwitchGenerateMutex:
    def test_switch_begins_when_idle(self):
        assert gs.try_begin_switch() is None  # None = 成功佔窗口
        assert gs._switch_active is True
        gs.end_switch()
        assert gs._switch_active is False

    def test_switch_refused_when_generate_active(self):
        assert gs.try_mark_generate_active("gen-token") is True
        # generate 在飛 → switch 不能開始（forward guard）
        assert gs.try_begin_switch() == "generate_in_progress"
        assert gs._switch_active is False

    def test_overlapping_switch_refused_and_first_window_intact(self):
        # PR #93 P2：第二個重疊 switch 必須被拒（否則第一個 end_switch 會在第二個窗口中
        # 清掉 _switch_active，讓 generate 趁隙補回卡）。
        assert gs.try_begin_switch() is None
        assert gs.try_begin_switch() == "switch_in_progress"
        assert gs._switch_active is True  # 第一個窗口仍握住、未被第二個誤設/清掉
        # 第二個被拒期間，generate 仍被第一個窗口擋住
        assert gs.try_mark_generate_active("g") is False
        gs.end_switch()
        assert gs._switch_active is False

    def test_generate_refused_while_switch_active(self):
        assert gs.try_begin_switch() is None
        # 切換窗口中 → 新 generate 掛號被拒（reverse guard，P1 核心）
        assert gs.try_mark_generate_active("gen-token") is False
        assert "gen-token" not in gs._active_tokens
        assert gs.is_generate_in_progress() is False

    def test_generate_allowed_after_switch_ends(self):
        assert gs.try_begin_switch() is None
        assert gs.try_mark_generate_active("t1") is False
        gs.end_switch()
        # 窗口釋放後 generate 可正常掛號
        assert gs.try_mark_generate_active("t1") is True
        assert gs.is_generate_in_progress() is True

    def test_switch_allowed_after_generate_done(self):
        assert gs.try_mark_generate_active("t1") is True
        assert gs.try_begin_switch() == "generate_in_progress"
        gs.mark_generate_done("t1")
        # generate 收尾後 switch 可開始
        assert gs.try_begin_switch() is None

    def test_end_switch_idempotent(self):
        gs.try_begin_switch()
        gs.end_switch()
        gs.end_switch()  # 二次釋放不炸
        assert gs._switch_active is False

    def test_two_generates_coexist_but_block_switch(self):
        assert gs.try_mark_generate_active("a") is True
        assert gs.try_mark_generate_active("b") is True
        assert gs.is_generate_in_progress() is True
        assert gs.try_begin_switch() == "generate_in_progress"
        gs.mark_generate_done("a")
        # 還有一個在飛 → 仍擋 switch
        assert gs.try_begin_switch() == "generate_in_progress"
        gs.mark_generate_done("b")
        assert gs.try_begin_switch() is None


class TestSwitchConfigSaveMutex:
    """PR #93 P2-e / 五審：整份設定儲存 ↔ switch 真互斥，儲存端用 token-set（非 bool）。"""

    def test_config_save_begins_when_idle(self):
        tok = object()
        assert gs.try_begin_config_save(tok) is None
        assert tok in gs._config_save_tokens
        gs.end_config_save(tok)
        assert tok not in gs._config_save_tokens

    def test_switch_refused_while_config_save_active(self):
        # 儲存持窗口中 → switch 不能開始（否則 purge 與存檔 mutate 交錯 → 舊快照寫回）
        tok = object()
        assert gs.try_begin_config_save(tok) is None
        assert gs.try_begin_switch() == "config_save_in_progress"
        assert gs._switch_active is False  # switch 未佔窗口
        assert tok in gs._config_save_tokens  # 儲存窗口仍握住

    def test_config_save_refused_while_switch_active(self):
        # switch purge 窗口中 → 新整份儲存被拒（反向 guard，P2-e 核心）
        assert gs.try_begin_switch() is None
        tok = object()
        assert gs.try_begin_config_save(tok) == "switch_in_progress"
        assert tok not in gs._config_save_tokens

    def test_config_save_allowed_after_switch_ends(self):
        assert gs.try_begin_switch() is None
        tok = object()
        assert gs.try_begin_config_save(tok) == "switch_in_progress"
        gs.end_switch()
        assert gs.try_begin_config_save(tok) is None  # 窗口釋放後可儲存

    def test_switch_allowed_after_config_save_ends(self):
        tok = object()
        assert gs.try_begin_config_save(tok) is None
        assert gs.try_begin_switch() == "config_save_in_progress"
        gs.end_config_save(tok)
        assert gs.try_begin_switch() is None  # 儲存收尾後 switch 可開始

    def test_generate_and_config_save_coexist(self):
        # 儲存不碰 gallery.directories 以外的 generate 語意 → 兩者可並存（只有 switch 被排除）
        assert gs.try_mark_generate_active("g") is True
        tok = object()
        assert gs.try_begin_config_save(tok) is None
        assert tok in gs._config_save_tokens
        assert gs.is_generate_in_progress() is True
        # 但兩者同時在 → switch 被 generate 先擋（reason 順序：generate 先檢查）
        assert gs.try_begin_switch() == "generate_in_progress"

    def test_end_config_save_idempotent(self):
        tok = object()
        gs.try_begin_config_save(tok)
        gs.end_config_save(tok)
        gs.end_config_save(tok)  # 同一 token 二次釋放不炸（discard no-op）
        assert tok not in gs._config_save_tokens

    # --- PR #93 五審 Codex：重疊存檔下第一個結束不得清掉第二個的窗口 ---

    def test_overlapping_saves_first_end_still_blocks_switch(self):
        # 這是 Codex 打回 bool 版的回歸樁：A、B 兩存檔重疊，A 先結束後 switch 仍須被擋
        a, b = object(), object()
        assert gs.try_begin_config_save(a) is None
        assert gs.try_begin_config_save(b) is None  # bool 版也回 None，但共享旗標
        gs.end_config_save(a)  # A 先收尾
        # bool 版此時旗標已 False → switch 誤放行；token-set 下 B 的 token 仍在 → 續擋
        assert gs.try_begin_switch() == "config_save_in_progress"
        assert b in gs._config_save_tokens

    def test_overlapping_saves_both_end_allows_switch(self):
        a, b = object(), object()
        assert gs.try_begin_config_save(a) is None
        assert gs.try_begin_config_save(b) is None
        gs.end_config_save(a)
        gs.end_config_save(b)
        assert not gs._config_save_tokens
        assert gs.try_begin_switch() is None  # 兩者皆收尾 → switch 可進場

    def test_three_way_overlap_switch_blocked_until_all_clear(self):
        # 兩存檔 + 一 generate 同時在飛 → switch 全程被擋，直到三者皆釋放
        a, b = object(), object()
        assert gs.try_mark_generate_active("g") is True
        assert gs.try_begin_config_save(a) is None
        assert gs.try_begin_config_save(b) is None
        assert gs.try_begin_switch() == "generate_in_progress"  # generate 先擋
        gs.mark_generate_done("g")
        assert gs.try_begin_switch() == "config_save_in_progress"  # 換存檔擋
        gs.end_config_save(a)
        assert gs.try_begin_switch() == "config_save_in_progress"  # B 仍在
        gs.end_config_save(b)
        assert gs.try_begin_switch() is None  # 全清 → 放行
