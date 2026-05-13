import pytest
from unittest.mock import patch, MagicMock
from core.similar.canonicalize import (
    _HARDCODED_ALIAS_MAP,
    _STOPWORDS,
    canonicalize,
    _invalidate_cache,
)


@pytest.fixture(autouse=True)
def isolate_canonicalize_cache():
    """每 test 前後清 cache + mock TagAliasRepository 為空，避免讀真實 dev DB"""
    _invalidate_cache()
    mock_repo = MagicMock()
    mock_repo.get_all.return_value = []
    with patch('core.database.TagAliasRepository', return_value=mock_repo):
        yield
    _invalidate_cache()


def test_alias_map_size():
    assert len(_HARDCODED_ALIAS_MAP) >= 15


def test_stopwords_size():
    assert len(_STOPWORDS) >= 10


def test_empty_input():
    assert canonicalize([]) == []


def test_alias_hit_one_way():
    assert canonicalize(["中出"]) == ["中出し"]


def test_alias_canonical_passthrough():
    assert canonicalize(["中出し"]) == ["中出し"]


def test_alias_miss():
    assert canonicalize(["巨乳"]) == ["巨乳"]


def test_stopword_filter():
    assert canonicalize(["高畫質"]) == []


def test_alias_then_stopword_order():
    # デジモ alias 映射為「數位馬賽克」，後者是 stopword
    assert canonicalize(["デジモ"]) == []


def test_mixed_input():
    assert canonicalize(["高畫質", "中出し", "高畫質"]) == ["中出し"]


def test_dedup_preserves_first_seen_order():
    assert canonicalize(["A", "B", "A"]) == ["A", "B"]


def test_falsy_values_skipped():
    assert canonicalize([None, "", "中出し"]) == ["中出し"]


def test_simplified_traditional_alias():
    # 内射 → 中出し（與「中出」同 canonical）
    assert canonicalize(["内射"]) == ["中出し"]


def test_traditional_to_japanese_alias():
    assert canonicalize(["單體作品"]) == []  # 単体作品 也是 stopword


def test_iterable_generator_input():
    def gen():
        yield "中出"
        yield "巨乳"
    assert canonicalize(gen()) == ["中出し", "巨乳"]


def test_alias_dedup_after_mapping():
    # 「中出」與「中出し」映射後重複，應只保留首次出現
    assert canonicalize(["中出", "中出し"]) == ["中出し"]
