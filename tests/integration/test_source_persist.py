"""TASK-61c-2: sources toggle / reorder 持久化測試。

PUT 一個 sources 陣列（部分 disabled、reordered）→ GET 回傳相同
sources（enabled flags + order 持久化）。
"""


def _base_config(client):
    resp = client.get("/api/config")
    return resp.json()["data"]


def test_toggle_enabled_persists(client, temp_config_path):
    """關閉某個 builtin → PUT → GET 該 source enabled=false 持久化。"""
    cfg = _base_config(client)
    assert len(cfg["sources"]) >= 2
    target_id = cfg["sources"][0]["id"]
    cfg["sources"][0]["enabled"] = False

    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 200

    new_cfg = _base_config(client)
    by_id = {s["id"]: s for s in new_cfg["sources"]}
    assert by_id[target_id]["enabled"] is False


def test_reorder_persists(client, temp_config_path):
    """reorder sources + 重算 order → PUT → GET 順序與 order 持久化。"""
    cfg = _base_config(client)
    sources = cfg["sources"]
    assert len(sources) >= 3

    # 反轉順序，並依新 index 重算 order
    reversed_sources = list(reversed(sources))
    for i, s in enumerate(reversed_sources):
        s["order"] = i
    cfg["sources"] = reversed_sources
    expected_order = [s["id"] for s in reversed_sources]

    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 200

    new_cfg = _base_config(client)
    got = sorted(new_cfg["sources"], key=lambda s: s["order"])
    assert [s["id"] for s in got] == expected_order
    for i, s in enumerate(got):
        assert s["order"] == i


def test_promote_appends_at_end(client, temp_config_path):
    """模擬 promote：新增一個 enabled metatube 落在末尾，order 為最大 → 持久化。"""
    cfg = _base_config(client)
    sources = cfg["sources"]
    next_order = len(sources)
    sources.append(
        {
            "id": "mt_demo",
            "type": "metatube",
            "display_name_key": "",
            "display_name_raw": "Metatube Demo",
            "enabled": True,
            "order": next_order,
            "config": {"censored_type": "censored"},
            "is_beta": False,
            "manual_only": False,
        }
    )
    cfg["sources"] = sources

    resp = client.put("/api/config", json=cfg)
    assert resp.status_code == 200

    new_cfg = _base_config(client)
    by_id = {s["id"]: s for s in new_cfg["sources"]}
    assert "mt_demo" in by_id
    assert by_id["mt_demo"]["enabled"] is True
    assert by_id["mt_demo"]["order"] == next_order
