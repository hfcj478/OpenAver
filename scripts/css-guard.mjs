#!/usr/bin/env node
/**
 * css-guard.mjs — contextual/relational CSS-block guard（96c，zero-dep）
 *
 * 承接 stylelint 標準 rule 表達不了的 selector-scoped / relational / 存在性 /
 * 跨 media-block breakpoint 值對齊 / inline-style token 掃描（CD-96c-1〔b〕）。
 *
 * T1：骨架 + 兩 helper（stripCssComments / parseRuleBlocks，port 自
 * test_fluent_materials_guards.py 的 _strip_css_comments / _parse_rule_blocks）
 * + 空 RULES 表 + runner。實際規則於 T2–T4 落地（T2 fluent method、T3
 * poster-crop 家族 + handoff、T4 motion_lab inline）。
 *
 * 非 pytest（遵 CLAUDE.md「lint 守衛寫 lint config、不寫 pytest」）。串 `npm run lint`。
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
// 可傳 <scratch-root> 覆蓋 repo root（mutation 自驗指向 scratch 副本，不污染真檔，
// 比照 static_guard_lint.mjs <scratch-root> / i18n_lint.mjs <locale-dir> 房規）。
// 空殼 T1 下無 RULES 讀檔，故 arg 只需被接受即可（exit 0）；T2–T4 rule 透過
// CSS(rel) resolve target，scratch 副本自動生效。
const ROOT = process.argv[2] ? resolve(process.argv[2]) : join(__dirname, '..');
// rule 用此 resolve target CSS 檔（T2 起使用）
const CSS = (rel) => join(ROOT, 'web', 'static', 'css', rel);

let hadError = false;
function fail(msg) {
  console.error(`✗ css-guard: ${msg}`);
  hadError = true;
}

// ── ported helpers（忠實鏡射 Python，CD-96c-2；T2 起由 RULES 使用）──

// _strip_css_comments：移除 /* … */ 區塊註解（可跨行）
function stripCssComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '');
}

// _parse_rule_blocks：逐字元走訪追 brace depth，depth 歸 0 時收 {selector, declarations}。
// @media wrapper 自然被當 depth-1 外層、回傳最內層 rule block（忠實鏡射 Python 逐字元
// 迴圈，非 regex 猜大括號配對）。
function parseRuleBlocks(cssText) {
  const blocks = [];
  let depth = 0;
  let start = 0;
  let selector = '';
  let blockStart = 0;
  for (let i = 0; i < cssText.length; i += 1) {
    const ch = cssText[i];
    if (ch === '{') {
      if (depth === 0) {
        selector = cssText.slice(start, i).trim();
        blockStart = i + 1;
      }
      depth += 1;
    } else if (ch === '}') {
      depth -= 1;
      if (depth === 0) {
        blocks.push({ selector, declarations: cssText.slice(blockStart, i) });
        start = i + 1;
      }
    }
  }
  return blocks;
}

// re.escape port（token 名含 `-`，CG-FLU-12 需精確 escape，CD-96c-2）
function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// @media (min-width:1024px) body 抽取（CG-FLU-09/10 11b；用 ctx.raw，鏡射 pytest css_raw）。
// parseRuleBlocks 對 @media wrapper 只回一個 depth-0 block，故需先 regex 抽 body 再 re-parse。
function extractDesktopMediaBodies(raw) {
  return [
    ...raw.matchAll(
      /@media\s*\(\s*min-width\s*:\s*1024px\s*\)\s*\{([\s\S]*?)\}(?=\s*(?:\/\*|@|[\[\.\#a-zA-Z]|$))/g,
    ),
  ].map((m) => m[1]);
}

// @media (max-width:480px) body 抽取（CG-FLU-14/15；手工 brace-walk，鏡射 pytest —
// 不用 parseRuleBlocks，否則抓到整個 @media body 而非單一 inner rule block）。
// 回傳 { body } 或 { err } — err 供 rule 決定失敗訊息。
function extractMobileMediaBody(css) {
  const m = css.match(/@media\s*\(\s*max-width\s*:\s*480px\s*\)\s*\{/);
  if (!m) return { err: 'no-media' };
  const braceIdx = m.index + m[0].length - 1; // '{' 位置（鏡射 pytest m.end()-1）
  let depth = 0;
  let end = null;
  for (let i = braceIdx; i < css.length; i += 1) {
    if (css[i] === '{') depth += 1;
    else if (css[i] === '}') {
      depth -= 1;
      if (depth === 0) {
        end = i;
        break;
      }
    }
  }
  if (end === null) return { err: 'unbalanced' };
  return { body: css.slice(braceIdx + 1, end) }; // 鏡射 pytest css[m.end():end]
}

// ── kind dispatcher（宣告式 selector-forbid / selector-require + fn escape-hatch）──
const KINDS = {
  // selector-block 負向屬性禁令：markers 全命中的 block 內 pattern 必不存在
  'selector-forbid': (rule, ctx) => {
    for (const { selector, declarations } of ctx.blocks) {
      if (!rule.markers.every((mk) => selector.includes(mk))) continue;
      if (rule.pattern.test(declarations)) ctx.fail(`${rule.id}: ${rule.msg} — ${selector}`);
    }
  },
  // selector-block 正向值斷言：markers block 必存在 + pattern 必命中（缺 block 亦違規）
  'selector-require': (rule, ctx) => {
    let found = false;
    for (const { selector, declarations } of ctx.blocks) {
      if (!rule.markers.every((mk) => selector.includes(mk))) continue;
      found = true;
      if (!rule.pattern.test(declarations)) ctx.fail(`${rule.id}: ${rule.msg} — ${selector}`);
    }
    if (!found) ctx.fail(`${rule.id}: ${rule.msg} — block 不存在`);
  },
  // bespoke relational escape-hatch
  fn: (rule, ctx) => rule.check(ctx),
};

const UNSCOPED_SHELL_TOPBARS = ['.search-bar', '.settings-header', '.avlist-header', '.showcase-toolbar'];
const SHELL_TOKENS = [
  '--glass-shell-gradient',
  '--glass-shell-fill',
  '--glass-shell-saturate',
  '--glass-shell-edge-top',
  '--glass-shell-edge-bottom',
  '--glass-shell-border',
];
const NON_SHELL_ROLE_MARKERS = {
  panel: '.help-card',
  caption: '.av-card-preview-footer',
  overlay: '.lightbox-content',
  'media-frame': '.similar-slot',
};

// ── 表驅動 rule-set（fluent 家族 14 條，忠實 port test_fluent_materials_guards.py，CD-96c-2）──
const RULES = [
  // CG-FLU-01 ← test_non_shell_backdrop_filter_dim_scoped
  {
    id: 'CG-FLU-01',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      for (const { selector, declarations } of ctx.blocks) {
        const bfValues = [
          ...declarations.matchAll(/(?<!-webkit-)backdrop-filter\s*:\s*([^;}]+)/g),
        ].map((m) => m[1]);
        if (bfValues.length === 0) continue;
        // 全部 backdrop-filter 值皆 explicit `none` → 例外（literal，不會 IACVT-fail）
        if (bfValues.every((v) => v.replace(/!important/g, '').trim() === 'none')) continue;
        const clean = selector.replace(/@media\s*\([^)]*\)\s*/g, '').trim();
        if (clean.includes('[data-theme="dim"]')) continue;
        if (UNSCOPED_SHELL_TOPBARS.some((cls) => clean.includes(cls))) continue;
        ctx.fail(
          `CG-FLU-01: backdrop-filter outside [data-theme="dim"] scope (not a whitelisted 77d chrome top-bar) — ${selector}`,
        );
      }
    },
  },

  // CG-FLU-03 ← test_webkit_backdrop_filter_pairing（line-adjacency，用 ctx.text）
  {
    id: 'CG-FLU-03',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      const lines = ctx.text.split('\n');
      let i = 0;
      while (i < lines.length) {
        const line = lines[i].trim();
        const m = line.match(/^(?<!-webkit-)backdrop-filter\s*:\s*(.+)/);
        if (m && !line.startsWith('-webkit-')) {
          const value = m[1].replace(/;+$/, '').trim();
          let j = i + 1;
          while (j < lines.length && lines[j].trim() === '') j += 1;
          if (j < lines.length) {
            const nextLine = lines[j].trim();
            const wm = nextLine.match(/^-webkit-backdrop-filter\s*:\s*(.+)/);
            if (wm) {
              const webkitValue = wm[1].replace(/;+$/, '').trim();
              if (value !== webkitValue) {
                ctx.fail(
                  `CG-FLU-03: backdrop-filter ${JSON.stringify(value)} but -webkit- has ${JSON.stringify(webkitValue)} (line ${i + 1})`,
                );
              }
            } else {
              ctx.fail(
                `CG-FLU-03: backdrop-filter ${JSON.stringify(value)} not followed by -webkit-backdrop-filter (line ${i + 1}, got ${JSON.stringify(nextLine)})`,
              );
            }
          }
        }
        i += 1;
      }
    },
  },

  // CG-FLU-04 ← test_caption_footer_no_backdrop_filter（selector-scoped 負向）
  {
    id: 'CG-FLU-04',
    file: 'components/fluent-materials.css',
    kind: 'selector-forbid',
    markers: ['.av-card-preview-footer'],
    pattern: /backdrop-filter\s*:/,
    msg: '.av-card-preview-footer must not have backdrop-filter (90-card perf)',
  },

  // CG-FLU-05 ← test_lightbox_metadata_hairline（selector-scoped 正向值）
  {
    id: 'CG-FLU-05',
    file: 'components/fluent-materials.css',
    kind: 'selector-require',
    markers: ['.lightbox-metadata', '[data-theme="dim"]'],
    pattern: /background\s*:\s*transparent/,
    msg: '[data-theme="dim"] .lightbox-metadata must set background: transparent',
  },

  // CG-FLU-06 ← test_modal_box_not_solid（正向 has-overlay + 負向 not-surface-2 複合）
  {
    id: 'CG-FLU-06',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      let found = false;
      for (const { selector, declarations } of ctx.blocks) {
        if (!(selector.includes('.fluent-modal-box') && selector.includes('[data-theme="dim"]'))) continue;
        found = true;
        const hasOverlay = /--glass-overlay-modal-fill/.test(declarations)
          || /--glass-overlay-fill-gradient/.test(declarations)
          || /border-box/.test(declarations);
        if (!hasOverlay) {
          ctx.fail(
            `CG-FLU-06: [data-theme="dim"] .fluent-modal-box must reference --glass-overlay-modal-fill or border-box gradient — ${selector}`,
          );
        }
        if (/background\s*:\s*var\(--surface-2\)/.test(declarations)) {
          ctx.fail(
            `CG-FLU-06: [data-theme="dim"] .fluent-modal-box must NOT set background: var(--surface-2) (solid breaks overlay glass) — ${selector}`,
          );
        }
      }
      if (!found) ctx.fail('CG-FLU-06: [data-theme="dim"] .fluent-modal-box block 不存在');
    },
  },

  // CG-FLU-07 ← test_similar_main_static_no_transition_transform（逐 transition 宣告檢 transform）
  {
    id: 'CG-FLU-07',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      for (const { selector, declarations } of ctx.blocks) {
        if (!(selector.includes('.similar-main-static') && selector.includes('[data-theme="dim"]'))) continue;
        const transitions = declarations.match(/transition\s*:[^;]+/g) || [];
        for (const t of transitions) {
          if (t.includes('transform')) {
            ctx.fail(
              `CG-FLU-07: [data-theme="dim"] .similar-main-static must NOT reference transform in a transition (C21 GSAP guard): ${JSON.stringify(t)}`,
            );
          }
        }
      }
    },
  },

  // CG-FLU-08 ← test_gsap_animating_guard_exists_in_theme_css（跨檔 theme.css 存在 + 值）
  {
    id: 'CG-FLU-08',
    file: 'theme.css',
    kind: 'selector-require',
    markers: ['.av-card-preview.gsap-animating'],
    pattern: /transition\s*:\s*none\s*!important/,
    msg: 'theme.css .av-card-preview.gsap-animating must contain transition: none !important (B-T1 GSAP pre-flight)',
  },

  // CG-FLU-09 ← test_77d_search_bar_float_theme_agnostic（@media≥1024px re-parse，用 ctx.raw）
  {
    id: 'CG-FLU-09',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      const searchBarBlocks = [];
      for (const mb of extractDesktopMediaBodies(ctx.raw)) {
        for (const { selector, declarations } of parseRuleBlocks(mb)) {
          if (selector.includes('.search-bar')) searchBarBlocks.push({ selector, declarations });
        }
      }
      if (searchBarBlocks.length === 0) {
        ctx.fail('CG-FLU-09: no .search-bar rule inside @media (min-width:1024px) — CD-D1 (Rule 45) missing');
        return;
      }
      for (const { selector, declarations } of searchBarBlocks) {
        if (selector.includes('[data-theme="dim"]')) {
          ctx.fail(`CG-FLU-09: .search-bar @media 1024px float rule must be theme-agnostic — ${selector}`);
        }
        if (!/border-radius\s*:/.test(declarations)) ctx.fail('CG-FLU-09: .search-bar @media 1024px block missing border-radius');
        if (!/\bborder\s*:/.test(declarations)) ctx.fail('CG-FLU-09: .search-bar @media 1024px block missing border');
        if (!/\bmargin\s*:/.test(declarations)) ctx.fail('CG-FLU-09: .search-bar @media 1024px block missing margin');
      }
    },
  },

  // CG-FLU-10 ← test_77d_headers_float_theme_agnostic（11a all-widths padding + 11b @media float）
  {
    id: 'CG-FLU-10',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      // 11a: all-widths padding rule（用 ctx.text/blocks，鏡射 css_no_comments）
      let paddingFound = false;
      for (const { selector, declarations } of ctx.blocks) {
        if (
          selector.includes('.settings-header')
          && selector.includes('.avlist-header')
          && !selector.includes('@media')
        ) {
          if (/padding\s*:/.test(declarations)) {
            paddingFound = true;
            if (selector.includes('[data-theme="dim"]')) {
              ctx.fail(`CG-FLU-10: :is(.settings-header, .avlist-header) padding rule must be theme-agnostic — ${selector}`);
            }
            if (!/padding\s*:\s*1rem\s+1\.5rem/.test(declarations)) {
              ctx.fail('CG-FLU-10: :is(.settings-header, .avlist-header) padding should be 1rem 1.5rem (flush-left fix)');
            }
          }
        }
      }
      if (!paddingFound) ctx.fail('CG-FLU-10: :is(.settings-header, .avlist-header) all-widths padding rule not found (Rule 46)');

      // 11b: desktop-gated floating rule（用 ctx.raw @media≥1024px）
      const desktopHeaderBlocks = [];
      for (const mb of extractDesktopMediaBodies(ctx.raw)) {
        for (const { selector, declarations } of parseRuleBlocks(mb)) {
          if (selector.includes('.settings-header') && selector.includes('.avlist-header')) {
            desktopHeaderBlocks.push({ selector, declarations });
          }
        }
      }
      if (desktopHeaderBlocks.length === 0) {
        ctx.fail('CG-FLU-10: no :is(.settings-header, .avlist-header) rule inside @media (min-width:1024px) — Rule 47 missing');
        return;
      }
      for (const { selector, declarations } of desktopHeaderBlocks) {
        if (selector.includes('[data-theme="dim"]')) {
          ctx.fail(`CG-FLU-10: :is(.settings-header, .avlist-header) @media float rule must be theme-agnostic — ${selector}`);
        }
        if (!/border-radius\s*:/.test(declarations)) ctx.fail('CG-FLU-10: :is(.settings-header, .avlist-header) @media 1024px block missing border-radius');
        if (!/\bborder\s*:/.test(declarations)) ctx.fail('CG-FLU-10: :is(.settings-header, .avlist-header) @media 1024px block missing border');
      }
    },
  },

  // CG-FLU-11 ← test_77c_t3_vt_name_regression_anchor（字面錨用 ctx.raw + block 值用 ctx.text）
  {
    id: 'CG-FLU-11',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      if (!ctx.raw.includes('.page-search #main-content:has(.showcase-lightbox.show)')) {
        ctx.fail('CG-FLU-11: regression anchor .page-search #main-content:has(.showcase-lightbox.show) not found — 77c-T3 per-card blur bug returns');
      }
      let found = false;
      for (const { selector, declarations } of ctx.blocks) {
        if (
          selector.includes('.page-search')
          && selector.includes('#main-content')
          && selector.includes('.showcase-lightbox')
        ) {
          found = true;
          if (!/view-transition-name\s*:\s*none/.test(declarations)) {
            ctx.fail(`CG-FLU-11: regression anchor rule must set view-transition-name: none — ${selector}`);
          }
        }
      }
      if (!found) ctx.fail('CG-FLU-11: regression anchor rule block not found after parsing');
    },
  },

  // CG-FLU-12 ← test_light_shell_tokens_complete（token-set 完整性，精確 selector 比對）
  {
    id: 'CG-FLU-12',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      let dimDecls = null;
      let lightDecls = null;
      for (const { selector, declarations } of ctx.blocks) {
        const sel = selector.trim();
        if (sel === '[data-theme="dim"]') dimDecls = declarations;
        else if (sel === '[data-theme="light"]') lightDecls = declarations;
      }
      if (dimDecls === null) ctx.fail('CG-FLU-12: [data-theme="dim"] token block not found');
      if (lightDecls === null) {
        ctx.fail('CG-FLU-12: [data-theme="light"] token block not found — light chrome top-bars would IACVT');
      }
      if (dimDecls !== null) {
        const missing = SHELL_TOKENS.filter((t) => !new RegExp(`${escapeRegExp(t)}\\s*:`).test(dimDecls));
        if (missing.length) ctx.fail(`CG-FLU-12: [data-theme="dim"] token block missing shell token(s): ${missing.join(', ')}`);
      }
      if (lightDecls !== null) {
        const missing = SHELL_TOKENS.filter((t) => !new RegExp(`${escapeRegExp(t)}\\s*:`).test(lightDecls));
        if (missing.length) {
          ctx.fail(`CG-FLU-12: [data-theme="light"] token block missing shell token(s): ${missing.join(', ')} (IACVT risk — CD-D2(a))`);
        }
      }
    },
  },

  // CG-FLU-13 ← test_non_shell_roles_stay_dim_scoped（4 role marker 存在 + dim-scoped）
  {
    id: 'CG-FLU-13',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      for (const [role, marker] of Object.entries(NON_SHELL_ROLE_MARKERS)) {
        const matched = ctx.blocks.filter((b) => b.selector.includes(marker));
        if (matched.length === 0) {
          ctx.fail(`CG-FLU-13: ${role} marker ${marker} not found (selector renamed? update NON_SHELL_ROLE_MARKERS)`);
          continue;
        }
        for (const { selector } of matched) {
          const clean = selector.replace(/@media\s*\([^)]*\)\s*/g, '').trim();
          if (!clean.includes('[data-theme="dim"]')) {
            ctx.fail(`CG-FLU-13: ${role} rule ${selector} (marker ${marker}) is not dim-scoped — S-2 violation`);
          }
        }
      }
    },
  },

  // CG-FLU-14 ← test_notification_drawer_mobile_sheet（@media(max-width:480px) 手工 brace-walk）
  {
    id: 'CG-FLU-14',
    file: 'components/fluent-materials.css',
    kind: 'fn',
    check(ctx) {
      const ext = extractMobileMediaBody(ctx.text);
      if (ext.err === 'no-media') {
        ctx.fail('CG-FLU-14: no @media (max-width:480px) block found (81c-T6 mobile sheet missing)');
        return;
      }
      if (ext.err === 'unbalanced') {
        ctx.fail('CG-FLU-14: unbalanced @media (max-width:480px) block');
        return;
      }
      const mediaBody = ext.body;
      if (!mediaBody.includes('.notification-drawer')) {
        ctx.fail('CG-FLU-14: @media (max-width:480px) must contain a .notification-drawer rule');
        return;
      }
      const dm = mediaBody.match(/\.notification-drawer\s*\{([^}]*)\}/);
      if (!dm) {
        ctx.fail('CG-FLU-14: .notification-drawer rule not parseable inside @media (max-width:480px)');
        return;
      }
      const decls = dm[1];
      for (const prop of ['position', 'left', 'right', 'top', 'width']) {
        if (!new RegExp(`\\b${prop}\\s*:[^;]*!important`).test(decls)) {
          ctx.fail(`CG-FLU-14: mobile .notification-drawer must set ${prop} with !important`);
        }
      }
      if (!/background\s*:\s*var\(--surface-2\)[^;]*!important/.test(decls)) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must set background: var(--surface-2) !important (solid fill, G2)');
      }
      if (/#[0-9a-fA-F]{3,8}\b/.test(decls)) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must not use a hex color literal (token-only)');
      }
      if (decls.includes('rgb(') || decls.includes('rgba(')) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must not use rgb()/rgba() (token-only)');
      }
      if (!/(?<!-webkit-)backdrop-filter\s*:\s*none\s*!important/.test(decls)) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must set backdrop-filter: none !important (G2)');
      }
      if (!/-webkit-backdrop-filter\s*:\s*none\s*!important/.test(decls)) {
        ctx.fail('CG-FLU-14: mobile .notification-drawer must set -webkit-backdrop-filter: none !important (macOS WKWebView pairing)');
      }
    },
  },

  // CG-FLU-15 ← test_rescrape_preview_mobile_stack（rescrape-modal.css @media(max-width:480px)）
  {
    id: 'CG-FLU-15',
    file: 'components/rescrape-modal.css',
    kind: 'fn',
    check(ctx) {
      const ext = extractMobileMediaBody(ctx.text);
      if (ext.err === 'no-media') {
        ctx.fail('CG-FLU-15: no @media (max-width:480px) block found (81c-T7 mobile stack missing)');
        return;
      }
      if (ext.err === 'unbalanced') {
        ctx.fail('CG-FLU-15: unbalanced @media (max-width:480px) block');
        return;
      }
      const mediaBody = ext.body;
      const pm = mediaBody.match(/\.rescrape-preview\s*\{([^}]*)\}/);
      if (!pm) {
        ctx.fail('CG-FLU-15: @media (max-width:480px) must contain a .rescrape-preview rule');
        return;
      }
      if (!/flex-direction\s*:\s*column/.test(pm[1])) {
        ctx.fail('CG-FLU-15: mobile .rescrape-preview must set flex-direction: column (AC-22 stack)');
      }
      const im = mediaBody.match(/\.rescrape-preview\s+\.pv-cover\s+img\s*\{([^}]*)\}/);
      if (!im) {
        ctx.fail('CG-FLU-15: @media (max-width:480px) must contain a .rescrape-preview .pv-cover img rule');
        return;
      }
      const coverDecls = im[1];
      const mw = coverDecls.match(/max-width\s*:\s*([^;]+)/);
      if (!mw) {
        ctx.fail('CG-FLU-15: mobile cover img must set max-width (widen off 38vw)');
        return;
      }
      if (mw[1].includes('38vw')) {
        ctx.fail('CG-FLU-15: mobile cover img max-width must be widened off 38vw (AC-22 cramp culprit)');
      }
      if (!mw[1].includes('100%')) {
        ctx.fail('CG-FLU-15: mobile cover img max-width should be 100% (structural value)');
      }
      if (/#[0-9a-fA-F]{3,8}\b/.test(coverDecls)) {
        ctx.fail('CG-FLU-15: mobile cover img rule must not use a hex color (token-only)');
      }
    },
  },
];

// ── per-file read+parse cache（同檔多 rule 共用，讀一次 → stripCssComments → parseRuleBlocks）──
const fileCache = new Map();
function loadFile(rel) {
  if (fileCache.has(rel)) return fileCache.get(rel);
  const raw = readFileSync(CSS(rel), 'utf-8');
  const text = stripCssComments(raw);
  const entry = { raw, text, blocks: parseRuleBlocks(text) };
  fileCache.set(rel, entry);
  return entry;
}

// ── runner（read-fail try/catch → fail+continue；全 rule 跑完才 exit(1)，i18n_lint 累積器範式）──
for (const rule of RULES) {
  let entry;
  try {
    entry = loadFile(rule.file);
  } catch {
    fail(`${rule.id}: 讀檔失敗 ${rule.file}`);
    continue;
  }
  const ctx = { text: entry.text, raw: entry.raw, blocks: entry.blocks, fail, rel: rule.file };
  KINDS[rule.kind](rule, ctx);
}

if (hadError) process.exit(1);
console.log(`✓ css-guard: ${RULES.length} 條 CSS-block guard 全過`);
