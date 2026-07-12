"""
TASK-87b-T1 — 跨 repo 等價性護欄（dedup pre-net, CD-87b-9）。

參數化 over [AliasRepository, TagAliasRepository]，每案 fresh empty DB，
斷言兩 repo 的可觀察結果一致（return 形狀 / 型別 / 集合 / 例外）。
種子輸入兩 repo 相同，故差異唯有底層表名——這正是 T-2 抽 base 後必須保持的不變式。

不涵蓋 sync_from_favorite（非對稱，僅 AliasRepository 有；由 test_alias_repository.py 守）。
"""
import pytest

from core.database import AliasRepository, TagAliasRepository, init_db


# 參數化骨架：所有情境 over 兩 repo class，id 標 class 名以利定位偏差。
repo_classes = pytest.mark.parametrize(
    "repo_cls",
    [AliasRepository, TagAliasRepository],
    ids=["AliasRepository", "TagAliasRepository"],
)


@pytest.fixture
def make_repo(tmp_path):
    """每次呼叫建立一個 fresh empty DB + repo（每案獨立，杜絕跨案耦合）。"""
    counter = {"n": 0}

    def _make(repo_cls):
        counter["n"] += 1
        db_path = tmp_path / f"eq_{counter['n']}.db"
        init_db(db_path)
        return repo_cls(db_path)

    return _make


# ---------------------------------------------------------------------------
# add — happy path
# ---------------------------------------------------------------------------

@repo_classes
def test_add_happy(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    record = repo.add("P", ["a1", "a2"], source="manual")
    assert record is not None
    assert record.primary_name == "P"
    assert set(record.aliases) == {"a1", "a2"}
    assert record.source == "manual"


# ---------------------------------------------------------------------------
# add — duplicate primary → ValueError
# ---------------------------------------------------------------------------

@repo_classes
def test_add_duplicate_primary_raises(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1"])
    with pytest.raises(ValueError):
        repo.add("P", ["other"])


# ---------------------------------------------------------------------------
# add — duplicate alias (collides with existing alias) → ValueError
# 經 _check_global_uniqueness_cursor 的 json_each 子查詢
# ---------------------------------------------------------------------------

@repo_classes
def test_add_duplicate_alias_raises(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1", "a2"])
    with pytest.raises(ValueError):
        repo.add("Q", ["a1"])  # a1 已是 P 的別名


# ---------------------------------------------------------------------------
# add_alias — success / missing primary / conflict
# ---------------------------------------------------------------------------

@repo_classes
def test_add_alias_success(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1"])
    result = repo.add_alias("P", "a2")
    assert result == (True, None)
    assert set(repo.get_by_primary("P").aliases) == {"a1", "a2"}


@repo_classes
def test_add_alias_missing_primary(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    ok, msg = repo.add_alias("NOPE", "a1")
    assert ok is False
    assert isinstance(msg, str)


@repo_classes
def test_add_alias_conflict(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1"])
    repo.add("Q", ["b1"])
    ok, msg = repo.add_alias("Q", "a1")  # a1 已屬 P
    assert ok is False
    assert isinstance(msg, str)


# ---------------------------------------------------------------------------
# remove_alias — hit / miss
# ---------------------------------------------------------------------------

@repo_classes
def test_remove_alias_hit(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1", "a2"])
    assert repo.remove_alias("P", "a1") is True
    assert set(repo.get_by_primary("P").aliases) == {"a2"}


@repo_classes
def test_remove_alias_miss(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1"])
    assert repo.remove_alias("P", "nope") is False      # alias 不在 group
    assert repo.remove_alias("NOPE", "a1") is False      # primary 不存在


# ---------------------------------------------------------------------------
# find_by_alias — hit / miss
# ---------------------------------------------------------------------------

@repo_classes
def test_find_by_alias_hit(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1", "a2"])
    record = repo.find_by_alias("a1")
    assert record is not None
    assert record.primary_name == "P"


@repo_classes
def test_find_by_alias_miss(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1"])
    assert repo.find_by_alias("nope") is None


# ---------------------------------------------------------------------------
# resolve — primary entry / alias entry (same set) / miss
# ---------------------------------------------------------------------------

@repo_classes
def test_resolve_three_paths(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1", "a2"])
    expected = {"P", "a1", "a2"}
    assert repo.resolve("P") == expected       # primary 入口
    assert repo.resolve("a1") == expected       # alias 入口（同集合）
    assert repo.resolve("unknown") == {"unknown"}  # miss


# ---------------------------------------------------------------------------
# delete — primary entry / alias entry / non-existent
# ---------------------------------------------------------------------------

@repo_classes
def test_delete_by_primary(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1"])
    assert repo.delete("P") is True
    assert repo.get_by_primary("P") is None


@repo_classes
def test_delete_by_alias(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("P", ["a1", "a2"])
    assert repo.delete("a1") is True             # alias 入口（json_each fallback）
    assert repo.get_by_primary("P") is None


@repo_classes
def test_delete_nonexistent(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    assert repo.delete("nope") is False


# ---------------------------------------------------------------------------
# get_all — empty / sorted after adds
# ---------------------------------------------------------------------------

@repo_classes
def test_get_all_empty(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    assert repo.get_all() == []


@repo_classes
def test_get_all_sorted(make_repo, repo_cls):
    repo = make_repo(repo_cls)
    repo.add("B", ["b1"])
    repo.add("A", ["a1"])
    records = repo.get_all()
    assert [r.primary_name for r in records] == ["A", "B"]
