// CJK 硬編碼守衛測試（103-T8b 重寫：JS 側改 eslint AST rule，模板側瘦身成粗略掃描器）。
// 零新依賴：Node 內建 node:test + repo 既有 devDependency `eslint`（RuleTester）。
// 跑：npm run test:cjk-guard
//
// JS 側（local/no-cjk-literal，`eslint.config.mjs`）：對應 TASK-103-T8b §驗證方式 J1–J12
// mutation 矩陣，用 RuleTester 直接測 rule 本體（AST，不需黑箱），J1–J11 各自獨立一條
// test()（非包成一條大 test，維持與舊版 38 條案例相當的細粒度，`npm test` case 數不減少）。
// J12（reportUnusedDisableDirectives）RuleTester 測不到，走 CLI 黑箱。
//
// 模板側（`cjk_guard_lint.mjs` 瘦身版）：對應 H1–H9，走 spawnSync 黑箱測（CD-12R：模板
// 掃描器不需要被 import 測——main() 直接執行，無 entry-point guard，也不 export 任何內部
// 函式）。
//
// 額外（extra-*）：AST 方案下「結構上不可能存在」的 T8 假陰性 #2/#3/#7 之 regression
// 對照，以及豁免行「真的有作用」的 load-bearing 驗證（memory: mutation anchor 必須先斷言
// 唯一——這裡用「拿掉豁免後轉紅」證明豁免不是裝飾）。全部用 literal scratch 內容，不碰
// 任何已 tracked 檔案（工作區已有本 task 的合法變更，不可再用 git checkout/restore 復原）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { RuleTester } from 'eslint';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, chmodSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { localPlugin, NO_CJK_LITERAL_MESSAGE } from '../../eslint.config.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const GUARD_PATH = join(__dirname, '..', 'cjk_guard_lint.mjs');
const REPO_ROOT = join(__dirname, '..', '..');
const rule = localPlugin.rules['no-cjk-literal'];
const langOpts = { ecmaVersion: 2022, sourceType: 'module' };
const ruleTester = new RuleTester();

// 小 helper：跑單一 invalid case，斷言錯誤數（可選 line）
function expectInvalid(code, opts = {}) {
  ruleTester.run('no-cjk-literal', rule, {
    valid: [],
    invalid: [{ code, languageOptions: langOpts, errors: opts.errors ?? 1 }],
  });
}
function expectValid(code) {
  ruleTester.run('no-cjk-literal', rule, {
    valid: [{ code, languageOptions: langOpts }],
    invalid: [],
  });
}

// ============================================================================
// JS 側：local/no-cjk-literal — J1–J11（各自獨立 test，J12 見下方 CLI 黑箱）
// ============================================================================

test('J1 — 普通字串中文 → RED', () => {
  expectInvalid("const s = '中文';");
});

test('J2 — 樣板字面中文 → RED', () => {
  expectInvalid('const s = `中文`;');
});

test('J3 — `${ {a:\'中文\'}.a }` → RED（巢狀在 ObjectExpression 內的 Literal 仍是 Literal 節點）', () => {
  expectInvalid("const s = `${ {a:'中文'}.a }`;");
});

test('J4 — 字串內含 `//` 的中文 → RED（AST 下 `//` 只是字串內容，不觸發任何特殊處理）', () => {
  expectInvalid("const s = 'a//b中文';");
});

test('J5 — [Literal 字串] `\\uXXXX` escape 寫的中文 → RED（免費：JS 引擎解碼後 Literal.value 本身含 CJK codepoint）', () => {
  expectInvalid('const s = "\\u4e2d\\u6587";');
});

test('J6 — 偽裝成豁免 pattern 字面的字串（整段是一個字串常數，非真三元式）→ RED', () => {
  expectInvalid("const s = \"window.t ? window.t('x') : '中文'\";");
});

test("J7 — `foo.window.t ? window.t('k') : '中文'`（偽裝三元式）→ RED（BLOCKER-2 在 AST 下結構上不可能存在：rule 不做 window.t 特判，真假三元式一視同仁）", () => {
  expectInvalid("const a = foo.window.t ? window.t('k') : '中文';");
});

test('J8 — console.log(...) 單行中文 → GREEN', () => {
  expectValid("console.log('中文');");
});

test('J9 — console.warn(...) 跨行中文 → GREEN（CD-3：往上找 parent 鏈的 CallExpression，跨行天然成立，不需括號配對機器）', () => {
  expectValid("console.warn(\n  '中文'\n);");
});

test('J10a — `// 中文` 行註解 → GREEN（AST 不掃 Comment 節點）', () => {
  expectValid('// 中文註解\nconst x = 1;');
});

test('J10b — `/* 中文 */` 區塊註解 → GREEN', () => {
  expectValid('/* 中文區塊註解 */ const x = 1;');
});

test("J11 — 合法 `window.t ? window.t('k') : '中文'` fallback（行內 disable）→ GREEN（CD-1R 決策：優先用行內取代 rule 內硬編 ③）", () => {
  // 注意：RuleTester 內部把被測 rule 註冊成 `rule-to-test/<ruleName>`（非我們在
  // eslint.config.mjs 掛的 `local/no-cjk-literal`），故此處 disable 用 RuleTester 的
  // 內部命名；真實 eslint.config.mjs 執行時用的是 `local/no-cjk-literal`
  // （見 file.js / state-config.js 的實際豁免行，以及下方 J12 CLI 測試）。
  expectValid(
    "// eslint-disable-next-line rule-to-test/no-cjk-literal -- [cjk-exempt: window.t() 防禦性 fallback，已是 i18n 路徑]\n" +
      "const label = window.t ? window.t('notif.title') : '通知';",
  );
});

test('J12 — 行內 eslint-disable 陳舊時 reportUnusedDisableDirectives 必須報紅（CLI 黑箱，RuleTester 測不到 linterOptions 層行為）', () => {
  // Flat config 的 `files` glob 相對 config 檔案位置比對，探針必須放在 web/static/js/**
  // 底下才會被規則匹配到；測完即刪，不留痕（不 commit）。
  const probeRel = join('web', 'static', 'js', '__cjk_j12_probe__.js');
  const probeAbs = join(REPO_ROOT, probeRel);
  try {
    // 目標中文已移除，但 disable 註解還在 → 陳舊 disable，reportUnusedDisableDirectives: 'error' 應報紅
    writeFileSync(
      probeAbs,
      "// eslint-disable-next-line local/no-cjk-literal -- [cjk-exempt: 已過期理由]\nconst label = 'stale';\n",
    );
    const result = spawnSync('npx', ['eslint', probeRel], { encoding: 'utf8', cwd: REPO_ROOT });
    const output = `${result.stdout}\n${result.stderr}`;
    assert.match(
      output,
      /unused eslint-disable directive/i,
      '陳舊 disable（目標中文已消失）必須被 reportUnusedDisableDirectives 抓到，不可靜默通過',
    );
    assert.notEqual(result.status, 0, '陳舊 disable 應讓 eslint 以非 0 結束碼收場');
  } finally {
    rmSync(probeAbs, { force: true });
  }
});

// ============================================================================
// JS 側額外：T8 假陰性 #2/#3/#7 的「結構上不可能存在」regression 對照 + AST 邊界
// ============================================================================

test('extra-J1 — [Literal 字串] `\\u{...}` 花括號 codepoint escape 形式同樣 RED（T8 BLOCKER-3b 對照）', () => {
  expectInvalid('const s = "\\u{4e2d}\\u{6587}";');
});

test('extra-J2 — [Literal 字串] 非中文的 `\\uXXXX` escape（`\\u0041`="A"）→ GREEN，不誤報（T8 BLOCKER-3d 對照）', () => {
  expectValid('const s = "\\u0041\\u0042";');
});

// ============================================================================
// Codex P1-1（實測複驗屬實）：T8b 卡片 §技術要點原寫「TemplateElement 用 value.raw」是
// 錯的規格——raw 是 escape 前的原始碼字面（`中` 這串 ASCII，不含 CJK codepoint），
// cooked 才是解碼後的實際字元。只查 raw 會讓樣板字面版的 escape 中文完全漏檢（T8 的假
// 陰性 #3 換了個節點型別在 template 路徑復活）。修法：rule 同時查 raw 與 cooked（任一
// 含 CJK 即報）。以下 4 條明確標注涵蓋的節點型別是 TemplateElement（非 Literal），
// 逐一驗證 \uXXXX / \u{...} 兩種 escape 形式 + ${} 插值夾在中間的情形。
// ============================================================================

test('P1-1a — [TemplateElement] `` `\\uXXXX` `` escape 中文 → RED（Codex 重現：cooked 才含 CJK，raw 是 ASCII escape 序列）', () => {
  expectInvalid('const t = `\\u4e2d\\u6587`;');
});

test('P1-1b — [TemplateElement] `` `\\u{...}` `` 花括號 escape 中文 → RED', () => {
  expectInvalid('const t = `\\u{4e2d}\\u{6587}`;');
});

test('P1-1c — [TemplateElement] ${} 插值夾在兩個 escape 中文 quasi 之間（`` `\\u4e2d${x}\\u6587` ``）→ 兩個 quasis 各自 RED（2 errors）', () => {
  expectInvalid('const t = `\\u4e2d${x}\\u6587`;', { errors: 2 });
});

test('P1-1d — [TemplateElement] escape 中文與字面中文混合（`` `中${1}\\u6587` ``）→ 2 個 quasis 各自 RED，非漏檢其一', () => {
  expectInvalid('const t = `中${1}\\u6587`;', { errors: 2 });
});

test('P1-1e — [TemplateElement] tagged template 內非法 escape 使 cooked=null 時不得 throw、且仍靠 raw 判定（不誤報無 CJK 的情形）', () => {
  // String.raw`\unicode` 是合法 JS（tagged template 允許非法 escape），cooked 會是 null。
  // raw 裡沒有 CJK codepoint（只是 ASCII \unicode 字面），故應 GREEN；規則不能因 cooked
  // 為 null 而拋例外。
  expectValid('const t = String.raw`\\unicode`;');
});

test('P1-1f — [TemplateElement] 非中文的 `\\uXXXX` escape（`\\u0041\\u0042`="AB"）→ GREEN，不誤報（自我複核發現的對稱缺口：extra-J2 只測了 Literal 這個方向，TemplateElement 沒有等價案例）', () => {
  expectValid('const t = `\\u0041\\u0042`;');
});

test('extra-J3 — RegExpLiteral（`node.value` 是 RegExp 物件非 string）不誤判為字串 → GREEN', () => {
  // Literal 的 typeof value === 'string' 檢查天然排除 RegExpLiteral（value 是 RegExp 實例），
  // 舊方案需要專門的 §G.3「找對應非跳脫 /」狀態機才能正確跳過正則字面量，AST 這裡是免費的。
  expectValid("const re = /[一-龥]/; const s = re.test('x');");
});

test('extra-J4 — 巢狀樣板字面（stack 而非單一旗標）→ 2 個獨立 Literal/TemplateElement 各自 RED', () => {
  expectInvalid('const s = `${ `內${1}層中文` }`;', { errors: 2 });
});

test(
  'extra-J5 — 多行樣板字面（中文在第 2 行）→ RED（設計取捨：eslint 回報點是 node 起點所在行，' +
    '不逐字元定位到 CJK 實際偏移；比 T8 舊 tokenizer 的逐字元行號粗，但換來 rule 本體 ~30 行，' +
    '開發者仍能在該 TemplateElement 內找到違規字元）',
  () => {
  ruleTester.run('no-cjk-literal', rule, {
    valid: [],
    invalid: [
      {
        code: 'const s = `line1\nline2中文`;',
        languageOptions: langOpts,
        errors: [{ message: NO_CJK_LITERAL_MESSAGE }],
      },
    ],
  });
});

test('extra-J6 — 巢狀呼叫 console.warn("a", foo("中文")) → foo(...) 非 console 呼叫，仍 RED（最內層呼叫決定豁免，非外層）', () => {
  expectInvalid("console.warn('a', foo('中文'));");
});

test('extra-J7 — 非 console 物件同名方法 foo.warn(\'中文\') → RED（不誤放行其他物件的 .warn/.log）', () => {
  expectInvalid("foo.warn('中文');");
});

test('extra-J8 — 同一行兩個獨立字串各含中文 → 各自報 1 個 error（AST 逐節點回報，非逐行去重）', () => {
  expectInvalid("const a = '甲文字', b = '乙文字';", { errors: 2 });
});

test('extra-J9 — 具名常數（如 file.js 的 chinesePatterns）用行內 disable 豁免後 GREEN；拿掉 disable 立刻轉 RED（load-bearing 驗證，非裝飾註解）', () => {
  const withDisable =
    "// eslint-disable-next-line rule-to-test/no-cjk-literal -- [cjk-exempt: 測試用途]\n" +
    "const chinesePatterns = ['中文字幕', '字幕'];";
  const withoutDisable = "const chinesePatterns = ['中文字幕', '字幕'];";
  ruleTester.run('no-cjk-literal', rule, {
    valid: [{ code: withDisable, languageOptions: langOpts }],
    invalid: [{ code: withoutDisable, languageOptions: langOpts, errors: 2 }],
  });
});

test('extra-J10 — [Accepted Residual，P1-2 同族排查發現] eslint-disable-next-line 是整行豁免，同行日後追加的不相干中文會被同一個 disable 靜默吞掉（ESLint 原生行為，非計數式；已於 eslint.config.mjs 頂部註記，未機制化修復）', () => {
  // 與 P1-2（模板側 cjk-exempt 整行溢出）同一種「豁免範圍溢出」，差別是這裡不是我們自己
  // 發明的標記語法，是 ESLint 的 disable-comment 原生語意——沒有「只抑制 N 個」這種內建
  // 機制。刻意留這條測試釘住現況行為，避免日後被誤當成尚未發現的 bug 重新調查。
  expectValid(
    "// eslint-disable-next-line rule-to-test/no-cjk-literal -- test\nconst a = '甲文字', b = '乙文字';",
  );
});

// ============================================================================
// 模板側：cjk_guard_lint.mjs 瘦身版 — H1–H9（TASK-103-T8b §驗證方式）
// 全部走 spawnSync 黑箱（掃描器主體不再 export 任何函式，main() 直接執行）。
// ============================================================================

function makeScratchRoot() {
  const tmp = mkdtempSync(join(tmpdir(), 'cjk-guard-tpl-'));
  mkdirSync(join(tmp, 'web', 'templates'), { recursive: true });
  return tmp;
}
function runGuard(root) {
  const result = spawnSync(process.execPath, [GUARD_PATH, root], { encoding: 'utf8' });
  return { ...result, output: `${result.stdout}\n${result.stderr}` };
}

test('〔H1〕<div>中文</div> → RED', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div>中文</div>');
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /a\.html:1/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H2〕無引號屬性值 <span title=中文> → RED（舊方案漏掃 #8，新方案不做屬性解析，天然抓到）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<span title=中文>ok</span>');
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /a\.html:1/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H3〕<SCRIPT>...</SCRIPT> 大寫關標籤 → 之後可見中文仍 RED（舊方案漏掃 #1）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      '<SCRIPT>var a=1;</SCRIPT>\n<div>大寫標籤後的中文</div>',
    );
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /a\.html:2/, '大寫關標籤之後的可見文字必須仍被掃到（不可整檔被吞掉）');
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H4〕<script data-note=\">\"> 後的可見中文 → RED（舊方案漏掃 #9；新方案不找 tag 內 \'>\'，直接找 </script>）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      '<script data-note=">">var x=1;</script>\n<div>屬性內含大於號後的中文</div>',
    );
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /a\.html:2/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H5〕{# 中文註解 #} → GREEN', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div>{# 中文註解 #}</div>');
    const r = runGuard(tmp);
    assert.equal(r.status, 0);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H6〕<!-- 中文註解 --> → GREEN', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div><!-- 中文註解 --></div>');
    const r = runGuard(tmp);
    assert.equal(r.status, 0);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H7〕<script>const s="中文"</script> → GREEN（已知 residual，整段跳過不解析內容，明文記錄）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<script>const s="中文"</script>');
    const r = runGuard(tmp);
    assert.equal(r.status, 0, 'Accepted Residual #1：模板內嵌 <script> 整段不掃，此為刻意設計而非 bug');
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H7b〕<style>.x{content:"中文"}</style> → GREEN（同 H7，style 整段亦跳過；Accepted Residual #2）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<style>.x{content:"中文"}</style>');
    const r = runGuard(tmp);
    assert.equal(r.status, 0);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H8〕帶正確內容 cjk-exempt(內容) 標記的行（宣告內容＝實際段落內容）→ GREEN', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div>中文</div> {# cjk-exempt(中文): 測試用途 #}');
    const r = runGuard(tmp);
    assert.equal(r.status, 0);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H8b〕拿掉 cjk-exempt(內容) 標記後同一行立刻轉 RED（load-bearing 驗證，模擬 base.html window.t fallback 真實模式）', () => {
  const tmp = makeScratchRoot();
  const withMarker =
    ':aria-label="window.t ? window.t(\'k\') : \'通知\'" {# cjk-exempt(通知): window.t() fallback #}';
  const withoutMarker = ':aria-label="window.t ? window.t(\'k\') : \'通知\'"';
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), `<div ${withMarker}></div>`);
    assert.equal(runGuard(tmp).status, 0, '有標記時應 GREEN');
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), `<div ${withoutMarker}></div>`);
    const r2 = runGuard(tmp);
    assert.notEqual(r2.status, 0, '拿掉標記後同一行必須轉 RED，證明標記不是裝飾');
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

// ============================================================================
// 豁免精確度演進（同一族缺口，逐輪收斂，全部改用現行語法 cjk-exempt(段1|段2|...)）：
//   1. Codex P1-2：「該行含 cjk-exempt 字樣即跳過整行」放任範圍溢出。
//      → 改宣告「段數」cjk-exempt(N)。
//   2. Codex 複驗：段數比對只走「有 hit 的行」，CJK 歸零但宣告還留著時該行永遠不進入比對，
//      陳舊宣告靜默存活。→ 補一輪獨立掃描 marker 所在行（即使 0 hit）。
//   3. Codex P1-3（本輪，實測複驗屬實且比原描述更嚴重）：宣告數量只鎖「段數」不鎖「內容」——
//      同段數下把內容整段換成完全無關的硬編碼、甚至整行用途都換掉，只要段數不變仍 GREEN。
//      → 改宣告**內容** cjk-exempt(段1|段2|...)，比對「該行實際 CJK 段序列（依序、含重複）
//      是否與宣告完全相同」。此法自然涵蓋段數比對，故舊 count 邏輯整個替換、非疊加，以下
//      測試全部只測現行內容語法（P1-2 的 count-only 語法已不存在，不留無意義的回歸測試）。
// ============================================================================

test('〔P1-3a〕Codex 原始重現：內容被替換成完全無關的新硬編碼（「通知」→「全新的硬編碼中文」），段數不變 → 必須 RED（宣告與實際不符）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      '<div>{# cjk-exempt(通知): window.t fallback #}全新的硬編碼中文</div>',
    );
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0, '同段數但內容被抽換必須轉紅，不可因為「段數沒變」就放行');
    assert.match(r.output, /本行 CJK 內容與豁免宣告不符——宣告=\[通知\] 實際=\[全新的硬編碼中文\]/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3b〕coordinator 加強版重現：整行的可見內容/用途都換掉（換成不相干的屬性與文字），只留著原 marker → 必須 RED（比 P1-3a 更嚴格：不是「同語境換內容」而是「整行語意都變了」）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      '<span title="完全無關的硬編碼">{# cjk-exempt(通知): window.t() fallback #}</span>',
    );
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0, 'marker 不能讓整行的用途被抽換後還繼續享有豁免');
    assert.match(r.output, /宣告=\[通知\] 實際=\[完全無關的硬編碼\]/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3c〕段序調換（宣告「開啟通知|關閉通知」，實際行上是「關閉通知」在前、「開啟通知」在後，兩段用非 CJK 字元隔開避免被誤併成一段）→ 必須 RED，證明比對是有序序列而非集合', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      "<div>{# cjk-exempt(開啟通知|關閉通知): a #}'關閉通知' abc '開啟通知'</div>",
    );
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0, '兩段集合相同但順序不同，若比對是無序集合就會誤放行，必須是有序比對');
    assert.match(r.output, /宣告=\[開啟通知\|關閉通知\] 實際=\[關閉通知\|開啟通知\]/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3d〕重複段（settings.html 語言切換器真實案例：繁/简/あ/繁，「繁」出現兩次）宣告完整含重複 → GREEN', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      "<div>{# cjk-exempt(繁|简|あ|繁): a #}{'繁','简','あ','en','繁'}</div>",
    );
    const r = runGuard(tmp);
    assert.equal(r.status, 0, '宣告序列含重複且與實際序列完全一致（含重複、含順序）應放行');
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3e〕同上情境但少宣告一次重複段（宣告「繁|简|あ」缺了第二個「繁」）→ RED，證明「宣告過一次同內容」不能涵蓋「行上出現兩次」', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      "<div>{# cjk-exempt(繁|简|あ): a #}{'繁','简','あ','en','繁'}</div>",
    );
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /宣告=\[繁\|简\|あ\] 實際=\[繁\|简\|あ\|繁\]/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3f〕marker 自身理由文字內含中文不污染實際內容計算（marker 包在 {# #} 內天然被剝除，含 coordinator 明確要求釘住的一點）→ GREEN', () => {
  const tmp = makeScratchRoot();
  try {
    // 理由「這是含中文的理由文字」本身含 CJK，若被誤算進 actual 會讓宣告(通知)判定不符。
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      '<div>{# cjk-exempt(通知): 這是含中文的理由文字 #}通知</div>',
    );
    const r = runGuard(tmp);
    assert.equal(r.status, 0, 'marker 理由文字必須被 {# #} 剝除，不可污染實際內容序列');
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3g〕完全正確時 → GREEN（多段案例，對照 base.html:513 的「關閉通知|開啟通知」真實模式，兩段用非 CJK 字元隔開避免被誤併成一段）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      "<div>{# cjk-exempt(關閉通知|開啟通知): a #}'關閉通知' abc '開啟通知'</div>",
    );
    const r = runGuard(tmp);
    assert.equal(r.status, 0);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

// ---- 邊界值（本輪自問「這條測試名字宣稱涵蓋什麼／實際餵了哪些邊界」逐一列出）----

test('〔P1-3h〕邊界值：空宣告 cjk-exempt()、實際 0 段 → GREEN（合法，語意等同無 marker）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div>{# cjk-exempt(): reason #}</div>');
    const r = runGuard(tmp);
    assert.equal(r.status, 0);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3h-2〕邊界值：空宣告 cjk-exempt() 但實際有 1 段中文 → RED（空宣告不是萬能豁免）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div>{# cjk-exempt(): reason #}中文</div>');
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /宣告=\[\] 實際=\[中文\]/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3i〕邊界值：宣告含結尾多餘的 `|`（cjk-exempt(通知|)）產生一個空字串段，長度變 2 但實際只有 1 段 → RED（不會被誤判成「只有一段」）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div>{# cjk-exempt(通知|): reason #}通知</div>');
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0, '結尾多餘的 | 會 split 出一個空字串元素，宣告序列長度變 2，與實際的 1 段不符');
    assert.match(r.output, /宣告=\[通知\|\] 實際=\[通知\]/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3i-2〕邊界值：宣告中間連續兩個 `|`（cjk-exempt(甲||乙)）產生一個空字串段插在中間，長度變 3 但實際只有 2 段 → RED（與 P1-3i 的「結尾多餘」是不同形狀的同一類malformation，位置不同但邏輯應一致）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), "<div>{# cjk-exempt(甲||乙): a #}'甲' x '乙'</div>");
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /宣告=\[甲\|\|乙\] 實際=\[甲\|乙\]/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3j〕邊界值：裸 cjk-exempt（完全無括號，最舊的語法殘留）仍不是合法豁免 → 該行照常 RED', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div>中文</div> {# cjk-exempt: 舊語法已失效 #}');
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0, '沒有括號內容的裸 cjk-exempt 不應被視為豁免標記');
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3k〕邊界值：同一行出現 2 個 cjk-exempt(...) marker（內容語法）→ RED「語意不明請合併成一個」（fail-closed，不取最後一個/合併等隱性規則）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(
      join(tmp, 'web', 'templates', 'a.html'),
      '<div>{# cjk-exempt(甲): a #}甲乙{# cjk-exempt(乙): b #}</div>',
    );
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /本行出現 2 個 cjk-exempt 標記，語意不明請合併成一個/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3l〕邊界值：marker 在檔案最後一行且無結尾換行符 → 正常判定不因缺 \\n 而出錯（內容完全正確 → GREEN）', () => {
  const tmp = makeScratchRoot();
  try {
    // writeFileSync 不會自動補 \n，'a.html' 內容故意不以換行結尾。
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div>{# cjk-exempt(中文): reason #}中文</div>');
    const r = runGuard(tmp);
    assert.equal(r.status, 0);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔P1-3m〕邊界值：CJK 歸零（本族第 2 輪缺口）在新的內容比對下仍必須被抓到（宣告非空、實際=[] 長度不等）→ RED', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'a.html'), '<div>{# cjk-exempt(通知): reason #}</div>');
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0, '內容比對取代數量比對後，歸零缺口必須仍被涵蓋（長度不等本身就會不符）');
    assert.match(r.output, /宣告=\[通知\] 實際=\[\]/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H9a〕掃描根不存在（web/templates 缺席）→ RED，fail-closed（修 #10）', () => {
  const tmp = mkdtempSync(join(tmpdir(), 'cjk-guard-tpl-empty-'));
  try {
    // 故意不建立 web/templates 目錄
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /掃描根目錄不存在/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H9b〕web/templates 存在但掃到 0 個 .html 檔 → RED，fail-closed（不得靜默視為「零殘留」）', () => {
  const tmp = makeScratchRoot(); // 建了 web/templates，但目錄內無任何 .html
  try {
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /掃到 0 個檔案/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔H9c〕掃描目錄讀取失敗（權限/不可讀）→ RED 並指出路徑（walk() 例外不得靜默吞掉）', () => {
  const tmp = makeScratchRoot();
  const blockedDir = join(tmp, 'web', 'templates', 'blocked');
  mkdirSync(blockedDir);
  writeFileSync(join(blockedDir, 'inner.html'), '<div>不重要</div>');
  try {
    // 移除目錄的讀取權限，觸發 walk() 內的 readdirSync 例外分支
    chmodSync(blockedDir, 0o000);
    if (process.getuid && process.getuid() === 0) {
      // root 不受檔案權限限制，此環境無法驗證此分支，跳過斷言（非 CI 常見情境）
      return;
    }
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /無法讀取目錄/);
    assert.match(r.output, /blocked/);
  } finally {
    try {
      chmodSync(blockedDir, 0o755);
    } catch {
      /* best effort cleanup */
    }
    rmSync(tmp, { recursive: true, force: true });
  }
});

// ============================================================================
// 額外：整檔豁免（T8 真資產沿用）+ 副檔名過濾 + 遞迴 + 混合豁免/違規
// ============================================================================

// EXEMPT-1/2：搭配一個非豁免的乾淨檔案，避免「唯一 .html 檔剛好是豁免檔」導致
// scanFiles 篩完剩 0 個，觸發的其實是 H9b fail-closed（另一條路徑）而非真的驗到「豁免生效」。
test('〔EXEMPT-1〕design-system.html 整檔豁免：內含中文不觸發（同批次另有乾淨檔案，證明是豁免生效而非 H9b 空掃）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'design-system.html'), '<div>中文不應被掃到</div>');
    writeFileSync(join(tmp, 'web', 'templates', 'clean.html'), '<div>ok</div>');
    const r = runGuard(tmp);
    assert.equal(r.status, 0);
    assert.doesNotMatch(r.output, /design-system\.html/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔EXEMPT-2〕motion_lab.html 整檔豁免：內含中文不觸發（同批次另有乾淨檔案，證明是豁免生效而非 H9b 空掃）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'motion_lab.html'), '<div>中文不應被掃到</div>');
    writeFileSync(join(tmp, 'web', 'templates', 'clean.html'), '<div>ok</div>');
    const r = runGuard(tmp);
    assert.equal(r.status, 0);
    assert.doesNotMatch(r.output, /motion_lab\.html/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔EXEMPT-3〕design_system/settings-components.html（子目錄整檔豁免）內含中文不觸發，但同目錄其他檔案仍受管轄', () => {
  const tmp = makeScratchRoot();
  try {
    mkdirSync(join(tmp, 'web', 'templates', 'design_system'), { recursive: true });
    writeFileSync(
      join(tmp, 'web', 'templates', 'design_system', 'settings-components.html'),
      '<div>豁免檔內中文</div>',
    );
    writeFileSync(join(tmp, 'web', 'templates', 'design_system', 'other.html'), '<div>非豁免中文</div>');
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0, '同目錄非豁免檔仍須被抓到');
    assert.doesNotMatch(r.output, /settings-components\.html/);
    assert.match(r.output, /other\.html/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔EXT-FILTER〕非 .html 副檔名（如 .txt）內含中文不被掃描（掃描根只收 .html）', () => {
  const tmp = makeScratchRoot();
  try {
    writeFileSync(join(tmp, 'web', 'templates', 'notes.txt'), '中文筆記，非模板檔');
    const r = runGuard(tmp);
    // 0 個 .html 檔案 → fail-closed RED（H9b 同一情境），但錯誤訊息必須是「掃到 0 個檔案」
    // 而非誤把 .txt 當成違規回報，證明副檔名過濾確實生效。
    assert.notEqual(r.status, 0);
    assert.match(r.output, /掃到 0 個檔案/);
    assert.doesNotMatch(r.output, /notes\.txt/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔RECURSE〕子目錄（如 _macros/）內的 .html 檔同樣被遞迴掃到', () => {
  const tmp = makeScratchRoot();
  try {
    mkdirSync(join(tmp, 'web', 'templates', '_macros'), { recursive: true });
    writeFileSync(join(tmp, 'web', 'templates', '_macros', 'pill.html'), '<span>子目錄中文</span>');
    const r = runGuard(tmp);
    assert.notEqual(r.status, 0);
    assert.match(r.output, /_macros[\\/]pill\.html:1/);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔real-repo〕真 repo 掃描目前零殘留（回歸總覽，非 mutation；含本 task 新增的 16 條行內 cjk-exempt(內容) 精確豁免）', () => {
  const r = spawnSync(process.execPath, [GUARD_PATH], { encoding: 'utf8' });
  assert.equal(r.status, 0, `${r.stdout}\n${r.stderr}`);
});
