"""Unit tests for core.enrich_contract — cover_uri_is_servable / compute_has_servable_cover.

Bug 1 (feature/105) 四組正交邊界：
1. DB 有 cover_path + 檔在磁碟 → True
2. DB 有 cover_path + 檔已刪 → False（Bug 1 核心）
3. 無 row / cover_path 空 → False（短路，不呼叫 os.path.exists）
4. path-mapping 解不到（uri_to_local_fs_path 回不存在路徑）→ False
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

from core.enrich_contract import cover_uri_is_servable, compute_has_servable_cover


# ── cover_uri_is_servable ────────────────────────────────────────────────────

class TestCoverUriIsServable:
    def test_cover_present_and_file_exists_true(self, mocker):
        mocker.patch("core.enrich_contract.os.path.exists", return_value=True)
        assert cover_uri_is_servable("file:///out/ABC-001/ABC-001.jpg", {}) is True

    def test_cover_present_but_file_deleted_false(self, mocker):
        """Bug 1 核心：DB 有 cover_path 但實體檔已被刪 → False。"""
        mocker.patch("core.enrich_contract.os.path.exists", return_value=False)
        assert cover_uri_is_servable("file:///out/ABC-001/ABC-001.jpg", {}) is False

    def test_empty_cover_short_circuits_without_disk_check(self, mocker):
        """cover_uri 空 → 短路 False，os.path.exists 不得被呼叫。"""
        m_exists = mocker.patch("core.enrich_contract.os.path.exists", return_value=True)
        assert cover_uri_is_servable("", {}) is False
        m_exists.assert_not_called()

    def test_path_mapping_unresolvable_false(self, mocker):
        """path-mapping 解不到 → uri_to_local_fs_path 回不存在路徑 → os.path.exists False。"""
        # 不 mock os.path.exists；用一個保證不存在的路徑，讓真實磁碟檢查回 False。
        assert cover_uri_is_servable(
            "file:///nonexistent-drive/definitely/not/here-xyz.jpg", {}
        ) is False


# ── compute_has_servable_cover ───────────────────────────────────────────────

class TestComputeHasServableCover:
    def _repo(self, cover_path):
        repo = MagicMock()
        repo.get_by_path.return_value = SimpleNamespace(cover_path=cover_path)
        return repo

    def test_db_has_cover_and_file_exists_true(self, mocker):
        mocker.patch("core.enrich_contract.os.path.exists", return_value=True)
        repo = self._repo("file:///out/ABC-001/ABC-001.jpg")
        assert compute_has_servable_cover(repo, "file:///src/ABC-001.mp4", {}) is True

    def test_db_has_cover_but_file_deleted_false(self, mocker):
        """Bug 1 核心：DB row 殘留 cover_path、磁碟檔已刪 → False。"""
        mocker.patch("core.enrich_contract.os.path.exists", return_value=False)
        repo = self._repo("file:///out/ABC-001/ABC-001.jpg")
        assert compute_has_servable_cover(repo, "file:///src/ABC-001.mp4", {}) is False

    def test_no_row_false_short_circuits(self, mocker):
        """無 row → cover_path '' → False，os.path.exists 不得被呼叫。"""
        m_exists = mocker.patch("core.enrich_contract.os.path.exists", return_value=True)
        repo = MagicMock()
        repo.get_by_path.return_value = None
        assert compute_has_servable_cover(repo, "file:///src/ABC-001.mp4", {}) is False
        m_exists.assert_not_called()

    def test_empty_cover_path_false_short_circuits(self, mocker):
        m_exists = mocker.patch("core.enrich_contract.os.path.exists", return_value=True)
        repo = self._repo("")
        assert compute_has_servable_cover(repo, "file:///src/ABC-001.mp4", {}) is False
        m_exists.assert_not_called()

    def test_path_mapping_unresolvable_false(self):
        """path-mapping 解不到 → 真實磁碟檢查回 False（不 mock os.path.exists）。"""
        repo = self._repo("file:///nonexistent-drive/definitely/not/here-xyz.jpg")
        assert compute_has_servable_cover(repo, "file:///src/ABC-001.mp4", {}) is False

    def test_uses_given_path_uri_key(self, mocker):
        """compute 必須用傳入的 path_uri 當 get_by_path 的 key（upsert 寫入同 key）。"""
        mocker.patch("core.enrich_contract.os.path.exists", return_value=True)
        repo = self._repo("file:///out/x.jpg")
        compute_has_servable_cover(repo, "file:///the/canonical/key.mp4", {})
        repo.get_by_path.assert_called_once_with("file:///the/canonical/key.mp4")
