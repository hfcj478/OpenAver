// TASK-144-T6: setFileList() 吃後端 filter-files skip_reason 與 duplicate_target

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { searchStateFileList } from '../state/file-list.js';
import { searchStateSearchFlow } from '../state/search-flow.js';
import { searchStateBase } from '../state/base.js';

globalThis.window = globalThis;
globalThis.window.t = (k) => k;

function makeFakeThis(overrides = {}) {
  return Object.assign(
    {},
    searchStateBase(),
    searchStateSearchFlow(),
    searchStateFileList(),
    { _resetCoverState() {}, showToast() {}, switchToFile: async () => {} },
    overrides,
  );
}

function mockSearchFile() {
  window.SearchFile = {
    parseFilenames: async (filenames) =>
      filenames.map((f, idx) => ({ filename: f, number: 'ABC-' + (idx + 1), has_subtitle: false })),
    detectSuffixes: () => [],
    extractChineseTitle: () => null,
  };
}

test('setFileList: skip_reason 從蛇形轉為駝峰 skipReason，未命中為空字串', async () => {
  mockSearchFile();
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      success: true,
      files: [
        { path: '/a/hit.mp4', has_nfo: false, skip_reason: 'not_found', duplicate_target: '' },
        { path: '/a/miss.mp4', has_nfo: false, skip_reason: '', duplicate_target: '' },
      ],
    }),
  });

  const fakeThis = makeFakeThis();
  await searchStateFileList().setFileList.call(fakeThis, ['/a/hit.mp4', '/a/miss.mp4']);

  assert.equal(fakeThis.fileList.length, 2);
  assert.equal(fakeThis.fileList[0].skipReason, 'not_found');
  assert.equal(fakeThis.fileList[1].skipReason, '');
});

test('setFileList: skip_reason=not_found → searched=true、searchResults=[]（沿用既有查無結果狀態）', async () => {
  mockSearchFile();
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      success: true,
      files: [
        { path: '/a/nf.mp4', has_nfo: false, skip_reason: 'not_found', duplicate_target: '' },
      ],
    }),
  });

  const fakeThis = makeFakeThis();
  await searchStateFileList().setFileList.call(fakeThis, ['/a/nf.mp4']);

  assert.equal(fakeThis.fileList.length, 1);
  assert.equal(fakeThis.fileList[0].searched, true);
  assert.deepEqual(fakeThis.fileList[0].searchResults, []);
  assert.equal(fakeThis.fileList[0].skipReason, 'not_found');
});

test('setFileList: skip_reason=duplicate → scrapeStatus=duplicate、duplicateTarget 帶值（沿用既有橘色標記）', async () => {
  mockSearchFile();
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      success: true,
      files: [
        {
          path: '/a/dup.mp4',
          has_nfo: false,
          skip_reason: 'duplicate',
          duplicate_target: 'ABC-123 [4K].mp4',
        },
      ],
    }),
  });

  const fakeThis = makeFakeThis();
  await searchStateFileList().setFileList.call(fakeThis, ['/a/dup.mp4']);

  assert.equal(fakeThis.fileList.length, 1);
  assert.equal(fakeThis.fileList[0].scrapeStatus, 'duplicate');
  assert.equal(fakeThis.fileList[0].duplicateTarget, 'ABC-123 [4K].mp4');
  assert.equal(fakeThis.fileList[0].skipReason, 'duplicate');
  assert.equal(fakeThis.fileList[0].searched, true);
});
