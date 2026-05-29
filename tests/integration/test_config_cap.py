"""TASK-61c-2: PUT /api/config 來源啟用上限（cap=10）守衛測試。

endpoint-level check（非 model_validator）：
- enabled=true AND manual_only=false count > 10 → HTTP 400 {error:'cap_exceeded',max:10}
- 恰 10 → 200
- manual_only 不計入 cap basis（CD-61-17）
"""
import json

from core.source_config import MAX_ENABLED_SOURCES


def _make_source(idx, *, enabled=True, manual_only=False):
    return {
        "id": f"src{idx}",
        "type": "builtin",
        "display_name_key": f"Src{idx}",
        "display_name_raw": "",
        "enabled": enabled,
        "order": idx,
        "config": {},
        "is_beta": False,
        "manual_only": manual_only,
    }


def _base_config(client):
    resp = client.get("/api/config")
    return resp.json()["data"]


def test_cap_exceeded_returns_400(client, temp_config_path):
    """11 個 enabled non-manual → 400 cap_exceeded，且不寫入檔案。"""
    cfg = _base_config(client)
    cfg["sources"] = [_make_source(i) for i in range(11)]

    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 400
    assert resp.json()["detail"] == {"error": "cap_exceeded", "max": MAX_ENABLED_SOURCES}

    # config.json 未被覆寫（仍是預設 8 builtin，無 src0..src10）
    with open(temp_config_path, "r", encoding="utf-8") as f:
        saved = json.load(f)
    saved_ids = {s["id"] for s in saved.get("sources", [])}
    assert "src10" not in saved_ids


def test_cap_exactly_10_returns_200(client, temp_config_path):
    """恰 10 個 enabled non-manual → 200。"""
    cfg = _base_config(client)
    cfg["sources"] = [_make_source(i) for i in range(10)]

    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_manual_only_not_counted_toward_cap(client, temp_config_path):
    """10 enabled non-manual + 1 enabled manual_only → 200（manual_only 不吃 cap）。"""
    cfg = _base_config(client)
    cfg["sources"] = [_make_source(i) for i in range(10)] + [
        _make_source(99, enabled=True, manual_only=True)
    ]

    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_eleven_with_one_manual_only_returns_200(client, temp_config_path):
    """11 個 enabled 但其中 1 個 manual_only → non-manual=10 → 200。"""
    cfg = _base_config(client)
    sources = [_make_source(i) for i in range(10)]
    sources.append(_make_source(99, enabled=True, manual_only=True))
    cfg["sources"] = sources

    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 200


def test_empty_sources_defaults_under_cap(client, temp_config_path):
    """空 sources 段 → AppConfig default（8 builtin）→ under cap → 200。"""
    cfg = _base_config(client)
    cfg["sources"] = []

    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 200
