"""
tests/unit/test_organize_failures.py — 失敗記憶資料層測試（TASK-144-T2）

覆蓋 DoD 1–11 與 mutation 點 M1–M6。
"""
import ast
import inspect
import sqlite3
from pathlib import Path
import pytest

from core.database.connection import init_db, get_connection
from core.path_utils import get_environment, normalize_path


@pytest.fixture
def test_db(tmp_path):
    db_path = tmp_path / "test_failures.db"
    init_db(db_path)
    return db_path


def test_schema_zero_migration(tmp_path):
    """DoD-1: 建表零遷移，init_db() 自動建立 organize_failures 表且欄位完全符合。"""
    db_path = tmp_path / "init_test.db"
    init_db(db_path)

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        # 驗證表格存在
        tables = [
            r[0] for r in cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='organize_failures'"
            ).fetchall()
        ]
        assert "organize_failures" in tables

        # 驗證欄位名稱與型態
        columns = {
            row[1]: {"type": row[2].upper(), "notnull": row[3], "dflt_value": row[4], "pk": row[5]}
            for row in cursor.execute("PRAGMA table_info(organize_failures)").fetchall()
        }
        assert "key" in columns
        assert columns["key"]["pk"] == 1
        assert "reason" in columns
        assert columns["reason"]["notnull"] == 1
        assert "number" in columns
        assert columns["number"]["notnull"] == 1
        assert "duplicate_target" in columns
        assert "attempt_count" in columns
        assert "last_failed_at" in columns
        assert columns["last_failed_at"]["notnull"] == 1

    # 再次呼叫 init_db 不應報錯（IF NOT EXISTS 冪等）
    init_db(db_path)


def test_should_skip_within_24h_window(test_db):
    """DoD-2 (M1): 寫入一筆 not_found → last_failed_at + 23h 查為 True；+ 25h 為 False。"""
    from core.database.organize_failures import record_failure, should_skip

    t0 = 1_700_000_000.0
    record_failure("not_found", "ABP-123", "ABP-123", now=t0, db_path=test_db)

    # 23 小時後：在 24 小時退避窗內 → 應跳過 (True)
    assert should_skip("not_found", "ABP-123", now=t0 + 23 * 3600, db_path=test_db) is True

    # 25 小時後：已過 24 小時退避窗 → 不跳過 (False)
    assert should_skip("not_found", "ABP-123", now=t0 + 25 * 3600, db_path=test_db) is False


def test_record_failure_increments_attempt_count(test_db):
    """DoD-5 (M4): 同鍵連呼叫 record_failure 三次 → attempt_count==3，最後時間戳與 target 覆寫。"""
    from core.database.organize_failures import record_failure

    key = "TEST-KEY"
    t1, t2, t3 = 1000.0, 2000.0, 3000.0
    record_failure("duplicate", key, "ABP-123", duplicate_target="target1.mp4", now=t1, db_path=test_db)
    record_failure("duplicate", key, "ABP-123", duplicate_target="target2.mp4", now=t2, db_path=test_db)
    record_failure("duplicate", key, "ABP-123", duplicate_target="target3.mp4", now=t3, db_path=test_db)

    with get_connection(test_db) as conn:
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT attempt_count, last_failed_at, duplicate_target FROM organize_failures WHERE key = ?",
            (key,),
        ).fetchone()
        assert row is not None
        assert row[0] == 3
        assert row[1] == t3
        assert row[2] == "target3.mp4"


def test_should_skip_7d_window(test_db):
    """DoD-3 (M2): 同一鍵第二次失敗（attempt_count 變 2）→ + 6 天為 True；+ 8 天為 False。"""
    from core.database.organize_failures import record_failure, should_skip

    t0 = 1_700_000_000.0
    record_failure("not_found", "ABP-123", "ABP-123", now=t0, db_path=test_db)

    # 第二次失敗，時間戳為 t1
    t1 = t0 + 25 * 3600
    record_failure("not_found", "ABP-123", "ABP-123", now=t1, db_path=test_db)

    # 6 天後：在 7 天退避窗內 → 應跳過 (True)
    assert should_skip("not_found", "ABP-123", now=t1 + 6 * 86400, db_path=test_db) is True

    # 8 天後：已過 7 天退避窗 → 不跳過 (False)
    assert should_skip("not_found", "ABP-123", now=t1 + 8 * 86400, db_path=test_db) is False


def test_should_skip_unknown_key_returns_false(test_db):
    """DoD-4 (M3): 查一個表裡沒有的鍵 → should_skip 回 False（從未失敗過，非已過期）。"""
    from core.database.organize_failures import should_skip, record_failure

    # 空表查詢
    assert should_skip("not_found", "UNKNOWN-999", db_path=test_db) is False

    # 表裡有其他鍵時查詢不存在的鍵
    record_failure("not_found", "EXIST-001", "EXIST-001", db_path=test_db)
    assert should_skip("not_found", "UNKNOWN-999", db_path=test_db) is False
    assert should_skip("duplicate", "EXIST-001", db_path=test_db) is False


def test_clear_on_success_only_clears_not_found(test_db):
    """DoD-6 (M5): clear_on_success 刪除 not_found 列，同番號的 duplicate 列必須還在。"""
    from core.database.organize_failures import record_failure, clear_on_success

    number = "MIDE-456"
    dup_key = "file:///path/to/MIDE-456-4K.mp4"

    # 同番號記一筆 not_found 與一筆 duplicate
    record_failure("not_found", number, number, db_path=test_db)
    record_failure("duplicate", dup_key, number, duplicate_target="MIDE-456.mp4", db_path=test_db)

    # 呼叫 clear_on_success
    clear_on_success(number, db_path=test_db)

    with get_connection(test_db) as conn:
        cursor = conn.cursor()
        # not_found 必須被清除
        nf_row = cursor.execute(
            "SELECT 1 FROM organize_failures WHERE reason = 'not_found' AND key = UPPER(?)",
            (number,),
        ).fetchone()
        assert nf_row is None

        # duplicate 必須依然存在
        dup_row = cursor.execute(
            "SELECT 1 FROM organize_failures WHERE reason = 'duplicate' AND key = ?",
            (dup_key,),
        ).fetchone()
        assert dup_row is not None

    # M5 邊界守衛：若存在 reason='duplicate' 且 key 正好等於 number 的列，clear_on_success 絕不得刪除
    record_failure("duplicate", "DUP-SAME-KEY", "DUP-SAME-KEY", duplicate_target="x.mp4", db_path=test_db)
    clear_on_success("DUP-SAME-KEY", db_path=test_db)
    with get_connection(test_db) as conn:
        row = conn.cursor().execute(
            "SELECT 1 FROM organize_failures WHERE reason = 'duplicate' AND key = 'DUP-SAME-KEY'"
        ).fetchone()
        assert row is not None, "clear_on_success 絕不得誤刪 reason='duplicate' 的列"


def test_case_insensitive_key(test_db):
    """DoD-7 (M6): 番號大小寫不敏感，record_failure 用小寫，should_skip 與 clear_on_success 用大寫/小寫/混合。"""
    from core.database.organize_failures import record_failure, should_skip, clear_on_success

    # 小寫寫入（SQL UPPER 存為大寫 ABC-123）
    record_failure("not_found", "abc-123", "abc-123", now=1_700_000_000.0, db_path=test_db)

    # 小寫查詢必須命中（若 WHERE 去掉 UPPER(?) 則 abc-123 != ABC-123 會回 False，M6 即被抓出）
    assert should_skip("not_found", "abc-123", now=1_700_000_000.0 + 3600, db_path=test_db) is True

    # 大寫查詢也應命中
    assert should_skip("not_found", "ABC-123", now=1_700_000_000.0 + 3600, db_path=test_db) is True

    # 混合大小寫清除
    clear_on_success("aBc-123", db_path=test_db)

    # 清除後大寫查應回 False（從未失敗過 / 已清空）
    assert should_skip("not_found", "ABC-123", now=1_700_000_000.0 + 3600, db_path=test_db) is False


def test_injectable_clock_and_monkeypatch(test_db, monkeypatch):
    """DoD-8 (BE-TEST-18): 支援注入時鐘，monkeypatch _now 之後不傳 now 的呼叫也生效，且無裸 time.time。"""
    import core.database.organize_failures as mod

    # 1. 驗證 monkeypatch 替換 _now
    fake_time = 1_800_000_000.0
    monkeypatch.setattr(mod, "_now", lambda: fake_time)

    # 不傳 now 呼叫 record_failure
    mod.record_failure("not_found", "CLOCK-1", "CLOCK-1", db_path=test_db)

    with get_connection(test_db) as conn:
        row = conn.cursor().execute(
            "SELECT last_failed_at FROM organize_failures WHERE key = UPPER('CLOCK-1')"
        ).fetchone()
        assert row[0] == fake_time

    # 不傳 now 呼叫 should_skip（此時 fake_time + 10s 在 24h 窗內）
    monkeypatch.setattr(mod, "_now", lambda: fake_time + 10.0)
    assert mod.should_skip("not_found", "CLOCK-1", db_path=test_db) is True

    # 2. 靜態檢查：除了 _now 函式定義外，不得出現裸的 time.time()
    source_path = Path(mod.__file__)
    source_tree = ast.parse(source_path.read_text(encoding="utf-8"))

    for node in ast.walk(source_tree):
        if isinstance(node, ast.FunctionDef) and node.name != "_now":
            # 在其他函式中檢查有沒有 time.time 呼叫
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Attribute) and func.attr == "time":
                        if isinstance(func.value, ast.Name) and func.value.id == "time":
                            pytest.fail(f"函式 {node.name} 中發現裸的 time.time() 呼叫（行 {child.lineno}）")


def test_duplicate_key_normalization_and_signature():
    """DoD-9: duplicate_key 是唯一入口，path_mappings 無預設值，且兩種路徑回傳相同鍵。"""
    from core.database.organize_failures import duplicate_key

    # 1. 簽章檢查：path_mappings 是必要參數，沒有預設值
    sig = inspect.signature(duplicate_key)
    params = sig.parameters
    assert "path_mappings" in params
    assert params["path_mappings"].default is inspect.Parameter.empty

    with pytest.raises(TypeError):
        duplicate_key("/some/path/video.mp4")  # type: ignore

    # 2. 契約檢查：同一檔案在原生路徑與 normalize_path 路徑下回傳相同鍵
    #
    # ⚠️ 取樣路徑必須跟著當前環境走，不可寫死 Windows 路徑：
    # `path_utils` 在**純 Linux／Mac 上對 `C:\...` 直接拋 ValueError**
    # （`core/path_utils.py:166`），而開發機是 WSL、那裡 Windows 路徑合法。
    # 寫死 `C:\Videos\...` 的話本機全綠、CI（ubuntu-latest）單獨紅——
    # 這支測試 2026-09-05 就是這樣讓 PR #181 的 CI 掛掉的，
    # 而「只含追蹤檔的乾淨樹」那種 parity 驗法**抓不到**（它驗的是檔案，不是環境）。
    if get_environment() in ("wsl", "windows"):
        raw_path = "C:\\Videos\\Folder\\ABP-123.mp4"
    else:
        raw_path = "/videos/folder/ABP-123.mp4"
    norm_path = normalize_path(raw_path)
    mappings = {}

    key1 = duplicate_key(raw_path, mappings)
    key2 = duplicate_key(norm_path, mappings)
    assert key1 == key2
    assert key1.startswith("file:///")


def test_adjudication_7_not_found_shared_by_different_paths(test_db):
    """DoD-10 (裁決⑦): 同番號兩個來源路徑記 not_found，其中一個清掉後另一個的 should_skip 也回 False。"""
    from core.database.organize_failures import record_failure, should_skip, clear_on_success

    number = "SHARED-777"

    # 兩個不同來源都失敗（not_found 以番號為鍵）
    record_failure("not_found", number, number, db_path=test_db)
    record_failure("not_found", number, number, db_path=test_db)

    # 兩個來源查詢都是 True
    assert should_skip("not_found", number, db_path=test_db) is True

    # 第一個來源成功入庫
    clear_on_success(number, db_path=test_db)

    # 兩個來源查詢都變 False
    assert should_skip("not_found", number, db_path=test_db) is False


def test_organize_failures_is_leaf_no_web_import():
    """DoD-11: organize_failures.py 是 leaf，不得 load_config()，不得 import 任何 web.*。"""
    repo_root = Path(__file__).resolve().parent.parent.parent
    target_file = repo_root / "core" / "database" / "organize_failures.py"
    tree = ast.parse(target_file.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("web"), f"禁止 import web 模組: {alias.name}"
                assert "load_config" not in alias.name, "禁止 load_config"
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            assert not node.module.startswith("web"), f"禁止 from web import: {node.module}"
            for alias in node.names:
                assert alias.name != "load_config", "禁止 import load_config"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "load_config":
                pytest.fail("禁止呼叫 load_config()")


def test_facade_reexport():
    """設計決策 6: core.database facade 匯出 organize_failures 模組本身。"""
    from core import database

    assert hasattr(database, "organize_failures")
    assert "organize_failures" in database.__all__
    assert hasattr(database.organize_failures, "should_skip")
    assert hasattr(database.organize_failures, "record_failure")
    assert hasattr(database.organize_failures, "clear_on_success")
    assert hasattr(database.organize_failures, "duplicate_key")


def test_clear_on_success_non_existent_key_does_not_raise(test_db):
    """邊界條件: clear_on_success 對不存在的鍵呼叫時安全返回，不拋出例外。"""
    from core.database.organize_failures import clear_on_success

    # 不應拋出任何例外
    clear_on_success("NON-EXISTENT-KEY", db_path=test_db)


def test_attempt_count_beyond_2_always_7d_window(test_db):
    """邊界條件: attempt_count >= 2 時（例如 3, 4），退避窗固定為 7 天。"""
    from core.database.organize_failures import record_failure, should_skip

    t0 = 1_700_000_000.0
    key = "RETRY-MANY"
    for i in range(5):
        record_failure("not_found", key, key, now=t0 + i * 10, db_path=test_db)

    # 經過 5 次失敗，attempt_count == 5
    last_time = t0 + 40
    # 6 天後仍應跳過
    assert should_skip("not_found", key, now=last_time + 6 * 86400, db_path=test_db) is True
    # 8 天後不應跳過
    assert should_skip("not_found", key, now=last_time + 8 * 86400, db_path=test_db) is False


def test_duplicate_key_is_case_sensitive_not_uppercased(test_db):
    """`duplicate` 的鍵是路徑 URI，**逐字原樣存**，不得比照番號做大小寫正規化。

    使用者流程（本功能的目標平台就是這一種）：片庫放在 NAS／Linux（區分大小寫），
    最愛資料夾裡同時有 `/videos/abc-123.mp4` 與 `/videos/ABC-123.mp4` 兩個**不同的**檔案
    → 其中一個因為「目標已存在」被記進失敗記憶 → 若鍵被大寫化，兩者會撞成同一列
    → **另一個檔也跟著被跳過**，最長 7 天不會被自動整理，而使用者看不出為什麼。

    這同時是 CD-144-8「以 `to_file_uri(fs_path, path_mappings)` 正規化後存」的字面要求
    ——大寫化不是正規化。
    """
    from core.database.organize_failures import record_failure, should_skip

    lower_key = "file:///videos/abc-123.mp4"
    upper_key = "file:///videos/ABC-123.mp4"
    base = 1_700_000_000.0

    record_failure("duplicate", lower_key, "ABC-123", duplicate_target="x.mp4",
                   now=base, db_path=test_db)

    assert should_skip("duplicate", lower_key, now=base + 60, db_path=test_db) is True
    assert should_skip("duplicate", upper_key, now=base + 60, db_path=test_db) is False, (
        "大小寫不同的路徑是兩個不同的檔案，不該共用同一筆失敗記憶"
    )

    # 兩者各自記一筆之後必須是兩列，不是一列
    record_failure("duplicate", upper_key, "ABC-123", duplicate_target="y.mp4",
                   now=base, db_path=test_db)
    with get_connection(test_db) as conn:
        n = conn.cursor().execute(
            "SELECT COUNT(*) FROM organize_failures WHERE reason = 'duplicate'"
        ).fetchone()[0]
    assert n == 2, "兩個大小寫不同的路徑必須各自佔一列"


def test_not_found_key_still_case_insensitive(test_db):
    """反向鎖：番號那一種**仍然**要大小寫不敏感（`abc-123` 與 `ABC-123` 是同一部片）。

    與上一支合起來夾住 `_normalize_key()` 的兩側——只放寬 `duplicate`，不得把 `not_found`
    一起放寬。
    """
    from core.database.organize_failures import record_failure, should_skip, clear_on_success

    base = 1_700_000_000.0
    record_failure("not_found", "abc-123", "abc-123", now=base, db_path=test_db)

    assert should_skip("not_found", "ABC-123", now=base + 60, db_path=test_db) is True
    assert should_skip("not_found", "AbC-123", now=base + 60, db_path=test_db) is True

    clear_on_success("aBc-123", db_path=test_db)
    assert should_skip("not_found", "ABC-123", now=base + 60, db_path=test_db) is False


def test_should_skip_boundary_is_strictly_less_than_window(test_db):
    """退避窗的邊界是**嚴格小於**：剛好滿一個窗的那一刻算「可以重查」，不算命中。

    兩位 reviewer 各自獨立指出既有測試只取 23h／25h、6d／8d，**沒有一支釘住
    `now - last_failed_at == window` 那一格**——把 `<` 改成 `<=` 現有測試會全綠。
    這一格 cron 幾乎不可能精準命中（12 小時跑一輪），所以不是使用者會踩到的路徑；
    補這支的理由是**讓不變式有守衛**，不是為了防某個具體症狀。
    """
    from core.database.organize_failures import record_failure, should_skip

    base = 1_700_000_000.0
    record_failure("not_found", "BOUND-001", "BOUND-001", now=base, db_path=test_db)

    # 24 小時窗：差一秒 → 命中；剛好整點 → 不命中
    assert should_skip("not_found", "BOUND-001", now=base + 86399, db_path=test_db) is True
    assert should_skip("not_found", "BOUND-001", now=base + 86400, db_path=test_db) is False

    # 進入 7 天窗後同理
    record_failure("not_found", "BOUND-001", "BOUND-001", now=base, db_path=test_db)
    week = 7 * 86400
    assert should_skip("not_found", "BOUND-001", now=base + week - 1, db_path=test_db) is True
    assert should_skip("not_found", "BOUND-001", now=base + week, db_path=test_db) is False
