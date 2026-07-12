"""
test_javdb_cainfo.py - javdb CAINFO override 單元測試（TASK-98-T1）

測試策略：
- 全 mock（本 dev 機 Linux + ASCII certifi 路徑，天然走 no-op 分支）
- patch 使用端 binding（core.scrapers.javdb.*），非定義端
- 每測例 autouse fixture 重置 module-level 快取（_cainfo_override=_UNSET, _ca_warned=False）
- 沿用 tests/unit/test_javdb_scraper.py 的 fixture 寫法 + TestJavdbCurlCffiDiagnostics 慣例
"""

import builtins
import importlib
import logging

import pytest
from unittest.mock import patch, MagicMock

from core.scrapers import javdb


# ============================================================
# Autouse fixture：每測例重置 module-level cache（避免測試間洩漏）
# ============================================================

@pytest.fixture(autouse=True)
def reset_cainfo_cache(monkeypatch):
    monkeypatch.setattr(javdb, "_cainfo_override", javdb._UNSET)
    monkeypatch.setattr(javdb, "_ca_warned", False)


@pytest.fixture
def scraper():
    with patch("core.scrapers.javdb.rate_limit"):
        s = javdb.JavDBScraper()
        yield s


# ============================================================
# 1. non-win platform → None; _get_html 不帶 curl_options
# ============================================================

class TestNonWin:
    def test_helper_returns_none_on_non_win(self, monkeypatch):
        monkeypatch.setattr(javdb.sys, "platform", "linux")
        monkeypatch.setattr(javdb.certifi, "where", lambda: "/etc/ssl/certs/ca-certificates.crt")
        assert javdb._cainfo_override_bytes() is None

    def test_non_win_short_circuits_before_encode_on_non_ascii_path(self, monkeypatch):
        """CD-98-2 平台半段隔離：non-win + 非 ASCII 路徑 + getencoding 可編 → 仍回 None。
        鎖住 `sys.platform == "win32" and` 這半個 gate——若被刪除，非 win 平台會誤入
        encode 分支回 bytes；此測即為該 mutation 的唯一守衛。"""
        monkeypatch.setattr(javdb.sys, "platform", "linux")
        monkeypatch.setattr(javdb.certifi, "where", lambda: "C:\\Users\\陳大文\\OpenAver\\certifi\\cacert.pem")
        monkeypatch.setattr(javdb.locale, "getencoding", lambda: "cp950")
        assert javdb._cainfo_override_bytes() is None

    def test_get_html_no_curl_options_on_non_win(self, scraper, monkeypatch):
        pytest.importorskip("curl_cffi")
        monkeypatch.setattr(javdb, "CURL_CFFI_AVAILABLE", True)
        monkeypatch.setattr(javdb.sys, "platform", "linux")
        monkeypatch.setattr(javdb.certifi, "where", lambda: "/etc/ssl/certs/ca-certificates.crt")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html></html>"
        mock_get = MagicMock(return_value=mock_resp)
        monkeypatch.setattr(javdb.curl_requests, "get", mock_get)

        result = scraper._get_html("https://javdb.com/v/Ww9zN8")

        assert result == "<html></html>"
        assert "curl_options" not in mock_get.call_args.kwargs


# ============================================================
# 2. win + ASCII certifi path → None (no-op)
# ============================================================

class TestWinAscii:
    def test_helper_returns_none_when_ascii(self, monkeypatch):
        monkeypatch.setattr(javdb.sys, "platform", "win32")
        monkeypatch.setattr(javdb.certifi, "where", lambda: r"C:\Users\peace\OpenAver\certifi\cacert.pem")
        assert javdb._cainfo_override_bytes() is None


# ============================================================
# 3. win + 非 ASCII + ACP 可編碼 → bytes；_get_html 帶 curl_options
# ============================================================

class TestWinNonAsciiEncodable:
    CJK_PATH = "C:\\Users\\陳大文\\OpenAver\\certifi\\cacert.pem"

    def test_helper_returns_expected_bytes(self, monkeypatch):
        monkeypatch.setattr(javdb.sys, "platform", "win32")
        monkeypatch.setattr(javdb.certifi, "where", lambda: self.CJK_PATH)
        monkeypatch.setattr(javdb.locale, "getencoding", lambda: "cp950")

        result = javdb._cainfo_override_bytes()

        expected = self.CJK_PATH.encode("cp950", errors="strict")
        assert result == expected

    def test_get_html_passes_curl_options(self, scraper, monkeypatch):
        pytest.importorskip("curl_cffi")
        monkeypatch.setattr(javdb, "CURL_CFFI_AVAILABLE", True)
        monkeypatch.setattr(javdb.sys, "platform", "win32")
        monkeypatch.setattr(javdb.certifi, "where", lambda: self.CJK_PATH)
        monkeypatch.setattr(javdb.locale, "getencoding", lambda: "cp950")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html></html>"
        mock_get = MagicMock(return_value=mock_resp)
        monkeypatch.setattr(javdb.curl_requests, "get", mock_get)

        result = scraper._get_html("https://javdb.com/v/Ww9zN8")

        assert result == "<html></html>"
        expected_bytes = self.CJK_PATH.encode("cp950", errors="strict")
        assert mock_get.call_args.kwargs["curl_options"] == {javdb.CurlOpt.CAINFO: expected_bytes}


# ============================================================
# 4. win + 非 ASCII + UnicodeEncodeError → None + warning once
# ============================================================

class TestWinNonAsciiUndecodable:
    CJK_PATH = "C:\\Users\\陳大文\\OpenAver\\certifi\\cacert.pem"

    def test_helper_returns_none_and_warns_once(self, monkeypatch, caplog):
        monkeypatch.setattr(javdb.sys, "platform", "win32")
        monkeypatch.setattr(javdb.certifi, "where", lambda: self.CJK_PATH)
        # ascii getencoding 讓 CJK 路徑必炸 UnicodeEncodeError（比 mock str.encode 乾淨）
        monkeypatch.setattr(javdb.locale, "getencoding", lambda: "ascii")

        with caplog.at_level(logging.WARNING, logger="OpenAver.core.scrapers.javdb"):
            result1 = javdb._cainfo_override_bytes()
            # 強制第二次重新進入 encode 分支（正常 cache 生效下第二次呼叫會被
            # _UNSET sentinel 短路、根本不重算——見 TestCacheSentinel）。
            # 這裡手動重置 _cainfo_override=_UNSET（保留 _ca_warned）模擬「快取失效後
            # 再次觸發降級路徑」，驗證 _ca_warned 本身才是 one-shot 的真正守衛。
            monkeypatch.setattr(javdb, "_cainfo_override", javdb._UNSET)
            result2 = javdb._cainfo_override_bytes()

        assert result1 is None
        assert result2 is None

        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1, f"應只 warn 一次，實得 {len(warnings)}"
        assert "javdb" in warnings[0].getMessage()

    def test_get_html_omits_curl_options_on_degrade(self, scraper, monkeypatch):
        pytest.importorskip("curl_cffi")
        monkeypatch.setattr(javdb, "CURL_CFFI_AVAILABLE", True)
        monkeypatch.setattr(javdb.sys, "platform", "win32")
        monkeypatch.setattr(javdb.certifi, "where", lambda: self.CJK_PATH)
        monkeypatch.setattr(javdb.locale, "getencoding", lambda: "ascii")

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html></html>"
        mock_get = MagicMock(return_value=mock_resp)
        monkeypatch.setattr(javdb.curl_requests, "get", mock_get)

        result = scraper._get_html("https://javdb.com/v/Ww9zN8")

        assert result == "<html></html>"
        assert "curl_options" not in mock_get.call_args.kwargs


# ============================================================
# 5. cache sentinel：算一次 + 降級終值為 None（非 _UNSET）
# ============================================================

class TestCacheSentinel:
    def test_certifi_where_called_once(self, monkeypatch):
        monkeypatch.setattr(javdb.sys, "platform", "win32")
        mock_where = MagicMock(return_value=r"C:\Users\peace\OpenAver\certifi\cacert.pem")
        monkeypatch.setattr(javdb.certifi, "where", mock_where)

        javdb._cainfo_override_bytes()
        javdb._cainfo_override_bytes()

        assert mock_where.call_count == 1

    def test_cache_final_value_none_not_unset_after_degrade(self, monkeypatch):
        monkeypatch.setattr(javdb.sys, "platform", "win32")
        monkeypatch.setattr(javdb.certifi, "where", lambda: "C:\\Users\\陳大文\\OpenAver\\certifi\\cacert.pem")
        monkeypatch.setattr(javdb.locale, "getencoding", lambda: "ascii")

        result = javdb._cainfo_override_bytes()

        assert result is None
        assert javdb._cainfo_override is None
        assert javdb._cainfo_override is not javdb._UNSET


# ============================================================
# 6. import guard：CURL_CFFI_AVAILABLE=False → 短路，不觸及 certifi
# ============================================================

class TestImportGuard:
    def test_get_html_short_circuits_without_touching_certifi(self, scraper, monkeypatch):
        monkeypatch.setattr(javdb, "CURL_CFFI_AVAILABLE", False)
        monkeypatch.setattr(javdb, "CURL_CFFI_IMPORT_ERROR", None)
        monkeypatch.setattr(javdb, "_warned", False)

        mock_where = MagicMock(return_value="/etc/ssl/certs/ca-certificates.crt")
        monkeypatch.setattr(javdb.certifi, "where", mock_where)

        result = scraper._get_html("https://javdb.com/v/Ww9zN8")

        assert result is None
        mock_where.assert_not_called()

    def test_certifi_import_failure_degrades_not_raises(self, monkeypatch):
        """CD-98-7 真正 invariant：`import certifi` 在 module-import 時失敗（curl_cffi 本身可 import）
        → module 降級成 CURL_CFFI_AVAILABLE=False，**不**在 import 時 raise。

        鎖住「certifi 必須在 try/except 內」——若被移到 try 外的頂層無條件 import，
        reload 會直接拋 ImportError（module 載入失敗，比現況更糟）。

        cleanup 極重要（reload 污染全 suite）：finally 還原 __import__ 並 reload 回乾淨態，
        且斷言還原成功（壞掉的 cleanup 要大聲失敗，不能靜默污染後續測試）。"""
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "certifi":
                raise ImportError("simulated: certifi missing")
            return real_import(name, *args, **kwargs)

        try:
            monkeypatch.setattr(builtins, "__import__", fake_import)
            # reload 重跑 module body：certifi import 失敗、curl_cffi 仍載入
            importlib.reload(javdb)   # MUST NOT raise
            assert javdb.CURL_CFFI_AVAILABLE is False
            assert isinstance(javdb.CURL_CFFI_IMPORT_ERROR, ImportError)
        finally:
            # 還原真 __import__ + reload 回乾淨態，否則後續全 suite 看到壞掉的 javdb
            monkeypatch.undo()
            importlib.reload(javdb)
            # cleanup 若壞掉要立刻大聲失敗（而非靜默污染）
            assert javdb.CURL_CFFI_AVAILABLE is True
            assert javdb._cainfo_override is javdb._UNSET
