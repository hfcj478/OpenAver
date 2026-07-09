"""
TestDMMScraperNewFields — DMM 爬蟲新欄位測試
（搬自 tests/integration/test_new_scrapers.py TestDMMScraperNewFields）

director / duration / series / label / sample_images 邊界條件
"""
import pytest
from unittest.mock import patch, MagicMock

from core.scrapers.dmm import DMMScraper
from core.scrapers.models import ScraperConfig


@pytest.fixture(autouse=True)
def _no_rate_limit(monkeypatch):
    """跳過 rate_limit sleep，加速測試"""
    monkeypatch.setattr("core.scrapers.dmm.rate_limit", lambda *a, **kw: None)


# ============================================================
# Mock Data
# ============================================================

DMM_DETAIL_RESPONSE_FULL = {
    "data": {
        "ppvContent": {
            "id": "sone00205",
            "title": "成人への卒業",
            "description": "テスト",
            "packageImage": {"largeUrl": "https://pics.dmm.co.jp/sone205pl.jpg"},
            "makerReleasedAt": "2024-03-19T00:00:00+09:00",
            "duration": 8966,
            "actresses": [{"name": "Nana Miho"}],
            "directors": [{"name": "前田文豪"}],
            "series": {"name": "S1 系列"},
            "maker": {"name": "S1 NO.1 STYLE"},
            "makerContentId": "SONE-205",
            "sampleImages": [
                {"imageUrl": "https://a.jpg"},
                {"imageUrl": "https://b.jpg"},
            ],
        }
    }
}


def _make_mock_resp(status_code=200, json_data=None, content=None):
    """Build a MagicMock that mimics requests.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    if json_data is not None:
        mock_resp.json = lambda: json_data
    if content is not None:
        mock_resp.content = content
    return mock_resp


# ============================================================
# Tests
# ============================================================

class TestDMMScraperNewFields:
    """DMM 爬蟲新欄位測試（director / duration / series / label / sample_images）"""

    @pytest.fixture
    def dmm_scraper(self, tmp_path, monkeypatch):
        import core.scrapers.dmm as dmm_module
        monkeypatch.setattr(dmm_module, "CACHE_FILE", tmp_path / "dmm_content_ids.json")
        monkeypatch.setattr(dmm_module, "PREFIX_FILE", tmp_path / "dmm_prefix_hints.json")
        config = ScraperConfig(proxy_url="http://test-proxy:8080")
        return DMMScraper(config)

    def _fetch(self, dmm_scraper, response_data, probe_return=([], "S1 NO.1 STYLE"),
               sample_images_return=[]):
        """Helper：用 mock response 呼叫 search，回傳 Video"""
        detail_resp = _make_mock_resp(status_code=200, json_data=response_data)
        with patch.object(dmm_scraper._session, 'post', return_value=detail_resp), \
             patch.object(dmm_scraper, '_probe_genres', return_value=probe_return), \
             patch.object(dmm_scraper, '_probe_sample_images', return_value=sample_images_return), \
             patch.object(dmm_scraper, '_fetch_tags_from_html', return_value=[]), \
             patch('core.scrapers.dmm.rate_limit'):
            return dmm_scraper.search("SONE-205")

    # ------------------------------------------------------------------
    # Happy path — all fields present
    # ------------------------------------------------------------------

    def test_all_new_fields_happy_path(self, dmm_scraper):
        """duration / director / series / label / sample_images 全部正常"""
        video = self._fetch(
            dmm_scraper,
            DMM_DETAIL_RESPONSE_FULL,
            probe_return=([], "S1 NO.1 STYLE"),
            sample_images_return=["https://a.jpg", "https://b.jpg"],
        )

        assert video is not None
        # duration: 8966 // 60 == 149
        assert video.duration == 149
        # director
        assert video.director == "前田文豪"
        # series
        assert video.series == "S1 系列"
        # label from probe
        assert video.label == "S1 NO.1 STYLE"
        # sample_images from probe
        assert video.sample_images == ["https://a.jpg", "https://b.jpg"]

    # ------------------------------------------------------------------
    # duration edge cases
    # ------------------------------------------------------------------

    def test_duration_null(self, dmm_scraper):
        """duration=null → Video.duration is None"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "duration": None,
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.duration is None

    def test_duration_zero(self, dmm_scraper):
        """duration=0 → Video.duration == 0"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "duration": 0,
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.duration == 0

    # ------------------------------------------------------------------
    # director edge cases
    # ------------------------------------------------------------------

    def test_directors_empty_list(self, dmm_scraper):
        """directors=[] → Video.director == ''"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "directors": [],
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.director == ""

    def test_directors_null(self, dmm_scraper):
        """directors=null → Video.director == ''"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "directors": None,
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.director == ""

    # ------------------------------------------------------------------
    # series edge cases
    # ------------------------------------------------------------------

    def test_series_null(self, dmm_scraper):
        """series=null → Video.series == ''"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "series": None,
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.series == ""

    # ------------------------------------------------------------------
    # label edge cases (from _probe_genres return value)
    # ------------------------------------------------------------------

    def test_label_from_probe(self, dmm_scraper):
        """probe 回傳 label → Video.label 正確設定"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], "S1 NO.1 STYLE"))
        assert video is not None
        assert video.label == "S1 NO.1 STYLE"

    def test_label_probe_empty(self, dmm_scraper):
        """probe 回傳 '' → Video.label == ''"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], ""))
        assert video is not None
        assert video.label == ""

    # ------------------------------------------------------------------
    # sample_images edge cases
    # ------------------------------------------------------------------

    def test_sample_images_null(self, dmm_scraper):
        """_probe_sample_images 回傳 [] → video.sample_images == []"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], "S1 NO.1 STYLE"),
                            sample_images_return=[])
        assert video is not None
        assert video.sample_images == []

    def test_sample_images_empty_list(self, dmm_scraper):
        """_probe_sample_images 回傳空列表 → video.sample_images == []"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], "S1 NO.1 STYLE"),
                            sample_images_return=[])
        assert video is not None
        assert video.sample_images == []

    def test_sample_images_missing_imageUrl_filtered(self, dmm_scraper):
        """_probe_sample_images 過濾後回傳空列表 → sample_images == []"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL,
                            probe_return=([], "S1 NO.1 STYLE"),
                            sample_images_return=[])
        assert video is not None
        assert video.sample_images == []

    # ------------------------------------------------------------------
    # summary (description) edge cases — TASK-93-T1
    # ------------------------------------------------------------------

    def test_summary_present(self, dmm_scraper):
        """description 存在且非空 → video.summary == 原文"""
        video = self._fetch(dmm_scraper, DMM_DETAIL_RESPONSE_FULL)
        assert video is not None
        assert video.summary == "テスト"

    def test_summary_key_missing(self, dmm_scraper):
        """description key 不存在 → video.summary == ''（不 raise）"""
        content = {**DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"]}
        content.pop("description", None)
        data = {"data": {"ppvContent": content}}
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.summary == ""

    def test_summary_empty_string(self, dmm_scraper):
        """description 為空字串 → video.summary == ''"""
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "description": "",
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.summary == ""

    def test_summary_null(self, dmm_scraper):
        """description=null (JSON null, key present) → video returned with summary==''.

        Regression (P2-2): `.get('description', '')` returns None when the value is
        JSON null → Video(summary=None) raises ValidationError → broad except swallows
        it → search returns None → the WHOLE DMM source is dropped. The `or ''` fix
        keeps the source alive.
        """
        data = {
            "data": {
                "ppvContent": {
                    **DMM_DETAIL_RESPONSE_FULL["data"]["ppvContent"],
                    "description": None,
                }
            }
        }
        video = self._fetch(dmm_scraper, data)
        assert video is not None
        assert video.summary == ""
