// TASK-144-T7: Alpine.data('autoOrganizePanel') open/close/setEnabled/runNow + 註冊

import { test } from 'node:test';
import assert from 'node:assert/strict';

let alpineInitCb;
globalThis.window = globalThis;
globalThis.document = { addEventListener: (_name, fn) => { alpineInitCb = fn; } };

const registered = [];
const toastCalls = [];
// 面板走既有的 Alpine.store('toast')（照 shared/state-toast.js），
// **不是** window.toast——全站沒有那個全域，為一個面板生一個等於開第二條 toast 路徑。
globalThis.Alpine = {
    data: (name, fn) => registered.push([name, fn]),
    store: (name) => (name === 'toast'
        ? { show: (msg, type) => { toastCalls.push([msg, type]); } }
        : undefined),
};
globalThis.window.t = (key) => key;
globalThis.window.pathToDisplay = (p) => p || '';

let fetchImpl = async () => ({ ok: true, json: async () => ({}) });
globalThis.fetch = (...args) => fetchImpl(...args);

const { autoOrganizePanel } = await import('../auto-organize-panel.js');

function freshPanel() {
    toastCalls.length = 0;
    return autoOrganizePanel();
}

test('open 初值 false；openPanel() 後 open 變 true；closePanel() 後變 false', async () => {
    const panel = freshPanel();
    assert.equal(panel.open, false);

    const urls = [];
    fetchImpl = async (url) => {
        urls.push(String(url));
        if (String(url).includes('/auto-organize/status')) {
            return {
                ok: true,
                json: async () => ({
                    running: false,
                    current_number: null,
                    enabled: false,
                    folder: '/tmp/fav',
                    folder_is_set: true,
                    resolved_folder: '/home/u/Downloads',
                }),
            };
        }
        return { ok: true, json: async () => ({}) };
    };

    await panel.openPanel();
    assert.equal(panel.open, true);
    panel.closePanel();
    assert.equal(panel.open, false);

    // 開一次面板只發**一支**請求：status 端點一次回完六個欄位。
    // 舊版打三支（/api/config、status、favorite-files），其中 favorite-files 會把整個
    // 下載資料夾列完、逐檔 stat，只為了讀一個路徑字串——這行就是那條回歸的守衛。
    assert.equal(urls.length, 1, `openPanel() 發了 ${urls.length} 個請求：${urls.join(', ')}`);
    assert.ok(urls[0].includes('/auto-organize/status'));
    assert.ok(!urls.some(u => u.includes('favorite-files')), 'openPanel() 不得去列檔');
});

test('openPanel: 還沒設最愛資料夾時，灰字顯示後端算出的候選路徑', async () => {
    const panel = freshPanel();
    fetchImpl = async () => ({
        ok: true,
        json: async () => ({
            running: false,
            current_number: null,
            enabled: false,
            folder: '',
            folder_is_set: false,
            resolved_folder: '/home/u/Downloads',
        }),
    });

    await panel.openPanel();
    assert.equal(panel.folderIsSet, false);
    // 顯示「按下『就用這個資料夾』之後會變成什麼」，與後端實際會寫入的值同源
    assert.equal(panel.folderPath, '/home/u/Downloads');
    assert.equal(panel.displayFolderPath(), '/home/u/Downloads');
});

test('init(): 同步從 server-render 的 data 屬性讀 enabled，零網路請求', () => {
    const panel = freshPanel();
    let fetched = false;
    fetchImpl = async () => { fetched = true; return { ok: true, json: async () => ({}) }; };
    panel.$el = { dataset: { autoOrganizeEnabled: '1' } };

    panel.init();

    assert.equal(panel.enabled, true, '按鈕的 accent 狀態必須在第一次求值時就是對的');
    assert.equal(fetched, false, 'init() 不得發任何請求——每次進搜尋頁都會多一個');
});

test('setEnabled(true) 打 POST /search/auto-organize/config，回應 {success:false} 時 this.enabled 不變', async () => {
    const panel = freshPanel();
    panel.enabled = false;
    panel.folderIsSet = true;

    let posted = null;
    fetchImpl = async (url, opts = {}) => {
        if (String(url).includes('/auto-organize/config') && opts.method === 'POST') {
            posted = JSON.parse(opts.body);
            return { ok: true, json: async () => ({ success: false, error: 'favorite_folder_unset' }) };
        }
        return { ok: true, json: async () => ({}) };
    };

    // 使用者點擊當下，瀏覽器已經把 checkbox 翻到 true 了——失敗時**兩邊都要還原**
    const el = { checked: true };

    await panel.setEnabled(true, el);
    assert.deepEqual(posted, { enabled: true });
    assert.equal(panel.enabled, false);
    assert.equal(
        el.checked, false,
        '只還原 this.enabled 不夠：綁定是 :checked="enabled"，指回同一個值不會重跑綁定，'
        + '開關會停在使用者撥過去的位置——畫面說開著、後端其實是關的（T7 CDP 實測到）',
    );
    assert.ok(toastCalls.length >= 1);
});

test('[TASK-144 Codex 四審] setEnabled 連點兩下：第一個請求還沒完成時，第二次呼叫不再發 fetch，並把 checkbox 拉回目前的 enabled', { timeout: 3000 }, async () => {
    const panel = freshPanel();
    panel.enabled = false;
    panel.folderIsSet = true;

    let fetchCalls = 0;
    let resolveFetch;
    const pending = new Promise((resolve) => { resolveFetch = resolve; });
    fetchImpl = async (url, opts = {}) => {
        if (String(url).includes('/auto-organize/config') && opts.method === 'POST') {
            fetchCalls += 1;
            await pending;
            return { ok: true, json: async () => ({ success: true }) };
        }
        return { ok: true, json: async () => ({}) };
    };

    const el1 = { checked: true };
    const firstCall = panel.setEnabled(true, el1); // 第一下：尚未 resolve，loading 應已變 true

    // 第二下點擊：瀏覽器已把 DOM 狀態翻成 true（模擬與目前 enabled 不同的殘留值），
    // 用來證明拉回動作真的發生，不是巧合相等
    const el2 = { checked: true };
    await panel.setEnabled(false, el2); // 第一個請求還在飛，這次呼叫必須早退

    assert.equal(fetchCalls, 1, '第一個請求還在進行時，第二次呼叫不得再發 fetch');
    assert.equal(
        el2.checked, panel.enabled,
        '早退必須把 checkbox 的 DOM 狀態拉回目前的 enabled——瀏覽器已經先把 checked 翻過去，'
        + 'Alpine 的 :checked 綁定在值沒變時不會重跑（FE-ALPINE-15）',
    );
    assert.equal(panel.enabled, false);

    resolveFetch();
    await firstCall;
    assert.equal(panel.enabled, true, '第一個請求 resolve 後應套用它送出的值');
    assert.equal(fetchCalls, 1, '全程只應有一次 fetch');
});

test('[TASK-144 Codex 四審 反向鎖] setEnabled 依序呼叫（第一次 await 完才第二次）→ fetch 被呼叫兩次，證明不是把功能鎖死', async () => {
    const panel = freshPanel();
    panel.enabled = false;
    panel.folderIsSet = true;

    let fetchCalls = 0;
    fetchImpl = async (url, opts = {}) => {
        if (String(url).includes('/auto-organize/config') && opts.method === 'POST') {
            fetchCalls += 1;
            return { ok: true, json: async () => ({ success: true }) };
        }
        return { ok: true, json: async () => ({}) };
    };

    await panel.setEnabled(true, { checked: true });
    await panel.setEnabled(false, { checked: false });

    assert.equal(fetchCalls, 2, '依序呼叫（非並行）必須各自成功發出請求');
    assert.equal(panel.enabled, false);
});

test('runNow() success=true → toast 使用「已開始」語意 key，不是「已完成」語意 key', async () => {
    const panel = freshPanel();
    panel.folderIsSet = true;

    fetchImpl = async (url, opts = {}) => {
        if (String(url).includes('/auto-organize/run-now') && opts.method === 'POST') {
            return { ok: true, json: async () => ({ success: true, reason: null }) };
        }
        return { ok: true, json: async () => ({}) };
    };

    await panel.runNow();
    assert.equal(toastCalls.length, 1);
    const [msg] = toastCalls[0];
    assert.equal(msg, 'search.auto_organize.run_now_started');
    assert.notEqual(msg, 'search.auto_organize.run_now_completed');
    assert.ok(!String(msg).includes('completed'));
    assert.ok(!String(msg).includes('已完成'));
});

test('runNow() success=false reason=already_running → toast 使用「已在進行中」語意 key', async () => {
    const panel = freshPanel();
    panel.folderIsSet = true;

    fetchImpl = async (url, opts = {}) => {
        if (String(url).includes('/auto-organize/run-now') && opts.method === 'POST') {
            return { ok: true, json: async () => ({ success: false, reason: 'already_running' }) };
        }
        return { ok: true, json: async () => ({}) };
    };

    await panel.runNow();
    assert.equal(toastCalls.length, 1);
    assert.equal(toastCalls[0][0], 'search.auto_organize.run_now_busy');
});

test("模組在 alpine:init 時把自己註冊成 Alpine.data('autoOrganizePanel', …)", () => {
    assert.equal(typeof alpineInitCb, 'function');
    const before = registered.length;
    alpineInitCb();
    assert.equal(registered.length, before + 1);
    assert.equal(registered[registered.length - 1][0], 'autoOrganizePanel');
    assert.equal(typeof registered[registered.length - 1][1], 'function');
    const instance = registered[registered.length - 1][1]();
    assert.equal(instance.open, false);
    assert.equal(typeof instance.openPanel, 'function');
    assert.equal(typeof instance.closePanel, 'function');
    assert.equal(typeof instance.setEnabled, 'function');
    assert.equal(typeof instance.runNow, 'function');
    assert.equal(typeof instance.useResolvedFolder, 'function');
});
