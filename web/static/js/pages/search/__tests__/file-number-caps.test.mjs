// TASK-caps: 番號字母 cap 對齊守衛（5/6 → 7），修復 7 字母前綴（PARATHD）
// 被 re.search-like 滑窗截斷掉首字的 bug + 前端「手動輸入番號」逃生口（CD-5）。
//
// file.js 是 classic script（掛到 window.SearchFile），非 ES module——
// stub window 後動態 import 觸發頂層副作用（見 TASK-caps.md「前端 node:test 選擇理由」）。
// 對 production 原始碼零侵入：只改 regex cap 本身，不改匯出方式。

import { test } from 'node:test';
import assert from 'node:assert/strict';

globalThis.window = globalThis;
await import('../file.js');
const { extractNumber, formatNumber, extractChineseTitle } = globalThis.window.SearchFile;

// === 必須新 PASS：formatNumber 逃生口（CD-5）===

test('formatNumber: 7 字母前綴逃生口不再截斷（帶 hyphen）', () => {
  assert.equal(formatNumber('PARATHD-02976'), 'PARATHD-02976');
});

test('formatNumber: 7 字母前綴逃生口不再截斷（無 hyphen 手動輸入）', () => {
  assert.equal(formatNumber('parathd02976'), 'PARATHD-02976');
});

// === 必須新 PASS：extractNumber fallback 對 7 字母不再回 null ===

test('extractNumber: parathd-02976.mp4 → PARATHD-02976（帶 hyphen，小寫）', () => {
  assert.equal(extractNumber('parathd-02976.mp4'), 'PARATHD-02976');
});

test('extractNumber: PARATHD-02976.mp4 → PARATHD-02976（已大寫）', () => {
  assert.equal(extractNumber('PARATHD-02976.mp4'), 'PARATHD-02976');
});

test('extractNumber: abcdefg-123.mp4 → ABCDEFG-123（合成 7 字母前綴，比照後端）', () => {
  assert.equal(extractNumber('abcdefg-123.mp4'), 'ABCDEFG-123');
});

// === 必須新 PASS：extractChineseTitle 不殘留 7 字母番號碎片 ===

test('extractChineseTitle: 7 字母番號靠通用 cleanup 完整剝除（number 不匹配）', () => {
  // number=ABC-999 故意不匹配 PARATHD-02976 → 必須靠 file.js:115 的通用 {2,7} regex 剝除。
  // 若 number 傳 'PARATHD-02976'，exact-number 移除（file.js:112-114）會先吃掉它，
  // 就算 :115 回歸到 {2,6} 也照樣 green —— cap 未被鎖。故意用不匹配的 number。
  // cap={2,7} → '純中文標題'；cap={2,6}（回歸）→ 只吃 'ARATHD-02976'、殘留首字 'P' → 'P純中文標題'。
  const result = extractChineseTitle('PARATHD-02976 純中文標題.mp4', 'ABC-999');
  assert.equal(result, '純中文標題');
});

// === Collision guard：既有格式不受 cap 加寬影響（mutation 驗證用回歸錨點）===

test('extractNumber: FC2-PPV 優先序不受寬度影響', () => {
  assert.equal(extractNumber('FC2-PPV-1234567.mp4'), 'FC2-PPV-1234567');
});

test('extractNumber: SONE-205.mp4 不變', () => {
  assert.equal(extractNumber('SONE-205.mp4'), 'SONE-205');
});

test('extractNumber: T28-103.mp4 混合格式（index 1）不變', () => {
  assert.equal(extractNumber('T28-103.mp4'), 'T28-103');
});

test('formatNumber: ABC-123 不變', () => {
  assert.equal(formatNumber('ABC-123'), 'ABC-123');
});

test('formatNumber: guard clause — null/空字串仍回 null（不受 cap 寬度影響）', () => {
  assert.equal(formatNumber(null), null);
  assert.equal(formatNumber(''), null);
});
