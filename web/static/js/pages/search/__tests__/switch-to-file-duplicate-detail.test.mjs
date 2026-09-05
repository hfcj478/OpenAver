// Codex PR#181 五審 P3：第一筆是「重複」時，右邊詳細區不可跳「查無結果」
//
// 使用者流程：你把一批檔案拖進搜尋頁，第一部之前整理過（目標位置已有同名檔）→
// 清單那一列是橘色「重複」標記，右邊詳細區卻寫「找不到 XXX 的資料」——兩句話互相打架，
// 使用者會以為番號查不到、跑去手動改番號。純顯示層，不影響任何寫入。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchStateFileList } from '../state/file-list.js';
import { searchStateBase } from '../state/base.js';

globalThis.window = globalThis;
// t() 回 key 本身，斷言分辨的是「走了哪一個分支」而不是文案內容
globalThis.window.t = (k) => k;

function makeFakeThis(file) {
  return Object.assign(
    {},
    searchStateBase(),
    searchStateFileList(),
    {
      fileList: [file],
      currentFileIndex: 0,
      listMode: 'file',
      _resetCoverState() {},
      searchForFile: async () => {},
    },
  );
}

test('switchToFile: skipReason=duplicate 的檔走「重複」文案，不走通用查無結果', async () => {
  const fakeThis = makeFakeThis({
    path: '/a/ABC-123.mp4',
    filename: 'ABC-123.mp4',
    number: 'ABC-123',
    searched: true,          // T6 把記憶命中的檔標成已搜尋
    searchResults: [],       // 但沒有結果 ⇒ 會落進通用 else 分支
    skipReason: 'duplicate',
    scrapeStatus: 'duplicate',
    duplicateTarget: 'ABC-123 [4K].mp4',
  });

  await fakeThis.switchToFile(0);

  assert.equal(
    fakeThis.coverError,
    'search.filelist.duplicate_detail',
    '重複的檔顯示「找不到資料」，與同一列上的橘色「重複」標記自相矛盾',
  );
});

test('switchToFile: skipReason=not_found 的檔維持既有查無結果文案', async () => {
  const fakeThis = makeFakeThis({
    path: '/a/ABC-999.mp4',
    filename: 'ABC-999.mp4',
    number: 'ABC-999',
    searched: true,
    searchResults: [],
    skipReason: 'not_found',
  });

  await fakeThis.switchToFile(0);

  assert.equal(fakeThis.coverError, 'search.filelist.not_found');
});

test('switchToFile: 沒有 skipReason 欄位（升級前存下的 session）維持既有查無結果文案', async () => {
  const fakeThis = makeFakeThis({
    path: '/a/ABC-777.mp4',
    filename: 'ABC-777.mp4',
    number: 'ABC-777',
    searched: true,
    searchResults: [],
  });

  await fakeThis.switchToFile(0);

  assert.equal(fakeThis.coverError, 'search.filelist.not_found');
});
