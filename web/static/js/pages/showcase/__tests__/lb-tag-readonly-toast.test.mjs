// TASK-143-T4: readonly_no_output toast — confirmAddLbTag / removeLbUserTag
// harness 照抄 lb-full-error-pill.test.mjs（register + importmap loader）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { register } from 'node:module';
import { pathToFileURL, fileURLToPath } from 'node:url';
import path from 'node:path';

globalThis.window = globalThis;
globalThis.window.t = (key) => key;

const IMPORTMAP = {
    '@/settings/': 'pages/settings/',
    '@/shared/': 'shared/',
    '@/components/': 'components/',
    '@/search/': 'pages/search/',
    '@/showcase/': 'pages/showcase/',
    '@/scanner/': 'pages/scanner/',
};
const STATIC_JS_ROOT = pathToFileURL(
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../') + '/',
).href;

const loaderCode = `
const IMPORTMAP = ${JSON.stringify(IMPORTMAP)};
const STATIC_JS_ROOT = ${JSON.stringify(STATIC_JS_ROOT)};
export async function resolve(specifier, context, nextResolve) {
    for (const [prefix, rel] of Object.entries(IMPORTMAP)) {
        if (specifier.startsWith(prefix)) {
            return nextResolve(STATIC_JS_ROOT + rel + specifier.slice(prefix.length), context);
        }
    }
    if (specifier.startsWith('@/')) {
        return nextResolve(STATIC_JS_ROOT + specifier.slice(2), context);
    }
    return nextResolve(specifier, context);
}
`;
register(`data:text/javascript,${encodeURIComponent(loaderCode)}`, import.meta.url);

const { stateLightbox } = await import('../state-lightbox.js');

const PATH = 'file:////tmp/openaver-ro-cdp-t4-test/T4-STUB.mp4';
const TOAST_KEY = 'showcase.lightbox.tag_nfo_not_written';

function mockFetch(payload) {
    const prev = globalThis.fetch;
    globalThis.fetch = async () => ({
        ok: true,
        status: 200,
        json: async () => payload,
    });
    return { restore() { globalThis.fetch = prev; } };
}

function makeComponent(overrides) {
    const toasts = [];
    const c = Object.assign({}, stateLightbox(), {
        addingLbTag: true,
        newLbTagValue: 'TESTTAG',
        currentLightboxVideo: {
            path: PATH,
            user_tags: ['EXISTING'],
        },
        $nextTick(fn) { if (typeof fn === 'function') fn(); },
        $refs: {},
        toasts,
        showToast(msg, kind) { toasts.push({ msg, kind }); },
    }, overrides);
    return c;
}

test('confirmAddLbTag: readonly_no_output true → showToast(tag_nfo_not_written, info)', async () => {
    const mock = mockFetch({
        success: true,
        user_tags: ['EXISTING', 'TESTTAG'],
        nfo_updated: false,
        readonly_no_output: true,
    });
    try {
        const c = makeComponent();
        await c.confirmAddLbTag();
        assert.ok(
            c.toasts.some((t) => t.msg === TOAST_KEY && t.kind === 'info'),
            `expected toast with ${TOAST_KEY}/info, got ${JSON.stringify(c.toasts)}`,
        );
        assert.deepEqual(c.currentLightboxVideo.user_tags, ['EXISTING', 'TESTTAG']);
    } finally {
        mock.restore();
    }
});

test('removeLbUserTag: readonly_no_output true → showToast(tag_nfo_not_written, info)', async () => {
    const mock = mockFetch({
        success: true,
        user_tags: [],
        nfo_updated: false,
        readonly_no_output: true,
    });
    try {
        const c = makeComponent({
            currentLightboxVideo: { path: PATH, user_tags: ['EXISTING'] },
        });
        await c.removeLbUserTag('EXISTING');
        assert.ok(
            c.toasts.some((t) => t.msg === TOAST_KEY && t.kind === 'info'),
            `expected toast with ${TOAST_KEY}/info, got ${JSON.stringify(c.toasts)}`,
        );
        assert.deepEqual(c.currentLightboxVideo.user_tags, []);
    } finally {
        mock.restore();
    }
});

test('confirmAddLbTag: readonly_no_output false → 不顯示 tag_nfo_not_written toast', async () => {
    const mock = mockFetch({
        success: true,
        user_tags: ['EXISTING', 'TESTTAG'],
        nfo_updated: true,
        readonly_no_output: false,
    });
    try {
        const c = makeComponent();
        await c.confirmAddLbTag();
        assert.equal(
            c.toasts.filter((t) => t.msg === TOAST_KEY).length,
            0,
            `unexpected toast calls: ${JSON.stringify(c.toasts)}`,
        );
    } finally {
        mock.restore();
    }
});

test('confirmAddLbTag: 欄位缺省（非唯讀）→ 不顯示 tag_nfo_not_written toast', async () => {
    const mock = mockFetch({
        success: true,
        user_tags: ['EXISTING', 'TESTTAG'],
        nfo_updated: true,
    });
    try {
        const c = makeComponent();
        await c.confirmAddLbTag();
        assert.equal(
            c.toasts.filter((t) => t.msg === TOAST_KEY).length,
            0,
            `unexpected toast calls: ${JSON.stringify(c.toasts)}`,
        );
    } finally {
        mock.restore();
    }
});
