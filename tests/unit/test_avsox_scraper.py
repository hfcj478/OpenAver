"""
test_avsox_scraper.py - AVSOX 爬蟲單元測試（TASK-73d-T2）

測試策略：
- 全 mock，不連網
- Mock scraper._session.get 回 /cn HTML（含 csrf-token meta）
- Mock scraper._session.post 依 URL 分派：/api/search → search JSON、/api/getMovie → movie JSON
- rate_limit 也 mock 掉（避免 sleep）
- 載入真實 API fixture JSON（tests/fixtures/scrapers/avsox_*.json）
"""

import copy
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ============================================================
# Fixture Loading
# ============================================================

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "scrapers"


def _load(name: str) -> dict:
    with open(_FIXTURES_DIR / name, encoding="utf-8") as f:
        return json.load(f)


# Pre-load all fixtures at module level
SEARCH_051119_917 = _load("avsox_051119-917_search.json")
MOVIE_051119_917 = _load("avsox_051119-917_movie.json")

SEARCH_062719_001 = _load("avsox_062719-001_search.json")
MOVIE_062719_001 = _load("avsox_062719-001_movie.json")

SEARCH_N0762 = _load("avsox_n0762_search.json")
MOVIE_N0762 = _load("avsox_n0762_movie.json")

SEARCH_SONE205_EMPTY = _load("avsox_SONE-205_search_empty.json")

# CSRF token used in all mocked HTML responses
_CSRF_TOKEN = "testtoken123"
_TOKEN_HTML = f'<html><head><meta name="csrf-token" content="{_CSRF_TOKEN}"></head><body></body></html>'


# ============================================================
# Mock Helpers
# ============================================================

def make_get_resp(html: str, status_code: int = 200) -> MagicMock:
    """Build a mock response for _session.get calls (token page)."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = html
    return resp


def make_post_resp(json_obj: dict, status_code: int = 200) -> MagicMock:
    """Build a mock response for _session.post calls (API endpoints)."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json = MagicMock(return_value=json_obj)
    return resp


def _make_post_side_effect(search_json: dict, movie_json: dict):
    """Return a side_effect function that dispatches by URL path."""
    def side_effect(url, *args, **kwargs):
        if "/api/search" in url:
            return make_post_resp(search_json)
        elif "/api/getMovie" in url:
            return make_post_resp(movie_json)
        raise ValueError(f"Unexpected POST url: {url}")
    return side_effect


def run_search(scraper, search_json: dict, movie_json: dict, number: str) -> object:
    """
    Wire up get/post mocks and call scraper.search(number).
    - get: always returns fresh token HTML
    - post: dispatched by URL
    """
    scraper._session.get = MagicMock(return_value=make_get_resp(_TOKEN_HTML))
    scraper._session.post = MagicMock(
        side_effect=_make_post_side_effect(search_json, movie_json)
    )
    return scraper.search(number)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def scraper():
    from core.scrapers.avsox import AVSOXScraper
    with patch("core.scrapers.avsox.rate_limit"):
        s = AVSOXScraper()
        yield s


# ============================================================
# Tests
# ============================================================

class TestHappyPath:
    """051119-917: full-fields happy path"""

    def _get_video(self, scraper):
        return run_search(scraper, SEARCH_051119_917, MOVIE_051119_917, "051119-917")

    def test_video_is_not_none(self, scraper):
        assert self._get_video(scraper) is not None

    def test_duration_is_int(self, scraper):
        video = self._get_video(scraper)
        assert video is not None
        assert video.duration == 63
        assert isinstance(video.duration, int)

    def test_series_present(self, scraper):
        video = self._get_video(scraper)
        assert video is not None
        assert video.series == "オリジナル動画"

    def test_number_canonical(self, scraper):
        """number must use the passed-in canonical number, not movieFanHao."""
        video = self._get_video(scraper)
        assert video is not None
        assert video.number == "051119-917"

    def test_maker(self, scraper):
        video = self._get_video(scraper)
        assert video is not None
        assert video.maker == "カリビアンコム"

    def test_title(self, scraper):
        video = self._get_video(scraper)
        assert video is not None
        assert video.title == "結婚直前で心が揺らいだ新婦の情事"

    def test_date(self, scraper):
        video = self._get_video(scraper)
        assert video is not None
        assert video.date == "2019-05-11"

    def test_actresses(self, scraper):
        video = self._get_video(scraper)
        assert video is not None
        names = [a.name for a in video.actresses]
        assert names == ["@YOU"]

    def test_tags(self, scraper):
        video = self._get_video(scraper)
        assert video is not None
        assert len(video.tags) == 7
        assert "AV女优" in video.tags

    def test_cover_url(self, scraper):
        video = self._get_video(scraper)
        assert video is not None
        expected = MOVIE_051119_917["data"]["posterLarge"]
        assert video.cover_url == expected

    def test_detail_url(self, scraper):
        video = self._get_video(scraper)
        assert video is not None
        movie_id = MOVIE_051119_917["data"]["movieId"]  # "nwrjayk"
        assert video.detail_url == f"{scraper._working_domain}/cn/movies/{movie_id}"


class TestNoDuration:
    """051119-917 movie dict with 'length' deleted → duration is None"""

    def test_duration_none(self, scraper):
        movie_no_length = copy.deepcopy(MOVIE_051119_917)
        del movie_no_length["data"]["length"]
        video = run_search(scraper, SEARCH_051119_917, movie_no_length, "051119-917")
        assert video is not None
        assert video.duration is None


class TestNoSeries:
    """062719-001 movie has no 'series' key → series == '' """

    def test_series_empty(self, scraper):
        video = run_search(scraper, SEARCH_062719_001, MOVIE_062719_001, "062719-001")
        assert video is not None
        assert video.series == ""

    def test_video_is_not_none(self, scraper):
        video = run_search(scraper, SEARCH_062719_001, MOVIE_062719_001, "062719-001")
        assert video is not None

    def test_number_canonical_underscore_not_leaked(self, scraper):
        """062719-001 fixture has movieFanHao=062719_001 (underscore); output must use hyphen."""
        video = run_search(scraper, SEARCH_062719_001, MOVIE_062719_001, "062719-001")
        assert video is not None
        assert video.number == "062719-001"


class TestTokyoHot:
    """n0762 → N0762 canonical (single-letter + 4-digit, no hyphen)"""

    def test_number_n0762_canonical(self, scraper):
        video = run_search(scraper, SEARCH_N0762, MOVIE_N0762, "n0762")
        assert video is not None
        assert video.number == "N0762"


class TestNumberMatch:
    """_number_match edge cases"""

    def test_hyphen_underscore_match(self, scraper):
        assert scraper._number_match("062719-001", "062719_001") is True

    def test_different_numbers_no_match(self, scraper):
        assert scraper._number_match("SONE-205", "SONE-206") is False


class TestEmptySearch:
    """SONE-205: search returns empty data list → search() returns None"""

    def test_empty_search_returns_none(self, scraper):
        # For an empty-search result, post to /api/search returns empty; getMovie never called.
        def post_side_effect(url, *args, **kwargs):
            if "/api/search" in url:
                return make_post_resp(SEARCH_SONE205_EMPTY)
            raise ValueError(f"Unexpected POST to {url} for empty-search test")

        scraper._session.get = MagicMock(return_value=make_get_resp(_TOKEN_HTML))
        scraper._session.post = MagicMock(side_effect=post_side_effect)
        result = scraper.search("SONE-205")
        assert result is None


class TestTokenExpireRetry:
    """
    Resilience: first POST returns code != 200 (CsrfExpired) →
    scraper clears cache, re-runs _ensure_session, retries → returns valid Video.

    post side_effect sequence: [bad_resp, search_resp, getMovie_resp]
    get side_effect: always returns fresh token HTML (serves both initial + retry calls)
    """

    def test_retry_after_csrf_expired_succeeds(self, scraper):
        from core.scrapers.avsox import CsrfExpired

        # HTTP 200 but JSON-level code != 200 → _api_post raises CsrfExpired (avsox.py:107-108)
        bad_resp = make_post_resp({"code": 403, "data": None}, status_code=200)

        post_responses = iter([
            bad_resp,                                    # First call (search) → CsrfExpired
            make_post_resp(SEARCH_051119_917),           # Retry search
            make_post_resp(MOVIE_051119_917),            # Retry getMovie
        ])

        def post_side_effect(url, *args, **kwargs):
            return next(post_responses)

        scraper._session.get = MagicMock(return_value=make_get_resp(_TOKEN_HTML))
        scraper._session.post = MagicMock(side_effect=post_side_effect)

        video = scraper.search("051119-917")
        assert video is not None
        assert video.number == "051119-917"


class TestAllDomainsFail:
    """
    Resilience: _session.get always returns status != 200 (or text without meta) →
    _ensure_session returns (None, None) → search() returns None.
    """

    def test_all_domains_fail_returns_none(self, scraper):
        scraper._session.get = MagicMock(return_value=make_get_resp("", status_code=503))
        result = scraper.search("051119-917")
        assert result is None

    def test_all_domains_no_csrf_meta_returns_none(self, scraper):
        """get returns 200 but HTML has no csrf-token meta → still fails."""
        scraper._session.get = MagicMock(return_value=make_get_resp("<html><body>No token here</body></html>"))
        result = scraper.search("051119-917")
        assert result is None
