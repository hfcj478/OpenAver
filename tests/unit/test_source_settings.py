"""Unit tests for core/source_settings.py business-layer helpers (TASK-61a-1b).

Covers Runtime Auto Pool filtering (`get_enabled_source_ids`) and the
uncensored-mode single-source-of-truth (`is_uncensored_mode_effective`).
"""
import pytest

from core import source_settings


# ---------------------------------------------------------------------------
# get_enabled_source_ids
# ---------------------------------------------------------------------------

def _patch_config(monkeypatch, fake_config):
    monkeypatch.setattr(
        'core.source_settings.load_config', lambda: fake_config
    )


def test_enabled_filter_excludes_disabled(monkeypatch):
    _patch_config(monkeypatch, {
        'sources': [
            {'id': 'dmm', 'type': 'builtin', 'enabled': True, 'order': 0, 'manual_only': False},
            {'id': 'javbus', 'type': 'builtin', 'enabled': False, 'order': 1, 'manual_only': False},
        ]
    })
    assert source_settings.get_enabled_source_ids() == ['dmm']


def test_order_sorting(monkeypatch):
    _patch_config(monkeypatch, {
        'sources': [
            {'id': 'c', 'type': 'builtin', 'enabled': True, 'order': 5, 'manual_only': False},
            {'id': 'a', 'type': 'builtin', 'enabled': True, 'order': 1, 'manual_only': False},
            {'id': 'b', 'type': 'builtin', 'enabled': True, 'order': 3, 'manual_only': False},
        ]
    })
    assert source_settings.get_enabled_source_ids() == ['a', 'b', 'c']


def test_missing_sources_returns_empty(monkeypatch):
    _patch_config(monkeypatch, {'search': {}})
    assert source_settings.get_enabled_source_ids() == []


def test_empty_sources_returns_empty(monkeypatch):
    _patch_config(monkeypatch, {'sources': []})
    assert source_settings.get_enabled_source_ids() == []


def test_manual_only_excluded_even_when_enabled(monkeypatch):
    _patch_config(monkeypatch, {
        'sources': [
            {'id': 'javlibrary', 'type': 'builtin', 'enabled': True, 'order': 0, 'manual_only': True},
            {'id': 'dmm', 'type': 'builtin', 'enabled': True, 'order': 1, 'manual_only': False},
        ]
    })
    assert source_settings.get_enabled_source_ids() == ['dmm']


def test_availability_none_includes_all_enabled_incl_metatube(monkeypatch):
    _patch_config(monkeypatch, {
        'sources': [
            {'id': 'dmm', 'type': 'builtin', 'enabled': True, 'order': 0, 'manual_only': False},
            {'id': 'mt1', 'type': 'metatube', 'enabled': True, 'order': 1, 'manual_only': False},
        ]
    })
    assert source_settings.get_enabled_source_ids(None) == ['dmm', 'mt1']


def test_populated_map_excludes_unavailable_metatube_keeps_builtin(monkeypatch):
    _patch_config(monkeypatch, {
        'sources': [
            {'id': 'dmm', 'type': 'builtin', 'enabled': True, 'order': 0, 'manual_only': False},
            {'id': 'mt1', 'type': 'metatube', 'enabled': True, 'order': 1, 'manual_only': False},
        ]
    })
    # mt1 absent from map -> excluded; builtin dmm bypasses gate even though absent.
    assert source_settings.get_enabled_source_ids({'mt1': False}) == ['dmm']
    assert source_settings.get_enabled_source_ids({}) == ['dmm']


def test_populated_map_keeps_available_metatube(monkeypatch):
    _patch_config(monkeypatch, {
        'sources': [
            {'id': 'dmm', 'type': 'builtin', 'enabled': True, 'order': 0, 'manual_only': False},
            {'id': 'mt1', 'type': 'metatube', 'enabled': True, 'order': 1, 'manual_only': False},
        ]
    })
    assert source_settings.get_enabled_source_ids({'mt1': True}) == ['dmm', 'mt1']


def test_malformed_entries_do_not_crash(monkeypatch):
    _patch_config(monkeypatch, {
        'sources': [
            {},  # no keys at all
            {'id': 'dmm', 'type': 'builtin', 'enabled': True},  # no order/manual_only
        ]
    })
    assert source_settings.get_enabled_source_ids() == ['dmm']


# ---------------------------------------------------------------------------
# is_uncensored_mode_effective
# ---------------------------------------------------------------------------

def test_uncensored_derive_all_censored_disabled_true():
    config = {
        'sources': [
            {'id': 'dmm', 'type': 'builtin', 'enabled': False},
            {'id': 'javbus', 'type': 'builtin', 'enabled': False},
            {'id': 'jav321', 'type': 'builtin', 'enabled': False},
            {'id': 'javdb', 'type': 'builtin', 'enabled': False},
            {'id': 'fc2', 'type': 'builtin', 'enabled': True},
        ]
    }
    assert source_settings.is_uncensored_mode_effective(config) is True


def test_uncensored_derive_one_censored_enabled_false():
    config = {
        'sources': [
            {'id': 'dmm', 'type': 'builtin', 'enabled': True},
            {'id': 'javbus', 'type': 'builtin', 'enabled': False},
            {'id': 'jav321', 'type': 'builtin', 'enabled': False},
            {'id': 'javdb', 'type': 'builtin', 'enabled': False},
        ]
    }
    assert source_settings.is_uncensored_mode_effective(config) is False


def test_uncensored_derive_censored_absent_treated_disabled_true():
    # No censored builtins present in sources at all -> none enabled -> True.
    config = {
        'sources': [
            {'id': 'fc2', 'type': 'builtin', 'enabled': True},
            {'id': 'avsox', 'type': 'builtin', 'enabled': True},
        ]
    }
    assert source_settings.is_uncensored_mode_effective(config) is True


def test_uncensored_fallback_legacy_true():
    config = {'search': {'uncensored_mode_enabled': True}}
    assert source_settings.is_uncensored_mode_effective(config) is True


def test_uncensored_fallback_legacy_false():
    config = {'search': {'uncensored_mode_enabled': False}}
    assert source_settings.is_uncensored_mode_effective(config) is False


def test_uncensored_fallback_legacy_absent_false():
    assert source_settings.is_uncensored_mode_effective({}) is False
    assert source_settings.is_uncensored_mode_effective({'search': {}}) is False


def test_uncensored_empty_sources_uses_legacy():
    # Empty sources list -> fallback to legacy key, NOT derive.
    config = {'sources': [], 'search': {'uncensored_mode_enabled': True}}
    assert source_settings.is_uncensored_mode_effective(config) is True
    config2 = {'sources': [], 'search': {'uncensored_mode_enabled': False}}
    assert source_settings.is_uncensored_mode_effective(config2) is False
