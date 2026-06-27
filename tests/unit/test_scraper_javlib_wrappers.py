"""
tests/unit/test_scraper_javlib_wrappers.py

core/scraper.py 薄包裝 unit tests：
  - search_javlib_versions
  - fetch_javlib_by_detail_url

patch target：core.scraper.JavLibraryScraper（使用端 binding，符合 gotchas-backend §1）。
TASK card 原稿指向 core.scrapers.javlibrary.JavLibraryScraper（定義端），
但 core/scraper.py 透過 `from core.scrapers import JavLibraryScraper` 建立了獨立 binding，
因此應 patch 使用端 core.scraper.JavLibraryScraper 才生效（CD-86-12 / gotchas-backend §1）。
"""
from unittest.mock import patch, MagicMock


def test_search_javlib_versions_delegates_and_converts():
    """
    search_javlib_versions:
      - 實例化 JavLibraryScraper → 呼叫 search_all_versions
      - 各 Video 轉 to_legacy_dict()
      - 回 list[dict]，len 和 dict 內容正確
    """
    from core.scraper import search_javlib_versions
    from core.scrapers.models import Video

    fake_video = MagicMock(spec=Video)
    fake_video.to_legacy_dict.return_value = {
        "number": "MIDV-010",
        "url": "https://www.javlibrary.com/ja/javme3bu7e.html",
        "title": "新片",
    }
    with patch('core.scraper.JavLibraryScraper') as MockScraper:
        instance = MockScraper.return_value
        instance.search_all_versions.return_value = [fake_video]
        result = search_javlib_versions("MIDV-010")

    assert len(result) == 1
    assert result[0]["url"] == "https://www.javlibrary.com/ja/javme3bu7e.html"
    instance.search_all_versions.assert_called_once_with("MIDV-010")
    fake_video.to_legacy_dict.assert_called_once()


def test_search_javlib_versions_empty():
    """search_all_versions 回 [] → 回 []（不 raise）"""
    from core.scraper import search_javlib_versions

    with patch('core.scraper.JavLibraryScraper') as MockScraper:
        MockScraper.return_value.search_all_versions.return_value = []
        result = search_javlib_versions("MIDV-010")

    assert result == []


def test_fetch_javlib_by_detail_url_delegates():
    """fetch_javlib_by_detail_url：呼叫 scraper.fetch_by_detail_url，回 Video（或 None）"""
    from core.scraper import fetch_javlib_by_detail_url
    from core.scrapers.models import Video

    fake_video = MagicMock(spec=Video)
    with patch('core.scraper.JavLibraryScraper') as MockScraper:
        MockScraper.return_value.fetch_by_detail_url.return_value = fake_video
        result = fetch_javlib_by_detail_url(
            "https://www.javlibrary.com/ja/javme3bu7e.html", "MIDV-010"
        )

    assert result is fake_video
    MockScraper.return_value.fetch_by_detail_url.assert_called_once_with(
        "https://www.javlibrary.com/ja/javme3bu7e.html", "MIDV-010"
    )
