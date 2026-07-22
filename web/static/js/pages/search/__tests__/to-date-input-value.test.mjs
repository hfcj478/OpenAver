// TASK-106-T4 CD-106-4/CD-106-8: toDateInputValue 純函式邊界
//
// toDateInputValue 是 result-card.js 的 module-level 純函式（不依賴 this），
// 直接 import 測試，不需 .call(fakeThis)（同 parse-actors-input.test.mjs 慣例）。
//
// result-card.js 用瀏覽器 importmap 別名 `@/shared/...`（見
// web/templates/base.html:697 `"@/shared/": "/static/js/shared/"`）匯入
// openLocal，plain `node --test` 不認得這個別名，需掛 alias-loader resolve
// hook（同 parse-actors-input.test.mjs 慣例）才能 import 本檔。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;

register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { toDateInputValue } = await import('../state/result-card.js');

test('toDateInputValue: 標準 YYYY-MM-DD → 原樣直通', () => {
  assert.equal(toDateInputValue('2020-01-01'), '2020-01-01');
});

test('toDateInputValue: 空字串 → \'\'', () => {
  assert.equal(toDateInputValue(''), '');
});

test('toDateInputValue: null → \'\'', () => {
  assert.equal(toDateInputValue(null), '');
});

test('toDateInputValue: undefined → \'\'', () => {
  assert.equal(toDateInputValue(undefined), '');
});

test('toDateInputValue: "2020/01/01"（斜線分隔）→ \'\'', () => {
  assert.equal(toDateInputValue('2020/01/01'), '');
});

test('toDateInputValue: "20200101"（無分隔符）→ \'\'', () => {
  assert.equal(toDateInputValue('20200101'), '');
});

test('toDateInputValue: "2020-01-01T00:00:00Z"（帶時間 ISO 8601）→ \'\'', () => {
  assert.equal(toDateInputValue('2020-01-01T00:00:00Z'), '');
});

test('toDateInputValue: "2020年1月1日"（中文日期）→ \'\'', () => {
  assert.equal(toDateInputValue('2020年1月1日'), '');
});

test('toDateInputValue: 前後空白合規格式 " 2020-01-01 " → trim 後直通 "2020-01-01"', () => {
  assert.equal(toDateInputValue(' 2020-01-01 '), '2020-01-01');
});

// Codex PR#115 round3 P2: 日曆合法性 round-trip（格式對但日期不存在需回 ''）

test('toDateInputValue: "2024-02-31"（格式對但日期不存在）→ \'\'', () => {
  assert.equal(toDateInputValue('2024-02-31'), '');
});

test('toDateInputValue: "2021-02-29"（2021 非閏年）→ \'\'', () => {
  assert.equal(toDateInputValue('2021-02-29'), '');
});

test('toDateInputValue: "2020-02-29"（2020 是閏年，須通過）→ 原樣直通', () => {
  assert.equal(toDateInputValue('2020-02-29'), '2020-02-29');
});

test('toDateInputValue: "2020-13-01"（月份超界）→ \'\'', () => {
  assert.equal(toDateInputValue('2020-13-01'), '');
});

test('toDateInputValue: "2020-00-15"（月份為 0）→ \'\'', () => {
  assert.equal(toDateInputValue('2020-00-15'), '');
});

test('toDateInputValue: "0000-00-00" → \'\'', () => {
  assert.equal(toDateInputValue('0000-00-00'), '');
});
