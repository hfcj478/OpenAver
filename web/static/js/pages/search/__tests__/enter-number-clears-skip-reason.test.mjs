// TASK-144-T6: enterNumber() 重輸番號清除 skipReason 與 duplicateTarget

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchStateFileList } from '../state/file-list.js';
import { searchStateBatch } from '../state/batch.js';

globalThis.window = globalThis;
globalThis.window.t = (k) => k;

function makeState(fileList, searchedCollector = []) {
  return {
    ...searchStateFileList(),
    ...searchStateBatch(),
    fileList,
    listMode: 'file',
    currentFileIndex: 0,
    batchState: { isProcessing: false, isPaused: false, batchSize: 50, total: 0, processed: 0, success: 0, failed: 0 },
    switchToFile() {},
    showToast() {},
    _searchFileBackground: async (f) => { searchedCollector.push(f); },
    _resetCoverState() {},
  };
}

test('enterNumber: 重輸番號後清除 skipReason 與 duplicateTarget，該筆可再被批次搜尋選中', async () => {
  const file = {
    number: 'OLD-001',
    searched: true,
    searchResults: [],
    skipReason: 'not_found',
    duplicateTarget: 'target.mp4',
    has_nfo: false,
  };
  const searched = [];
  const state = makeState([file], searched);

  globalThis.prompt = () => 'NEW-002';
  state.enterNumber(0);

  assert.equal(file.number, 'NEW-002');
  assert.equal(file.skipReason, '');
  assert.equal(file.duplicateTarget, undefined);

  // 驗證再跑 searchAll() 時該筆能進入 searchableFiles 並被搜尋
  await state.searchAll();
  assert.equal(searched.length, 1);
  assert.equal(searched[0], file);
});

test('enterNumber: duplicate 記憶命中的那筆重輸番號後，橘色「重複」標記不會殘留', async () => {
  // setFileList() 現在會在列檔階段就把 duplicate 記憶命中的檔標成 scrapeStatus='duplicate'。
  // 重輸番號後若不清掉，重搜到候選之後 search.html:1131 的「產生 NFO」鈕與 :1163 的橘色
  // 「重複」鈕會同時顯示，而橘色那顆點開是空白（duplicateTarget 已清）。
  const file = {
    number: 'OLD-001',
    searched: true,
    searchResults: [],
    skipReason: 'duplicate',
    duplicateTarget: 'ABC-123 [4K].mp4',
    scrapeStatus: 'duplicate',
    has_nfo: false,
  };
  const state = makeState([file]);

  globalThis.prompt = () => 'NEW-002';
  state.enterNumber(0);

  assert.equal(file.skipReason, '');
  assert.equal(file.duplicateTarget, undefined);
  assert.notEqual(file.scrapeStatus, 'duplicate');
});
