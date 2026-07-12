"""
TestExtractNumber — extract_number 和 normalize_number 單元測試
（搬自 tests/integration/test_new_scrapers.py TestExtractNumber）

純邏輯測試，不需 mock
"""
from core.scrapers.utils import extract_number
from core.scrapers.d2pass import D2PassScraper
from core.scraper import is_prefix_only
from core.gallery_scanner import VideoScanner


class TestExtractNumber:
    """extract_number 和 normalize_number 單元測試"""

    def test_extract_number_underscore_3digit(self):
        """底線格式 3-digit suffix 正確提取"""
        result = extract_number("120415_201.mp4")
        assert result == "120415_201"

    def test_extract_number_underscore_2digit(self):
        """底線格式 2-digit suffix 正確提取"""
        result = extract_number("082912_01.mp4")
        assert result == "082912_01"

    def test_normalize_number_preserves_underscore(self):
        """D2PassScraper.normalize_number 不破壞底線格式番號"""
        scraper = D2PassScraper()
        result = scraper.normalize_number("120415_201")
        assert result == "120415_201"

    def test_extract_number_hyphen_2digit(self):
        """hyphen 格式 2-digit suffix 正確提取（T6b regex 修正）"""
        result = extract_number("041417-41.mp4")
        assert result == "041417-41"

    # --- TASK-73a-T2: 單字母 + 4 位無碼番號（Tokyo Hot）---

    def test_extract_single_letter_tokyo_hot_full_filename(self):
        """用戶 bug 本體：[無碼]n0762 Tokyo Hot n0762.mp4 → N0762（大寫無 hyphen）"""
        result = extract_number("[無碼]n0762 Tokyo Hot n0762.mp4")
        assert result == "N0762"

    def test_extract_single_letter_k0150(self):
        """k0150.mp4 → K0150（單字母 + 4 位，不插 hyphen）"""
        assert extract_number("k0150.mp4") == "K0150"

    def test_extract_single_letter_c0050(self):
        """c0050.mp4 → C0050（單字母 + 4 位，不插 hyphen）"""
        assert extract_number("c0050.mp4") == "C0050"

    # --- TASK-73a-T2: 回歸守衛（單字母 pattern 不得污染既有行為）---

    def test_regression_multiletter_no_hyphen_still_inserts(self):
        """SONE205.mp4 → SONE-205（多字母走 index 6，照舊插 hyphen）"""
        assert extract_number("SONE205.mp4") == "SONE-205"

    def test_regression_hyphen_format_unchanged(self):
        """ABC-123.mp4 → ABC-123（帶 hyphen 不變）"""
        assert extract_number("ABC-123.mp4") == "ABC-123"

    def test_regression_date_format_unchanged(self):
        """041417-413.mp4 → 041417-413（日期型不變）"""
        assert extract_number("041417-413.mp4") == "041417-413"

    def test_regression_fc2_unchanged(self):
        """FC2-PPV-1234567.mp4 → FC2-PPV-1234567（不變）"""
        assert extract_number("FC2-PPV-1234567.mp4") == "FC2-PPV-1234567"

    def test_regression_t28_unchanged(self):
        """T28-103.mp4 → T28-103（混合格式不變）"""
        assert extract_number("T28-103.mp4") == "T28-103"

    def test_regression_no_false_extract_4digit_year(self):
        """random_movie_2024.mp4 不誤抽（4 位數字前非緊鄰單字母，_ 隔開）"""
        assert extract_number("random_movie_2024.mp4") is None

    def test_regression_no_false_extract_s1_underscore(self):
        """S1_2024.mp4 不誤抽成 S2024（底線隔開單字母與數字）"""
        result = extract_number("S1_2024.mp4")
        assert result != "S2024"

    # --- TASK-73a-T2 bugfix: right-side digit boundary (no truncation) ---

    def test_no_truncate_5digit_n12345(self):
        """n12345.mp4 不應截斷為 N1234（單字母 + 5 位 → 不是 Tokyo Hot，應回 None）"""
        result = extract_number("n12345.mp4")
        # 5-digit after single letter is NOT Tokyo Hot (spec: exactly 4 digits)
        # Earlier patterns don't match either, so result must NOT be N1234
        assert result != "N1234"
        assert result is None

    def test_no_truncate_5digit_n07620(self):
        """n07620.mp4 不應截斷為 N0762（單字母 + 5 位 → 不是 Tokyo Hot，應回 None）"""
        result = extract_number("n07620.mp4")
        assert result != "N0762"
        assert result is None

    # --- TASK-73e-T8: 前綴收窄負向 case ---

    def test_non_th_prefix_A_holiday(self):
        """holiday_A2024.mp4 → None（A 非 Tokyo Hot 前綴 n/k/c/m/s，不得誤抽）"""
        assert extract_number("holiday_A2024.mp4") is None

    def test_non_th_prefix_B_vacation(self):
        """vacation_B2023.mp4 → None（B 非 Tokyo Hot 前綴 n/k/c/m/s，不得誤抽）"""
        assert extract_number("vacation_B2023.mp4") is None


# --- TASK-caps: 7 字母前綴 cap 對齊（{1,6}/{2,6} → {1,7}/{2,7}）---

class TestExtractNumberCapAlignment:
    """7 字母前綴（如 PARATHD）不再被 re.search 滑窗截斷掉首字"""

    def test_parathd_hyphen_lowercase(self):
        """parathd-02976.mp4 → PARATHD-02976（7 字母前綴，帶 hyphen，小寫輸入）"""
        assert extract_number("parathd-02976.mp4") == "PARATHD-02976"

    def test_parathd_hyphen_uppercase(self):
        """PARATHD-02976.mp4 → PARATHD-02976（7 字母前綴，帶 hyphen，已大寫）"""
        assert extract_number("PARATHD-02976.mp4") == "PARATHD-02976"

    def test_parathd_no_hyphen(self):
        """parathd02976.mp4 → PARATHD-02976（無 hyphen，走 index 6 插 hyphen）"""
        assert extract_number("parathd02976.mp4") == "PARATHD-02976"

    def test_parathd_bracket(self):
        """[parathd-02976] 標題.mp4 → PARATHD-02976（方括號變體，帶標題雜訊）"""
        assert extract_number("[parathd-02976] 標題.mp4") == "PARATHD-02976"

    def test_synthetic_7letter_prefix(self):
        """abcdefg-123.mp4 → ABCDEFG-123（合成 7 字母前綴，證明非 PARATHD 單一案例）"""
        assert extract_number("abcdefg-123.mp4") == "ABCDEFG-123"


class TestExtractNumberKnownLimitationUnchanged:
    """
    已知限制、維持不變（非回歸）：8+ 字母前綴 cap=7 下仍截斷。
    investigation-A §3 記錄的既有 false-positive class——cap 從未真正防過
    英文字誤判，只是換種錯法。cap=7 只宣稱修到 7 字母，不宣稱修 8+。
    此處測試僅記錄「維持不變」的現況，防日後誤判回歸（例如誤放寬到 8）。
    """

    def test_8letter_prefix_still_truncated(self):
        """abcdefgh-123.mp4 — 8 字母前綴 cap=7 下仍截斷（掉首字 a，變 BCDEFGH-123）"""
        result = extract_number("abcdefgh-123.mp4")
        assert result != "ABCDEFGH-123"
        assert result == "BCDEFGH-123"

    def test_10letter_stepmother_still_truncated(self):
        """[JavBus] STEPMOTHER-123 標題.mp4 — 10 字母前綴仍截斷（cap=7 下現況 PMOTHER-123）"""
        result = extract_number("[JavBus] STEPMOTHER-123 標題.mp4")
        assert result != "STEPMOTHER-123"
        assert result == "PMOTHER-123"


class TestExtractNumberCollisionGuards:
    """cap 對齊不得影響既有格式的抽取（mutation 驗證用回歸錨點）"""

    def test_tokyo_hot_n0762_unchanged(self):
        assert extract_number("[無碼]n0762 Tokyo Hot n0762.mp4") == "N0762"

    def test_tokyo_hot_k0150_unchanged(self):
        assert extract_number("k0150.mp4") == "K0150"

    def test_date_hyphen_format_unchanged(self):
        assert extract_number("041417-413.mp4") == "041417-413"

    def test_date_underscore_format_unchanged(self):
        assert extract_number("120415_201.mp4") == "120415_201"

    def test_fc2_unchanged(self):
        assert extract_number("FC2-PPV-1234567.mp4") == "FC2-PPV-1234567"

    def test_sone_205_unchanged(self):
        assert extract_number("SONE-205.mp4") == "SONE-205"

    def test_ssni_123_unchanged(self):
        assert extract_number("SSNI-123.mp4") == "SSNI-123"

    def test_abc_123_unchanged(self):
        assert extract_number("ABC-123.mp4") == "ABC-123"

    def test_sone103_no_hyphen_unchanged(self):
        """sone103.mp4 → SONE-103（無 hyphen 插入行為不受 cap 寬度影響）"""
        assert extract_number("sone103.mp4") == "SONE-103"

    def test_dmm_content_id_1sdms00808_unchanged(self):
        """1sdms00808.mp4 → SDMS-00808（CD-6：DMM content-id 不被自動轉成 SDMS-808）。

        SDMS-808 才是 DMM 正式番號（Bug B，本 task 刻意不做）。extract_number
        走 index 8 pattern（123ABC456）產出 SDMS-00808，保留完整 5 位數字。
        鎖住此字面值，防日後 cap/pattern 變動誤動 CD-6 邊界。
        """
        assert extract_number("1sdms00808.mp4") == "SDMS-00808"

    def test_is_prefix_only_unchanged_CD4(self):
        """is_prefix_only("ABCDEFG") is False（CD-4，core/scraper.py 零行變更）"""
        assert is_prefix_only("ABCDEFG") is False

    def test_pathological_long_string_bounded(self):
        """"A"*50 + "-123" 有界不 hang，輸出前綴長度 <= 7"""
        result = extract_number("A" * 50 + "-123.mp4")
        assert result is not None
        prefix = result.split('-')[0]
        assert len(prefix) <= 7


class TestExtractNumberGalleryScannerRegressionGuard:
    """
    gallery_scanner.py 零行變更的證明（回歸守衛 only，不修改
    tests/unit/test_gallery_scanner.py 既有測試）。
    """

    def test_gallery_scanner_parathd_already_correct(self):
        """VideoScanner: parathd-002.mp4 → PARATHD-002（7 字母在 gallery_scanner 本來就對）"""
        scanner = VideoScanner()
        assert scanner.find_num_from_filename("parathd-002.mp4") == "PARATHD-002"

    def test_gallery_scanner_vacation_wordguard_unchanged(self):
        """VideoScanner: my-vacation-2024.mp4 → ""（8 字母 word-guard 維持）"""
        scanner = VideoScanner()
        assert scanner.find_num_from_filename("my-vacation-2024.mp4") == ""

    def test_gallery_scanner_tutorial_wordguard_unchanged(self):
        """VideoScanner: tutorial-123.mp4 → ""（8 字母 word-guard 維持）"""
        scanner = VideoScanner()
        assert scanner.find_num_from_filename("tutorial-123.mp4") == ""
