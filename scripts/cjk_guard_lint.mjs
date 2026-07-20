#!/usr/bin/env node
/**
 * cjk_guard_lint.mjs — 中文硬編碼守衛（103-T8，zero-dep）
 *
 * 對 `web/static/js/**` + `web/templates/**`（排除 vendor/node_modules/__tests__）做
 * stateful tokenizer 全字面掃描，抓落在字串／樣板字面／HTML 可見文字／JS-bearing 屬性值
 * 內的 CJK 字元，套一份明文分層豁免清單，殘留即 exit(1)。目的：讓 T6/T7 清完的硬編碼中文
 * 不會半年後長回來（spec-103 §1）。
 *
 * 掃描範圍**不含 `scripts/`**（本檔自己的 docblock／豁免註記都是中文，掃自己＝守衛把自己
 * 豁免掉——用「不掃該目錄」實現，不是「掃了再豁免」，見 TASK-103-T8 §H.1／裁決 2）。
 *
 * **不重用 `i18n_lint.mjs` 的 `stripComments()`**（CD-12）：那支是 regex-based，over-strip
 * 是其安全方向；本守衛假陰性不可接受，需要逐字元 stateful tokenizer（見 §G 規格）。
 *
 * 用法：
 *   node scripts/cjk_guard_lint.mjs                 # 掃真 repo
 *   node scripts/cjk_guard_lint.mjs <scratch-root>   # 掃 scratch 副本（供 mutation 自驗）
 *
 * 非 pytest（遵 CLAUDE.md「lint 守衛寫 lint config、不寫 pytest」）。串 `npm run lint`。
 */

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve, extname } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = join(__dirname, '..');

// ---- args：scratch-root 覆蓋（比照 static_guard_lint.mjs/i18n_lint.mjs 房規）----
const argv = process.argv.slice(2);
const rootArg = argv.find((a) => !a.startsWith('--'));
const ROOT = rootArg ? resolve(rootArg) : REPO_ROOT;

// ---- 掃描根（刻意只列這兩個目錄——scripts/ 不在其中，見裁決 2）----
const SCAN_TARGETS = [
  { dir: join(ROOT, 'web', 'static', 'js'), exts: ['.js'] },
  { dir: join(ROOT, 'web', 'templates'), exts: ['.html'] },
];
// 組態自檢：任一掃描根字面含 'scripts' 段即視為配置錯誤（守衛不得掃到自己與姊妹腳本）。
for (const t of SCAN_TARGETS) {
  if (t.dir.split(/[\\/]/).includes('scripts')) {
    throw new Error(
      'cjk_guard_lint: SCAN_TARGETS 意外包含 scripts/ 目錄，違反 TASK-103-T8 裁決 2（守衛不得掃自己）',
    );
  }
}

const CJK_RE = /[一-鿿぀-ヿ㐀-䶿]/;
function isCJK(ch) {
  return CJK_RE.test(ch);
}

let hadError = false;
function err(msg) {
  console.error(`✗ cjk_guard_lint: ${msg}`);
  hadError = true;
}

// ============================================================================
// 豁免清單（明文、可審，逐條 [cjk-exempt: 理由] 註記 — plan-103 §1.2）
// ============================================================================

// ---- EXEMPT_FILES（整檔豁免，§H.1）----
const EXEMPT_FILES = [
  'web/templates/design-system.html', // [cjk-exempt: 開發用頁面，owner 已拍板不翻 — spec-103 §3.1]
  'web/templates/motion_lab.html', // [cjk-exempt: 同上]
  'web/templates/design_system/gallery-components.html', // [cjk-exempt: 同上]
  'web/templates/design_system/page-compositions.html', // [cjk-exempt: 同上]
  'web/templates/design_system/page-states.html', // [cjk-exempt: 同上]
  'web/templates/design_system/settings-components.html', // [cjk-exempt: 同上]
  'web/static/js/pages/motion-lab.js', // [cjk-exempt: 餵 motion_lab.html 資料的 JS，spec §3.1 點名隨模板一併豁免]
  'web/static/js/pages/motion-lab-state.js', // [cjk-exempt: 同上]
  'web/static/js/pages/motion-lab/constellation-host.js', // [cjk-exempt: 同上；修正 spec/plan 誤植的 shared/constellation/ 路徑 — TASK-103-T8 §H.1]
];

// ---- EXEMPT_RANGES（檔內具名區塊，start anchor + end 判定，§H.2）----
const EXEMPT_RANGES = [
  {
    file: 'web/static/js/pages/search/file.js',
    startAnchor: /const chinesePatterns = \['中文字幕', '字幕', '中字', '\[中字\]', '【中字】'\];/,
    endMode: 'same-line',
    note: "[cjk-exempt: TEMPORARY — checkSubtitle() 內字幕比對常數，非 UI copy；T5 刪除 checkSubtitle 時必須移除本條，否則 anchor 缺席會 fail-closed RED，見 TASK-103-T8 §J]",
  },
  {
    file: 'web/static/js/pages/search/file.js',
    startAnchor: /const _SUBTITLE_BRACKETS = \['\[中文字幕\]', '【中文字幕】', '\[中字\]', '【中字】'\];/,
    endMode: 'same-line',
    note: '[cjk-exempt: stripSubtitleMarkers 用字幕標記比對資料，非 UI copy，現役路徑（file-list.js:357）]',
  },
  {
    file: 'web/static/js/pages/search/file.js',
    startAnchor: /const _SUBTITLE_TEXT_MARKERS = \['中文字幕', '中字', '字幕'\];/,
    endMode: 'same-line',
    note: '[cjk-exempt: stripSubtitleMarkers 用字幕標記比對資料，非 UI copy，現役路徑（file-list.js:357）]',
  },
  {
    file: 'web/static/js/pages/settings/state-config.js',
    startAnchor: /FOLDER_PREVIEW_DATA:\s*\{/,
    endMode: 'brace-balance',
    note: '[cjk-exempt: 資料夾命名範本預覽樣例，非 UI copy — spec-103 §3.1]',
  },
  {
    file: 'web/templates/settings.html',
    startAnchor: /x-text="\{'zh-TW':'繁','zh-CN':'简','ja':'あ','en':'EN'\}\[locale\]/,
    endMode: 'same-line',
    note: '[cjk-exempt: 語言切換器原生字形（繁/简/あ/EN），全球化 UI 慣例不隨介面語言翻譯 — TASK-103-T7 §F.2]',
  },
  {
    file: 'web/templates/help.html',
    startAnchor: /<pre class="bg-base-200 rounded-lg p-3 text-sm overflow-x-auto"><code>ABC-123\//,
    endMode: 'end-anchor',
    endAnchor: /<\/code><\/pre>/,
    note: '[cjk-exempt: 檔名命名慣例真實範例，非 UI copy — TASK-103-T7 §F.3]',
  },
  {
    file: 'web/templates/help.html',
    startAnchor: /<tr><th>\{\{ t\('help\.format\.col_var'\) \}\}<\/th>/,
    endMode: 'end-anchor',
    endAnchor: /<\/tbody>/,
    note: '[cjk-exempt: 格式變數對照表範例值（真實藝名/範例標題），非 UI copy — TASK-103-T7 §F.3；anchor 錨在表頭列非 <tbody>（<tbody> 全檔 4 次不唯一）— TASK-103-T8 §H.2]',
  },
];

// ---- EXEMPT_PATTERNS（行型態／結構型態，§H.3；由 tokenizer 內建機制判定，非逐行 regex）----
const EXEMPT_PATTERNS = {
  consoleCall: {
    calleeRe: /^console$/,
    note: '[cjk-exempt: console.* 診斷輸出，非 UI copy — CD-3]',
  },
  // 左邊界 lookbehind（BLOCKER 2 修正）：無此界線時任何以 window.t 結尾的成員存取
  // （如 `foo.window.t ? window.t('k') : '偽裝中文'`）都會被誤判成合法 fallback、
  // 讓其後字串的 CJK 靜默放行——方向是假陰性，CD-12 明文不可接受。
  windowTFallbackRe:
    /(?<![A-Za-z0-9_$.])window\.t\s*\?\s*window\.t\(\s*'[a-zA-Z0-9_.]+'\s*\)\s*:\s*'[^']*'/g,
  // [cjk-exempt: window.t() 防禦性 fallback，已是 i18n 路徑 — TASK-103-T7 §B]
};

function calleeObjectPart(identBuf) {
  const lastDot = identBuf.lastIndexOf('.');
  if (lastDot === -1) return null;
  return identBuf.slice(0, lastDot);
}
function isConsoleCallee(calleeObj) {
  if (calleeObj == null) return false;
  return EXEMPT_PATTERNS.consoleCall.calleeRe.test(calleeObj);
}

function computeWindowTFallbackSkip(text) {
  const intervals = [];
  const re = new RegExp(EXEMPT_PATTERNS.windowTFallbackRe.source, 'g');
  let m;
  while ((m = re.exec(text)) !== null) {
    intervals.push([m.index, m.index + m[0].length]);
    if (m[0].length === 0) re.lastIndex += 1;
  }
  return intervals;
}
function inSkipIntervals(intervals, idx) {
  for (const [s, e] of intervals) {
    if (idx >= s && idx < e) return true;
  }
  return false;
}

// ============================================================================
// §G.3 正則字面量辨識——逐字元找對應的非跳脫 `/`，字元類 `[...]` 內的 `/` 不算結束
// ============================================================================
function scanRegexLiteral(text, start) {
  const n = text.length;
  let i = start + 1; // 跳過開頭 '/'
  let inClass = false;
  let closed = false;
  while (i < n) {
    const ch = text[i];
    if (ch === '\n') break; // 未閉合，放棄正則解析
    if (ch === '\\') {
      i += 2;
      continue;
    }
    if (inClass) {
      if (ch === ']') inClass = false;
      i += 1;
      continue;
    }
    if (ch === '[') {
      inClass = true;
      i += 1;
      continue;
    }
    if (ch === '/') {
      i += 1;
      closed = true;
      break;
    }
    i += 1;
  }
  if (!closed) return -1;
  while (i < n && /[a-zA-Z]/.test(text[i])) i += 1;
  return i;
}

// \uXXXX／\u{X...}／\xXX escape 解碼（BLOCKER 3 修正）：tokenizer 原本只看原始碼字面
// codepoint，`"中文"` 這種 escape 寫法的中文完全繞過偵測（CD-12「假陰性不可
// 接受」明文禁止）。回傳 { length, isCjk } 或 null（非合法 escape，回退成一般跳脫消耗）。
// `\x` 兩位 hex 最大只到 0xFF，數學上不可能編碼到任何 CJK range（最低 0x3040），仍一併
// 解碼是為了在同一個判斷點堵住所有 escape 向量、不留只堵一半的印象。
function tryDecodeEscape(text, i) {
  const kind = text[i + 1];
  if (kind === 'u') {
    if (text[i + 2] === '{') {
      const closeIdx = text.indexOf('}', i + 3);
      if (closeIdx === -1) return null;
      const hex = text.slice(i + 3, closeIdx);
      if (!/^[0-9a-fA-F]{1,6}$/.test(hex)) return null;
      const codepoint = parseInt(hex, 16);
      if (codepoint > 0x10ffff) return null;
      return { length: closeIdx + 1 - i, isCjk: isCJK(String.fromCodePoint(codepoint)) };
    }
    const hex = text.slice(i + 2, i + 6);
    if (!/^[0-9a-fA-F]{4}$/.test(hex)) return null;
    return { length: 6, isCjk: isCJK(String.fromCharCode(parseInt(hex, 16))) };
  }
  if (kind === 'x') {
    const hex = text.slice(i + 2, i + 4);
    if (!/^[0-9a-fA-F]{2}$/.test(hex)) return null;
    return { length: 4, isCjk: isCJK(String.fromCharCode(parseInt(hex, 16))) };
  }
  return null;
}

// ============================================================================
// tokenizeJS — §G.1 逐字元 stateful 掃描（CODE/LINE_COMMENT/BLOCK_COMMENT/STRING/TEMPLATE）
// 回傳 hit 陣列：{ offset, exempt: 'console' | null }（offset 相對於傳入 text 的 baseOffset）
// ============================================================================
export function tokenizeJS(text, opts = {}) {
  const baseOffset = opts.baseOffset || 0;
  const skipIntervals = computeWindowTFallbackSkip(text);
  const hits = [];

  let runStart = -1;
  const callStack = []; // { calleeObj: string|null }
  function flushRun() {
    if (runStart !== -1) {
      const top = callStack[callStack.length - 1];
      const exempt = top && isConsoleCallee(top.calleeObj) ? 'console' : null;
      hits.push({ offset: baseOffset + runStart, exempt });
      runStart = -1;
    }
  }
  // cjk 由呼叫端算好傳入（原始字元用 isCJK(ch)，escape 序列用 tryDecodeEscape 的結果）——
  // 兩種來源共用同一條 run-合併／flush 邏輯，讓 "中文" 這種混合寫法自然併成一個 hit。
  function feed(idx, cjk) {
    if (!inSkipIntervals(skipIntervals, idx) && cjk) {
      if (runStart === -1) runStart = idx;
    } else if (runStart !== -1) {
      flushRun();
    }
  }

  // 顯式 stack（非單一旗標）——TEMPLATE 內 `${` 推回 CODE，CODE 內再遇反引號推新 TEMPLATE，
  // 支援巢狀樣板字面（plan §1.1）。outer CODE frame 無 braceDepth，永不因 `}` 被 pop。
  const stack = [{ type: 'CODE' }];
  let identBuf = '';
  let lastMeaningfulChar = '';
  let i = 0;
  const n = text.length;

  while (i < n) {
    const top = stack[stack.length - 1];
    const ch = text[i];

    if (top.type === 'LINE_COMMENT') {
      if (ch === '\n') stack.pop();
      i += 1;
      continue;
    }
    if (top.type === 'BLOCK_COMMENT') {
      if (ch === '*' && text[i + 1] === '/') {
        stack.pop();
        i += 2;
        continue;
      }
      i += 1;
      continue;
    }
    if (top.type === 'STRING') {
      if (ch === '\\') {
        const esc = tryDecodeEscape(text, i);
        if (esc) {
          feed(i, esc.isCjk);
          i += esc.length;
          continue;
        }
        i += 2;
        continue;
      }
      if (ch === top.quote) {
        flushRun();
        stack.pop();
        i += 1;
        continue;
      }
      feed(i, isCJK(ch));
      i += 1;
      continue;
    }
    if (top.type === 'TEMPLATE') {
      if (ch === '\\') {
        const esc = tryDecodeEscape(text, i);
        if (esc) {
          feed(i, esc.isCjk);
          i += esc.length;
          continue;
        }
        i += 2;
        continue;
      }
      if (ch === '`') {
        flushRun();
        stack.pop();
        i += 1;
        continue;
      }
      if (ch === '$' && text[i + 1] === '{') {
        flushRun();
        stack.push({ type: 'CODE', braceDepth: 1 });
        i += 2;
        continue;
      }
      feed(i, isCJK(ch));
      i += 1;
      continue;
    }

    // top.type === 'CODE'
    if (ch === '/' && text[i + 1] === '/') {
      stack.push({ type: 'LINE_COMMENT' });
      i += 2;
      identBuf = '';
      lastMeaningfulChar = '';
      continue;
    }
    if (ch === '/' && text[i + 1] === '*') {
      stack.push({ type: 'BLOCK_COMMENT' });
      i += 2;
      continue;
    }
    if (ch === "'" || ch === '"') {
      stack.push({ type: 'STRING', quote: ch });
      i += 1;
      identBuf = '';
      lastMeaningfulChar = '';
      continue;
    }
    if (ch === '`') {
      stack.push({ type: 'TEMPLATE' });
      i += 1;
      identBuf = '';
      lastMeaningfulChar = '';
      continue;
    }
    if (ch === '/') {
      // §G.3：上一個有意義字元是 )/]/alnum → 除號；否則嘗試解析正則字面量
      const isDivide = /[)\]]/.test(lastMeaningfulChar) || /[A-Za-z0-9_$]/.test(lastMeaningfulChar);
      if (!isDivide) {
        const end = scanRegexLiteral(text, i);
        if (end !== -1) {
          i = end;
          lastMeaningfulChar = '/';
          identBuf = '';
          continue;
        }
      }
      lastMeaningfulChar = '/';
      identBuf = '';
      i += 1;
      continue;
    }
    if (ch === '{') {
      if (Object.prototype.hasOwnProperty.call(top, 'braceDepth')) top.braceDepth += 1;
      lastMeaningfulChar = '{';
      identBuf = '';
      i += 1;
      continue;
    }
    if (ch === '}') {
      if (Object.prototype.hasOwnProperty.call(top, 'braceDepth')) {
        top.braceDepth -= 1;
        if (top.braceDepth === 0) {
          stack.pop();
          lastMeaningfulChar = '}';
          identBuf = '';
          i += 1;
          continue;
        }
      }
      lastMeaningfulChar = '}';
      identBuf = '';
      i += 1;
      continue;
    }
    if (ch === '(') {
      callStack.push({ calleeObj: calleeObjectPart(identBuf) });
      identBuf = '';
      lastMeaningfulChar = '(';
      i += 1;
      continue;
    }
    if (ch === ')') {
      if (callStack.length) callStack.pop();
      identBuf = '';
      lastMeaningfulChar = ')';
      i += 1;
      continue;
    }
    if (/[A-Za-z0-9_$]/.test(ch)) {
      identBuf += ch;
      lastMeaningfulChar = ch;
      i += 1;
      continue;
    }
    if (ch === '.') {
      identBuf += ch;
      lastMeaningfulChar = ch;
      i += 1;
      continue;
    }
    if (/\s/.test(ch)) {
      // 空白：跳過但不重置 identBuf/lastMeaningfulChar（容忍 `console . warn (` 這種寫法）
      i += 1;
      continue;
    }
    // 其餘標點：重置
    identBuf = '';
    lastMeaningfulChar = ch;
    i += 1;
  }
  flushRun();
  return hits;
}

// ============================================================================
// tokenizeHTML — §G.2 逐字元掃描（TEXT/TAG/HTML_COMMENT/JINJA_COMMENT/SCRIPT/STYLE）
// 用「往前看固定前綴字串」判斷子狀態（比通用狀態機更貼近實測有效的簡化設計，§G.2）。
// ============================================================================

// 大小寫不敏感的字面搜尋（BLOCKER 1 修正）：開標籤偵測有 .toLowerCase()，但關標籤搜尋
// 原本用 text.indexOf('</script>') 沒有——`<SCRIPT>...</SCRIPT>` 會讓關標籤找不到，
// 導致整個檔案剩餘部分被吞成 script 內容、後面所有 CJK 全部隱形（獨立 reviewer 對抗性審查
// BLOCKER 1）。用 regex 'gi' 搜尋而非 text.toLowerCase() 整檔轉換，避免罕見 Unicode 大小寫
// 折疊改變字串長度導致 index 位移的風險。
function indexOfCI(text, needle, fromIndex) {
  const escaped = needle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const re = new RegExp(escaped, 'gi');
  re.lastIndex = fromIndex;
  const m = re.exec(text);
  return m ? m.index : -1;
}

const JS_BEARING_ATTR_RE = /^(x-[\w:.-]+|@[\w:.-]+|:[\w-]+)$/i;
// hasIndices（'d' flag）取得每個 capture group 的絕對 offset，供屬性值精確定位（Node 16+）。
const ATTR_RE = /([a-zA-Z_:@][-\w:.@]*)\s*=\s*("|')((?:(?!\2)[\s\S])*)\2/gsd;

function scanPlainTextRun(text, start, end, baseOffset, hits) {
  let runStart = -1;
  const flush = (idx) => {
    if (runStart !== -1) {
      hits.push({ offset: baseOffset + runStart, exempt: null });
      runStart = -1;
    }
  };
  for (let i = start; i < end; i += 1) {
    if (isCJK(text[i])) {
      if (runStart === -1) runStart = i;
    } else {
      flush(i);
    }
  }
  flush(end);
}

function parseTagAttributes(tagText, tagAbsStart, hits) {
  ATTR_RE.lastIndex = 0;
  let m;
  while ((m = ATTR_RE.exec(tagText)) !== null) {
    const name = m[1];
    const valueSpan = m.indices[3]; // [start, end) within tagText
    const value = m[3];
    const valueAbsStart = tagAbsStart + valueSpan[0];
    if (JS_BEARING_ATTR_RE.test(name)) {
      const subHits = tokenizeJS(value, { baseOffset: valueAbsStart });
      hits.push(...subHits);
    } else {
      scanPlainTextRun(value, 0, value.length, valueAbsStart, hits);
    }
  }
}

export function tokenizeHTML(text, opts = {}) {
  const baseOffset = opts.baseOffset || 0;
  const hits = [];
  const n = text.length;
  let i = 0;
  let textRunStart = -1;

  function flushTextRun(idx) {
    if (textRunStart !== -1) {
      hits.push({ offset: baseOffset + textRunStart, exempt: null });
      textRunStart = -1;
    }
  }

  while (i < n) {
    if (text.startsWith('{#', i)) {
      flushTextRun(i);
      const end = text.indexOf('#}', i + 2);
      i = end === -1 ? n : end + 2;
      continue;
    }
    if (text.startsWith('<!--', i)) {
      flushTextRun(i);
      const end = text.indexOf('-->', i + 4);
      i = end === -1 ? n : end + 3;
      continue;
    }
    const isScriptOpen =
      text.slice(i, i + 7).toLowerCase() === '<script' && /[\s>]/.test(text[i + 7] || '>');
    if (isScriptOpen) {
      flushTextRun(i);
      const tagEnd = text.indexOf('>', i);
      if (tagEnd === -1) {
        i = n;
        continue;
      }
      const openTag = text.slice(i, tagEnd + 1);
      // 屬性名比對也要大小寫不敏感（`SRC="x.js"` 若漏判會被誤當內聯 script 掃描其 body）——
      // 自我攻擊複查時發現的第二個大小寫不對稱點，一併修正。
      // 邊界另一個坑（自我攻擊追加發現，非獨立 reviewer 原始 3 條 BLOCKER 之一）：`\b` word
      // boundary 在 `-` 前後也成立，`\bsrc\s*=` 會誤配 `data-src="..."` 這種屬性名（真實存在
      // 於 lazy-load 慣例，雖本庫模板目前無此寫法）——一旦誤配，hasSrc 會被誤判 true，把一個
      // 「其實沒有真正 src=」的內聯 script 當成外部腳本、跳過其 body 掃描，方向是假陰性
      // （CD-12 不可接受，比原本的 hasSrc 大小寫問題更嚴重）。改用 `(?:^|\s)src\s*=`
      // 要求 src 前必須是字串開頭或空白，不能是連字號等其他屬性名字元。
      const hasSrc = /(?:^|\s)src\s*=/i.test(openTag);
      const bodyStart = tagEnd + 1;
      const closeIdx = indexOfCI(text, '</script>', bodyStart);
      const bodyEnd = closeIdx === -1 ? n : closeIdx;
      if (!hasSrc) {
        const body = text.slice(bodyStart, bodyEnd);
        const subHits = tokenizeJS(body, { baseOffset: baseOffset + bodyStart });
        hits.push(...subHits);
      }
      i = closeIdx === -1 ? n : closeIdx + '</script>'.length;
      continue;
    }
    const isStyleOpen =
      text.slice(i, i + 6).toLowerCase() === '<style' && /[\s>]/.test(text[i + 6] || '>');
    if (isStyleOpen) {
      flushTextRun(i);
      const tagEnd = text.indexOf('>', i);
      if (tagEnd === -1) {
        i = n;
        continue;
      }
      const closeIdx = indexOfCI(text, '</style>', tagEnd + 1);
      i = closeIdx === -1 ? n : closeIdx + '</style>'.length;
      continue;
    }
    if (text[i] === '<' && /[a-zA-Z/]/.test(text[i + 1] || '')) {
      flushTextRun(i);
      // 逐字元找對應 '>'，跳過屬性值內的 '>'（簡易 quote-tracking）
      let j = i + 1;
      let inQuote = null;
      while (j < n) {
        const c = text[j];
        if (inQuote) {
          if (c === inQuote) inQuote = null;
        } else if (c === '"' || c === "'") {
          inQuote = c;
        } else if (c === '>') {
          break;
        }
        j += 1;
      }
      const tagEnd = j; // index of '>'（或 n，未閉合）
      const tagText = text.slice(i, Math.min(tagEnd + 1, n));
      parseTagAttributes(tagText, baseOffset + i, hits);
      i = tagEnd + 1;
      continue;
    }
    // 預設 TEXT：CJK 即回報（含 {{ }}/{% %} 內容，§G.2 規則 6 — 保留 fail-safe 掃描能力）
    if (isCJK(text[i])) {
      if (textRunStart === -1) textRunStart = i;
    } else {
      flushTextRun(i);
    }
    i += 1;
  }
  flushTextRun(n);
  return hits;
}

// ============================================================================
// walk() — 比照 i18n_lint.mjs 簽章，排除 __tests__/vendor/node_modules
// ============================================================================
function walk(dir, exts, out) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    if (e.name === '__tests__' || e.name === 'vendor' || e.name === 'node_modules') continue;
    const full = join(dir, e.name);
    if (e.isDirectory()) {
      walk(full, exts, out);
      // BUG 5 修正（獨立 reviewer sibling 掃描）：node:path 的 extname() 保留原始大小寫，
      // `exts` 只列小寫（'.js'/'.html'）。CI 跑在 ubuntu-latest（case-sensitive 檔案系統），
      // `Probe.JS`/`Foo.Html` 這種大寫或混合大小寫副檔名的檔案會被 exts.includes() 判 false，
      // 整個檔案連 files 清單都進不去——不是「掃了漏判」，是「守衛眼中這檔案不存在」，
      // 比前 3 個 BLOCKER 更嚴重的假陰性。.toLowerCase() 後再比對（呼應 main() dispatch 那處
      // 同源修正，兩處必須一起改，否則檔案進了清單卻被送去錯的 tokenizer，見下方 main()）。
    } else if (exts.includes(extname(e.name).toLowerCase())) {
      out.push(full);
    }
  }
}

// ============================================================================
// EXEMPT_RANGES 範圍求解——same-line / brace-balance / end-anchor（§H.2）
// ============================================================================
function resolveSameLine(text, matchIndex) {
  const start = text.lastIndexOf('\n', matchIndex - 1) + 1;
  let end = text.indexOf('\n', matchIndex);
  if (end === -1) end = text.length;
  return [start, end];
}

// JS 語法感知 brace-balance：string/template-aware，避免字串/樣板字面內的 {/} 誤計
// （§H.2 note：不可裸字元 indexOf 計數）。
function findBalancedBraceEnd(text, openIdx) {
  const n = text.length;
  let depth = 0;
  let i = openIdx;
  let inStr = null;
  let inTemplate = false;
  while (i < n) {
    const ch = text[i];
    if (inStr) {
      if (ch === '\\') {
        i += 2;
        continue;
      }
      if (ch === inStr) inStr = null;
      i += 1;
      continue;
    }
    if (inTemplate) {
      if (ch === '\\') {
        i += 2;
        continue;
      }
      if (ch === '`') inTemplate = false;
      i += 1;
      continue;
    }
    if (ch === "'" || ch === '"') {
      inStr = ch;
      i += 1;
      continue;
    }
    if (ch === '`') {
      inTemplate = true;
      i += 1;
      continue;
    }
    if (ch === '{') {
      depth += 1;
      i += 1;
      continue;
    }
    if (ch === '}') {
      depth -= 1;
      i += 1;
      if (depth === 0) return i; // exclusive end
      continue;
    }
    i += 1;
  }
  return -1;
}
function resolveBraceBalance(text, matchIndex, matchLength) {
  let idx = matchIndex + matchLength - 1;
  if (text[idx] !== '{') {
    idx = text.indexOf('{', matchIndex);
    if (idx === -1) return null;
  }
  const end = findBalancedBraceEnd(text, idx);
  if (end === -1) return null;
  return [matchIndex, end];
}

function resolveEndAnchor(text, matchIndex, matchLength, endAnchorRe) {
  const searchFrom = matchIndex + matchLength;
  const re = new RegExp(endAnchorRe.source, endAnchorRe.flags.includes('g') ? endAnchorRe.flags : `${endAnchorRe.flags}g`);
  re.lastIndex = searchFrom;
  const m = re.exec(text);
  if (!m) return null;
  return [matchIndex, m.index + m[0].length];
}

function withG(re) {
  return new RegExp(re.source, re.flags.includes('g') ? re.flags : `${re.flags}g`);
}

// ============================================================================
// 行號計算——逐字元累計 `\n` 位置一次性建索引，之後 O(log n) 查詢（不用 split('\n')，CD-3）
// ============================================================================
function buildLineIndex(text) {
  const newlines = [];
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === '\n') newlines.push(i);
  }
  return newlines;
}
function offsetToLine(newlines, offset) {
  let lo = 0;
  let hi = newlines.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (newlines[mid] < offset) lo = mid + 1;
    else hi = mid;
  }
  return lo + 1;
}

// ============================================================================
// main()
// ============================================================================
function main() {
  const files = [];
  for (const t of SCAN_TARGETS) walk(t.dir, t.exts, files);

  const exemptFileSet = new Set(EXEMPT_FILES);
  const toRel = (absPath) => absPath.slice(ROOT.length + 1).split('\\').join('/');
  const scanFiles = files
    .map((absPath) => ({ absPath, relPath: toRel(absPath) }))
    .filter(({ relPath }) => !exemptFileSet.has(relPath));

  const textCache = new Map();
  const readCached = (relPath, absPath) => {
    let text = textCache.get(relPath);
    if (text === undefined) {
      text = readFileSync(absPath, 'utf8');
      textCache.set(relPath, text);
    }
    return text;
  };

  // ---- EXEMPT_RANGES pre-flight：anchor 必須恰 1 次命中，否則 fail-closed RED ----
  const rangesByFile = new Map();
  for (const entry of EXEMPT_RANGES) {
    const known = scanFiles.find((f) => f.relPath === entry.file);
    const absPath = known ? known.absPath : join(ROOT, entry.file);
    if (!existsSync(absPath)) {
      err(`EXEMPT_RANGES [${entry.file}] anchor pre-flight 失敗：檔案不存在 — ${entry.note}`);
      continue;
    }
    const text = readCached(entry.file, absPath);
    const re = withG(entry.startAnchor);
    const matches = [...text.matchAll(re)];
    if (matches.length === 0) {
      err(`EXEMPT_RANGES [${entry.file}] anchor 消失（0 次命中，內容可能已被改名/刪除）— ${entry.note}`);
      continue;
    }
    if (matches.length >= 2) {
      err(`EXEMPT_RANGES [${entry.file}] anchor 歧義（${matches.length} 次命中，須恰為 1）— ${entry.note}`);
      continue;
    }
    const m = matches[0];
    let range = null;
    if (entry.endMode === 'same-line') range = resolveSameLine(text, m.index);
    else if (entry.endMode === 'brace-balance') range = resolveBraceBalance(text, m.index, m[0].length);
    else if (entry.endMode === 'end-anchor') range = resolveEndAnchor(text, m.index, m[0].length, entry.endAnchor);
    if (!range) {
      err(`EXEMPT_RANGES [${entry.file}] 範圍解析失敗（endMode=${entry.endMode}，anchor 命中但 end 判定失敗）— ${entry.note}`);
      continue;
    }
    if (!rangesByFile.has(entry.file)) rangesByFile.set(entry.file, []);
    rangesByFile.get(entry.file).push(range);
  }

  // ---- 逐檔 tokenize + 套豁免 ----
  const violations = [];
  const seen = new Set();
  for (const { absPath, relPath } of scanFiles) {
    let text;
    try {
      text = readCached(relPath, absPath);
    } catch (e) {
      err(`讀取 ${relPath} 失敗：${e.message}`);
      continue;
    }
    // BUG 5 修正（同上 walk() 那處）：大小寫不 lower 的話，一個大小寫混合副檔名的檔案就算
    // 僥倖被 walk() 收進清單，也會在這裡因為 ext === '.html' 比對失敗而被送去錯的 tokenizer
    // （HTML 當純 JS CODE 狀態掃、標籤/屬性語法完全不解析，實務上等同零偵測）。
    const ext = extname(absPath).toLowerCase();
    let rawHits;
    try {
      rawHits = ext === '.html' ? tokenizeHTML(text) : tokenizeJS(text);
    } catch (e) {
      err(`解析 ${relPath} 時發生例外（tokenizer bug 或編碼問題，視為 RED 不靜默跳過）：${e.stack || e.message}`);
      continue;
    }
    const ranges = rangesByFile.get(relPath) || [];
    const newlineIdx = buildLineIndex(text);
    for (const hit of rawHits) {
      if (hit.exempt === 'console') continue;
      if (ranges.some(([s, e]) => hit.offset >= s && hit.offset < e)) continue;
      const line = offsetToLine(newlineIdx, hit.offset);
      const key = `${relPath}:${line}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const lineStart = line === 1 ? 0 : newlineIdx[line - 2] + 1;
      const lineEnd = newlineIdx[line - 1] !== undefined ? newlineIdx[line - 1] : text.length;
      violations.push({ relPath, line, snippet: text.slice(lineStart, lineEnd).trim() });
    }
  }

  violations.sort((a, b) => (a.relPath === b.relPath ? a.line - b.line : a.relPath < b.relPath ? -1 : 1));
  for (const v of violations) {
    err(`${v.relPath}:${v.line}  ${v.snippet}`);
  }

  if (hadError) {
    process.exit(1);
  }
  console.log(
    `✓ cjk_guard_lint: 全庫零殘留硬編碼中文（${scanFiles.length} 檔已掃；` +
      `${EXEMPT_FILES.length} 檔整檔豁免；${EXEMPT_RANGES.length} 條區塊豁免生效）`,
  );
}

// entry-point guard：直接執行才跑 main()，被 import（node:test）時不觸發（T8 是第一支需要此
// guard 的 lint 腳本——tokenizeJS/tokenizeHTML 需可被測試檔 import，見 TASK-103-T8 修改範圍表）。
if (import.meta.url === `file://${process.argv[1]}`) {
  main();
}

export { EXEMPT_FILES, EXEMPT_RANGES, EXEMPT_PATTERNS, SCAN_TARGETS };
