"""
tests/unit/test_javlibrary_scraper.py
──────────────────────────────────────
mock transport 驗 search 流程（TDD-lite RED → GREEN）

情境 a–g：
  a) single-hit 302 → detail page 直接 parse（fetch 呼叫一次）
  b) multi-result → 兩次 fetch
  c) not-found：_extract_detail_url 回 None
  d) not-found：title + cover 同時空
  e) transport None → CfTransportUnavailable
  f) fetch 回 CF challenge HTML → CfChallengeRequired
  g) search_by_keyword 回空 list
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.cf_transport import CfChallengeRequired, CfTransportUnavailable
from core.scrapers.javlibrary import JavLibraryScraper, _extract_all_detail_urls
from core.scrapers.models import Video

# ──────────────────────────────────────
# 共用 fixture HTML
# ──────────────────────────────────────

DETAIL_HTML = """\
<html><head><title>TCD-332 恥辱の映像</title></head><body>
  <h3 class="post-title">TCD-332　恥辱の映像 鈴白めいか</h3>
  <div id="video_id"><table><tr><td class="text">TCD-332</td></tr></table></div>
  <div id="video_date"><table><tr><td class="text">2026-05-12</td></tr></table></div>
  <div id="video_length"><table><tr><td class="text"><span>126</span></td></tr></table></div>
  <div id="video_director"><table><tr><td class="text"><span><a>監督名</a></span></td></tr></table></div>
  <div id="video_maker"><table><tr><td class="text"><span><a>TRANS CLUB</a></span></td></tr></table></div>
  <div id="video_label"><table><tr><td class="text"><span><a>----</a></span></td></tr></table></div>
  <div id="video_review"><span>(8.50)</span></div>
  <img id="video_jacket_img" src="//pics.dmm.co.jp/mono/tcd332pl.jpg" />
  <div id="video_genres"><a>変性者</a><a>単体作品</a></div>
  <div id="video_cast"><span class="star"><a>鈴白めいか</a></span></div>
  <div class="previewthumbs">
    <a href="//pics.dmm.co.jp/s1.jpg"><img></a>
  </div>
</body></html>"""

SEARCH_RESULT_HTML = """\
<html><head><title>Search Results</title></head><body>
  <div class="video"><a href="./javmezzbqu.html" title="TCD-332 恥辱...">TCD-332 恥辱...</a></div>
</body></html>"""

EMPTY_DETAIL_HTML = """\
<html><head><title>TCD-332</title></head><body>
  <div id="video_id"><table><tr><td class="text">TCD-332</td></tr></table></div>
</body></html>"""

CF_CHALLENGE_HTML = """\
<html><head><title>Just a moment...</title></head><body>
  <form id="challenge-form"></form>
</body></html>"""

NO_RESULT_HTML = """\
<html><head><title>No Results</title></head><body>
  <p>No results.</p>
</body></html>"""

PATCH_TARGET = "core.scrapers.javlibrary.get_cf_transport"


def _make_transport(*html_responses: str) -> MagicMock:
    """建立回傳依序 HTML 的 mock transport"""
    transport = MagicMock()
    transport.fetch.side_effect = list(html_responses)
    return transport


# ──────────────────────────────────────
# (a) single-hit 302 → detail page 直接 parse
# ──────────────────────────────────────

def test_search_single_hit_returns_video():
    """mock transport fetch 一次回傳含 #video_id 的 HTML，結果應回傳 Video"""
    transport = _make_transport(DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")
    assert isinstance(result, Video)
    assert result.source == "javlibrary"


def test_search_single_hit_detail_url_is_empty():
    """FIX-4：single-hit 302 路徑 detail_url 應為空字串（非 search-php URL）"""
    transport = _make_transport(DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")
    assert result is not None
    assert result.detail_url == "", (
        f"single-hit 的 detail_url 應為空字串（非 search-php URL），got: {result.detail_url!r}"
    )


def test_search_single_hit_fetch_called_once():
    """single-hit 路徑 fetch 只應呼叫一次"""
    transport = _make_transport(DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        scraper.search("TCD-332")
    assert transport.fetch.call_count == 1


def test_search_single_hit_title_not_empty():
    transport = _make_transport(DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")
    assert result is not None
    assert result.title != ""


def test_search_single_hit_tags():
    transport = _make_transport(DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")
    assert result is not None
    assert "変性者" in result.tags


def test_search_single_hit_rating():
    transport = _make_transport(DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")
    assert result is not None
    assert result.rating == 8.5


# ──────────────────────────────────────
# (b) multi-result → 兩次 fetch
# ──────────────────────────────────────

def test_search_multi_result_returns_video():
    """第一次 fetch 搜尋列表，第二次 fetch 詳情頁，應回傳 Video"""
    transport = _make_transport(SEARCH_RESULT_HTML, DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")
    assert isinstance(result, Video)


def test_search_multi_result_fetch_called_twice():
    """multi-result 路徑 fetch 應呼叫兩次"""
    transport = _make_transport(SEARCH_RESULT_HTML, DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        scraper.search("TCD-332")
    assert transport.fetch.call_count == 2


# ──────────────────────────────────────
# (c) not-found：_extract_detail_url 回 None
# ──────────────────────────────────────

def test_search_not_found_no_video_links():
    """搜尋頁無 .video a，應回傳 None 不拋例外"""
    transport = _make_transport(NO_RESULT_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")
    assert result is None


# ──────────────────────────────────────
# (d) not-found：title + cover 同時空
# ──────────────────────────────────────

def test_search_not_found_empty_title_and_cover():
    """parse 出的 title/cover 均空，應回傳 None"""
    transport = _make_transport(EMPTY_DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")
    assert result is None


# ──────────────────────────────────────
# (e) transport None → CfTransportUnavailable
# ──────────────────────────────────────

def test_search_no_transport_raises_unavailable():
    """get_cf_transport() 回傳 None 應拋 CfTransportUnavailable"""
    with patch(PATCH_TARGET, return_value=None):
        scraper = JavLibraryScraper()
        with pytest.raises(CfTransportUnavailable):
            scraper.search("TCD-332")


# ──────────────────────────────────────
# (f) fetch 回 CF challenge HTML → CfChallengeRequired
# ──────────────────────────────────────

def test_search_cf_challenge_raises_required():
    """fetch 回 CF challenge page 應拋 CfChallengeRequired"""
    transport = _make_transport(CF_CHALLENGE_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        with pytest.raises(CfChallengeRequired):
            scraper.search("TCD-332")


# ──────────────────────────────────────
# (g) search_by_keyword 回空 list
# ──────────────────────────────────────

def test_search_by_keyword_returns_empty_list():
    """search_by_keyword 一律回傳空 list，不拋例外"""
    transport = MagicMock()
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search_by_keyword("葵つかさ")
    assert result == []
    # transport.fetch 不應被呼叫
    transport.fetch.assert_not_called()


def test_search_by_keyword_no_transport_still_returns_empty():
    """即使 transport=None，search_by_keyword 仍回傳空 list"""
    with patch(PATCH_TARGET, return_value=None):
        scraper = JavLibraryScraper()
        result = scraper.search_by_keyword("keyword")
    assert result == []


# ──────────────────────────────────────
# (h) 回歸：footer 含 利用規約/18歳 不誤判 age gate
# ──────────────────────────────────────

# 有效詳情頁 HTML — 含 #video_id / h3.post-title / img#video_jacket_img，
# 同時在 footer 放了 「利用規約」與「18歳以上」字串（真實 javlibrary 頁面的樣貌）。
# 修正前：_is_age_gate 命中 footer → search() 誤拋 CfChallengeRequired。
# 修正後：search() 正常解析，回傳 Video。
DETAIL_HTML_WITH_TERMS_FOOTER = """\
<html><head><title>TCD-332 恥辱の映像</title></head><body>
  <h3 class="post-title">TCD-332　恥辱の映像 鈴白めいか</h3>
  <div id="video_id"><table><tr><td class="text">TCD-332</td></tr></table></div>
  <div id="video_date"><table><tr><td class="text">2026-05-12</td></tr></table></div>
  <div id="video_length"><table><tr><td class="text"><span>126</span></td></tr></table></div>
  <div id="video_maker"><table><tr><td class="text"><span><a>TRANS CLUB</a></span></td></tr></table></div>
  <div id="video_label"><table><tr><td class="text"><span><a>----</a></span></td></tr></table></div>
  <div id="video_review"><span>(8.50)</span></div>
  <img id="video_jacket_img" src="//pics.dmm.co.jp/mono/tcd332pl.jpg" />
  <div id="video_genres"><a>変性者</a></div>
  <div id="video_cast"><span class="star"><a>鈴白めいか</a></span></div>
  <footer>
    <a href="/ja/agreement.php">利用規約</a>
    本サービスは18歳以上の方のみご利用いただけます。
    <a href="/ja/index.php?mode=over18">18歳以上</a>
  </footer>
</body></html>"""


def test_search_valid_page_with_terms_footer_does_not_raise():
    """
    回歸：有效詳情頁 footer 含「利用規約」「18歳以上」字串，
    search() 不應拋 CfChallengeRequired，應正常回傳 Video
    且 title / cover 正確。
    （修正前此測試 FAIL；修正後 PASS）
    """
    transport = _make_transport(DETAIL_HTML_WITH_TERMS_FOOTER)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")

    assert isinstance(result, Video), "應回傳 Video，不應拋例外或回傳 None"
    assert "恥辱" in result.title, f"title 應含番號後標題，got: {result.title!r}"
    assert result.cover_url.startswith("https://"), f"cover_url 應補全 https:，got: {result.cover_url!r}"


# ──────────────────────────────────────
# duration int 轉換明確斷言
# ──────────────────────────────────────

def test_search_single_hit_duration_is_int():
    """single-hit 路徑 duration 應解析為 int 126（不是 str 或 None）"""
    transport = _make_transport(DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")
    assert result is not None
    assert result.duration == 126, f"duration 應為 int 126，got: {result.duration!r}"
    assert isinstance(result.duration, int), f"duration 型別應為 int，got: {type(result.duration)}"


# ──────────────────────────────────────
# FIX-5：number guard — fallback 回錯片守衛
# ──────────────────────────────────────

# 詳情頁 HTML，番號為 ABW-001（與請求 TCD-332 不符）
WRONG_NUMBER_DETAIL_HTML = """\
<html><head><title>ABW-001 別の映像</title></head><body>
  <h3 class="post-title">ABW-001　別の映像 テスト女優</h3>
  <div id="video_id"><table><tr><td class="text">ABW-001</td></tr></table></div>
  <div id="video_date"><table><tr><td class="text">2026-01-10</td></tr></table></div>
  <div id="video_maker"><table><tr><td class="text"><span><a>テストメーカー</a></span></td></tr></table></div>
  <img id="video_jacket_img" src="//pics.dmm.co.jp/mono/abw001pl.jpg" />
  <div id="video_genres"><a>単体作品</a></div>
</body></html>"""

# 多命中搜尋結果頁（番號 TCD-332 無精確比對，fallback 到第一個連結）
SEARCH_RESULT_MISMATCH_HTML = """\
<html><head><title>Search Results</title></head><body>
  <div class="video"><a href="./javabwxxx.html" title="ABW-001 別の映像">ABW-001 別の映像</a></div>
  <div class="video"><a href="./javother.html" title="ZZZ-999 他の映像">ZZZ-999 他の映像</a></div>
</body></html>"""


def test_search_multi_result_number_mismatch_returns_none():
    """
    FIX-5：多命中 fallback 到 links[0]，parse 出的番號與請求番號不符
    → search() 應回 None（誠實 miss，不回錯片資料）。
    """
    # 第一次 fetch 回搜尋列表（無 TCD-332 精確比對，fallback links[0] = ABW-001 頁）
    # 第二次 fetch 回 ABW-001 詳情頁（番號不符）
    transport = _make_transport(SEARCH_RESULT_MISMATCH_HTML, WRONG_NUMBER_DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")

    assert result is None, (
        f"fallback 回錯番號（ABW-001 ≠ TCD-332）時應回 None，got: {result!r}"
    )


def test_search_multi_result_correct_number_returns_video():
    """
    FIX-5 正常路徑：多命中，links[0] parse 出的番號與請求番號相符
    → search() 仍應回 Video（守衛不誤殺合法命中）。
    """
    transport = _make_transport(SEARCH_RESULT_HTML, DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.search("TCD-332")

    assert isinstance(result, Video), (
        f"number 相符的多命中路徑應回 Video，got: {result!r}"
    )
    assert result.number == "TCD-332"


# ──────────────────────────────────────
# T1：_extract_all_detail_urls + search_all_versions + fetch_by_detail_url
# ──────────────────────────────────────

# 多版本列表頁（模擬 MIDV-010 風格）
# ─ 含 2 個 MIDV-010 框（各 1 主連結 + 3 href 空的動作連結）
# ─ 另含 1 個前綴鄰號框（MIDV-100，boundary-match 測試用）
MULTI_VERSION_LIST_HTML = """\
<html><head><title>品番検索結果</title></head><body>
  <div class="video">
    <a href="./javlidaori.html" title="MIDV-010 Angel Kiss ビアンたちの愛情物語">MIDV-010 Angel Kiss</a>
    <a href="">これが欲しい</a><a href="">見た</a><a href="">持ってる</a>
  </div>
  <div class="video">
    <a href="./javme3bu7e.html" title="MIDV-010 連続中出しオーガズムSP">MIDV-010 連続...</a>
    <a href="">これが欲しい</a><a href="">見た</a><a href="">持ってる</a>
  </div>
  <div class="video">
    <a href="./javmidv100.html" title="MIDV-100 隣のお姉さん">MIDV-100 隣の...</a>
    <a href="">これが欲しい</a><a href="">見た</a><a href="">持ってる</a>
  </div>
</body></html>"""

# 舊片 detail（date=2009-12-01）
OLD_DETAIL_HTML = """\
<html><head><title>MIDV-010 Angel Kiss</title></head><body>
  <h3 class="post-title">MIDV-010 Angel Kiss ビアンたちの愛情物語</h3>
  <div id="video_id"><table><tr><td class="text">MIDV-010</td></tr></table></div>
  <div id="video_date"><table><tr><td class="text">2009-12-01</td></tr></table></div>
  <div id="video_maker"><table><tr><td class="text"><span><a>グラフィティジャパン</a></span></td></tr></table></div>
  <img id="video_jacket_img" src="//pics.dmm.co.jp/mono/midv010old.jpg" />
</body></html>"""

# 新片 detail（date=2021-12-07）
NEW_DETAIL_HTML = """\
<html><head><title>MIDV-010 連続中出し</title></head><body>
  <h3 class="post-title">MIDV-010 連続中出しオーガズムSP</h3>
  <div id="video_id"><table><tr><td class="text">MIDV-010</td></tr></table></div>
  <div id="video_date"><table><tr><td class="text">2021-12-07</td></tr></table></div>
  <div id="video_maker"><table><tr><td class="text"><span><a>MOODYZ</a></span></td></tr></table></div>
  <img id="video_jacket_img" src="//pics.dmm.co.jp/mono/midv010new.jpg" />
</body></html>"""


def test_extract_all_detail_urls_collects_all():
    """
    多相符 + href 空濾掉 + 前綴鄰號 boundary 濾掉 + 無相符回 []。
    """
    base = "https://www.javlibrary.com/ja"

    # 主案例：MIDV-010 多版本列表，MIDV-100 須被 boundary 濾掉
    urls = _extract_all_detail_urls(MULTI_VERSION_LIST_HTML, "MIDV-010", base)
    assert len(urls) == 2, f"應收 2 個相符 url（MIDV-100 被 boundary 過濾），got {urls}"
    assert any("javlidaori" in u for u in urls), "舊片 url 應被收進"
    assert any("javme3bu7e" in u for u in urls), "新片 url 應被收進"
    assert not any("javmidv100" in u for u in urls), "MIDV-100 應被 boundary-match 濾掉"

    # href 空的動作連結濾掉
    href_null_html = """\
<html><body>
  <div class="video">
    <a href="./javtest.html" title="MIDV-010 テスト">MIDV-010 テスト</a>
    <a href="">これが欲しい</a>
    <a>見た</a>
  </div>
</body></html>"""
    urls2 = _extract_all_detail_urls(href_null_html, "MIDV-010", base)
    assert urls2 == [f"{base}/javtest.html"], f"動作連結不應被收進，got {urls2}"

    # 無相符 → []（不 fallback links[0]）
    no_match_html = """\
<html><body>
  <div class="video">
    <a href="./javother.html" title="ZZZ-999 他の映像">ZZZ-999</a>
  </div>
</body></html>"""
    urls3 = _extract_all_detail_urls(no_match_html, "MIDV-010", base)
    assert urls3 == [], f"無相符應回 []，got {urls3}"

    # 前置黏連號濾掉（Gemini P1-A：lookbehind 擋 AMIDV-010 / 1MIDV-010）
    prefix_glued_html = """\
<html><body>
  <div class="video"><a href="./javA.html" title="AMIDV-010 前置字母">AMIDV-010</a></div>
  <div class="video"><a href="./javB.html" title="1MIDV-010 前置數字">1MIDV-010</a></div>
</body></html>"""
    urls4 = _extract_all_detail_urls(prefix_glued_html, "MIDV-010", base)
    assert urls4 == [], f"前置黏連號（AMIDV-010/1MIDV-010）應被 lookbehind 濾掉，got {urls4}"

    # P2-1 一致性：番號只在 link text（title 為空）也應收進（對齊 _extract_detail_url 的 text OR title）
    # mutation：把 text 比對拿掉 → 此 case RED（urls5 變 []）
    text_only_html = """\
<html><body>
  <div class="video"><a href="./javtextonly.html" title="">MIDV-010 タイトル空</a></div>
</body></html>"""
    urls5 = _extract_all_detail_urls(text_only_html, "MIDV-010", base)
    assert urls5 == [f"{base}/javtextonly.html"], \
        f"番號在 get_text()（title 空）應被收進（title-OR-text），got {urls5}"


def test_search_all_versions_multi():
    """
    多版本列表 → 2 筆相符 detail → 新片在 index 0（date desc）。
    * index 0 = MOODYZ 2021（新），index 1 = グラフィティ 2009（舊）
    * MIDV-100 框應被 boundary-match 濾掉（不收進 urls）
    * href 空的動作連結不收
    """
    # fetch 呼叫順序：列表頁 → old detail（javlidaori）→ new detail（javme3bu7e）
    transport = _make_transport(MULTI_VERSION_LIST_HTML, OLD_DETAIL_HTML, NEW_DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        versions = scraper.search_all_versions("MIDV-010")

    assert len(versions) == 2
    assert versions[0].date == "2021-12-07", f"新片應在 index 0，got {versions[0].date!r}"
    assert versions[1].date == "2009-12-01", f"舊片應在 index 1，got {versions[1].date!r}"
    assert versions[0].maker == "MOODYZ"
    # transport.fetch 呼叫：1（列表）+ 2（detail × 2）= 3 次
    assert transport.fetch.call_count == 3


def test_search_all_versions_single_hit_302():
    """
    302 單一命中（首次 fetch 已是 detail page）→ 回 1-element list，
    fetch 只呼叫一次。
    """
    transport = _make_transport(DETAIL_HTML)  # 含 #video_id
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        versions = scraper.search_all_versions("TCD-332")

    assert len(versions) == 1
    assert isinstance(versions[0], Video)
    assert transport.fetch.call_count == 1


def test_fetch_by_detail_url():
    """
    直接給 detail_url → 正確回傳 Video，detail_url 落地在 Video.detail_url。
    """
    transport = _make_transport(DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        scraper = JavLibraryScraper()
        result = scraper.fetch_by_detail_url(
            "https://www.javlibrary.com/ja/javmezzbqu.html",
            "TCD-332",
        )

    assert isinstance(result, Video)
    assert result.detail_url == "https://www.javlibrary.com/ja/javmezzbqu.html"
    assert transport.fetch.call_count == 1


# ── helper 抽取後 search() 行為零回歸 ──

def test_search_unchanged_regression_single_hit():
    """helper 抽取後 search() 的 single-hit 行為不變。"""
    transport = _make_transport(DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        result = JavLibraryScraper().search("TCD-332")
    assert isinstance(result, Video)
    assert result.detail_url == ""  # FIX-4


def test_search_unchanged_regression_multi_result():
    """helper 抽取後 search() 的 multi-result 行為不變。"""
    transport = _make_transport(SEARCH_RESULT_HTML, DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        result = JavLibraryScraper().search("TCD-332")
    assert isinstance(result, Video)
    assert transport.fetch.call_count == 2


def test_search_unchanged_regression_not_found():
    """helper 抽取後 no match → None。"""
    transport = _make_transport(NO_RESULT_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        result = JavLibraryScraper().search("TCD-332")
    assert result is None


def test_search_unchanged_regression_empty_parse():
    """helper 抽取後 title+cover 空 → None。"""
    transport = _make_transport(EMPTY_DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        result = JavLibraryScraper().search("TCD-332")
    assert result is None


def test_search_unchanged_regression_number_mismatch():
    """helper 抽取後 FIX-5 番號不符 → None。"""
    transport = _make_transport(SEARCH_RESULT_MISMATCH_HTML, WRONG_NUMBER_DETAIL_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        result = JavLibraryScraper().search("TCD-332")
    assert result is None


# ── CF 案例 ──

def test_search_all_versions_list_cf_challenge_raises():
    """search_all_versions：列表頁遇 CF challenge → CfChallengeRequired。"""
    transport = _make_transport(CF_CHALLENGE_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        with pytest.raises(CfChallengeRequired):
            JavLibraryScraper().search_all_versions("MIDV-010")


def test_search_all_versions_detail_cf_challenge_raises():
    """search_all_versions：detail fetch 遇 CF challenge → CfChallengeRequired。"""
    transport = _make_transport(MULTI_VERSION_LIST_HTML, CF_CHALLENGE_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        with pytest.raises(CfChallengeRequired):
            JavLibraryScraper().search_all_versions("MIDV-010")


def test_search_all_versions_transport_none_raises():
    """get_cf_transport() None → CfTransportUnavailable。"""
    with patch(PATCH_TARGET, return_value=None):
        with pytest.raises(CfTransportUnavailable):
            JavLibraryScraper().search_all_versions("MIDV-010")


def test_fetch_by_detail_url_cf_challenge_raises():
    """fetch_by_detail_url：detail fetch 遇 CF challenge → CfChallengeRequired。"""
    transport = _make_transport(CF_CHALLENGE_HTML)
    with patch(PATCH_TARGET, return_value=transport):
        with pytest.raises(CfChallengeRequired):
            JavLibraryScraper().fetch_by_detail_url(
                "https://www.javlibrary.com/ja/javtest.html", "TCD-332"
            )


def test_fetch_by_detail_url_transport_none_raises():
    """fetch_by_detail_url：transport None → CfTransportUnavailable。"""
    with patch(PATCH_TARGET, return_value=None):
        with pytest.raises(CfTransportUnavailable):
            JavLibraryScraper().fetch_by_detail_url(
                "https://www.javlibrary.com/ja/javtest.html", "TCD-332"
            )
