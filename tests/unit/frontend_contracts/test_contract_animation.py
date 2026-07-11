"""前端契約守衛（KEEP，跨檔 contract）— 由 test_frontend_lint.py 拆出（96c T5，純搬移零行為變更）。

module-level 路徑常數為源檔複製（CD-96c-7：源檔殘留 class 仍引用同名常數，故複製非剪走）。
"""
import re
from pathlib import Path

SHOWCASE_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "showcase.html"
SHOWCASE_VIDEOS_JS   = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-videos.js"
SHOWCASE_ACTRESS_JS  = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-actress.js"
SHOWCASE_LIGHTBOX_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
SHOWCASE_ANIMATIONS_JS = (
    Path(__file__).parent.parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "animations.js"
)
GHOST_FLY_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "shared" / "ghost-fly.js"
SHOWCASE_CSS_T4CD = Path(__file__).parent.parent.parent.parent / "web" / "static" / "css" / "pages" / "showcase.css"
STATE_LIGHTBOX_JS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
_T2_SHOWCASE_HTML = Path(__file__).parent.parent.parent.parent / "web" / "templates" / "showcase.html"
_T2_SHOWCASE_CSS = Path(__file__).parent.parent.parent.parent / "web" / "static" / "css" / "pages" / "showcase.css"
_T2_SIMILAR_JS = (
    Path(__file__).parent.parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "state-similar.js"
)
_T2_LIGHTBOX_JS = (
    Path(__file__).parent.parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "state-lightbox.js"
)
_T2_BASE_JS = (
    Path(__file__).parent.parent.parent.parent
    / "web" / "static" / "js" / "pages" / "showcase" / "state-base.js"
)
_T2_BURST_PICKER_JS = (
    Path(__file__).parent.parent.parent.parent
    / "web" / "static" / "js" / "shared" / "burst-picker.js"
)
_T3_GHOST_FLY_JS = (
    Path(__file__).parent.parent.parent.parent
    / "web" / "static" / "js" / "shared" / "ghost-fly.js"
)


class TestGhostFlyGuards:
    """T8: Ghost Fly architecture guards (method folded)"""

    def test_ghost_fly_js_and_html_contains(self):
        """ghost-fly.js exists + loaded in base.html + skipCover support + delegates"""
        assert Path("web/static/js/shared/ghost-fly.js").exists(), \
            "web/static/js/shared/ghost-fly.js missing"
        html = Path("web/templates/base.html").read_text(encoding="utf-8")
        assert "ghost-fly.js" in html, "base.html missing: 'ghost-fly.js'"
        ghost_fly_js = Path("web/static/js/shared/ghost-fly.js").read_text(encoding="utf-8")
        assert "skipCover" in ghost_fly_js, "ghost-fly.js missing: 'skipCover'"
        for path in [
            "web/static/js/pages/showcase/animations.js",
            "web/static/js/pages/search/animations.js",
        ]:
            js = Path(path).read_text(encoding="utf-8")
            assert "GhostFly.playLightboxOpen" in js, f"{path} missing: 'GhostFly.playLightboxOpen'"
        # search/animations.js fallback
        search_js = Path("web/static/js/pages/search/animations.js").read_text(encoding="utf-8")
        lines = search_js.split('\n')
        ghost_fly_refs = [i for i, line in enumerate(lines) if 'window.GhostFly' in line]
        assert len(ghost_fly_refs) >= 3, \
            "search/animations.js missing: at least 3 window.GhostFly references"

    def test_gsap_animating_before_lightbox_open(self):
        """state-lightbox.js gsap-animating before lightboxOpen = true (ordering)"""
        content = SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")
        for fn_name in ("openLightbox(", "openHeroCardLightbox("):
            idx_fn = content.find(fn_name)
            assert idx_fn > 0, f"state-lightbox.js missing: {fn_name!r}"
            fn_scope = content[idx_fn:idx_fn + 4000]
            idx_animating = fn_scope.find("gsap-animating")
            idx_open = fn_scope.find("this.lightboxOpen = true")
            assert idx_animating > 0, f"state-lightbox.js {fn_name} missing: 'gsap-animating'"
            assert idx_open > 0, f"state-lightbox.js {fn_name} missing: 'lightboxOpen = true'"
            assert idx_animating < idx_open, \
                f"state-lightbox.js {fn_name}: gsap-animating must precede lightboxOpen = true"

    # ── 71b-T3: both-restore guard（hide/restore 目標皆為 .lightbox-cover 容器）──
    # element-bound：regex 抽 OPEN(playGridToLightbox) / CLOSE(playLightboxToGrid)
    # 各自 function body，斷言兩路 hide + restore 都指向 coverEl 容器（非僅單一 img）。
    # 非檔案層級的 '.lightbox-cover' 字串存在性檢查（comment 留字串無法騙過）。

    GHOST_FLY_JS = Path("web/static/js/shared/ghost-fly.js")

    def _extract_method_body(self, js, method_name):
        """抓 `methodName: function (...) {` 物件方法的 body（大括號平衡匹配）。"""
        pattern = re.compile(
            re.escape(method_name) + r'\s*:\s*function\s*\([^)]*\)\s*\{',
            re.DOTALL,
        )
        m = pattern.search(js)
        assert m is not None, f"ghost-fly.js 找不到 {method_name} 方法"
        start = m.end()  # 位於 { 之後
        depth = 1
        i = start
        while i < len(js) and depth > 0:
            c = js[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        return js[start:i - 1]

    def test_open_hide_and_restore_target_is_cover_container(self):
        """OPEN(playGridToLightbox) body：coverEl 取自 .lightbox-cover 容器，
        hide（data-ghost-hidden + opacity:0）與 cleanupGhost restore 皆指向 coverEl，
        而非僅單一 lbImg。"""
        js = self.GHOST_FLY_JS.read_text(encoding="utf-8")
        body = self._extract_method_body(js, "playGridToLightbox")
        # coverEl 由 .lightbox-cover 容器取得（closest / querySelector 任一）
        assert re.search(r'var\s+coverEl\s*=', body), \
            "playGridToLightbox body 缺少 coverEl 宣告（應隱 .lightbox-cover 容器而非單一 img）"
        assert "closest('.lightbox-cover')" in body or "querySelector('.lightbox-cover')" in body, \
            "playGridToLightbox coverEl 必須取自 .lightbox-cover 容器"
        # hide 目標是 coverEl（attribute + opacity:0）
        assert re.search(r"coverEl\.setAttribute\(\s*'data-ghost-hidden'", body), \
            "playGridToLightbox hide 必須對 coverEl 掛 data-ghost-hidden（容器，非僅 lbImg）"
        assert re.search(r"gsap\.set\(\s*coverEl\s*,\s*\{\s*opacity:\s*0", body), \
            "playGridToLightbox hide 必須對 coverEl 設 opacity:0（容器，非僅 lbImg）"
        # restore 目標是 coverEl（cleanupGhost 帶 coverEl）
        assert re.search(r"cleanupGhost\(\s*ghost\s*,\s*coverEl", body), \
            "playGridToLightbox cleanupGhost restore 必須帶 coverEl（容器），非僅 lbImg"

    def test_close_hide_and_restore_target_is_cover_container(self):
        """CLOSE(playLightboxToGrid) body：coverEl 取自 .lightbox-cover 容器，
        hide 補掛 data-ghost-hidden + opacity:0，abort 還原 coverEl，
        normal-complete 的 cleanupGhost restore 參數含 coverEl（與 OPEN 對稱）。"""
        js = self.GHOST_FLY_JS.read_text(encoding="utf-8")
        body = self._extract_method_body(js, "playLightboxToGrid")
        # coverEl 由 .lightbox-cover 容器取得
        assert re.search(r'var\s+coverEl\s*=', body), \
            "playLightboxToGrid body 缺少 coverEl 宣告（應隱 .lightbox-cover 容器而非單一 fromImg）"
        assert "closest('.lightbox-cover')" in body or "querySelector('.lightbox-cover')" in body, \
            "playLightboxToGrid coverEl 必須取自 .lightbox-cover 容器"
        # hide 目標是 coverEl（補上 attribute，舊版漏掛）+ opacity:0
        assert re.search(r"coverEl\.setAttribute\(\s*'data-ghost-hidden'", body), \
            "playLightboxToGrid hide 必須對 coverEl 掛 data-ghost-hidden（舊版漏掛 → stale-cleanup 兜不到）"
        assert re.search(r"gsap\.set\(\s*coverEl\s*,\s*\{\s*opacity:\s*0", body), \
            "playLightboxToGrid hide 必須對 coverEl 設 opacity:0（容器，非僅 fromImg）"
        # abort 還原 coverEl
        assert re.search(r"gsap\.set\(\s*coverEl\s*,\s*\{\s*opacity:\s*1", body), \
            "playLightboxToGrid abort 必須還原 coverEl opacity:1（容器，非僅 fromImg）"
        # normal-complete restore 含 coverEl（對稱還原來源容器，修舊不對稱）
        assert re.search(r"cleanupGhost\(\s*ghost\s*,\s*targetImg\s*,\s*coverEl", body), \
            "playLightboxToGrid cleanupGhost restore 參數必須含 coverEl（對稱還原來源容器，非僅 targetImg）"


class TestModeToggleFadeOutGuard:
    """T1: 模式切換動畫補 fade-out（playModeCrossfade 4-arg + toggleActressMode callback 延遲翻轉）"""

    def _core_js(self):
        # toggleActressMode / searchActressFilms → state-actress.js
        # switchMode → state-videos.js
        return (
            SHOWCASE_ACTRESS_JS.read_text(encoding="utf-8") + "\n" +
            SHOWCASE_VIDEOS_JS.read_text(encoding="utf-8")
        )

    def _anim_js(self):
        return SHOWCASE_ANIMATIONS_JS.read_text(encoding="utf-8")

    def _extract_method_body(self, js, method_name):
        """抓取 Alpine state method（methodName(...) { ... }）函式主體，大括號平衡（容忍 async 前綴）。"""
        pattern = re.compile(
            r'(?:^|\n)\s*(?:async\s+)?' + re.escape(method_name) + r'\s*\([^)]*\)\s*\{',
            re.DOTALL,
        )
        m = pattern.search(js)
        assert m is not None, f"找不到 {method_name} 方法"
        start = m.end()
        depth = 1
        i = start
        while i < len(js) and depth > 0:
            c = js[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        return js[start:i - 1]

    def _extract_property_function_body(self, js, prop_name):
        """抓取 propName: function (...) { ... } 形式的函式主體，大括號平衡。"""
        pattern = re.compile(
            r'\b' + re.escape(prop_name) + r'\s*:\s*function\s*\([^)]*\)\s*\{',
            re.DOTALL,
        )
        m = pattern.search(js)
        assert m is not None, f"找不到 {prop_name} property function"
        start = m.end()
        depth = 1
        i = start
        while i < len(js) and depth > 0:
            c = js[i]
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
            i += 1
        return js[start:i - 1]

    def test_play_mode_crossfade_has_callbacks_param(self):
        """animations.js playModeCrossfade 簽名包含 4 個參數 (oldMode, newMode, params, callbacks)"""
        js = self._anim_js()
        assert re.search(
            r'playModeCrossfade\s*:\s*function\s*\(\s*oldMode\s*,\s*newMode\s*,\s*params\s*,\s*callbacks\s*\)',
            js,
        ), "showcase/animations.js playModeCrossfade 缺少 callbacks 第 4 參數"

    def test_play_mode_crossfade_old_fade_out(self):
        """playModeCrossfade 函數體含 oldEl fade-out (tl.to(oldEl,...) + clearProps:'opacity')"""
        js = self._anim_js()
        body = self._extract_property_function_body(js, 'playModeCrossfade')
        assert re.search(r'tl\s*\.\s*to\s*\(\s*oldEl', body), \
            "playModeCrossfade 函數體缺少 oldEl fade-out (tl.to(oldEl,...))"
        assert re.search(r"clearProps\s*:\s*['\"]opacity['\"]", body), \
            "playModeCrossfade 函數體缺少 clearProps: 'opacity'（避免 CSS transition 殘留）"

    def test_play_mode_crossfade_new_fade_in_preserved(self):
        """playModeCrossfade 函數體保留 newEl fade-in（tl.fromTo(newEl,...) + clearProps:'opacity'）"""
        js = self._anim_js()
        body = self._extract_property_function_body(js, 'playModeCrossfade')
        assert re.search(r'(?:tl\s*\.\s*)?fromTo\s*\(\s*newEl', body), \
            "playModeCrossfade 函數體缺少 newEl fade-in (fromTo(newEl,...))"
        # newEl 段落（從第一次 newEl 出現到結尾）必須有 clearProps
        new_idx = body.find('newEl')
        assert new_idx >= 0, "playModeCrossfade 函數體找不到 newEl 區段"
        new_section = body[new_idx:]
        assert re.search(r"clearProps\s*:\s*['\"]opacity['\"]", new_section), \
            "playModeCrossfade newEl fade-in 段落缺少 clearProps: 'opacity'"

    def test_toggle_actress_mode_uses_callback(self):
        """toggleActressMode 函數體使用 onOldFadeComplete callback，不直接翻轉 showFavoriteActresses"""
        js = self._core_js()
        body = self._extract_method_body(js, 'toggleActressMode')
        assert 'onOldFadeComplete' in body, \
            "toggleActressMode 函數體缺少 onOldFadeComplete callback"
        assert 'playModeCrossfade' in body, \
            "toggleActressMode 函數體缺少 playModeCrossfade 呼叫"
        assert not re.search(
            r'this\.showFavoriteActresses\s*=\s*!\s*this\.showFavoriteActresses',
            body,
        ), "toggleActressMode 不應直接翻轉 this.showFavoriteActresses，應延遲到 callback 內"

    def test_toggle_actress_mode_animgen_guard(self):
        """toggleActressMode 函數體內 _animGeneration 出現 ≥ 2 次（外層 gen + 內層 gen2 race guard）"""
        js = self._core_js()
        body = self._extract_method_body(js, 'toggleActressMode')
        count = len(re.findall(r'_animGeneration', body))
        assert count >= 2, \
            f"toggleActressMode 函數體 _animGeneration 出現次數應 ≥ 2 (外 gen + 內 gen2)，實際 {count}"

    def test_old_caller_backward_compat(self):
        """switchMode 內 playModeCrossfade 呼叫不含 onOldFadeComplete（保持影片模式內切換行為不變）。
        searchActressFilms 自 T7 起為 async 並使用 onOldFadeComplete 觸發 ghost fly fade-out，
        故僅驗證 switchMode 路徑不退化。"""
        js = self._core_js()
        search_body = self._extract_method_body(js, 'searchActressFilms')
        switch_body = self._extract_method_body(js, 'switchMode')
        # 兩處都應呼叫 playModeCrossfade
        assert 'playModeCrossfade' in search_body, \
            "searchActressFilms 應仍呼叫 playModeCrossfade"
        assert 'playModeCrossfade' in switch_body, \
            "switchMode 應仍呼叫 playModeCrossfade"
        # switchMode 不該帶 onOldFadeComplete（保持原 2/3-arg 行為）
        assert 'onOldFadeComplete' not in switch_body, \
            "switchMode 內 playModeCrossfade 呼叫不應帶 onOldFadeComplete（保持影片模式內切換行為不變）"

    def test_toggle_actress_mode_handles_animations_unavailable(self):
        """Codex P1: animations.js 不可用時 toggleActressMode 必須有 fallback path（不能讓 callback 永不觸發）"""
        js = self._core_js()
        body = self._extract_method_body(js, 'toggleActressMode')
        # callback body 應抽成 named function（給 onOldFadeComplete 用、也給 fallback path 用）
        assert re.search(
            r'(?:function\s+\w*FadeIn\w*|var\s+\w*FadeIn\w*\s*=\s*function|\w*FadeIn\w*\s*=\s*function)',
            body,
        ), "toggleActressMode 應將 callback body 抽成 named function（如 flipAndFadeIn）以便 fallback 重用"
        # 必須顯式檢查 playModeCrossfade 是否存在（不能單靠 optional chaining 短路）
        assert re.search(
            r'(?:typeof\s+\w+\s*===\s*[\'"]function[\'"]|window\.ShowcaseAnimations\s*&&\s*window\.ShowcaseAnimations\.playModeCrossfade)',
            body,
        ), "toggleActressMode 應顯式檢查 playModeCrossfade 是否可用（不能單靠 optional chaining）"
        # 抽出來的 named function 應在函數體內被引用 ≥ 2 次（一次給 onOldFadeComplete、一次 fallback 直接呼叫）
        # 找出第一個 *FadeIn* 識別字
        m = re.search(r'\b(\w*[Ff]adeIn\w*)\b', body)
        assert m is not None, "toggleActressMode 找不到 FadeIn 命名函數"
        fname = m.group(1)
        count = len(re.findall(r'\b' + re.escape(fname) + r'\b', body))
        assert count >= 3, (
            f"toggleActressMode 內 {fname} 應出現 ≥ 3 次"
            f"（宣告 1 + onOldFadeComplete 引用 1 + fallback 同步呼叫 1），實際 {count}"
        )

    def test_toggle_actress_mode_reduced_motion_guard_on_fade_in(self):
        """Codex P2: toggleActressMode 內 newEl fade-in 必須有 reduced-motion 防護。

        49a-T4 起：原本的 inline `gsap.fromTo` 已重構為呼叫
        `window.ShowcaseAnimations.playContainerFadeIn`，該 helper 內部的
        `shouldSkip()` 已涵蓋 reduced-motion。本 test 接受兩種寫法擇一：
        (a) inline guard（舊架構）— 函數體內含 `prefersReducedMotion` 檢查
        (b) helper 委派（新架構）— 函數體內呼叫 `playContainerFadeIn`
        """
        js = self._core_js()
        body = self._extract_method_body(js, 'toggleActressMode')
        has_inline_guard = 'prefersReducedMotion' in body
        has_helper_delegation = 'playContainerFadeIn' in body
        assert has_inline_guard or has_helper_delegation, (
            "toggleActressMode newEl fade-in 應走 inline prefersReducedMotion guard，"
            "或委派 ShowcaseAnimations.playContainerFadeIn helper（後者 shouldSkip 已涵蓋）"
        )


class TestPickerIntegrationGuard:
    """49b-T4cd: 守衛 Actress Photo Picker 在 Showcase Lightbox 的 UI + Alpine + SSE 整合（method folded）"""

    def _html(self):
        return SHOWCASE_HTML.read_text(encoding="utf-8")

    def _core_js(self):
        return SHOWCASE_LIGHTBOX_JS.read_text(encoding="utf-8")

    def _css(self):
        return SHOWCASE_CSS_T4CD.read_text(encoding="utf-8")

    def test_picker_html_contains(self):
        """showcase.html 含 picker button、overlay 結構"""
        html = self._html()
        for expected in [
            "bi-arrow-clockwise",
            "showcase.actress.change_photo",
            "currentLightboxActress?.is_favorite",
            "actress-picker-overlay",
            "picker-candidates-grid",
            "picker-source-badge",
            "picker-loading",
            "picker-empty",
        ]:
            assert expected in html, f"showcase.html missing: {expected!r}"
        # T1: actress-picker-area must be renamed
        assert "actress-picker-area" not in html, \
            "showcase.html should not contain: 'actress-picker-area'"

    def test_picker_js_contains(self):
        """core.js 含 picker state、methods、params、SSE handler 等必要字串"""
        js = self._core_js()
        for expected in [
            # state
            "_pickerOpen: false",
            "_pickerRunId: 0",
            "_candidates: []",
            "_pickerSelected: false",
            # methods
            "openActressPicker(",
            "_startPickerSSE(",
            "_closePicker(",
            "_resetPicker(",
            "_fadeMetadataPanel(",
            "_cancelPicker",
            # params
            "_PICKER_PARAMS",
            "arcOvershoot: 1.3",
            # burst picker animations
            "playPickerFlipReplace",
            "playPickerExitAll",
            "typeof window.BurstPicker",
            "playPickerReverseAll",
            # SSE defer-burst
            "_burstAllPickerCandidates",
            # i18n
            "showcase.actress.picker.replaced",
            "showcase.actress.picker.error",
            "showToast(",
            # reduced motion
            "prefers-reduced-motion",
            "matchMedia",
            # lightbox teardown
            "_pickerOpen",
            "_closePicker",
            # stale name capture
            "capturedName",
            "currentLightboxActress",
        ]:
            assert expected in js, f"core.js missing: {expected!r}"
        # arcDuration
        assert ("arcDuration:  0.75" in js or "arcDuration: 0.75" in js), \
            "core.js missing: 'arcDuration: 0.75' in _PICKER_PARAMS"
        # _burstAllPickerCandidates ≥ 4 occurrences
        assert js.count("_burstAllPickerCandidates") >= 4, \
            "_burstAllPickerCandidates must appear ≥4 times (def + done/timeout/error)"

    def test_picker_css_rules_present(self):
        """showcase.css 含 .picker-candidate-card opacity:0 + overlay fixed + spin keyframes"""
        css = self._css()
        assert ".picker-candidate-card" in css, \
            "showcase.css missing: '.picker-candidate-card'"
        card_block = re.search(
            r"(?:^|\n)\.picker-candidate-card\s*\{[^}]*\}", css, re.DOTALL
        )
        assert card_block, "showcase.css: cannot find .picker-candidate-card style block"
        assert "opacity: 0" in card_block.group(0), \
            ".picker-candidate-card missing: 'opacity: 0'"
        area_block = re.search(
            r"\.actress-picker-overlay\s*\{[^}]*\}", css, re.DOTALL
        )
        assert area_block, "showcase.css: cannot find .actress-picker-overlay style block"
        overlay_css = area_block.group(0)
        for expected in ["position: fixed", "bottom:", "width:"]:
            assert expected in overlay_css, \
                f".actress-picker-overlay missing: {expected!r}"
        assert "@keyframes spin" in css, \
            "showcase.css missing: '@keyframes spin'"

    def test_picker_overlay_is_showcase_lightbox_direct_child(self):
        """49c-T1: actress-picker-overlay 必須為 .showcase-lightbox 的直接 child"""
        import html.parser as _html_parser

        html_text = self._html()
        assert "actress-picker-overlay" in html_text, \
            "showcase.html missing: 'actress-picker-overlay'"

        class _DivStackParser(_html_parser.HTMLParser):
            def __init__(self):
                super().__init__()
                self.div_stack = []
                self.overlay_ancestors = None
                self.found_overlay_in_lightbox_content = False

            def handle_starttag(self, tag, attrs):
                if tag != "div":
                    return
                attr_dict = dict(attrs)
                classes = set(attr_dict.get("class", "").split())
                if "actress-picker-overlay" in classes:
                    if self.overlay_ancestors is None:
                        self.overlay_ancestors = [s.copy() for s in self.div_stack]
                    if any("lightbox-content" in s for s in self.div_stack):
                        self.found_overlay_in_lightbox_content = True
                self.div_stack.append(classes)

            def handle_endtag(self, tag):
                if tag != "div":
                    return
                if self.div_stack:
                    self.div_stack.pop()

        parser = _DivStackParser()
        parser.feed(html_text)
        assert parser.overlay_ancestors is not None, \
            "actress-picker-overlay not found in markup"
        assert not parser.found_overlay_in_lightbox_content, \
            "actress-picker-overlay should not be inside lightbox-content"
        assert "showcase-lightbox" in parser.overlay_ancestors[-1], \
            "actress-picker-overlay direct parent should have showcase-lightbox class"


class TestUS5PosterCropGhostCrossfade:
    """TASK-75b-T7：poster 格開燈箱的 cover→contain 溶接（Codex 視覺 bug2）。

    契約：state-lightbox.js 依「≤480px ∩ 非女優模式 ∩ 非 hero」算 posterCrop 並傳給
    playGridToLightbox；ghost-fly.js 在 posterCrop 下對齊縮圖右裁（objectPosition right center）
    並於落地 crossfade（coverEl 淡入 + ghost 淡出 0.12s）取代硬切 cleanupGhost。
    三問：刪 posterCrop 傳遞 → 紅；刪 objectPosition 對齊 → 紅；把 crossfade 改回硬切 → 紅。
    """

    def _grid_to_lightbox_body(self) -> str:
        js = GHOST_FLY_JS.read_text(encoding="utf-8")
        start = js.find("playGridToLightbox: function")
        assert start >= 0, "ghost-fly.js 找不到 playGridToLightbox"
        end = js.find("playLightboxToGrid: function", start)
        assert end > start, "ghost-fly.js 找不到 playGridToLightbox 結束邊界"
        return js[start:end]

    def test_state_lightbox_threads_poster_crop(self):
        js = STATE_LIGHTBOX_JS.read_text(encoding="utf-8")
        # 計算條件三要素
        assert "posterCrop" in js, "state-lightbox.js 應計算 posterCrop"
        # T11（US-10）：門檻由 ≤480 擴到 ≤899（共用常數 POSTER_CROP_MAX_W，對齊守衛 TestPosterCropThresholdAlignment）。
        assert "window.innerWidth <= POSTER_CROP_MAX_W" in js, "posterCrop 應 gate ≤POSTER_CROP_MAX_W"
        assert "showFavoriteActresses" in js, "posterCrop 應排除女優模式"
        assert "hero-card" in js, "posterCrop 應排除 hero 卡（女優入口）"
        # 傳入 playGridToLightbox 的 options
        assert "posterCrop: posterCrop" in js, (
            "state-lightbox.js 應把 posterCrop 傳入 playGridToLightbox options"
        )

    def test_ghost_fly_consumes_and_aligns_crop(self):
        body = self._grid_to_lightbox_body()
        assert "options.posterCrop" in body, "playGridToLightbox 應消費 options.posterCrop"
        # (A) 對齊縮圖右裁
        assert "objectPosition = 'right center'" in body, (
            "posterCrop 下 ghost 應對齊縮圖 objectPosition right center（消起飛 pan）"
        )

    def test_ghost_fly_landing_crossfade(self):
        body = self._grid_to_lightbox_body()
        # (D) 落地 crossfade：coverEl 淡入 + ghost 淡出，且綁在 posterCrop 分支
        assert "posterCrop && coverEl" in body, (
            "落地 crossfade 應 gate 在 posterCrop（非 poster 路徑維持硬切 cleanupGhost）"
        )
        assert "opacity: 1, duration: 0.12" in body, "coverEl 應 0.12s 淡入（contain 真圖浮現）"
        assert "opacity: 0, duration: 0.12" in body, "ghost 應 0.12s 淡出（溶接 cover→contain）"
        # 非 poster 仍走硬切 cleanupGhost
        assert "cleanupGhost(ghost, coverEl)" in body, (
            "非 posterCrop 路徑應保留硬切 cleanupGhost（桌面零回歸）"
        )


class TestMobileSimilarPanelContractGuard:
    """TASK-83b-T2: 行動相似面板（.similar-mobile-panel）13 條合約守衛。

    鎖住 T1 建立的 CSS / HTML / JS 合約，防回歸。
    每條 guard 均 mutation-detectable：刪除對應實作即 RED。
    """

    @staticmethod
    def _html():
        return _T2_SHOWCASE_HTML.read_text(encoding="utf-8")

    @staticmethod
    def _css():
        return _T2_SHOWCASE_CSS.read_text(encoding="utf-8")

    @staticmethod
    def _similar_js():
        return _T2_SIMILAR_JS.read_text(encoding="utf-8")

    @staticmethod
    def _lightbox_js():
        return _T2_LIGHTBOX_JS.read_text(encoding="utf-8")

    @staticmethod
    def _base_js():
        return _T2_BASE_JS.read_text(encoding="utf-8")

    @staticmethod
    def _extract_function_body(js, func_pattern):
        """大括號平衡法擷取函式體。"""
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

    # ── 1. CSS default-hidden + .show visible ──────────────────────────────

    def test_mobile_panel_default_hidden(self):
        """.similar-mobile-panel 存在於 HTML；CSS 含 default-hidden（opacity:0/visibility:hidden/
        pointer-events:none）+ .show block（opacity:1/visibility:visible/pointer-events:auto）。"""
        html = self._html()
        assert 'class="similar-mobile-panel"' in html, \
            "showcase.html 缺 .similar-mobile-panel div"
        css = self._css()
        # default-hidden block（strip CSS comment 後查，commented-out 行也應 RED）
        m_panel = re.search(r'\.similar-mobile-panel\s*\{([^}]+)\}', css, re.DOTALL)
        assert m_panel, "showcase.css 缺 .similar-mobile-panel default-hidden block"
        block = re.sub(r'/\*.*?\*/', '', m_panel.group(1), flags=re.DOTALL)
        assert "opacity: 0" in block, \
            ".similar-mobile-panel block 缺 opacity: 0（FOUC 防護）"
        assert "visibility: hidden" in block, \
            ".similar-mobile-panel block 缺 visibility: hidden"
        assert "pointer-events: none" in block, \
            ".similar-mobile-panel block 缺 pointer-events: none"
        # .show block
        m_show = re.search(r'\.similar-mobile-panel\.show\s*\{([^}]+)\}', css, re.DOTALL)
        assert m_show, "showcase.css 缺 .similar-mobile-panel.show block"
        show_block = re.sub(r'/\*.*?\*/', '', m_show.group(1), flags=re.DOTALL)
        assert "opacity: 1" in show_block, \
            ".similar-mobile-panel.show 缺 opacity: 1"
        assert "visibility: visible" in show_block, \
            ".similar-mobile-panel.show 缺 visibility: visible"
        assert "pointer-events: auto" in show_block, \
            ".similar-mobile-panel.show 缺 pointer-events: auto"

    # ── 2. Desktop safety net ───────────────────────────────────────────────

    def test_mobile_panel_desktop_safety_net(self):
        """showcase.css @media (min-width:960px) 內含 similar-mobile-panel + display:none（桌面安全網）。"""
        css = self._css()
        # 找含 similar-mobile-panel 的那個 @media (min-width:960px) block（可能有多個同斷點）
        found = False
        for m in re.finditer(r'@media\s*\(\s*min-width\s*:\s*960px\s*\)', css):
            window = css[m.start():m.start() + 500]
            if "similar-mobile-panel" in window and "display: none" in window:
                found = True
                break
        assert found, (
            "showcase.css 缺含 similar-mobile-panel + display:none 的 @media (min-width: 960px) block"
            "（桌面安全網缺失，面板在桌面可能顯示）"
        )

    # ── 3. HTML x-trap ─────────────────────────────────────────────────────

    def test_mobile_panel_has_x_trap(self):
        """showcase.html .similar-mobile-panel block 含 x-trap.inert=\"similarModeMobileOpen\"。"""
        html = self._html()
        # 找 .similar-mobile-panel div 開始的 block
        m = re.search(r'class="similar-mobile-panel"[^>]*>(.*?)</div>', html, re.DOTALL)
        # 寬鬆：直接全文搜尋（similar-mobile-panel 唯一，不會誤中）
        idx_panel = html.find('class="similar-mobile-panel"')
        assert idx_panel != -1, "showcase.html 缺 similar-mobile-panel"
        # x-trap 必須在 panel div 開啟標籤附近（同一 tag attribute）
        panel_tag_end = html.index('>', idx_panel)
        panel_opening_tag = html[idx_panel:panel_tag_end + 1]
        assert 'x-trap.inert="similarModeMobileOpen"' in panel_opening_tag, \
            "similar-mobile-panel div 開啟標籤缺 x-trap.inert=\"similarModeMobileOpen\""

    # ── 4. Lightbox trap yields to mobile panel ─────────────────────────────

    def test_mobile_panel_lightbox_trap_yields(self):
        """showcase.html lightbox x-trap.inert 含 similarModeMobileOpen 條件（!similarModeMobileOpen）。
        面板開時 trap 釋放給面板（防焦點被困在 lightbox）。
        """
        html = self._html()
        # 錨定含 deleteVideoModalOpen 的那條（lightbox x-trap，T2 rewrite 後的錨點）
        m = re.search(r'x-trap\.inert="([^"]*deleteVideoModalOpen[^"]*)"', html)
        assert m, "showcase.html 缺含 deleteVideoModalOpen 的 x-trap.inert 行（lightbox trap）"
        expr = m.group(1)
        assert "similarModeMobileOpen" in expr, \
            f"lightbox x-trap.inert 未含 similarModeMobileOpen: {expr!r}"
        assert "!similarModeMobileOpen" in expr, \
            f"lightbox x-trap.inert 缺 !similarModeMobileOpen（面板開時 trap 未釋放）: {expr!r}"

    # ── 5. Burst card CSS ───────────────────────────────────────────────────

    def test_mobile_burst_card_class_exists(self):
        """.similar-mobile-burst-card block 存在；含 opacity:0、position:relative、transition:none。"""
        css = self._css()
        m = re.search(r'\.similar-mobile-burst-card\s*\{([^}]+)\}', css, re.DOTALL)
        assert m, "showcase.css 缺 .similar-mobile-burst-card block（T1 burst card CSS 未被誤刪）"
        block = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.DOTALL)
        assert "opacity: 0" in block, \
            ".similar-mobile-burst-card 缺 opacity: 0（GSAP-only，防 1-frame paint glitch）"
        assert "position: relative" in block, \
            ".similar-mobile-burst-card 缺 position: relative"
        assert "transition: none" in block, \
            ".similar-mobile-burst-card 缺 transition: none（GSAP-only）"

    def test_mobile_burst_card_img_poster_crop(self):
        """.similar-mobile-burst-card img block 含 aspect-ratio:var(--poster-crop-ratio)（單一真理、禁硬編碼）
        + object-position:right center（右半裁切）。
        恢復退役的 test_similar_mobile_card_img_has_poster_crop_ratio / _no_hardcoded_4_5 之 contract。
        """
        css = self._css()
        m = re.search(r'\.similar-mobile-burst-card\s+img\s*\{([^}]+)\}', css, re.DOTALL)
        assert m, "showcase.css 缺 .similar-mobile-burst-card img block"
        block = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.DOTALL)
        assert "aspect-ratio: var(--poster-crop-ratio)" in block, (
            ".similar-mobile-burst-card img 缺 aspect-ratio: var(--poster-crop-ratio)（單一真理，禁硬編碼比例）"
        )
        assert "4/5" not in block, \
            ".similar-mobile-burst-card img 不得含硬編碼 4/5（應用 var(--poster-crop-ratio)）"
        assert "object-position: right center" in block, (
            ".similar-mobile-burst-card img 缺 object-position: right center（右半裁切）"
        )

    # ── 6. Scrim blur token ─────────────────────────────────────────────────

    def test_mobile_panel_scrim_blur_token(self):
        """.similar-mobile-scrim 含 var(--fluent-blur)（不硬編碼 px）且含 -webkit-backdrop-filter。"""
        css = self._css()
        m = re.search(r'\.similar-mobile-scrim\s*\{([^}]+)\}', css, re.DOTALL)
        assert m, "showcase.css 缺 .similar-mobile-scrim block"
        block = m.group(1)
        assert "var(--fluent-blur)" in block, \
            ".similar-mobile-scrim backdrop-filter 必須用 var(--fluent-blur)（禁硬編碼 px）"
        assert "-webkit-backdrop-filter" in block, \
            ".similar-mobile-scrim 缺 -webkit-backdrop-filter（Safari fallback）"

    # ── 7. Drill lock before await ──────────────────────────────────────────

    def test_mobile_drill_lock_before_await(self):
        """onMobileDrillClick 函式體在首個 await keyword 之前有 similarModeAnimating = true（lock-before-await）。"""
        js = self._similar_js()
        body = self._extract_function_body(js, r'async\s+onMobileDrillClick\s*\(')
        assert body is not None, \
            "state-similar.js 找不到 onMobileDrillClick 函式宣告"
        # 去掉 // 單行 comment 和 /* */ 多行 comment，避免 "lock-before-await" 誤中
        body_no_comments = re.sub(r'//[^\n]*', '', body)
        body_no_comments = re.sub(r'/\*.*?\*/', '', body_no_comments, flags=re.DOTALL)
        # 找首個 await 作為 JS 關鍵字（空白/符號前置，非 -await 形式）
        m_await = re.search(r'(?<![A-Za-z0-9_$-])\bawait\b', body_no_comments)
        assert m_await is not None, "onMobileDrillClick 函式體找不到 await keyword（非 async 路徑？）"
        pre_await = body_no_comments[:m_await.start()]
        assert "similarModeAnimating = true" in pre_await, (
            "onMobileDrillClick 在首個 await keyword 之前缺 similarModeAnimating = true（lock-before-await 缺失，"
            "連點空窗導致並發進入）"
        )

    # ── 8. closeMobilePanel does NOT call closeSimilarMode ──────────────────

    def test_mobile_panel_no_call_desktop_closeSimilarMode(self):
        """state-similar.js closeMobilePanel 函式體不含 closeSimilarMode() 呼叫（CD-4 / R3 防凍結）。
        注：去掉 comment 後檢查（comment 中提及 closeSimilarMode 做對比說明是合法的）。
        """
        js = self._similar_js()
        body = self._extract_function_body(js, r'closeMobilePanel\s*\(\s*\)\s*\{')
        assert body is not None, \
            "state-similar.js 找不到 closeMobilePanel 函式宣告"
        # 去掉 comment，避免說明性文字（如 mirror closeSimilarMode）誤觸
        body_no_comments = re.sub(r'//[^\n]*', '', body)
        body_no_comments = re.sub(r'/\*.*?\*/', '', body_no_comments, flags=re.DOTALL)
        assert "closeSimilarMode" not in body_no_comments, (
            "closeMobilePanel 函式體含 closeSimilarMode() 呼叫（非 comment）！"
            "CD-4/R3：桌面 close 在 similarCards={} 時 await playExit 永不 resolve → 凍結"
        )

    # ── 9. Burst card count = 6 ─────────────────────────────────────────────

    def test_mobile_burst_card_count_6(self):
        """state-similar.js _openMobilePanel 函式體含 slice(0, 6)（CD-6 固定 6 張）。"""
        js = self._similar_js()
        body = self._extract_function_body(js, r'async\s+_openMobilePanel\s*\(')
        assert body is not None, \
            "state-similar.js 找不到 _openMobilePanel 函式宣告"
        assert "slice(0, 6)" in body, (
            "_openMobilePanel 函式體缺 slice(0, 6)（CD-6：行動面板固定 6 張，不多不少）"
        )

    # ── 10. Uses own picker params ───────────────────────────────────────────

    def test_mobile_uses_own_picker_params(self):
        """state-similar.js 含 _MOBILE_PICKER_PARAMS local const 定義；
        且程式碼（非 comment）中不含裸 _PICKER_PARAMS 字串（不直接引用 state-lightbox 的 private const）。
        """
        js = self._similar_js()
        assert "_MOBILE_PICKER_PARAMS" in js, \
            "state-similar.js 缺 _MOBILE_PICKER_PARAMS（行動面板專屬 picker params 未定義）"
        # const 定義（不只是字串使用）
        assert re.search(r'const\s+_MOBILE_PICKER_PARAMS', js), \
            "state-similar.js 缺 const _MOBILE_PICKER_PARAMS 定義"
        # 去掉 comment，再去掉 _MOBILE_PICKER_PARAMS，剩下若有 _PICKER_PARAMS 即裸引用
        js_no_comments = re.sub(r'//[^\n]*', '', js)
        js_no_comments = re.sub(r'/\*.*?\*/', '', js_no_comments, flags=re.DOTALL)
        js_stripped = js_no_comments.replace("_MOBILE_PICKER_PARAMS", "")
        assert "_PICKER_PARAMS" not in js_stripped, (
            "state-similar.js 程式碼（非 comment）含裸 _PICKER_PARAMS 引用（state-lightbox private const，"
            "直接引用在 stateSimilar 作用域會 ReferenceError）"
        )

    # ── 11. matchMedia 960 reset ─────────────────────────────────────────────

    def test_mobile_panel_matchmedia_960(self):
        """state-base.js 含 matchMedia + 960 + similarModeMobileOpen + closeMobilePanel（D12 reset）。"""
        js = self._base_js()
        assert "matchMedia" in js, "state-base.js 缺 matchMedia（D12 breakpoint reset 未實作）"
        assert "960" in js, "state-base.js 缺 960（matchMedia 960px breakpoint）"
        assert "similarModeMobileOpen" in js, \
            "state-base.js 缺 similarModeMobileOpen（D12 reset 條件缺失）"
        assert "closeMobilePanel" in js, \
            "state-base.js 缺 closeMobilePanel 呼叫（D12 reset 動作缺失）"

    # ── 12. burst-picker back.out exists, no 1.7 pinned ─────────────────────

    def test_burst_picker_back_out_exists_no_1_7_pinned(self):
        """burst-picker.js 含 back.out；且 guard 自身不 pin 具體 1.7 值（CD-11：doc/code drift）。"""
        js = _T2_BURST_PICKER_JS.read_text(encoding="utf-8")
        assert "back.out" in js, \
            "burst-picker.js 缺 back.out（爆射 overshoot ease 未使用）"
        # guard 自身不 assert 1.7（CD-11：不把 1.7 寫進守衛，避免文件/code drift）
        # 只守 back.out 存在；具體值由 arcOvershoot param 決定，不硬鎖
        # 反向：確保 burst-picker.js 仍用動態 arcOvershoot（非硬編碼 1.7 字串）
        assert "arcOvershoot" in js, \
            "burst-picker.js 缺 arcOvershoot param（back.out 值應來自 param，非硬編碼）"

    # ── 13. Keydown intercept ────────────────────────────────────────────────

    def test_mobile_panel_keydown_intercept(self):
        """state-lightbox.js handleKeydown 函式體含 similarModeMobileOpen 條件分支 + closeMobilePanel。
        且 similarModeMobileOpen guard block 不含 closeLightbox / prevLightboxVideo / nextLightboxVideo
        （CD-7/D10：Esc 不關 lightbox，箭頭不切片）。
        """
        js = self._lightbox_js()
        body = self._extract_function_body(js, r'handleKeydown\s*\(')
        assert body is not None, \
            "state-lightbox.js 找不到 handleKeydown 函式宣告"
        assert "similarModeMobileOpen" in body, \
            "handleKeydown 函式體缺 similarModeMobileOpen 條件（面板開時未攔截鍵盤）"
        assert "closeMobilePanel" in body, \
            "handleKeydown 函式體缺 closeMobilePanel 呼叫（Esc 未關行動面板）"
        # 找 similarModeMobileOpen guard block，確認 block 不含 closeLightbox/prev/next
        m = re.search(
            r'if\s*\(\s*this\.similarModeMobileOpen\s*\)\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}',
            body, re.DOTALL
        )
        assert m, "handleKeydown 缺 if (this.similarModeMobileOpen) { ... } block"
        guard_block = m.group(1)
        assert "closeLightbox" not in guard_block, (
            "handleKeydown similarModeMobileOpen block 含 closeLightbox()（Esc 不得關 lightbox，CD-7）"
        )
        assert "prevLightboxVideo" not in guard_block, (
            "handleKeydown similarModeMobileOpen block 含 prevLightboxVideo（箭頭不得切片，D10）"
        )
        assert "nextLightboxVideo" not in guard_block, (
            "handleKeydown similarModeMobileOpen block 含 nextLightboxVideo（箭頭不得切片，D10）"
        )


class TestMobilePanelT3Guards:
    """TASK-83b-T3: 行動相似面板封面飛行進退場（6 條靜態守衛）。

    每條 guard 均 mutation-detectable：刪除或改動對應實作即 RED。
    """

    @staticmethod
    def _ghost_fly_js():
        return _T3_GHOST_FLY_JS.read_text(encoding="utf-8")

    @staticmethod
    def _similar_js():
        return _T2_SIMILAR_JS.read_text(encoding="utf-8")

    @staticmethod
    def _extract_function_body(js, func_pattern):
        """大括號平衡法擷取函式體（reuse T2 pattern）。"""
        m = re.search(func_pattern, js)
        if not m:
            return None
        start = m.start()
        try:
            body_start = js.index('{', start)
        except ValueError:
            return None
        depth = 0
        for i, ch in enumerate(js[body_start:], body_start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    return js[body_start:i + 1]
        return None

    # ── 1. Helper functions exported ────────────────────────────────────────

    def test_mobile_panel_enter_exit_functions_exported(self):
        """ghost-fly.js 含 playMobilePanelEnter + playMobilePanelExit 函式定義，
        且兩者均出現在 GhostFly export 物件中。"""
        js = self._ghost_fly_js()
        assert "playMobilePanelEnter" in js, \
            "ghost-fly.js 缺 playMobilePanelEnter 函式（83b-T3 helper 未建立）"
        assert "playMobilePanelExit" in js, \
            "ghost-fly.js 缺 playMobilePanelExit 函式（83b-T3 helper 未建立）"
        # 確認 export 在 GhostFly 物件中（兩者均以 property: function 形式 export）
        assert re.search(r'playMobilePanelEnter\s*:\s*playMobilePanelEnter', js), \
            "ghost-fly.js GhostFly export 物件缺 playMobilePanelEnter 屬性"
        assert re.search(r'playMobilePanelExit\s*:\s*playMobilePanelExit', js), \
            "ghost-fly.js GhostFly export 物件缺 playMobilePanelExit 屬性"

    # ── 2. Enter uses createCoverGhost, not constellation wrapper ───────────

    def test_mobile_enter_uses_create_cover_ghost_not_constellation(self):
        """ghost-fly.js playMobilePanelEnter 函式體含 createCoverGhost，
        且不含 play56cConstellationEnter（不包裝桌面禁區函式）。
        comment 中的字串不算（去掉 // 和 /* */ comment 後才驗證）。"""
        js = self._ghost_fly_js()
        body = self._extract_function_body(js, r'function\s+playMobilePanelEnter\s*\(')
        assert body is not None, \
            "ghost-fly.js 找不到 playMobilePanelEnter 函式宣告"
        assert "createCoverGhost" in body, \
            "playMobilePanelEnter 函式體缺 createCoverGhost 呼叫（必須直接用 primitive，不可包裝桌面函式）"
        # 去掉 comment 後再搜尋（comment 中可能有說明性文字提及禁區函式名）
        body_no_comments = re.sub(r'//[^\n]*', '', body)
        body_no_comments = re.sub(r'/\*.*?\*/', '', body_no_comments, flags=re.DOTALL)
        assert "play56cConstellationEnter" not in body_no_comments, \
            "playMobilePanelEnter 函式體（去注釋後）含 play56cConstellationEnter（禁區：不可包裝桌面函式）"

    # ── 3. Transition tokenized（DURATION.medium + fluent ease strings）──────

    def test_mobile_transition_tokenized(self):
        """ghost-fly.js playMobilePanelEnter / playMobilePanelExit 均：
        - 含 DURATION.medium（token 不硬編碼）
        - 含 0.333（fallback 允許）
        - enter 含 fluent-decel；exit 含 fluent-accel
        - 函式體（排除 fallback 表達式後）不含裸 duration 數字 literal（如 duration: 0.333）

        Correction B：0.333 只允許作為 || fallback，不得作為 duration: 的直接值。
        """
        js = self._ghost_fly_js()

        enter_body = self._extract_function_body(js, r'function\s+playMobilePanelEnter\s*\(')
        assert enter_body is not None, "ghost-fly.js 找不到 playMobilePanelEnter"
        exit_body = self._extract_function_body(js, r'function\s+playMobilePanelExit\s*\(')
        assert exit_body is not None, "ghost-fly.js 找不到 playMobilePanelExit"

        for name, body in [("playMobilePanelEnter", enter_body), ("playMobilePanelExit", exit_body)]:
            assert "DURATION.medium" in body, \
                f"{name} 函式體缺 DURATION.medium（必須用 token，不可硬編碼 duration）"
            assert "0.333" in body, \
                f"{name} 函式體缺 0.333 fallback（token guard chain 要求 || 0.333 fallback）"

        assert "fluent-decel" in enter_body, \
            "playMobilePanelEnter 函式體缺 fluent-decel ease（禁用 power2.* 代換）"
        assert "fluent-accel" in exit_body, \
            "playMobilePanelExit 函式體缺 fluent-accel ease（禁用 power2.* 代換）"

        # Correction B：排除 || 0.333 fallback 行後，不得有 duration: <數字> 裸值
        # 方法：把 "|| 0.333" fallback 表達式置換掉，再搜尋 duration: 後接數字
        for name, body in [("playMobilePanelEnter", enter_body), ("playMobilePanelExit", exit_body)]:
            body_stripped = body.replace("|| 0.333", "").replace("|| 0.5", "")
            # 搜尋 duration: 後緊接數字 literal（含小數）
            assert not re.search(r'\bduration\s*:\s*\d+(\.\d+)?', body_stripped), \
                (f"{name} 函式體含裸 duration 數字 literal（排除 fallback 後仍殘留）；"
                 "必須用 dur 變數（來自 DURATION.medium || 0.333）")

    # ── 4. closeMobilePanel is async ────────────────────────────────────────

    def test_mobile_close_panel_is_async(self):
        """state-similar.js closeMobilePanel 為 async 函式（exit ghost await 前提）。"""
        js = self._similar_js()
        assert re.search(r'async\s+closeMobilePanel\s*\(', js), \
            "state-similar.js closeMobilePanel 不是 async 函式（83b-T3：exit ghost 需 async + await）"

    # ── 5. PRM fallback branches exist ──────────────────────────────────────

    def test_mobile_transition_prm_fallback(self):
        """state-similar.js _openMobilePanel 函式體含 shouldSkip（PRM 閘），
        且 enter ghost 飛行（playMobilePanelEnter）被 shouldSkip 閘控（!...shouldSkip 在呼叫前）；
        closeMobilePanel 含 shouldSkip + playMobilePanelExit 被閘控。"""
        js = self._similar_js()

        open_body = self._extract_function_body(js, r'async\s+_openMobilePanel\s*\(')
        assert open_body is not None, \
            "state-similar.js 找不到 _openMobilePanel 函式宣告"
        assert "shouldSkip" in open_body, \
            "_openMobilePanel 函式體缺 shouldSkip（PRM 降級分支未實作）"
        assert "mobilePanelCoverImg" in open_body, \
            "_openMobilePanel 函式體缺 mobilePanelCoverImg（PRM 分支中央主圖 src 設定缺失）"
        # Nit 強化：enter ghost 飛行必須被 PRM 閘控（!...shouldSkip(...) 出現在 playMobilePanelEnter 呼叫之前）
        assert "playMobilePanelEnter" in open_body, \
            "_openMobilePanel 函式體缺 playMobilePanelEnter 呼叫（enter 飛行未接線）"
        open_no_comments = re.sub(r'//[^\n]*', '', open_body)
        open_no_comments = re.sub(r'/\*.*?\*/', '', open_no_comments, flags=re.DOTALL)
        m_neg = re.search(r'!\s*window\.BurstPicker\.shouldSkip', open_no_comments)
        m_enter = re.search(r'playMobilePanelEnter', open_no_comments)
        assert m_neg is not None, \
            "_openMobilePanel 缺 !window.BurstPicker.shouldSkip 否定閘（enter 飛行未受 PRM 閘控）"
        assert m_neg.start() < m_enter.start(), (
            "_openMobilePanel 的 !shouldSkip 閘必須在 playMobilePanelEnter 呼叫之前"
            "（否則 PRM 用戶仍會跑進場飛行）"
        )

        close_body = self._extract_function_body(js, r'async\s+closeMobilePanel\s*\(')
        assert close_body is not None, \
            "state-similar.js 找不到 async closeMobilePanel 函式宣告"
        assert "shouldSkip" in close_body, \
            "closeMobilePanel 函式體缺 shouldSkip（PRM 快捷隱藏路徑未實作）"
        # exit ghost 飛行同樣被 PRM 閘控
        assert "playMobilePanelExit" in close_body, \
            "closeMobilePanel 函式體缺 playMobilePanelExit 呼叫（exit 飛行未接線）"
        close_no_comments = re.sub(r'//[^\n]*', '', close_body)
        close_no_comments = re.sub(r'/\*.*?\*/', '', close_no_comments, flags=re.DOTALL)
        m_neg_c = re.search(r'!\s*window\.BurstPicker\.shouldSkip', close_no_comments)
        m_exit = re.search(r'playMobilePanelExit', close_no_comments)
        assert m_neg_c is not None and m_neg_c.start() < m_exit.start(), (
            "closeMobilePanel 的 !shouldSkip 閘必須在 playMobilePanelExit 呼叫之前"
            "（否則 PRM 用戶仍會跑退場飛行）"
        )

    # ── 5b. closeMobilePanel kills in-flight enter timeline (P1-T3fix) ───────

    def test_mobile_close_kills_enter_timeline(self):
        """state-similar.js closeMobilePanel 函式體在 playMobilePanelExit 之前 kill in-flight
        enter timeline（_mobileEnterTl.kill()）+ 顯式 cleanup enter ghost（_mobileEnterGhost）。
        P1-T3fix：防中途打斷時 enter onComplete 在 exit 飛行中誤還原 mobileCoverEl opacity → 雙圖。"""
        js = self._similar_js()
        close_body = self._extract_function_body(js, r'async\s+closeMobilePanel\s*\(')
        assert close_body is not None, \
            "state-similar.js 找不到 async closeMobilePanel 函式宣告"
        close_no_comments = re.sub(r'//[^\n]*', '', close_body)
        close_no_comments = re.sub(r'/\*.*?\*/', '', close_no_comments, flags=re.DOTALL)
        # 必須 kill in-flight enter timeline
        m_kill = re.search(r'_mobileEnterTl\s*\.\s*kill\s*\(', close_no_comments)
        assert m_kill is not None, (
            "closeMobilePanel 缺 _mobileEnterTl.kill()（P1-T3fix：未 kill in-flight 進場 timeline → "
            "中途打斷雙圖）"
        )
        # 必須顯式 cleanup enter ghost（.kill() 不保證 fire onInterrupt，故不可只靠 timeline 自清）
        assert "_mobileEnterGhost" in close_no_comments, (
            "closeMobilePanel 缺 _mobileEnterGhost 顯式 cleanup（.kill() 不 fire onInterrupt → "
            "enter ghost 殘留 + opacity 未還原）"
        )
        # kill 必須在 exit 飛行（playMobilePanelExit）之前
        m_exit = re.search(r'playMobilePanelExit', close_no_comments)
        assert m_exit is not None, "closeMobilePanel 缺 playMobilePanelExit"
        assert m_kill.start() < m_exit.start(), (
            "_mobileEnterTl.kill() 必須在 playMobilePanelExit 之前"
            "（否則 enter ghost 仍在飛 → 與 exit ghost 雙圖）"
        )

    # ── 6. Desktop constellation anchor not in mobile enter ─────────────────

    def test_desktop_constellation_byte_identical_anchor(self):
        """ghost-fly.js 含 .similar-main-anchor（桌面 anchor lookup 未被移除）；
        且 playMobilePanelEnter 函式體不含 .similar-main-anchor（禁區 anchor 不被 mobile helper 引用）。"""
        js = self._ghost_fly_js()
        assert ".similar-main-anchor" in js, \
            "ghost-fly.js 缺 .similar-main-anchor（桌面 play56cConstellationEnter 被破壞或移除）"

        enter_body = self._extract_function_body(js, r'function\s+playMobilePanelEnter\s*\(')
        assert enter_body is not None, \
            "ghost-fly.js 找不到 playMobilePanelEnter 函式宣告"
        assert ".similar-main-anchor" not in enter_body, \
            "playMobilePanelEnter 函式體含 .similar-main-anchor（禁區：桌面 DOM 不得出現在 mobile helper）"

