"""
test_readonly_source.py — core/readonly_source.py 純函式直測（TASK-90c-T2）

兩個無 IO 純函式：
- is_path_readonly(file_uri, readonly_prefixes) -> bool
- readonly_source_prefixes(gallery_config, path_mappings) -> list

純邏輯、無 IO → 直接傳 dict/list，無需 mock。
"""

from core.readonly_source import (
    is_path_readonly,
    readonly_source_prefixes,
    writable_source_prefixes,
)
from core.path_utils import to_file_uri


class TestIsPathReadonly:
    """is_path_readonly：無 IO 純比對。"""

    def test_hit_returns_true(self):
        prefix = to_file_uri("/tmp/ro_src", {})
        file_uri = to_file_uri("/tmp/ro_src/ABC-001.mp4", {})
        assert is_path_readonly(file_uri, [prefix]) is True

    def test_miss_returns_false(self):
        prefix = to_file_uri("/tmp/ro_src", {})
        file_uri = to_file_uri("/tmp/rw_src/ABC-001.mp4", {})
        assert is_path_readonly(file_uri, [prefix]) is False

    def test_empty_prefixes_returns_false(self):
        file_uri = to_file_uri("/tmp/ro_src/ABC-001.mp4", {})
        assert is_path_readonly(file_uri, []) is False

    def test_hit_among_multiple_prefixes(self):
        p1 = to_file_uri("/tmp/other", {})
        p2 = to_file_uri("/tmp/ro_src", {})
        file_uri = to_file_uri("/tmp/ro_src/ABC-001.mp4", {})
        assert is_path_readonly(file_uri, [p1, p2]) is True

    def test_unc_prefix_hit(self):
        prefix = to_file_uri(r"\\server\share", {})
        file_uri = to_file_uri(r"\\server\share\ABC-001.mp4", {})
        assert is_path_readonly(file_uri, [prefix]) is True

    def test_canonical_file_uri_prefix(self):
        # 來源已是 canonical file:/// URI，片也是 → 命中
        prefix = "file:///D:/ro"
        file_uri = "file:///D:/ro/ABC.mp4"
        assert is_path_readonly(file_uri, [prefix]) is True

    # --- PR #93 Codex P2：可寫來源巢狀在唯讀夾下時 override（is_readonly_source=False）---

    def test_writable_nested_under_readonly_overrides(self):
        # 唯讀 D:/media + 可寫 D:/media/local；片在可寫子夾 → 不算唯讀（可寫 override）
        ro = to_file_uri("/tmp/media", {})
        wo = to_file_uri("/tmp/media/local", {})
        file_uri = to_file_uri("/tmp/media/local/ABC-001.mp4", {})
        assert is_path_readonly(file_uri, [ro], [wo]) is False

    def test_readonly_sibling_not_overridden(self):
        # 片在唯讀夾其他子路徑（非可寫子夾）→ 仍唯讀
        ro = to_file_uri("/tmp/media", {})
        wo = to_file_uri("/tmp/media/local", {})
        file_uri = to_file_uri("/tmp/media/other/ABC-001.mp4", {})
        assert is_path_readonly(file_uri, [ro], [wo]) is True

    def test_deeper_writable_nesting_overrides(self):
        # 可寫子夾下更深子目錄的片 → 仍 override（is_path_under_dir 任意深度）
        ro = to_file_uri("/tmp/media", {})
        wo = to_file_uri("/tmp/media/local", {})
        file_uri = to_file_uri("/tmp/media/local/sub/deep/ABC.mp4", {})
        assert is_path_readonly(file_uri, [ro], [wo]) is False

    def test_writable_prefixes_none_is_backward_compatible(self):
        # writable_prefixes 省略/None → 退回純唯讀比對（舊呼叫相容）
        ro = to_file_uri("/tmp/media", {})
        file_uri = to_file_uri("/tmp/media/ABC.mp4", {})
        assert is_path_readonly(file_uri, [ro]) is True
        assert is_path_readonly(file_uri, [ro], None) is True

    def test_writable_override_only_applies_when_readonly_hit(self):
        # 片不落唯讀前綴 → 早退 False，可寫前綴不影響結論
        ro = to_file_uri("/tmp/media", {})
        wo = to_file_uri("/tmp/other", {})
        file_uri = to_file_uri("/tmp/elsewhere/ABC.mp4", {})
        assert is_path_readonly(file_uri, [ro], [wo]) is False

    # --- PR #93 二審 P2-a：反向巢狀（可寫父 + 唯讀子）→ 最具體(唯讀子)勝，仍唯讀 ---

    def test_readonly_nested_under_writable_stays_readonly(self):
        # 可寫父 D:/media + 唯讀子 D:/media/cloud；片在唯讀子夾 → 唯讀子更具體 → True
        # （這正是上一輪「任一可寫壓唯讀」修法弄壞的反向 case，最具體前綴勝修回）
        wo = to_file_uri("/tmp/media", {})
        ro = to_file_uri("/tmp/media/cloud", {})
        file_uri = to_file_uri("/tmp/media/cloud/ABC-001.mp4", {})
        assert is_path_readonly(file_uri, [ro], [wo]) is True

    def test_readonly_nested_deeper_stays_readonly(self):
        wo = to_file_uri("/tmp/media", {})
        ro = to_file_uri("/tmp/media/cloud", {})
        file_uri = to_file_uri("/tmp/media/cloud/sub/deep/ABC.mp4", {})
        assert is_path_readonly(file_uri, [ro], [wo]) is True

    def test_writable_sibling_under_writable_parent_not_readonly(self):
        # 可寫父下、非唯讀子夾的片 → 只命中可寫 → False
        wo = to_file_uri("/tmp/media", {})
        ro = to_file_uri("/tmp/media/cloud", {})
        file_uri = to_file_uri("/tmp/media/other/ABC.mp4", {})
        assert is_path_readonly(file_uri, [ro], [wo]) is False

    def test_equal_length_prefix_tiebreak_favours_writable(self):
        # 同一路徑同時屬唯讀與可寫兩表（設定自相矛盾）→ 打平偏可寫（保守放行讀取判定）
        same = to_file_uri("/tmp/media", {})
        file_uri = to_file_uri("/tmp/media/ABC.mp4", {})
        assert is_path_readonly(file_uri, [same], [same]) is False


class TestWritableSourcePrefixes:
    """writable_source_prefixes：枚舉可寫（非唯讀）來源 → coerce 成前綴集（鏡射 readonly 版）。"""

    def test_writable_source_filtered_in(self):
        gallery = {"directories": [{"path": "/tmp/rw_src", "readonly": False}]}
        assert writable_source_prefixes(gallery, {}) == [to_file_uri("/tmp/rw_src", {})]

    def test_readonly_source_filtered_out(self):
        gallery = {"directories": [{"path": "/tmp/ro_src", "readonly": True}]}
        assert writable_source_prefixes(gallery, {}) == []

    def test_bare_str_source_is_writable(self):
        # 裸 str → iter_gallery_sources 降級 readonly=False → 視為可寫、計入
        gallery = {"directories": ["/tmp/bare_src"]}
        assert writable_source_prefixes(gallery, {}) == [to_file_uri("/tmp/bare_src", {})]

    def test_mixed_only_writable_kept(self):
        gallery = {
            "directories": [
                {"path": "/tmp/ro_src", "readonly": True},
                {"path": "/tmp/rw_src", "readonly": False},
                "/tmp/bare_src",
            ]
        }
        prefixes = writable_source_prefixes(gallery, {})
        assert prefixes == [to_file_uri("/tmp/rw_src", {}), to_file_uri("/tmp/bare_src", {})]

    def test_empty_gallery_returns_empty(self):
        assert writable_source_prefixes({}, {}) == []
        assert writable_source_prefixes({"directories": []}, {}) == []

    def test_source_missing_path_skipped(self):
        gallery = {"directories": [{"path": "", "readonly": False}]}
        assert writable_source_prefixes(gallery, {}) == []

    def test_dirty_source_raising_valueerror_skipped(self, mocker):
        good_prefix = to_file_uri("/tmp/rw_good", {})

        def fake_canonical(value, mappings=None):
            if value == "DIRTY":
                raise ValueError("dirty path")
            return good_prefix

        mocker.patch("core.readonly_source._canonical_source_prefix", side_effect=fake_canonical)
        gallery = {
            "directories": [
                {"path": "DIRTY", "readonly": False},
                {"path": "/tmp/rw_good", "readonly": False},
            ]
        }
        assert writable_source_prefixes(gallery, {}) == [good_prefix]


class TestReadonlySourcePrefixes:
    """readonly_source_prefixes：枚舉唯讀來源 → coerce 成前綴集。"""

    def test_readonly_source_filtered_in(self):
        gallery = {"directories": [{"path": "/tmp/ro_src", "readonly": True}]}
        prefixes = readonly_source_prefixes(gallery, {})
        assert prefixes == [to_file_uri("/tmp/ro_src", {})]

    def test_writable_source_filtered_out(self):
        gallery = {"directories": [{"path": "/tmp/rw_src", "readonly": False}]}
        assert readonly_source_prefixes(gallery, {}) == []

    def test_bare_str_source_filtered_out(self):
        # 裸 str 來源 → iter_gallery_sources 降級 readonly=False → 不計入
        gallery = {"directories": ["/tmp/bare_src"]}
        assert readonly_source_prefixes(gallery, {}) == []

    def test_empty_gallery_returns_empty(self):
        assert readonly_source_prefixes({}, {}) == []
        assert readonly_source_prefixes({"directories": []}, {}) == []

    def test_mixed_only_readonly_kept(self):
        gallery = {
            "directories": [
                {"path": "/tmp/ro_src", "readonly": True},
                {"path": "/tmp/rw_src", "readonly": False},
                "/tmp/bare_src",
            ]
        }
        prefixes = readonly_source_prefixes(gallery, {})
        assert prefixes == [to_file_uri("/tmp/ro_src", {})]

    def test_source_missing_path_skipped(self):
        gallery = {"directories": [{"path": "", "readonly": True}]}
        assert readonly_source_prefixes(gallery, {}) == []

    def test_dirty_source_raising_valueerror_skipped(self, mocker):
        """_canonical_source_prefix 拋 ValueError 的髒來源 → skip、不使整批拋。"""
        good_prefix = to_file_uri("/tmp/ro_good", {})

        def fake_canonical(value, mappings=None):
            if value == "DIRTY":
                raise ValueError("dirty path")
            return good_prefix

        mocker.patch("core.readonly_source._canonical_source_prefix", side_effect=fake_canonical)
        gallery = {
            "directories": [
                {"path": "DIRTY", "readonly": True},
                {"path": "/tmp/ro_good", "readonly": True},
            ]
        }
        prefixes = readonly_source_prefixes(gallery, {})
        assert prefixes == [good_prefix]


class TestP2fUriSourcePrefixMapping:
    """PR #93 Codex P2-f：file:/// URI 型來源在 WSL+path_mappings 下也要套映射對齊 DB。

    coerce_to_file_uri 對「已是 file:/// URI」的來源原樣回、不套 mappings；但 producer 存
    DB row 的 path 走 to_file_uri(FS, mappings) → mapped 命名空間。改用 _canonical_source_prefix
    後 URI 型來源也走 uri_to_fs_path→to_file_uri(mappings)，落同一命名空間 → 匹配得上。

    CI 是純 Linux，to_file_uri 的 mapping 分支只在 CURRENT_ENV=='wsl' 生效 → 需 monkeypatch
    core.path_utils.CURRENT_ENV='wsl'（readonly_source 未自行 import CURRENT_ENV，單 patch 即可）。
    """

    MAPPINGS = {"/home/user/nas/ro": "//NAS/share/ro"}

    def _db_row_path(self):
        # producer 存 DB row 的 canonical path：掃描 FS 路徑走 to_file_uri(mappings)
        return to_file_uri("/home/user/nas/ro/ABC-001/ABC-001.mp4", self.MAPPINGS)

    def test_uri_form_readonly_source_prefix_is_mapped(self, monkeypatch):
        import core.path_utils as pu
        monkeypatch.setattr(pu, "CURRENT_ENV", "wsl")
        # 來源在 config 存成未映射的 file:/// URI（DirectoryConfig.path 允許 URI 形）
        gallery = {"directories": [{"path": "file:///home/user/nas/ro", "readonly": True}]}
        prefixes = readonly_source_prefixes(gallery, self.MAPPINGS)
        # 前綴應落 mapped 命名空間（//NAS/share/ro），而非原樣的 /home/user/nas/ro
        assert prefixes == ["file://///NAS/share/ro"]
        # 且能匹配到 producer 存的 mapped DB row（修前 coerce 原樣回 → miss）
        assert is_path_readonly(self._db_row_path(), prefixes) is True

    def test_uri_form_source_unmapped_would_miss_before_fix(self, monkeypatch):
        import core.path_utils as pu
        monkeypatch.setattr(pu, "CURRENT_ENV", "wsl")
        # 回歸樁：舊 coerce 行為（原樣回 unmapped URI）對不上 mapped DB row
        unmapped_prefix = "file:///home/user/nas/ro"
        assert is_path_readonly(self._db_row_path(), [unmapped_prefix]) is False

    def test_writable_uri_form_source_prefix_is_mapped(self, monkeypatch):
        import core.path_utils as pu
        monkeypatch.setattr(pu, "CURRENT_ENV", "wsl")
        gallery = {"directories": [{"path": "file:///home/user/nas/ro", "readonly": False}]}
        prefixes = writable_source_prefixes(gallery, self.MAPPINGS)
        assert prefixes == ["file://///NAS/share/ro"]

    def test_fs_path_source_no_mapping_unchanged(self, monkeypatch):
        # 非映射命中的 FS-path 來源 → 等價原 coerce 行為（無回歸）
        import core.path_utils as pu
        monkeypatch.setattr(pu, "CURRENT_ENV", "wsl")
        gallery = {"directories": [{"path": "/tmp/ro_src", "readonly": True}]}
        assert readonly_source_prefixes(gallery, self.MAPPINGS) == [to_file_uri("/tmp/ro_src", {})]

    def test_non_wsl_uri_source_canonicalized_to_db_namespace(self, monkeypatch):
        # 非 WSL：mapping 分支不觸發，但 URI 型 posix 來源仍被 canonical 成 producer 存 DB
        # row 的同一形（to_file_uri("/data/ro") → file:////data/ro，4 斜線）。舊 coerce 對
        # URI 型原樣回 3 斜線，反而對不上 DB 的 4 斜線 row —— 修法連非映射情境也一併對齊。
        import core.path_utils as pu
        monkeypatch.setattr(pu, "CURRENT_ENV", "linux")
        gallery = {"directories": [{"path": "file:///data/ro", "readonly": True}]}
        prefixes = readonly_source_prefixes(gallery, self.MAPPINGS)
        assert prefixes == [to_file_uri("/data/ro", {})]
        # 與 producer 存的 DB row（同走 to_file_uri）匹配得上
        db_row = to_file_uri("/data/ro/ABC-001/ABC-001.mp4", {})
        assert is_path_readonly(db_row, prefixes) is True
