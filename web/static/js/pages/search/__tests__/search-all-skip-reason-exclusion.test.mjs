// TASK-144-T6: searchAll() 兩分支排除 skipReason 命中的檔案

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchStateBatch } from '../state/batch.js';

globalThis.window = globalThis;
globalThis.window.t = (k) => k;

function makeState(fileList, searchedFilesCollector = []) {
  const toasts = [];
  return {
    ...searchStateBatch(),
    batchState: {
      isProcessing: false,
      isPaused: false,
      batchSize: 50,
      total: 0,
      processed: 0,
      success: 0,
      failed: 0,
    },
    fileList,
    listMode: 'file',
    currentFileIndex: 0,
    showToast(msg, type) { toasts.push({ msg, type }); },
    toasts,
    _searchFileBackground: async (file) => {
      searchedFilesCollector.push(file);
    },
    _resetCoverState() {},
  };
}

test('searchAll: skipReason 命中的檔案不進入 searchableFiles 分支', async () => {
  const searched = [];
  const file1 = { number: 'ABC-101', searched: false, has_nfo: false, skipReason: 'not_found' };
  const file2 = { number: 'ABC-102', searched: false, has_nfo: false, skipReason: '' };
  const state = makeState([file1, file2], searched);

  await state.searchAll();

  assert.equal(searched.length, 1, '只有非記憶命中的檔案進入批次');
  assert.equal(searched.includes(file1), false, 'skipReason 命中的檔案不得被搜尋');
  assert.equal(searched.includes(file2), true, '無 skipReason 的檔案正常搜尋');
});

test('searchAll: skipReason 命中的檔案不被 failedFiles 分支撈回重跑', async () => {
  const searched = [];
  const file1 = { number: 'ABC-101', searched: true, searchResults: [], has_nfo: false, skipReason: 'not_found' };
  const file2 = { number: 'ABC-102', searched: true, searchResults: [], has_nfo: false, skipReason: '' };
  const state = makeState([file1, file2], searched);

  await state.searchAll();

  assert.equal(searched.length, 1, 'failedFiles 分支僅重試無 skipReason 者');
  assert.equal(searched.includes(file1), false, 'skipReason 命中的檔案不被 failedFiles 撈回');
  assert.equal(searched.includes(file2), true, '無 skipReason 且失敗的檔案被撈回重試');
  assert.equal(file1.searched, true, 'skipReason 命中的檔案 searched 不得被重置為 false');
});

test('searchAll: 清單只剩記憶命中的檔時顯示 no_searchable_files toast 且零檔案進 targetFiles', async () => {
  const searched = [];
  const file1 = { number: 'ABC-101', searched: true, searchResults: [], has_nfo: false, skipReason: 'not_found' };
  const file2 = { number: 'ABC-102', searched: false, has_nfo: false, skipReason: 'duplicate' };
  const state = makeState([file1, file2], searched);

  await state.searchAll();

  assert.equal(state.batchState.isProcessing, false, '不啟動批次');
  assert.equal(state.batchState.total, 0, '零檔案進 targetFiles');
  assert.equal(searched.length, 0, '零檔案被搜尋');
  assert.equal(state.toasts.length, 1, '顯示且僅顯示一則 toast');
  assert.equal(state.toasts[0].msg, 'search.toast.no_searchable_files');
  assert.equal(file1.searched, true, 'file1 searched 狀態未被重置');
});
