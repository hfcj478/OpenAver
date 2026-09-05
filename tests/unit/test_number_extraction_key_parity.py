"""tests/unit/test_number_extraction_key_parity.py — 自動輪與手動清單同鍵測試（TASK-144-T6）。

覆蓋 DoD 5 與 mutation 點 M5。
"""
from pathlib import Path

from core.auto_organize import run_one_round
from core.database import organize_failures
from core.database.connection import init_db
from core.scrapers.utils import extract_number as real_extract_number
from web.routers.search import _filter_files_sync


def test_run_one_round_and_filter_files_use_same_basename_key(tmp_path, monkeypatch, mocker):
    """D5: core/auto_organize.py 的 run_one_round() 與 filter-files 對同一份檔案算出的 not_found 鍵逐字相同。"""
    db_path = tmp_path / "test_parity.db"
    init_db(db_path)
    monkeypatch.setattr("core.database.connection.get_db_path", lambda: db_path)

    # 構造父目錄與檔名都像番號的檔案路徑
    fav_dir = tmp_path / "ABP-100"
    fav_dir.mkdir()
    video_file = fav_dir / "CAWD-500.mp4"
    video_file.write_bytes(b"dummy video content")

    # 真正的 oracle：兩側 extract_number **收到的參數**都必須是 basename。
    # 不可改用「假的 extract_number 對含分隔符的字串回父目錄番號」——那是把斷言建在自己編的
    # 行為上。真的 extract_number 在 POSIX 路徑上對整條路徑與對 basename 回同一個值，所以在
    # Linux 測試機上**回傳值分不出** M2／M5 有沒有被引入；分得出來的只有「傳進去的是什麼」。
    # 這裡兩側各包一層委派真函式的記錄器，分開記帳才能指出是哪一側退化。
    auto_args = []
    web_args = []

    def make_recorder(sink):
        def recording_extract(name_or_path):
            sink.append(str(name_or_path))
            return real_extract_number(name_or_path)
        return recording_extract

    monkeypatch.setattr("core.auto_organize.extract_number", make_recorder(auto_args))
    monkeypatch.setattr("core.scrapers.utils.extract_number", make_recorder(web_args))

    # mock smart_search 回空列表，使 run_one_round 走進 record_failure('not_found', ...)
    monkeypatch.setattr("core.auto_organize.smart_search", lambda *args, **kwargs: [])

    config = {
        "search": {"favorite_folder": str(fav_dir)},
        "scraper": {"video_extensions": [".mp4"]},
        "gallery": {"min_size_mb": 0, "path_mappings": {}},
        "translate": {"enabled": False},
    }

    spy_record = mocker.spy(organize_failures, "record_failure")

    # 執行自動輪
    run_one_round(config)

    assert spy_record.call_count == 1
    # 驗證 run_one_round 記錄的 failure key
    call_args = spy_record.call_args[0]
    reason, auto_key, auto_number = call_args[0], call_args[1], call_args[2]
    assert reason == "not_found"
    assert auto_key == "CAWD-500"
    assert auto_number == "CAWD-500"

    # 驗證 filter-files 也使用同一個鍵：此時 DB 內已有 CAWD-500 的 not_found 記憶
    result = _filter_files_sync([str(video_file)])
    assert result["success"] is True
    assert len(result["files"]) == 1
    assert result["files"][0]["skip_reason"] == "not_found"

    # M5／M2 的正向鎖：兩側都必須只拿到純檔名，且**拿到同一個字串**——
    # CD-144-8 的整條命脈就是「自動輪與手動清單對同一份檔案算出同一個鍵」。
    assert auto_args == ["CAWD-500.mp4"], (
        f"run_one_round 傳給 extract_number 的不是 basename：{auto_args!r}"
    )
    assert web_args == ["CAWD-500.mp4"], (
        f"_filter_files_sync 傳給 extract_number 的不是 basename：{web_args!r}"
    )
    assert auto_args == web_args, "兩側取番號的輸入不同源，兩邊會算出不同的鍵"
