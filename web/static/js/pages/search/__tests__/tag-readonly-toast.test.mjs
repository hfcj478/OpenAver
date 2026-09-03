// TASK-143-T4（sonnet review P2 #2）：搜尋頁的 confirmAddTag / removeUserTag
// 也消費 POST /api/user-tags，過去完全不讀 `readonly_no_output`。
//
// 使用者流程：從搜尋頁對一個「唯讀來源 ＋ 還沒成功產生輸出」的片加標籤 →
// 後端已正確回報 readonly_no_output:true（NFO 沒寫、標籤只進 DB），但搜尋頁
// 什麼提示都沒有 → 使用者以為 Jellyfin 之後看得到，其實永遠不會。
// 這正是 spec-143 §3.2 要修的那個靜默失敗，只是從另一個入口復活。
//
// harness 照 confirm-edit-actors-fetch-spy.test.mjs 慣例（alias-loader + .call/展開 mixin）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;

register(new URL('./alias-loader.mjs', import.meta.url), import.meta.url);
const { searchStateResultCard } = await import('../state/result-card.js');

const TOAST_KEY = 'search.error.tag_nfo_not_written';

function makeThis(responsePayload, toasts) {
    const file = { path: 'file:////tmp/ro-src/T4-STUB.mp4', user_tags: [] };
    globalThis.fetch = async () => ({ ok: true, status: 200, json: async () => responsePayload });
    return {
        ...searchStateResultCard(),
        fileList: [file],
        currentFileIndex: 0,
        addingTag: true,
        newTagValue: 'TESTTAG',
        saveState: () => {},
        showToast: (msg, type) => { toasts.push([msg, type]); },
        _file: file,
    };
}

test('confirmAddTag: readonly_no_output=true → 跳出「沒有 NFO 可更新」提示', async () => {
    const toasts = [];
    const ctx = makeThis(
        { success: true, user_tags: ['TESTTAG'], nfo_updated: false, readonly_no_output: true },
        toasts,
    );
    await ctx.confirmAddTag.call(ctx);

    assert.deepEqual(ctx._file.user_tags, ['TESTTAG'], '標籤仍照常寫進畫面狀態');
    assert.equal(toasts.length, 1, '應該剛好跳一則提示');
    assert.deepEqual(toasts[0], [TOAST_KEY, 'info']);
});

test('confirmAddTag: readonly_no_output 不存在（一般片）→ 不跳任何提示', async () => {
    const toasts = [];
    const ctx = makeThis({ success: true, user_tags: ['TESTTAG'], nfo_updated: true }, toasts);
    await ctx.confirmAddTag.call(ctx);

    assert.equal(toasts.length, 0, '一般片寫得進 NFO，不該多一則提示');
});

test('removeUserTag: readonly_no_output=true → 同樣跳提示（兩側對稱）', async () => {
    const toasts = [];
    const ctx = makeThis(
        { success: true, user_tags: [], nfo_updated: false, readonly_no_output: true },
        toasts,
    );
    await ctx.removeUserTag.call(ctx, 'TESTTAG');

    assert.deepEqual(ctx._file.user_tags, [], '移除後的標籤陣列照常寫回');
    assert.equal(toasts.length, 1);
    assert.deepEqual(toasts[0], [TOAST_KEY, 'info']);
});

test('removeUserTag: readonly_no_output 不存在 → 不跳提示', async () => {
    const toasts = [];
    const ctx = makeThis({ success: true, user_tags: [], nfo_updated: true }, toasts);
    await ctx.removeUserTag.call(ctx, 'TESTTAG');

    assert.equal(toasts.length, 0);
});
