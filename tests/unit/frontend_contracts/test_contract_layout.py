"""前端契約守衛（KEEP，跨檔 contract）— 由 test_frontend_lint.py 拆出（96c T5，純搬移零行為變更）。

module-level 路徑常數為源檔複製（CD-96c-7：源檔殘留 class 仍引用同名常數，故複製非剪走）。
"""
import re
from pathlib import Path

SHOWCASE_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "showcase.html"
SHOWCASE_LIGHTBOX_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
SETTINGS_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "settings.html"
BASE_HTML_T76 = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "base.html"
APPLE_TOUCH_ICON_PNG = Path(__file__).parent.parent.parent.parent / "web" / "static" / "apple-touch-icon.png"
THEME_COLOR_DIM = "#2a303c"
THEME_COLOR_LIGHT = "#ffffff"
SETTINGS_PROVIDERS_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "settings" / "state-providers.js"
NAVIGATION_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "search" / "state" / "navigation.js"
SHOWCASE_CSS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "css" / "pages" / "showcase.css"
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # /home/peace/OpenAver
SOURCE_PILL_CSS         = Path(__file__).parent.parent.parent.parent / "web" / "static" / "css" / "components" / "source-pill.css"
SHOWCASE_SIMILAR_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-similar.js"
SOURCE_PILL_MACRO = (
    Path(__file__).parent.parent.parent.parent
    / "web" / "templates" / "_macros" / "source_pill.html"
)
T11_BREAKPOINTS_JS    = PROJECT_ROOT / "web" / "static" / "js" / "shared" / "breakpoints.js"
T11_STATE_LIGHTBOX_JS = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
T11_GRID_MODE_JS      = PROJECT_ROOT / "web" / "static" / "js" / "pages" / "search" / "state" / "grid-mode.js"
T11_SHOWCASE_CSS      = PROJECT_ROOT / "web" / "static" / "css" / "pages" / "showcase.css"
T11_SEARCH_CSS        = PROJECT_ROOT / "web" / "static" / "css" / "pages" / "search.css"


class TestPartsBinStagedAffordanceGuard:
    """Parts Bin 可達/不可達膠囊視覺語義對調守衛（TASK-partsbin-staged-affordance）。

    Template（settings.html）↔ CSS（source-pill.css）↔ Design-system（D.13）跨檔 contract；
    eslint 不解析 Jinja template，stylelint 無法表達選擇器歸屬語義，故走 pytest
    （沿用 TestPicker64aThreeStateGuard / TestCoverLoadingUx67Guard 先例）。

    強度：先 regex 擷取目標區塊再斷言，非整檔裸字串存在性（gotchas G5）。
    6 條契約各對應 1 個 test method，獨立失敗便於定位。
    """

    SETTINGS_HTML    = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "settings.html"
    SOURCE_PILL_CSS  = Path(__file__).parent.parent.parent.parent / "web" / "static" / "css" / "components" / "source-pill.css"
    DS_SETTINGS_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "design_system" / "settings-components.html"

    def _settings(self):
        return self.SETTINGS_HTML.read_text(encoding="utf-8")

    def _css(self):
        return self.SOURCE_PILL_CSS.read_text(encoding="utf-8")

    def _ds(self):
        return self.DS_SETTINGS_HTML.read_text(encoding="utf-8")

    def _partsbin_pill_block(self):
        """抽出 settings.html Parts Bin pill loop 的 template x-for 區塊。"""
        html = self._settings()
        m = re.search(
            r'<template x-for="src in partsBinSources"[^>]*>.*?</template>',
            html, re.DOTALL,
        )
        assert m, "settings.html: 找不到 Parts Bin pill x-for 區塊（partsBinSources）"
        return m.group(0)

    # ── 契約 1：settings.html Parts Bin pill 含 bi-plus-circle（plus-icn）──────────────

    def test_settings_partsbin_pill_has_plus_icn(self):
        """Contract 1：settings.html Parts Bin pill loop 內存在 bi-plus-circle plus-icn（可加入 affordance）。"""
        block = self._partsbin_pill_block()
        assert "bi-plus-circle" in block, (
            "TASK-partsbin 違規 C1：settings.html Parts Bin pill 缺 bi-plus-circle（plus-icn）。"
            "可加入 affordance 需常駐 DOM，靠 CSS 依 data-available 控顯隱。"
        )
        assert "plus-icn" in block, (
            "TASK-partsbin 違規 C1：settings.html Parts Bin pill 缺 plus-icn class。"
        )

    # ── 契約 2：settings.html 不再含 settings-mt-probe-hint / mt_probe_hint_title ──────

    def test_settings_no_probe_hint_details(self):
        """Contract 2：settings.html 不含 settings-mt-probe-hint（3-cause <details> 已硬刪）。"""
        html = self._settings()
        assert "settings-mt-probe-hint" not in html, (
            "TASK-partsbin 違規 C2：settings.html 仍含 settings-mt-probe-hint（三因摺疊區塊應已整段硬刪）。"
        )
        assert "mt_probe_hint_title" not in html, (
            "TASK-partsbin 違規 C2：settings.html 仍含 mt_probe_hint_title（三因摺疊標題應已整段硬刪）。"
        )

    # ── 契約 3：settings.html Parts Bin slash-icn 仍在（不可達態靠它）────────────────

    def test_settings_partsbin_pill_slash_icn_retained(self):
        """Contract 3：settings.html Parts Bin pill loop 內 slash-icn 仍在（不可達態靠 CSS 顯示）。"""
        block = self._partsbin_pill_block()
        assert "slash-icn" in block, (
            "TASK-partsbin 違規 C3：settings.html Parts Bin pill 的 slash-icn 被誤刪（不可達態靠它，CSS 控顯隱）。"
        )
        assert "bi-slash-circle" in block, (
            "TASK-partsbin 違規 C3：settings.html Parts Bin pill 缺 bi-slash-circle icon。"
        )

    # ── 契約 4：source-pill.css 含可達態 .pill-name text-decoration:none ───────────────

    def test_css_partsbin_available_true_removes_line_through(self):
        """Contract 4：source-pill.css 含 .is-partsbin[data-available='true'] .pill-name text-decoration:none（選擇器歸屬）。"""
        css = self._css()
        m = re.search(
            r'\.source-pill\.is-partsbin\[data-available="true"\]\s+\.pill-name\s*\{([^}]+)\}',
            css, re.DOTALL,
        )
        assert m, (
            "TASK-partsbin 違規 C4：source-pill.css 缺 "
            ".source-pill.is-partsbin[data-available=\"true\"] .pill-name 規則。"
            "（可達正面態需 (0,4,0) specificity 勝全域 (0,3,0) line-through）"
        )
        assert "text-decoration: none" in m.group(1), (
            "TASK-partsbin 違規 C4：可達態 .pill-name 規則缺 text-decoration:none。"
        )

    # ── 契約 5：source-pill.css .is-partsbin cursor pointer ───────────────────────────

    def test_css_partsbin_cursor_pointer(self):
        """Contract 5：source-pill.css .source-pill.is-partsbin cursor 為 pointer（click-to-promote 語義）。"""
        css = self._css()
        m = re.search(
            r'\.source-pill\.is-partsbin\s*\{([^}]+)\}',
            css, re.DOTALL,
        )
        assert m, (
            "TASK-partsbin 違規 C5：source-pill.css 缺 .source-pill.is-partsbin cursor 規則。"
        )
        assert "cursor: pointer" in m.group(1), (
            "TASK-partsbin 違規 C5：.source-pill.is-partsbin 的 cursor 非 pointer。"
        )

    # ── 契約 6：design-system D.13 不含 rec-star/data-rec，含 available true/false 兩 demo ──

    def test_ds_d13_no_rec_star_and_has_both_available_states(self):
        """Contract 6：design-system D.13 不含 rec-star/data-rec（dead 清除），含 available=true 與 false 兩 demo。"""
        ds = self._ds()
        assert "rec-star" not in ds, (
            "TASK-partsbin 違規 C6：design-system settings-components.html 仍含 rec-star（dead CSS class，應清除）。"
        )
        assert "data-rec" not in ds, (
            "TASK-partsbin 違規 C6：design-system settings-components.html 仍含 data-rec 屬性（dead，應清除）。"
        )
        assert 'data-available="true"' in ds, (
            "TASK-partsbin 違規 C6：design-system D.13 缺 is-partsbin data-available=\"true\" demo（staged 可加入態）。"
        )
        assert 'data-available="false"' in ds, (
            "TASK-partsbin 違規 C6：design-system D.13 缺 is-partsbin data-available=\"false\" demo（不可達態）。"
        )


class TestSourcePillFlatCss:
    """TASK-74b-T1: .source-pill--flat 唯讀變體 CSS contract（cross-file，element-bound）。

    flat 變體保留 tint、只關互動（CD-74b-1）：cursor default + hover 無 lift/shadow + focus 無 outline。
    cross-file 契約：macro 在 variant='flat' 輸出 source-pill--flat ↔ CSS 必有對應規則。
    過「三問」：刪 .source-pill--flat 規則 → 紅；macro 移除 flat 分支 → 紅；改 cursor 值 → 紅。
    """

    def _css(self) -> str:
        return SOURCE_PILL_CSS.read_text(encoding="utf-8")

    def _macro(self) -> str:
        return SOURCE_PILL_MACRO.read_text(encoding="utf-8")

    def test_flat_rule_defines_cursor_default(self):
        """`.source-pill--flat { cursor: default; }` 存在（覆寫 base cursor: grab）。"""
        css = self._css()
        m = re.search(r"\.source-pill--flat\s*\{([^}]*)\}", css)
        assert m, "source-pill.css 缺 .source-pill--flat 規則（74b T1 enabler）"
        assert "cursor: default" in m.group(1), (
            f".source-pill--flat 必須 cursor: default（關掉 base grab）；body: {m.group(1)!r}"
        )

    def test_flat_hover_negates_lift(self):
        """`.source-pill--flat:hover` 關掉 base hover 的 transform + box-shadow。"""
        css = self._css()
        m = re.search(r"\.source-pill--flat:hover\s*\{([^}]*)\}", css)
        assert m, "source-pill.css 缺 .source-pill--flat:hover 規則"
        body = m.group(1)
        assert "transform: none" in body, (
            f".source-pill--flat:hover 必須 transform: none（關掉 base lift）；body: {body!r}"
        )
        assert "box-shadow: none" in body, (
            f".source-pill--flat:hover 必須 box-shadow: none（關掉 base shadow）；body: {body!r}"
        )

    def test_macro_emits_flat_class_cross_file(self):
        """cross-file：macro variant='flat' 分支輸出 source-pill--flat（CSS 規則的唯一消費路徑）。"""
        macro = self._macro()
        assert "source-pill--flat" in macro, (
            "source_pill.html 未輸出 source-pill--flat — flat CSS 將無消費者（cross-file 契約斷裂）"
        )


class TestPosterCropThresholdAlignment:
    """US-10 / CD-10：posterCrop 門檻（JS）與燈箱封面貼合 / poster grid 斷點（CSS）對齊 899。"""

    POSTER_CROP_CONST = "POSTER_CROP_MAX_W"

    # ---- helpers ----
    def _const_value(self) -> int:
        """從 shared/breakpoints.js 抽 POSTER_CROP_MAX_W 常數值。"""
        content = T11_BREAKPOINTS_JS.read_text(encoding="utf-8")
        m = re.search(
            rf"export\s+const\s+{self.POSTER_CROP_CONST}\s*=\s*(\d+)", content
        )
        assert m, f"breakpoints.js 缺少 `export const {self.POSTER_CROP_CONST} = <int>`"
        return int(m.group(1))

    def _js_poster_crop_threshold(self, path: Path, label: str) -> int:
        """抽某 JS 檔的 posterCrop 門檻值。

        共用常數方案：斷言檔案 import 了 POSTER_CROP_MAX_W 並用於 innerWidth 比較，
        門檻值即常數值（單一真理來源在 breakpoints.js）。
        """
        content = path.read_text(encoding="utf-8")
        # 1. import 共用常數（物理同源）
        assert re.search(
            rf"import\s*\{{[^}}]*\b{self.POSTER_CROP_CONST}\b[^}}]*\}}\s*from\s*"
            r"['\"]@/shared/breakpoints\.js['\"]",
            content,
        ), f"{label} 必須 import {{ {self.POSTER_CROP_CONST} }} from '@/shared/breakpoints.js'"
        # 2. 用於 innerWidth 門檻比較
        assert re.search(
            rf"window\.innerWidth\s*<=\s*{self.POSTER_CROP_CONST}\b", content
        ), f"{label} 必須以 `window.innerWidth <= {self.POSTER_CROP_CONST}` 作 posterCrop 門檻"
        # 3. 舊的 480 字面量門檻已消失（防只改一半）
        assert not re.search(
            r"window\.innerWidth\s*<=\s*480\b", content
        ), f"{label} 仍殘留 `window.innerWidth <= 480`（posterCrop 門檻未擴）"
        return self._const_value()

    def _css_media_max_width_for_selector(
        self, css: str, selector_substr: str, name: str
    ) -> int:
        """找含 selector_substr 的 @media 區塊，回傳其 max-width 值。"""
        for m in re.finditer(r"@media\s*\(([^)]*max-width[^)]*)\)\s*\{", css):
            start = m.end()
            depth = 1
            i = start
            while i < len(css) and depth > 0:
                if css[i] == "{":
                    depth += 1
                elif css[i] == "}":
                    depth -= 1
                i += 1
            body = css[start : i - 1]
            if selector_substr in body:
                mw = re.search(r"max-width:\s*(\d+)px", m.group(1))
                assert mw, f"{name} 的 @media 條件抽不到 max-width: {m.group(1)!r}"
                return int(mw.group(1))
        raise AssertionError(f"{name} 找不到含 selector {selector_substr!r} 的 @media block")

    def _poster_grid_max_width(self, css: str, grid_class: str, name: str) -> int:
        """T10 poster-crop grid 斷點：回傳「481–899 4 欄直式右裁 poster」@media 的 max-width。

        grid_class（.showcase-grid / .search-grid）在多個 @media 出現（≤480、481–899、
        1100–1499 桌面等都可能是 repeat(4)）。poster-crop 斷點唯一特徵 = 下界 481px：
        鎖 `(min-width: 481px) and (max-width: Npx)` 且 grid 為 repeat(4) 的那塊，回傳 N。
        """
        for m in re.finditer(r"@media\s*([^{]*?)\s*\{", css):
            cond = m.group(1)
            mn = re.search(r"min-width:\s*481px", cond)
            mw = re.search(r"max-width:\s*(\d+)px", cond)
            if not (mn and mw):
                continue
            start = m.end()
            depth, i = 1, start
            while i < len(css) and depth > 0:
                if css[i] == "{":
                    depth += 1
                elif css[i] == "}":
                    depth -= 1
                i += 1
            body = css[start : i - 1]
            if re.search(
                rf"\.{re.escape(grid_class)}\b[^{{}}]*\{{[^}}]*repeat\(\s*4\b", body, re.DOTALL
            ):
                return int(mw.group(1))
        raise AssertionError(
            f"{name} 找不到 (min-width:481px)+(max-width)+.{grid_class} repeat(4) poster grid @media block"
        )

    # ---- 常數定義 ----
    def test_breakpoint_const_is_899(self):
        """shared/breakpoints.js 匯出 POSTER_CROP_MAX_W = 899。"""
        assert self._const_value() == 899, "POSTER_CROP_MAX_W 不為 899"

    # ---- JS 門檻 ----
    def test_showcase_js_threshold_899(self):
        """state-lightbox.js posterCrop 門檻 == 899（import 共用常數 + innerWidth 比較 + 無 480 殘留）。"""
        assert self._js_poster_crop_threshold(
            T11_STATE_LIGHTBOX_JS, "state-lightbox.js"
        ) == 899

    def test_search_js_threshold_899(self):
        """grid-mode.js（search）posterCrop 門檻 == 899（同上）。"""
        assert self._js_poster_crop_threshold(
            T11_GRID_MODE_JS, "grid-mode.js"
        ) == 899

    def test_parity_both_js_thresholds_equal(self):
        """CD-11：兩頁 JS 門檻值彼此相等（防只改一頁）。"""
        sc = self._js_poster_crop_threshold(T11_STATE_LIGHTBOX_JS, "state-lightbox.js")
        se = self._js_poster_crop_threshold(T11_GRID_MODE_JS, "grid-mode.js")
        assert sc == se, f"兩頁 posterCrop 門檻不一致：showcase={sc} search={se}"

    # ---- CSS 燈箱封面貼合 ----
    def test_showcase_lightbox_fit_covers_899(self):
        """showcase.css 燈箱封面貼合：83b-T2 後由 modal-hug 規則（.lightbox-content .lightbox-cover.has-cover img）
        無條件提供 width:100%（不再依賴 @media max-width:899px T8 block）。
        守衛改為確認 modal-hug img 規則存在且含 width:100%。
        """
        css = T11_SHOWCASE_CSS.read_text(encoding="utf-8")
        # 83b-T2 移除 T8 block，modal-hug 接管（無 @media gate）
        assert ".lightbox-content .lightbox-cover.has-cover img" in css, (
            "showcase.css modal-hug img 規則缺失（83b-T2 後應由此規則提供 width:100%）"
        )
        # 確認 img 規則內含 width:100%（strip comments 後查）
        css_no_comments = re.sub(r'/\*.*?\*/', '', css, flags=re.DOTALL)
        m = re.search(r'\.lightbox-content\s+\.lightbox-cover\.has-cover\s+img\s*\{([^}]+)\}', css_no_comments)
        assert m, "showcase.css modal-hug img block 找不到"
        assert "width: 100%" in m.group(1), "modal-hug img block 缺 width: 100%"

    def test_search_lightbox_fit_covers_899(self):
        """search.css 燈箱封面貼合（.search-container .lightbox-cover.has-cover）@media == max-width: 899px。"""
        css = T11_SEARCH_CSS.read_text(encoding="utf-8")
        mw = self._css_media_max_width_for_selector(
            css, ".search-container .lightbox-cover.has-cover", "search.css 燈箱貼合"
        )
        assert mw == 899, f"search.css 燈箱貼合 @media max-width={mw}px，應為 899"

    # ---- T10 poster grid 斷點（參考；三位一體比對）----
    def test_showcase_poster_grid_breakpoint_899(self):
        """showcase.css poster-crop grid 斷點（.showcase-grid 4 欄）== max-width: 899px（T10）。"""
        css = T11_SHOWCASE_CSS.read_text(encoding="utf-8")
        mw = self._poster_grid_max_width(css, "showcase-grid", "showcase.css")
        assert mw == 899, f"showcase.css poster grid @media max-width={mw}px，應為 899"

    def test_search_poster_grid_breakpoint_899(self):
        """search.css poster-crop grid 斷點（.search-grid 4 欄）== max-width: 899px（T10）。"""
        css = T11_SEARCH_CSS.read_text(encoding="utf-8")
        mw = self._poster_grid_max_width(css, "search-grid", "search.css")
        assert mw == 899, f"search.css poster grid @media max-width={mw}px，應為 899"

    # ---- 核心：跨 6 值單一對齊斷言 ----
    def test_all_thresholds_aligned_899(self):
        """核心對齊守衛：2 JS 門檻 + search CSS 燈箱貼合 + 2 CSS poster grid 全部相等且 == 899。

        83b-T2：showcase.css T8 block（@media max-width:899px .lightbox-cover:has(.lb-full)）已移除；
        showcase 燈箱貼合改由 modal-hug 無條件提供。核心對齊守衛去掉 showcase-lightbox-fit 維度，
        保留其他 5 值（2 JS + 1 search CSS lightbox-fit + 2 poster grid）。
        """
        showcase_css = T11_SHOWCASE_CSS.read_text(encoding="utf-8")
        search_css = T11_SEARCH_CSS.read_text(encoding="utf-8")
        values = {
            "js:showcase": self._js_poster_crop_threshold(
                T11_STATE_LIGHTBOX_JS, "state-lightbox.js"
            ),
            "js:search": self._js_poster_crop_threshold(
                T11_GRID_MODE_JS, "grid-mode.js"
            ),
            "css:search-lightbox-fit": self._css_media_max_width_for_selector(
                search_css, ".search-container .lightbox-cover.has-cover", "search.css 燈箱貼合"
            ),
            "css:showcase-poster-grid": self._poster_grid_max_width(
                showcase_css, "showcase-grid", "showcase.css"
            ),
            "css:search-poster-grid": self._poster_grid_max_width(
                search_css, "search-grid", "search.css"
            ),
        }
        assert all(v == 899 for v in values.values()), (
            f"posterCrop 門檻 ↔ 燈箱貼合 ↔ poster grid 斷點未全對齊 899：{values}"
        )


class TestLightboxCoverSizeGuards:
    """71c: 守衛 lightbox 封面縮水修復（thumb 放大填滿 + blur-up 鏡像 + same-URL complete-check）

    四條 element-bound 守衛：
    G1 — .lightbox-cover img 有明確 height:（非僅 max-height），確保 400px thumb 放大到 60vh
    G2 — .lb-full 有明確 height:（非僅 max-height），確保 overlay 與 base 尺寸鏡像
    G3 — state-lightbox.js 含 _refreshLbFullBlurUp helper（same-URL complete-check 抽出共用），
         且 _setLightboxIndex 與 slip-through 兩處均呼叫該 helper（防回歸繞過）
    G4 — state-similar.js similarExitVideo 含 cover_full_url 欄位
    """

    def _css(self):
        return SHOWCASE_CSS.read_text(encoding="utf-8")

    def _lightbox_js(self):
        return SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")

    def _similar_js(self):
        return SHOWCASE_SIMILAR_JS.read_text(encoding="utf-8")

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def test_lightbox_cover_img_has_explicit_height(self):
        """G1: .lightbox-cover img 含明確 height: 規則（非僅 max-height），讓 thumb 放大填滿"""
        css = self._css()
        import re
        # 找到 .lightbox-cover img { ... } 區塊
        block_match = re.search(r'\.lightbox-cover\s+img\s*\{([^}]+)\}', css, re.DOTALL)
        assert block_match, ".lightbox-cover img 規則在 showcase.css 找不到"
        block = block_match.group(1)
        # 確認有明確的 height:（不只是 max-height:）
        assert re.search(r'(?<!\w)height\s*:', block), (
            ".lightbox-cover img 缺少明確 height: 規則（只有 max-height 不足以放大小 thumb）"
        )

    def test_lb_full_has_explicit_height(self):
        """G2: .lb-full 含明確 height: 規則（非僅 max-height），與 base img 鏡像對齊"""
        css = self._css()
        import re
        block_match = re.search(r'\.lb-full\s*\{([^}]+)\}', css, re.DOTALL)
        assert block_match, ".lb-full 規則在 showcase.css 找不到"
        block = block_match.group(1)
        assert re.search(r'(?<!\w)height\s*:', block), (
            ".lb-full 缺少明確 height: 規則（overlay 需與 base img 尺寸完全鏡像）"
        )

    def test_lightbox_js_has_sameurl_complete_check(self):
        """G3: state-lightbox.js 抽出 _refreshLbFullBlurUp helper 含 same-URL complete-check，
        且 _setLightboxIndex 與 state-similar.js slip-through 均呼叫該 helper（71c-P2 防回歸）"""
        import re
        js = self._lightbox_js()
        similar_js = self._similar_js()

        # (a) helper 函數體必須存在於 state-lightbox.js，且含 complete-check 三要素
        helper_idx = js.find("_refreshLbFullBlurUp(")
        assert helper_idx != -1, (
            "state-lightbox.js 找不到 _refreshLbFullBlurUp helper"
            "（71c-P2：blur-up reset + same-URL complete-check 應抽成共用 helper）"
        )
        # 截取 helper 函數體（含至 closing brace，取 600 字元已足夠）
        helper_snippet = js[helper_idx: helper_idx + 600]
        assert "lightboxCoverFull" in helper_snippet, (
            "_refreshLbFullBlurUp helper 缺少 lightboxCoverFull x-ref 取用"
            "（same-URL complete-check 需 $refs.lightboxCoverFull）"
        )
        # 鎖 runtime 表達式（非註解）
        assert "fullImg.complete" in helper_snippet and "fullImg.naturalWidth" in helper_snippet, (
            "_refreshLbFullBlurUp helper 缺少 fullImg.complete && fullImg.naturalWidth 檢查"
            "（same-URL 時瀏覽器不重新 fire @load，需手動偵測 complete）"
        )
        assert "_lbFullLoaded" in helper_snippet, (
            "_refreshLbFullBlurUp helper 缺少 _lbFullLoaded 賦值"
        )

        # (b) _setLightboxIndex 必須呼叫 _refreshLbFullBlurUp（不再 inline）
        set_idx = js.find("_setLightboxIndex(")
        assert set_idx != -1, "state-lightbox.js 找不到 _setLightboxIndex 函數"
        set_snippet = js[set_idx: set_idx + 800]
        assert "_refreshLbFullBlurUp" in set_snippet, (
            "state-lightbox.js _setLightboxIndex 未呼叫 _refreshLbFullBlurUp"
            "（抽 helper 後 _setLightboxIndex 應委託 helper，避免邏輯漂移）"
        )

        # (c) slip-through 路徑（state-similar.js）必須在 currentLightboxVideo = similarExitVideo 之後
        #     呼叫 _refreshLbFullBlurUp（防止繞過 _setLightboxIndex 殘留舊 _lbFullLoaded）
        slip_idx = similar_js.find("this.currentLightboxVideo = this.similarExitVideo")
        assert slip_idx != -1, (
            "state-similar.js 找不到 currentLightboxVideo = similarExitVideo 指派"
            "（slip-through 路徑應設 currentLightboxVideo 後呼叫 _refreshLbFullBlurUp）"
        )
        # 截取指派後 300 字元（應含 helper 呼叫）
        after_assign = similar_js[slip_idx: slip_idx + 300]
        assert "_refreshLbFullBlurUp" in after_assign, (
            "state-similar.js slip-through（currentLightboxVideo = similarExitVideo）後缺少 _refreshLbFullBlurUp 呼叫"
            "（71c-P2：slip-through 繞過 _setLightboxIndex，舊 _lbFullLoaded true → 跳過 blur-up；"
            "false + same-URL → @load 不 fire → opacity:0 卡死）"
        )

    def test_similar_exit_video_has_cover_full_url(self):
        """G4（JS contract）: state-similar.js similarExitVideo 含 cover_full_url 欄位"""
        js = self._similar_js()
        # 找 similarExitVideo = { ... } 構建區塊
        idx = js.find("this.similarExitVideo = {")
        assert idx != -1, "state-similar.js 找不到 similarExitVideo = { 構建"
        snippet = js[idx: idx + 600]
        assert "cover_full_url" in snippet, (
            "state-similar.js similarExitVideo 缺少 cover_full_url 欄位"
            "（slip-through 路徑缺此欄 → .lb-full src=undefined → @load 永不 fire → opacity:0 卡死）"
        )


class TestMobileSimilarDrillFallbackGuard:
    """BUGfix-mobile-similar-stale-cover: 守衛 mobile similar drill 三層 fallback 合約

    (a) state-lightbox.js 的 _setLightboxIndex 函式體必須清除 similarExitVideo（= null），
        確保 in-grid 切換後不殘留 standalone 旗標（Codex P2b 根治）。
    (b) state-similar.js 的 onSimilarMobileCardClick 函式體必須含：
        - `_videos` 查找（tier 2 fallback）
        - 設置 `similarExitVideo`（standalone 旗標）
        - 呼叫 `_refreshLbFullBlurUp`（blur-up reset）
    """

    def _lightbox_js(self):
        return SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")

    def _similar_js(self):
        return SHOWCASE_SIMILAR_JS.read_text(encoding="utf-8")

    @staticmethod
    def _extract_function_body(js, func_pattern):
        """用計數括弧深度方式擷取函式體，從 func_pattern regex 匹配處起算。"""
        m = re.search(func_pattern, js)
        if not m:
            return None
        start = m.start()
        body_start = js.index('{', start)
        depth = 0
        for i, ch in enumerate(js[body_start:], body_start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return js[body_start:i + 1]
        return None

    def test_set_lightbox_index_clears_similar_exit_video(self):
        """_setLightboxIndex 函式體必須含 similarExitVideo = null（清除 standalone 旗標）。
        根治：in-grid 切換（tier 1）後不殘留 standalone，prev/next + fly-back 恢復正常。
        """
        js = self._lightbox_js()
        body = self._extract_function_body(js, r'_setLightboxIndex\s*\(')
        assert body is not None, \
            "state-lightbox.js 找不到 _setLightboxIndex 函式宣告"
        # 允許有無空格兩種寫法
        assert re.search(r'similarExitVideo\s*=\s*null', body), (
            "_setLightboxIndex 函式體未含 'similarExitVideo = null'。\n"
            "in-grid 切換（tier 1）後 similarExitVideo 不清除，\n"
            "連點 tier2/3 再 tier1 時 standalone 旗標殘留，prev/next 被錯誤禁用。\n"
            f"當前函式體：\n{body[:400]}"
        )

    def test_close_similar_mode_fallback_has_videos_tier(self):
        """closeSimilarMode 退場 fallback 必須與 onSimilarMobileCardClick 同採三層策略：
        _filteredVideos miss 後先查 _videos.findIndex（命中保完整 metadata + path），
        且仍保留 _similarLastDrilledItem snapshot 當孤兒列 fallback（Codex P2）。
        否則 mobile tier2 的完整 metadata 會在關閉 similar mode 時被重新降級。
        """
        js = self._similar_js()
        body = self._extract_function_body(js, r'async\s+closeSimilarMode\s*\(')
        assert body is not None, \
            "state-similar.js 找不到 closeSimilarMode 函式宣告"
        assert re.search(r'_videos\s*\.\s*findIndex', body), (
            "closeSimilarMode fallback 未含 '_videos.findIndex'（tier 2）。\n"
            "退場時 _filteredVideos miss 直接降級成 5 欄 snapshot，\n"
            "mobile tier2 點擊時的完整 metadata + path 會在關閉 similar mode 時被重新降級。"
        )
        assert '_similarLastDrilledItem' in body, (
            "closeSimilarMode fallback 未保留 '_similarLastDrilledItem' snapshot（孤兒列 fallback）。\n"
            "_videos 也 miss（孤兒列 / demo）時需 snapshot 兜底，不可移除。"
        )

    def test_mobile_silent_switch_three_tier(self):
        """_mobileSilentSwitch 函式體必須採 3-tier silent-switch（恢復退役的 onSimilarMobileCardClick 守衛之 contract）：
        tier1 _silentSwitchLightboxByNumber（_filteredVideos 命中 → _setLightboxIndex）、
        tier2 _videos.findIndex（庫內 standalone，setSimilarExitVideo）、
        tier3 snapshot（_mobileLastDrilledItem 孤兒列 fallback）、
        且 tier2/3 收尾呼叫 _refreshLbFullBlurUp（blur-up reset，否則 overlay opacity:0 卡死）。
        """
        js = self._similar_js()
        # 錨定方法宣告（行首縮排 + 名稱，非 this._mobileSilentSwitch( 呼叫處）
        body = self._extract_function_body(js, r'\n\s*_mobileSilentSwitch\s*\(')
        assert body is not None, \
            "state-similar.js 找不到 _mobileSilentSwitch 函式宣告"
        # tier 1: _filteredVideos 命中走 _silentSwitchLightboxByNumber
        assert '_silentSwitchLightboxByNumber' in body, (
            "_mobileSilentSwitch 缺 tier1 '_silentSwitchLightboxByNumber'（_filteredVideos 命中路徑）。"
        )
        # tier 2: _videos.findIndex 撈庫內被 filter 排除片的完整 metadata
        assert re.search(r'_videos\s*\.\s*findIndex', body), (
            "_mobileSilentSwitch 缺 tier2 '_videos.findIndex'（庫內 standalone metadata 撈回）。"
        )
        # tier 2/3 設 similarExitVideo standalone 旗標
        assert re.search(r'similarExitVideo\s*=', body), (
            "_mobileSilentSwitch 缺 'similarExitVideo =' 指派（tier2/3 standalone 旗標，close 不 fly-back / prev-next 禁用）。"
        )
        # tier 3: snapshot 兜底（孤兒列 / demo）
        assert '_mobileLastDrilledItem' in body, (
            "_mobileSilentSwitch 缺 '_mobileLastDrilledItem' snapshot（tier3 孤兒列 fallback）。"
        )
        # tier 2/3 收尾：blur-up reset
        assert '_refreshLbFullBlurUp' in body, (
            "_mobileSilentSwitch 缺 '_refreshLbFullBlurUp' 呼叫（tier2/3 blur-up reset，否則 overlay opacity:0 卡死）。"
        )


class TestAppleTouchIconThemeColor:
    """TASK-81a-T8 (US-4): apple-touch-icon link + 動態 theme-color meta 守衛。

    - head 有 apple-touch-icon link 指向 /static/apple-touch-icon.png
    - head 有 theme-color meta，content 為 Jinja 條件，兩白名單 hex 都在
    - x-init 的 $watch('theme') 會更新 meta[name=theme-color] content（dim/light 雙向）
    - apple-touch-icon.png 存在且為 180×180（PIL）
    """

    def _base(self):
        return BASE_HTML_T76.read_text(encoding="utf-8")

    def test_head_has_apple_touch_icon(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(self._base(), "html.parser")
        link = soup.find("link", rel="apple-touch-icon")
        assert link is not None, "base.html head 缺 <link rel=\"apple-touch-icon\">"
        assert link.get("href") == "/static/apple-touch-icon.png", \
            f"apple-touch-icon href 應為 /static/apple-touch-icon.png，實為 {link.get('href')!r}"

    def test_head_has_theme_color_meta(self):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(self._base(), "html.parser")
        meta = soup.find("meta", attrs={"name": "theme-color"})
        assert meta is not None, "base.html head 缺 <meta name=\"theme-color\">"
        content = meta.get("content", "")
        # 初值為 Jinja 條件：{{ '#2a303c' if theme == 'dim' else '#ffffff' }}
        assert "theme == 'dim'" in content or "theme=='dim'" in content, \
            f"theme-color content 應為隨 theme 的 Jinja 條件，實為 {content!r}"
        assert THEME_COLOR_DIM in content and THEME_COLOR_LIGHT in content, \
            f"theme-color content 須含 dim/light 兩白名單 hex，實為 {content!r}"

    def test_theme_watch_updates_theme_color(self):
        """$watch('theme', ...) 區塊會把 dim/light hex 寫進 meta[name=theme-color].content"""
        html = self._base()
        # 找出更新 theme-color 的 $watch callback（容忍 &quot; HTML escape）
        pattern = re.compile(
            r"\$watch\(\s*['\"]theme['\"].*?theme-color.*?\.content.*?"
            + re.escape(THEME_COLOR_DIM) + r".*?" + re.escape(THEME_COLOR_LIGHT),
            re.DOTALL,
        )
        assert pattern.search(html), (
            "base.html x-init 缺 $watch('theme') 更新 meta[name=theme-color].content "
            f"為 {THEME_COLOR_DIM}/{THEME_COLOR_LIGHT} 的區塊（動態狀態列色被移除？）"
        )

    def test_apple_touch_icon_png_exists_and_180(self):
        from PIL import Image
        assert APPLE_TOUCH_ICON_PNG.exists(), \
            f"apple-touch-icon.png 不存在：{APPLE_TOUCH_ICON_PNG}（跑 tools/gen_apple_touch_icon.py）"
        with Image.open(APPLE_TOUCH_ICON_PNG) as img:
            assert img.size == (180, 180), \
                f"apple-touch-icon.png 應為 180×180，實為 {img.size}"
            # apple-touch-icon 須不透明品牌底（iOS 自動加圓角，透明背景會變黑/白底不一致）
            assert img.mode == "RGB", \
                f"apple-touch-icon.png 須為 RGB 不透明（無 alpha），實為 {img.mode}"
            assert img.getpixel((0, 0)) == (26, 26, 46), \
                f"apple-touch-icon.png 四角須為品牌底 #1a1a2e，實為 {img.getpixel((0, 0))}"


class TestCodexFixes:
    """39a Codex review 修正守衛"""

    def _navigation_js(self):
        return NAVIGATION_JS.read_text(encoding="utf-8")

    def _settings_js(self):
        return SETTINGS_PROVIDERS_JS.read_text(encoding="utf-8")

    def test_loadmore_no_currentindex_assignment(self):
        """F1：loadMore() 成功分支不含 this.currentIndex = 賦值"""
        js = self._navigation_js()
        # 找到 loadMore 函數體，截取到 finally 區塊結束
        start = js.find("async loadMore(trigger")
        assert start != -1, "navigation.js 找不到 async loadMore(trigger ...) 函數"
        # 截取 loadMore 函數體（到函數結尾）
        func_body = js[start:]
        # 找到 finally { ... } 後的第一個右大括號（函數結束）
        finally_pos = func_body.find("finally {")
        if finally_pos != -1:
            # 截取 loadMore 函數範圍：從函數開始到 finally 區塊後的 } 結尾
            end_pos = func_body.find("}", finally_pos + len("finally {"))
            # 再找外層函數的 }
            end_pos = func_body.find("},", end_pos + 1)
            func_body = func_body[:end_pos] if end_pos != -1 else func_body
        # 確認函數體內不含 this.currentIndex = 賦值（有空格的賦值語句）
        assert "this.currentIndex =" not in func_body, \
            "navigation.js loadMore() 成功分支不應含 this.currentIndex = 賦值（破壞 shared state contract）"

    def test_gemini_model_fallback_includes_check(self):
        """F2：testGeminiConnection() 成功後包含 includes() 檢查舊 model 是否在 allowlist"""
        js = self._settings_js()
        assert "modelNames.includes(this.form.geminiModel)" in js or \
               "includes(this.form.geminiModel)" in js, \
            "settings.js testGeminiConnection() 成功後應含 includes(this.form.geminiModel) allowlist 檢查"

