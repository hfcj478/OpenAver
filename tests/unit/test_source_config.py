"""TASK-61a-1: SourceConfig 模型 + helper + validator 單元測試"""
from core.scrapers.utils import SOURCE_ORDER
from core.source_config import (
    MAX_ENABLED_SOURCES,
    SourceConfig,
    get_builtin_sources,
    get_source_enum,
    render_name,
    validate_source_id,
)


# ---------------------------------------------------------------------------
# MAX_ENABLED_SOURCES 常數
# ---------------------------------------------------------------------------
def test_max_enabled_sources_constant():
    assert MAX_ENABLED_SOURCES == 10


# ---------------------------------------------------------------------------
# render_name 雙模式
# ---------------------------------------------------------------------------
def test_render_name_builtin_uses_display_name_key():
    s = SourceConfig(
        id='javbus',
        type='builtin',
        display_name_key='JavBus',
        display_name_raw='ignored',
    )
    assert render_name(s) == 'JavBus'


def test_render_name_metatube_uses_display_name_raw():
    s = SourceConfig(
        id='mt-foo',
        type='metatube',
        display_name_key='ignored',
        display_name_raw='Some External Provider',
    )
    assert render_name(s) == 'Some External Provider'


# ---------------------------------------------------------------------------
# get_builtin_sources
# ---------------------------------------------------------------------------
def test_get_builtin_sources_count():
    assert len(get_builtin_sources()) == 8


def test_get_builtin_sources_ids_match_source_order():
    ids = [s.id for s in get_builtin_sources()]
    assert ids == SOURCE_ORDER


def test_get_builtin_sources_all_manual_only_false():
    assert all(s.manual_only is False for s in get_builtin_sources())


def test_get_builtin_sources_all_type_builtin():
    assert all(s.type == 'builtin' for s in get_builtin_sources())


def test_get_builtin_sources_all_enabled():
    assert all(s.enabled is True for s in get_builtin_sources())


def test_get_builtin_sources_all_not_beta():
    assert all(s.is_beta is False for s in get_builtin_sources())


def test_get_builtin_sources_order_values():
    orders = [s.order for s in get_builtin_sources()]
    assert orders == list(range(8))


def test_get_builtin_sources_excludes_auto():
    ids = [s.id for s in get_builtin_sources()]
    assert 'auto' not in ids


def test_get_builtin_sources_display_name_key_is_brand():
    by_id = {s.id: s for s in get_builtin_sources()}
    assert by_id['javbus'].display_name_key == 'JavBus'
    assert by_id['dmm'].display_name_key == 'DMM'


# ---------------------------------------------------------------------------
# validate_source_id
# ---------------------------------------------------------------------------
def test_validate_source_id_known_builtins():
    for sid in SOURCE_ORDER:
        assert validate_source_id(sid) is True


def test_validate_source_id_auto():
    assert validate_source_id('auto') is True


def test_validate_source_id_unknown():
    assert validate_source_id('foobar') is False


def test_validate_source_id_empty():
    assert validate_source_id('') is False


# ---------------------------------------------------------------------------
# manual_only default
# ---------------------------------------------------------------------------
def test_manual_only_defaults_false():
    s = SourceConfig(id='x', type='builtin', display_name_key='X')
    assert s.manual_only is False


# ---------------------------------------------------------------------------
# is_censored computed field
# ---------------------------------------------------------------------------
def test_is_censored_builtin_censored():
    s = SourceConfig(id='dmm', type='builtin', display_name_key='DMM')
    assert s.is_censored is True


def test_is_censored_builtin_censored_javbus():
    s = SourceConfig(id='javbus', type='builtin', display_name_key='JavBus')
    assert s.is_censored is True


def test_is_censored_builtin_uncensored_fc2():
    s = SourceConfig(id='fc2', type='builtin', display_name_key='FC2')
    assert s.is_censored is False


def test_is_censored_builtin_uncensored_d2pass():
    s = SourceConfig(id='d2pass', type='builtin', display_name_key='D2Pass')
    assert s.is_censored is False


def test_is_censored_builtin_unknown_id_conservative():
    s = SourceConfig(id='mystery', type='builtin', display_name_key='Mystery')
    assert s.is_censored is True


def test_is_censored_metatube_uncensored():
    s = SourceConfig(
        id='mt-1',
        type='metatube',
        display_name_key='',
        display_name_raw='MT One',
        config={'censored_type': 'uncensored'},
    )
    assert s.is_censored is False


def test_is_censored_metatube_censored():
    s = SourceConfig(
        id='mt-2',
        type='metatube',
        display_name_key='',
        display_name_raw='MT Two',
        config={'censored_type': 'censored'},
    )
    assert s.is_censored is True


def test_is_censored_metatube_missing_censored_type_conservative():
    s = SourceConfig(
        id='mt-3',
        type='metatube',
        display_name_key='',
        display_name_raw='MT Three',
        config={},
    )
    assert s.is_censored is True


def test_is_censored_metatube_invalid_censored_type_conservative():
    s = SourceConfig(
        id='mt-4',
        type='metatube',
        display_name_key='',
        display_name_raw='MT Four',
        config={'censored_type': 'banana'},
    )
    assert s.is_censored is True


# ---------------------------------------------------------------------------
# get_source_enum（TASK-61a-4）
# ---------------------------------------------------------------------------
def test_get_source_enum_without_auto_matches_source_order():
    assert get_source_enum() == list(SOURCE_ORDER)
    assert get_source_enum(include_auto=False) == list(SOURCE_ORDER)


def test_get_source_enum_without_auto_excludes_auto():
    assert 'auto' not in get_source_enum(include_auto=False)


def test_get_source_enum_with_auto_prepends_auto():
    assert get_source_enum(include_auto=True) == ['auto', *SOURCE_ORDER]
    assert get_source_enum(include_auto=True)[0] == 'auto'


def test_get_source_enum_returns_list():
    assert isinstance(get_source_enum(), list)
    assert isinstance(get_source_enum(include_auto=True), list)
