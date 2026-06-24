"""
T1: Showcase scroll-triggered toolbar collapse guard
守衛 state-base.js 包含 scroll listener、toolbarOpen 條件、search/actressSearch 條件、
相對基準 Y 追蹤（_toolbarOpenY）、以及 cleanup。
"""
from pathlib import Path


class TestShowcaseScrollCollapse:
    """T1: Showcase scroll-triggered toolbar collapse guard"""

    def _read_state_base(self):
        p = Path("web/static/js/pages/showcase/state-base.js")
        return p.read_text()

    def test_scroll_listener_registered(self):
        """state-base.js 必須包含 scroll listener 登記（passive）"""
        content = self._read_state_base()
        assert "addEventListener('scroll'" in content or 'addEventListener("scroll"' in content

    def test_scroll_collapse_checks_toolbar_open(self):
        """scroll handler 必須檢查 toolbarOpen 才能收合"""
        content = self._read_state_base()
        assert "toolbarOpen" in content

    def test_scroll_collapse_checks_empty_search(self):
        """scroll handler 必須在 search 為空時才收合"""
        content = self._read_state_base()
        assert "search !== ''" in content or "search === ''" in content

    def test_scroll_collapse_checks_actress_search(self):
        """scroll handler 必須同時保護 actressSearch 非空情況"""
        content = self._read_state_base()
        assert "actressSearch" in content

    def test_scroll_collapse_uses_relative_threshold(self):
        """scroll handler 使用相對基準 Y（_toolbarOpenY）而非絕對位置"""
        content = self._read_state_base()
        assert "_toolbarOpenY" in content

    def test_scroll_listener_cleanup(self):
        """cleanup callback 必須移除 scroll listener"""
        content = self._read_state_base()
        assert "removeEventListener" in content
        assert "_scrollHideHandler" in content
