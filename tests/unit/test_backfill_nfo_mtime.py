"""Unit tests for core/database/migrate.py::backfill_readonly_nfo_mtime (TASK-104).

Real temp SQLite DB (via core.database.connection.init_db) + real tmp files —
pure-logic unit test per CLAUDE.md 測試檔案放置規則 (no network / external service).
"""
from core.database.connection import init_db
from core.database.video import Video, VideoRepository
from core.database.migrate import backfill_readonly_nfo_mtime
from core.path_utils import to_file_uri


def _make_video(path_uri: str, cover_path: str = "", nfo_mtime: float = 0.0) -> Video:
    return Video(
        path=path_uri,
        number="TEST-001",
        title="test",
        cover_path=cover_path,
        nfo_mtime=nfo_mtime,
    )


class TestBackfillReadonlyNfoMtime:
    def test_heals_row_with_sibling_nfo(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        cover_fs = tmp_path / "TEST-001.jpg"
        cover_fs.write_bytes(b"fake-jpg")
        nfo_fs = tmp_path / "TEST-001.nfo"
        nfo_fs.write_text("<movie></movie>")

        cover_uri = to_file_uri(str(cover_fs), {})
        video_uri = to_file_uri(str(tmp_path / "TEST-001.mp4"), {})
        repo.upsert(_make_video(video_uri, cover_path=cover_uri, nfo_mtime=0.0))

        healed = backfill_readonly_nfo_mtime(db_path=db_path, path_mappings={})

        assert healed == 1
        row = repo.get_by_path(video_uri)
        assert row.nfo_mtime == nfo_fs.stat().st_mtime
        assert row.nfo_mtime > 0

    def test_skips_missing_nfo(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        cover_fs = tmp_path / "TEST-002.jpg"
        cover_fs.write_bytes(b"fake-jpg")
        # 刻意不建立 sibling .nfo

        cover_uri = to_file_uri(str(cover_fs), {})
        video_uri = to_file_uri(str(tmp_path / "TEST-002.mp4"), {})
        repo.upsert(_make_video(video_uri, cover_path=cover_uri, nfo_mtime=0.0))

        healed = backfill_readonly_nfo_mtime(db_path=db_path, path_mappings={})

        assert healed == 0
        row = repo.get_by_path(video_uri)
        assert row.nfo_mtime == 0.0

    def test_ignores_healthy_rows(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        cover_fs = tmp_path / "TEST-003.jpg"
        cover_fs.write_bytes(b"fake-jpg")
        nfo_fs = tmp_path / "TEST-003.nfo"
        nfo_fs.write_text("<movie></movie>")

        cover_uri = to_file_uri(str(cover_fs), {})
        video_uri = to_file_uri(str(tmp_path / "TEST-003.mp4"), {})
        repo.upsert(_make_video(video_uri, cover_path=cover_uri, nfo_mtime=12345.0))

        healed = backfill_readonly_nfo_mtime(db_path=db_path, path_mappings={})

        assert healed == 0
        row = repo.get_by_path(video_uri)
        assert row.nfo_mtime == 12345.0

    def test_ignores_no_cover_rows(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        video_uri = to_file_uri(str(tmp_path / "TEST-004.mp4"), {})
        repo.upsert(_make_video(video_uri, cover_path="", nfo_mtime=0.0))

        healed = backfill_readonly_nfo_mtime(db_path=db_path, path_mappings={})

        assert healed == 0
        row = repo.get_by_path(video_uri)
        assert row.nfo_mtime == 0.0

    def test_idempotent_second_run_heals_zero(self, tmp_path):
        db_path = tmp_path / "test.db"
        init_db(db_path)
        repo = VideoRepository(db_path)

        cover_fs = tmp_path / "TEST-005.jpg"
        cover_fs.write_bytes(b"fake-jpg")
        nfo_fs = tmp_path / "TEST-005.nfo"
        nfo_fs.write_text("<movie></movie>")

        cover_uri = to_file_uri(str(cover_fs), {})
        video_uri = to_file_uri(str(tmp_path / "TEST-005.mp4"), {})
        repo.upsert(_make_video(video_uri, cover_path=cover_uri, nfo_mtime=0.0))

        first = backfill_readonly_nfo_mtime(db_path=db_path, path_mappings={})
        assert first == 1
        healed_mtime = repo.get_by_path(video_uri).nfo_mtime

        second = backfill_readonly_nfo_mtime(db_path=db_path, path_mappings={})
        assert second == 0
        row = repo.get_by_path(video_uri)
        assert row.nfo_mtime == healed_mtime
