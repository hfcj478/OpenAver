"""Integration tests for GET /api/showcase/source-status and lifespan probe.

Covers TASK-142-T2 DoD 1–5:
1. Rapid calls (5 times in 60s window) probe at most once and respond < 50ms.
2. Lifespan context manager yields within 100ms even if probe takes 10s.
3. get_snapshot exception does not affect GET /api/showcase/videos.
4. Returns empty list [] when all sources are ok/unknown/unprobed.
5. Display formatting for UNC (\\\\host) and non-UNC paths.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import core.source_reachability as sr
from web.app import app, lifespan


def _reset_sr_module() -> None:
    with sr._lock:
        sr._snapshot = {}
        sr._snapshot_at = sr._NEVER
        sr._in_flight = False
        sr._pending_exists.clear()
        sr._reprobe_task = None


def test_dod1_five_rapid_calls_probe_at_most_once_and_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD 1: 5 rapid calls in 60s window trigger at most 1 probe, each < 50ms."""
    _reset_sr_module()

    probe_count = 0

    async def mock_probe_all() -> None:
        nonlocal probe_count
        probe_count += 1
        with sr._lock:
            sr._snapshot = {"/test/path": "unreachable"}
            sr._snapshot_at = time.monotonic()
            sr._in_flight = False

    monkeypatch.setattr(sr, "_probe_all", mock_probe_all)

    client = TestClient(app, client=("127.0.0.1", 50000))
    durations = []
    for _ in range(5):
        t0 = time.perf_counter()
        resp = client.get("/api/showcase/source-status")
        elapsed_ms = (time.perf_counter() - t0) * 1000
        durations.append(elapsed_ms)
        assert resp.status_code == 200

    assert probe_count <= 1
    for d in durations:
        assert d < 50, f"Response duration {d:.2f}ms exceeds 50ms"


@pytest.mark.asyncio
async def test_dod2_lifespan_yield_not_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD 2: lifespan to yield takes < 100ms even when probe runs for 10s."""
    _reset_sr_module()

    monkeypatch.setattr("web.app.init_db", lambda *a, **kw: None)
    monkeypatch.setattr("web.app.ensure_schema", lambda *a, **kw: None)
    monkeypatch.setattr("web.app.backfill_readonly_nfo_mtime", lambda *a, **kw: 0)
    monkeypatch.setattr("web.app.startup_reconnect", lambda *a, **kw: None)
    monkeypatch.setattr("web.app._startup_update_check", AsyncMock())
    # v0.15.13：shutdown 開始 drain 通知 writer 之後，這一行才變成「會真的做事」。
    # 在那之前 start_notification_persistence() 幾乎總是提早 return——它開頭有
    # `if _writer_thread is not None and _writer_thread.is_alive(): return`，而
    # 前面任何一支測試留下的活 writer thread 都會讓它命中那道閘、根本不碰 DB。
    # 現在 shutdown 會把 _writer_thread 設回 None，於是下一次 lifespan 啟動真的會去
    # load_recent_notifications() 連**真實的** output/openaver.db，被 repo-write 守衛
    # 擋成 RepoWriteGuardViolation（繼承 BaseException，start_notification_persistence()
    # 內的 `except Exception` 攔不到）⇒ 整段 startup 炸掉。
    # 這裡與上面五行同樣的處置：本測試量的是「lifespan 到 yield 的耗時」，
    # 通知歷史載回與它無關，照鄰居的形狀一起 mock 掉（順便避免把真實 DB I/O
    # 算進那個 < 0.1s 的斷言裡）。
    monkeypatch.setattr("web.app.start_notification_persistence", lambda *a, **kw: None)

    async def slow_probe_all() -> None:
        await asyncio.sleep(10.0)

    monkeypatch.setattr(sr, "_probe_all", slow_probe_all)

    called = False
    real_schedule = sr.schedule_reprobe_if_stale

    async def tracking_schedule() -> None:
        nonlocal called
        called = True
        await real_schedule()

    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", tracking_schedule)

    t0 = time.perf_counter()
    cm = lifespan(app)
    try:
        await asyncio.wait_for(cm.__aenter__(), timeout=1.0)
        elapsed = time.perf_counter() - t0
        assert called, "lifespan must call schedule_reprobe_if_stale()"
        assert elapsed < 0.1, f"lifespan startup took {elapsed:.3f}s, expected < 0.1s"
    finally:
        with contextlib.suppress(Exception):
            await cm.__aexit__(None, None, None)
        if sr._reprobe_task and not sr._reprobe_task.done():
            sr._reprobe_task.cancel()


def test_dod3_get_snapshot_error_does_not_affect_videos(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """DoD 3: get_snapshot exception does not affect GET /api/showcase/videos."""
    from core.database import init_db

    test_db = tmp_path / "test_showcase.db"
    init_db(test_db)
    monkeypatch.setattr("web.routers.showcase.get_db_path", lambda: test_db)
    monkeypatch.setattr(
        "web.routers.showcase.load_config",
        lambda: {"gallery": {"directories": [], "path_mappings": {}}},
    )

    def failing_snapshot() -> dict[str, str]:
        raise RuntimeError("simulated get_snapshot failure")

    monkeypatch.setattr(sr, "get_snapshot", failing_snapshot)

    client = TestClient(app, client=("127.0.0.1", 50000))
    resp = client.get("/api/showcase/videos")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("success") is True
    assert "videos" in data


def test_dod4_all_ok_or_unknown_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD 4: all sources ok/unknown/unprobed returns empty list []."""
    monkeypatch.setattr(
        sr,
        "get_snapshot",
        lambda: {
            "//server/share1": "ok",
            "//server/share2": "unknown",
            "/local/media": "ok",
        },
    )
    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", AsyncMock())

    client = TestClient(app, client=("127.0.0.1", 50000))
    resp = client.get("/api/showcase/source-status")
    assert resp.status_code == 200
    assert resp.json() == []

    # Unprobed scenario (empty snapshot)
    monkeypatch.setattr(sr, "get_snapshot", lambda: {})
    resp_empty = client.get("/api/showcase/source-status")
    assert resp_empty.status_code == 200
    assert resp_empty.json() == []


def test_dod5_unreachable_sources_display_format(monkeypatch: pytest.MonkeyPatch) -> None:
    """DoD 5: unreachable UNC formats to \\\\<host>, non-UNC to raw path."""
    mock_snapshot = {
        "\\\\nas-box\\share\\videos": "unreachable",
        "/mnt/storage/media": "unreachable",
        "//other-nas/data": "ok",
    }
    monkeypatch.setattr(sr, "get_snapshot", lambda: mock_snapshot)
    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", AsyncMock())

    client = TestClient(app, client=("127.0.0.1", 50000))
    resp = client.get("/api/showcase/source-status")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 2

    unc_item = next(
        (item for item in data if item["path"] == "\\\\nas-box\\share\\videos"),
        None,
    )
    assert unc_item is not None
    assert unc_item["display"] == "\\\\nas-box"
    assert unc_item["status"] == "unreachable"

    local_item = next(
        (item for item in data if item["path"] == "/mnt/storage/media"),
        None,
    )
    assert local_item is not None
    assert local_item["display"] == "/mnt/storage/media"
    assert local_item["status"] == "unreachable"


def test_cold_start_waits_for_first_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺陷 B：快照從未寫過時，端點要等第一次探測寫完，不能拿到 []。"""
    _reset_sr_module()

    async def fake_probe_all() -> None:
        await asyncio.sleep(0.05)
        with sr._lock:
            sr._snapshot = {"/mnt/cold": "unreachable"}
            sr._snapshot_at = sr._now()
            sr._in_flight = False

    monkeypatch.setattr(sr, "_probe_all", fake_probe_all)

    client = TestClient(app, client=("127.0.0.1", 50000))
    resp = client.get("/api/showcase/source-status")
    assert resp.status_code == 200
    data = resp.json()
    assert any(item["path"] == "/mnt/cold" for item in data), (
        f"cold start must wait for first probe, got {data!r}"
    )


def test_warm_snapshot_does_not_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    """缺陷 B 的反向守衛：已探測過（快照新鮮）時，就算 _reprobe_task 永不完成，端點也要立刻回應。"""
    _reset_sr_module()

    with sr._lock:
        sr._snapshot = {"/mnt/warm": "unreachable"}
        sr._snapshot_at = sr._now()

    async def never_finishes() -> None:
        await asyncio.sleep(3600)

    # schedule_reprobe_if_stale is patched so the never-finishing task is created
    # on whatever event loop actually runs the endpoint coroutine (TestClient runs
    # each request through the app's own loop), rather than on this test's loop.
    async def install_never_finishing_task() -> None:
        with sr._lock:
            sr._reprobe_task = asyncio.ensure_future(never_finishes())

    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", install_never_finishing_task)

    client = TestClient(app, client=("127.0.0.1", 50000))
    t0 = time.perf_counter()
    resp = client.get("/api/showcase/source-status")
    elapsed = time.perf_counter() - t0
    assert resp.status_code == 200
    assert elapsed < 1.0, f"warm path must not wait, took {elapsed:.3f}s"
    data = resp.json()
    assert any(item["path"] == "/mnt/warm" for item in data)

    task = sr._reprobe_task
    if task is not None and not task.done():
        task.cancel()


def test_cold_start_waits_for_slow_multi_source_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """PR#178 R2 缺陷D：_probe_all 是循序探測、快照只在整個迴圈跑完才寫入。端點等的
    必須是 task 本身跑完，不是某個固定秒數——用多來源、迴圈結束後才寫快照的假探測，
    斷言端點拿到的是完整快照（每一筆都在），證明沒有任何來源在中途被「等到一半就放棄」
    漏接。（刻意不真的睡 15 秒，也不在這支測試裡動 _FIRST_PROBE_WAIT_S——那是保險絲
    測試的手法，混進來會測到保險絲而不是測到正確性。）"""
    _reset_sr_module()

    sources = ["/mnt/multi-1", "/mnt/multi-2", "/mnt/multi-3", "/mnt/multi-4", "/mnt/multi-5"]

    async def fake_probe_all() -> None:
        snapshot: dict[str, str] = {}
        for s in sources:
            await asyncio.sleep(0.1)
            snapshot[s] = "unreachable"
        # 快照只在迴圈整個跑完後才一次寫入（與真正的 _probe_all 同形狀）
        with sr._lock:
            sr._snapshot = snapshot
            sr._snapshot_at = sr._now()
            sr._in_flight = False

    monkeypatch.setattr(sr, "_probe_all", fake_probe_all)

    client = TestClient(app, client=("127.0.0.1", 50000))
    resp = client.get("/api/showcase/source-status")
    assert resp.status_code == 200
    data = resp.json()
    got_paths = {item["path"] for item in data}
    assert got_paths == set(sources), (
        f"cold start 必須等到 task 本身跑完，拿到的應是完整快照，實際={data!r}"
    )


def test_first_probe_wait_is_a_fuse_not_a_deadline(monkeypatch: pytest.MonkeyPatch) -> None:
    """PR#178 R2 缺陷D 的保險絲測試（不驗正確性）：_FIRST_PROBE_WAIT_S 必須是遠大於任何
    正常探測耗時的保險絲值，只用來防止 task 永久卡住時把請求焊死，不是拿來當「正確」
    秒數算出來的猜測值。用一個永不完成的 task + 直接呼叫真正的 wait_for_first_probe
    並把 timeout 顯式覆寫成極小值，證明逾時後端點仍會回應（不拋、不掛住）——這支只守
    保險絲機制本身會動，不守等待時長的正確性語意。"""
    _reset_sr_module()
    assert sr._FIRST_PROBE_WAIT_S >= 120.0

    async def never_finishes() -> None:
        await asyncio.sleep(3600)

    async def install_never_finishing_task() -> None:
        with sr._lock:
            sr._reprobe_task = asyncio.ensure_future(never_finishes())

    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", install_never_finishing_task)

    real_wait_for_first_probe = sr.wait_for_first_probe

    async def wait_with_tiny_fuse() -> None:
        await real_wait_for_first_probe(timeout=0.01)

    monkeypatch.setattr(sr, "wait_for_first_probe", wait_with_tiny_fuse)

    client = TestClient(app, client=("127.0.0.1", 50000))
    t0 = time.perf_counter()
    resp = client.get("/api/showcase/source-status")
    elapsed = time.perf_counter() - t0

    assert resp.status_code == 200
    assert elapsed < 1.0, f"保險絲必須讓端點快速回應，實際耗時 {elapsed:.3f}s"

    task = sr._reprobe_task
    if task is not None and not task.done():
        task.cancel()


def test_same_unc_host_sources_merge_into_one_display(monkeypatch: pytest.MonkeyPatch) -> None:
    """spec F3: 同一主機底下多個來源合成一個名字（否則 footer 列兩次同一台 NAS，
    「N 個位置無法存取」也會多算）。非 UNC 的不同根路徑仍各自一筆。"""
    monkeypatch.setattr(
        sr,
        "get_snapshot",
        lambda: {
            "\\\\nas-box\\share\\videos": "unreachable",
            "\\\\nas-box\\share2\\more": "unreachable",
            "/mnt/usb-a": "unreachable",
            "/mnt/usb-b": "unreachable",
        },
    )
    monkeypatch.setattr(sr, "schedule_reprobe_if_stale", AsyncMock())

    client = TestClient(app, client=("127.0.0.1", 50000))
    data = client.get("/api/showcase/source-status").json()

    displays = [item["display"] for item in data]
    assert displays.count("\\\\nas-box") == 1, "同一 UNC 主機只該出現一次"
    assert sorted(displays) == sorted(["\\\\nas-box", "/mnt/usb-a", "/mnt/usb-b"])
