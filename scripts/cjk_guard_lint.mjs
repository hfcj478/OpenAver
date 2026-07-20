#!/usr/bin/env node
/**
 * cjk_guard_lint.mjs — 模板側中文硬編碼守衛（103-T8b 瘦身重寫，取代 852 行 stateful tokenizer）
 *
 * 承 plan-103 CD-1R／CD-12R：JS 側硬編碼中文已改走 eslint AST rule `local/no-cjk-literal`
 * （`eslint.config.mjs`，假陰性不可接受，AST 天然滿足）。本檔**只掃模板**
 * `web/templates` 目錄下所有 `.html`（含子目錄），且刻意做粗（CD-12R「模板側降級為刻意偏向
 * 誤報」）：只剝 `{# #}`／`<!-- -->`／整段跳過 `<script>`／`<style>`，其餘一律報，不做屬性
 * 解析、不做 tag 狀態機。誤報用行內 `{# cjk-exempt(段1|段2|...): 理由 #}` 精確豁免（段落是
 * 該行實際的 CJK 連續段**內容**，依出現順序、可重複，見下方 Codex P1-3 說明；見 §Residual，
 * TASK-103-T8b.md）。
 *
 * fail-closed：掃到 0 個檔案，或掃描目錄讀取失敗，一律 RED（不得靜默通過）。
 *
 * 演進（同一族豁免精確度缺口，逐輪收斂）：
 * - Codex P1-2：原「該行含 cjk-exempt 字樣即跳過整行」放任範圍溢出（同行新增不相干中文仍
 *   GREEN）→ 改宣告「段數」（`cjk-exempt(N)`），逐行比對實際段數與宣告數量。
 * - Codex 複驗：宣告數量比對只走「有 hit 的行」，CJK 被改到剩 0 但宣告還留著時該行永遠不進
 *   入比對 → 補一輪獨立掃描 marker 所在行（即使 0 hit）。
 * - Codex P1-3（本輪，實測複驗屬實且比 Codex 原描述更嚴重）：宣告數量只鎖「段數」不鎖
 *   「內容」——同段數下把被豁免的內容整段換成完全無關的硬編碼中文，甚至整行用途都換掉，
 *   只要段數不變，一樣 GREEN。改宣告**內容**（`cjk-exempt(段1|段2|...)`，`|` 分隔，不可能
 *   出現在 CJK 段內），比對**該行實際 CJK 段序列（依序、含重複）是否與宣告完全相同**。
 *   此法自然涵蓋段數比對（序列長度不同必然不等），故舊的純數量邏輯整個替換，非疊加。
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
const argv2 = process.argv[2];
const ROOT = argv2 && !argv2.startsWith('--') ? resolve(argv2) : join(__dirname, '..');
const TEMPLATES_DIR = join(ROOT, 'web', 'templates');
const CJK_RE = /[一-鿿぀-ヿ㐀-䶿]/;

// ---- 整檔豁免（T8 的真資產，沿用）：owner 已拍板不翻的開發用頁面 + 隨其豁免的資料頁 ----
const EXEMPT_FILES = new Set([
  'web/templates/design-system.html',
  'web/templates/motion_lab.html',
  'web/templates/design_system/gallery-components.html',
  'web/templates/design_system/page-compositions.html',
  'web/templates/design_system/page-states.html',
  'web/templates/design_system/settings-components.html',
]);

let hadError = false;
const err = (msg) => {
  console.error(`✗ cjk_guard_lint: ${msg}`);
  hadError = true;
};

// 粗略掃描：剝 {# #}／<!-- -->／整段跳過 <script>/<style>，其餘一律回報 CJK 字元 offset。
// 不解析屬性、不做 tag 狀態機（CD-12R：模板側失敗方向是「吵」不是「漏」）。
function scanTemplate(text) {
  const n = text.length;
  const hits = [];
  for (let i = 0; i < n; ) {
    if (text.startsWith('{#', i)) {
      const e = text.indexOf('#}', i + 2);
      i = e < 0 ? n : e + 2;
      continue;
    }
    if (text.startsWith('<!--', i)) {
      const e = text.indexOf('-->', i + 4);
      i = e < 0 ? n : e + 3;
      continue;
    }
    if (/^<script(?=[\s>/])/i.test(text.slice(i, i + 8))) {
      const rel = text.slice(i).search(/<\/script>/i);
      i = rel < 0 ? n : i + rel + 9;
      continue;
    }
    if (/^<style(?=[\s>/])/i.test(text.slice(i, i + 7))) {
      const rel = text.slice(i).search(/<\/style>/i);
      i = rel < 0 ? n : i + rel + 8;
      continue;
    }
    if (CJK_RE.test(text[i])) hits.push(i);
    i += 1;
  }
  return hits;
}

function walk(dir, out) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch (e) {
    err(`無法讀取目錄 ${dir}：${e.message}`);
    return;
  }
  for (const e of entries) {
    const full = join(dir, e.name);
    if (e.isDirectory()) walk(full, out);
    else if (extname(e.name).toLowerCase() === '.html') out.push(full);
  }
}

function main() {
  const files = [];
  if (!existsSync(TEMPLATES_DIR)) err(`掃描根目錄不存在：${TEMPLATES_DIR}`);
  else walk(TEMPLATES_DIR, files);

  const toRel = (p) => p.slice(ROOT.length + 1).split('\\').join('/');
  const scanFiles = files.filter((p) => !EXEMPT_FILES.has(toRel(p)));
  if (scanFiles.length === 0) err(`掃到 0 個檔案（掃描根：${TEMPLATES_DIR}），fail-closed 不得靜默視為通過`);

  const violations = [];
  for (const absPath of scanFiles) {
    const relPath = toRel(absPath);
    let text;
    try {
      text = readFileSync(absPath, 'utf8');
    } catch (e) {
      err(`讀取 ${relPath} 失敗：${e.message}`);
      continue;
    }
    // 依「連續 CJK 字元」分段（run），記下每段的**實際文字內容**（非只算數量）並依序歸屬到
    // 所在行——P1-3 比對的是內容序列，不是數量。每行另記第一個 run 的 offset，供定位
    // lineStart/lineEnd 用。
    const runsPerLine = new Map(); // line -> { texts: [...], offset }
    const hits = scanTemplate(text);
    let runStart = null;
    let prevOffset = null;
    const flushRun = () => {
      if (runStart === null) return;
      const line = text.slice(0, runStart).split('\n').length;
      const entry = runsPerLine.get(line) || { texts: [], offset: runStart };
      entry.texts.push(text.slice(runStart, prevOffset + 1));
      runsPerLine.set(line, entry);
    };
    for (const offset of hits) {
      if (runStart === null) runStart = offset;
      else if (offset !== prevOffset + 1) {
        flushRun();
        runStart = offset;
      }
      prevOffset = offset;
    }
    flushRun();

    // 獨立掃一遍全文找出**每一個** marker 所在行（即使該行 0 hit——Codex 複驗發現的缺口：
    // 若只走「有 hit 的行」，CJK 被改到剩 0 但宣告還留著時該行永遠不會進入比對，陳舊宣告
    // 靜默存活）。空括號 `cjk-exempt()` 視為宣告「零段」；同一行出現 ≥2 個 marker 視為語意
    // 不明，fail-closed（不取最後一個/合併等隱性規則）。
    const markersByLine = new Map(); // line -> [{ declared: string[], offset }, ...]
    for (const m of text.matchAll(/cjk-exempt\(([^)]*)\)/g)) {
      const line = text.slice(0, m.index).split('\n').length;
      const declared = m[1] === '' ? [] : m[1].split('|');
      const list = markersByLine.get(line) || [];
      list.push({ declared, offset: m.index });
      markersByLine.set(line, list);
    }

    const allLines = new Set([...runsPerLine.keys(), ...markersByLine.keys()]);
    for (const line of allLines) {
      const actualTexts = runsPerLine.get(line)?.texts ?? [];
      const markers = markersByLine.get(line);
      const offset = runsPerLine.get(line)?.offset ?? markers?.[0].offset;
      const s = text.lastIndexOf('\n', offset - 1) + 1;
      const e = text.indexOf('\n', offset);
      const lineText = text.slice(s, e < 0 ? text.length : e);
      if (!markers) {
        if (actualTexts.length > 0) violations.push({ relPath, line, snippet: lineText.trim() });
        continue;
      }
      if (markers.length > 1) {
        violations.push({ relPath, line, snippet: `本行出現 ${markers.length} 個 cjk-exempt 標記，語意不明請合併成一個：${lineText.trim()}` });
        continue;
      }
      const declared = markers[0].declared;
      const matches = declared.length === actualTexts.length && declared.every((d, idx) => d === actualTexts[idx]);
      if (matches) continue;
      violations.push({
        relPath,
        line,
        snippet: `本行 CJK 內容與豁免宣告不符——宣告=[${declared.join('|')}] 實際=[${actualTexts.join('|')}]：${lineText.trim()}`,
      });
    }
  }

  violations.sort((a, b) => (a.relPath === b.relPath ? a.line - b.line : a.relPath < b.relPath ? -1 : 1));
  for (const v of violations) err(`${v.relPath}:${v.line}  ${v.snippet}`);

  if (hadError) process.exit(1);
  console.log(`✓ cjk_guard_lint: 模板側零殘留硬編碼中文（${scanFiles.length} 檔已掃；${EXEMPT_FILES.size} 檔整檔豁免）`);
}

main();
