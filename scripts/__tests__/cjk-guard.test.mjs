// cjk_guard_lint.mjs tokenizer 邊界測試（TASK-103-T8 §G/§I 表 1，9 類）。
// 零新依賴：Node 內建 node:test。跑：npm run test:cjk-guard
//
// 涵蓋：(1) `//` 在字串內 (2) http:// URL (3) 多行樣板字面行號 (4) ${} 內字串
// (5) ${} 內物件字面 brace-depth (6) 巢狀樣板字面 (7) <script> 內的 `//`
// (8) Jinja {# #} 內含中文 (9) HTML 屬性值 vs 屬性名。
//
// 每個 hit 的 offset 是相對於傳入 text 的絕對字元位置；本檔用 text.slice(0, offset)
// 的 '\n' 計數換算行號（與 cjk_guard_lint.mjs 內部 buildLineIndex/offsetToLine 等價，
// 兩者可各自實作而不互相 import——tokenizer 是被測對象，不應依賴受測腳本自己的行號工具）。

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { tokenizeJS, tokenizeHTML } from '../cjk_guard_lint.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const GUARD_PATH = join(__dirname, '..', 'cjk_guard_lint.mjs');

function lineOf(text, offset) {
  return text.slice(0, offset).split('\n').length;
}
function textOfHit(text, hit) {
  return text.slice(hit.offset, hit.offset + 6);
}

test('〔1〕`//` 出現在字串內 → 回報 1 個 hit（"中文" 在 STRING 內，// 不觸發 LINE_COMMENT）', () => {
  const src = 'const s = "a//b中文";';
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  assert.equal(textOfHit(src, hits[0]), '中文";');
});

test('〔2〕http:// URL 字串 → hit（"例子" 在 STRING 內）', () => {
  const src = 'const u = "http://例子.com";';
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  assert.equal(textOfHit(src, hits[0]).startsWith('例子'), true);
});

test('〔3〕多行樣板字面 → hit 且行號指向第二行', () => {
  const src = '`line1\nline2中文`;';
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  assert.equal(lineOf(src, hits[0].offset), 2);
});

test('〔4〕${} 內含字串 → hit（內部字串仍在 STRING 狀態）', () => {
  const src = "`${ '內部中文' }`;";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  assert.equal(textOfHit(src, hits[0]).startsWith('內部中文'), true);
});

test('〔5〕${} 內含物件字面（brace depth）→ hit（不因第一個 } 提前彈出）', () => {
  const src = "`${ {a:'中文'}.a }`;";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1, 'brace depth 錯誤會漏檢或誤報，兩者都不對');
  assert.equal(textOfHit(src, hits[0]).startsWith('中文'), true);
});

test('〔5b〕${} 內物件字面之後、TEMPLATE 收尾之後的內容不得誤判為仍在 TEMPLATE 內', () => {
  // 驗證 } 只在 braceDepth 歸零時才彈回 TEMPLATE；若過早彈出，後面這個新字串會被誤判成
  // 已經離開 TEMPLATE 而在 CODE 狀態 —— 但因為它本來就是合法字串，兩種狀態都會回報，
  // 用行為上更精確的方式驗證：物件字面外的第二個獨立字串仍要能正確被抓到。
  const src = "`${ {a:'甲'}.a }` ; const y = '乙';";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 2);
});

test('〔5c〕brace-depth 對「巢狀物件字面 + 之後的 // 註解」的不變式（獨立 reviewer N2）：\n' +
  '    depth 錯亂會讓 CODE 提早彈回 TEMPLATE，使 `//` 不再被當註解、其後中文被誤報成 hit', () => {
  // 反例矩陣：〔5〕〔5b〕都用「只巢一層」的物件字面，無法戳破「遇任何 } 就無條件 pop」這種
  // 壞掉的簡化實作——因為只巢一層時，第一個 `}` 本來就該是 depth 歸零的那個，行為碰巧一致。
  // 本例故意巢兩層（{a:{b:1}}），中間會出現一個「depth 還沒歸零」的 `}`；若實作把它當成
  // 收尾（無條件 pop），CODE frame 提早消失、").a.b // 中文註解" 會被當成已經回到 TEMPLATE
  // 的純文字掃描，`//` 不再觸發 LINE_COMMENT，"中文註解" 便被誤判成一個 hit（應為 0）。
  const src = '`${ {a:{b:1}}.a.b // 中文註解\n + 1 }`;';
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 0, 'depth 正確時 // 之後是真註解，中文註解不應回報');
});

// ============================================================================
// 獨立 reviewer 對抗性審查（28 條攻擊）BLOCKER 1-3 regression（Opus 複驗屬實後修正）
// ============================================================================

test('〔BLOCKER-1〕<SCRIPT>...</SCRIPT> 大寫關標籤 → 不得吞掉檔案剩餘部分', () => {
  // 開標籤偵測有 toLowerCase()，關標籤搜尋原本用大小寫敏感的 indexOf('</script>')，
  // 導致大寫或混合大小寫關標籤永遠找不到 —— 整個檔案剩餘內容被誤當成 script body 吞掉，
  // 後面所有可見文字的 CJK 全部隱形（本 task 最嚴重的一條：不是漏一個字串，是漏半個檔案）。
  const html = '<SCRIPT>var a=1;</SCRIPT>\n<div>大寫標籤後的中文可見文字</div>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 1, '大寫關標籤之後的可見文字必須仍被掃到');
  assert.equal(textOfHit(html, hits[0]).startsWith('大寫標籤'), true);
});

test('〔BLOCKER-1b〕<STYLE>...</STYLE> 大寫關標籤 → 同一 bug 的姊妹案例', () => {
  const html = '<STYLE>.x{color:red}</STYLE>\n<div>樣式後中文</div>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 1);
});

test('〔BLOCKER-1c〕<script SRC="..."> 大寫屬性名 → 外部腳本的殘留 body 不得被誤當內聯掃描', () => {
  // 自我攻擊複查時發現的姊妹案例：hasSrc 判斷原本也大小寫敏感，SRC= 大寫會被漏判成
  // 「沒有 src」，導致外部腳本標籤間的殘留死文字被誤當內聯 JS 掃描。用字串字面（而非裸
  // identifier）當殘留內容，才能真的戳出行為差異——裸 CODE 狀態字元本來就不掃 CJK
  // （合法 JS 識別字可以是中文變數名，不算 UI copy），只有字串字面內容才會被誤報。
  const html = '<script SRC="/static/x.js">var x = "殘留字串不應被掃";</script>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 0, 'src 屬性（大寫）存在時，body 內的字串字面也不該被掃到');
});

test('〔SELF-ATTACK-1〕<script data-src="..."> 不得被誤判為外部腳本（\\b word boundary 誤配連字號屬性名）', () => {
  // BLOCKER-1 修完後的自我攻擊複查追加發現（非獨立 reviewer 原始 3 條之一）：`\bsrc\s*=`
  // 的 `\b` 在連字號前後也成立，會誤配 `data-src=` 這種屬性名，讓「其實沒有真正 src=」的
  // 內聯 <script> 被誤判成外部腳本、跳過其 body 掃描——這個方向是漏檢（CD-12 不可接受），
  // 比原本已修的 hasSrc 大小寫問題更嚴重。改用 `(?:^|\s)src\s*=` 要求 src 前必須是字串
  // 開頭或空白字元。
  const html = '<script data-src="lazy-marker">const s = "本該被掃到的中文";</script>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 1, 'data-src 不是真正的 src，body 必須照常被當內聯 JS 掃描');
});

test('〔SELF-ATTACK-1b〕真正的 src= 仍正確被辨識為外部腳本（不誤傷）', () => {
  const html = '<script defer src="/static/x.js">殘留內容不應被掃</script>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 0);
});

test('〔BLOCKER-2〕window.t fallback 左邊界：`foo.window.t ? window.t(...) : "中文"` 不得被誤豁免', () => {
  // 原 regex 沒有左邊界，任何以 window.t 結尾的成員存取都會命中，變成過度豁免（假陰性方向，
  // CD-12 明文不可接受）。加 (?<![A-Za-z0-9_$.]) 後，前面接 `.` 的偽裝三元式不再命中。
  const src = "const a = foo.window.t ? window.t('k') : '偽裝三元式的中文';";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1, '偽裝的 fallback 不應被豁免，中文必須回報');
  assert.equal(textOfHit(src, hits[0]).startsWith('偽裝三元'), true);
});

test('〔BLOCKER-2b〕真正的 window.t fallback（左邊界是行首/括號）仍正常豁免，不誤傷', () => {
  const src = "const label = window.t ? window.t('notif.title') : '通知';";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 0, '合法 fallback 不應因新加的左邊界被誤傷');
});

test('〔BLOCKER-3〕\\uXXXX escape 寫的中文必須被偵測（不可靠原始 codepoint 字面比對繞過）', () => {
  // "中文" 原始碼字面完全沒有 CJK codepoint（只有 ASCII 中 這些字元），
  // 純看字面 isCJK() 會漏掉。CD-12「假陰性不可接受」，T8 卡任務說明列為關鍵測試項。
  const src = "const esc = \"\\u4e2d\\u6587\";\nconst lit = '字面對照';";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 2, 'escape 中文（第 1 行）與字面中文（第 2 行）都必須各回報 1 個 hit');
  assert.equal(lineOf(src, hits[0].offset), 1, 'escape 那行的 hit 行號必須正確');
  assert.equal(lineOf(src, hits[1].offset), 2);
});

test('〔BLOCKER-3b〕\\u{...} 花括號 codepoint escape 形式也要被偵測', () => {
  const src = "const esc = \"\\u{4e2d}\\u{6587}\";";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1, '兩個相鄰 escape 應合併成一個 run（比照字面相鄰字元的合併行為）');
});

test('〔BLOCKER-3c〕escape 中文在前、字面中文在後 → 合併成同一個 hit run 且 offset 落在 escape 起點', () => {
  // 刻意把 escape 放在「前面、無字面 CJK 打頭」——若把 escape 換成「字面在前」寫法，即使
  // escape 解碼整個失效，前面的字面字元仍會先開 run、string 結尾 flush 時照樣報 1 個 hit，
  // 測試會誤判通過（本卡開發時踩過這個坑：3c/3e 原始版本用「字面在前」寫，revert BLOCKER-3
  // 後兩者都沒有真的轉紅，是假的 regression case）。用 escape 在前 + 斷言 offset 精確落在
  // escape 的反斜線位置，才能確保「escape 沒被解碼」時完全沒有 run 可以 flush。
  const src = "const s = \"\\u4e2d文\";"; // 中(中，escape) + 文(字面)，緊鄰無空隙
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1, '字面字元與 escape 字元相鄰應視為同一個連續 CJK run');
  const escapeOffset = src.indexOf('\\u4e2d');
  assert.equal(hits[0].offset, escapeOffset, 'run 起點必須是 escape 本身，不是後面的字面字元');
});

test('〔BLOCKER-3d〕非中文的 \\uXXXX escape（如 \\u0041="A"）不誤報為 hit', () => {
  const src = "const s = \"\\u0041\\u0042\";"; // = "AB"，非 CJK
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 0);
});

test('〔BLOCKER-3e〕樣板字面（TEMPLATE 狀態）內的 \\u escape 中文（無字面字元打頭）同樣要被偵測', () => {
  const src = "const s = `\\u4e2d\\u6587結尾`;"; // escape 開頭、字面「結尾」在後——同 3c 理由
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  const escapeOffset = src.indexOf('\\u4e2d');
  assert.equal(hits[0].offset, escapeOffset);
});

// ============================================================================
// BUG 5（獨立 reviewer sibling 掃描，二審複驗屬實）：extname() 大小寫敏感，
// 副檔名非全小寫的檔案在 walk() 收檔階段就整個消失（不是掃了漏判，是連候選清單都進不去）。
// ============================================================================

test('〔BUG-5〕副檔名大小寫不敏感：.JS/.Html 混合大小寫檔案必須被掃到（黑箱驗證整條 walk→dispatch→tokenize 管線）', () => {
  // 為什麼用 child_process 跑真正的 CLI 入口、而不是把 walk() export 出來直接單元測：
  //
  // 這個 bug 其實橫跨兩個獨立的比對點，兩點都要修對才算真的修好：
  //   1. walk() 的收檔過濾 exts.includes(extname(e.name).toLowerCase())——決定檔案「進不進
  //      files 清單」。
  //   2. main() 的 dispatch ext === '.html' ? tokenizeHTML(text) : tokenizeJS(text)——決定
  //      「進了清單之後，用哪支 tokenizer 解析」。
  //
  // 只單元測 walk()（就算 export 出來）只能證明第 1 點，證明不了第 2 點：一個 .Html 檔就算
  // 僥倖被 walk() 收進清單，若 dispatch 那行沒有同步 .toLowerCase()，`ext === '.html'`
  // 仍會因為大小寫不符而判 false，整份 HTML 被送去 tokenizeJS 當純 JS 碼掃——HTML 標籤/
  // 屬性語法在 JS tokenizer 眼裡全部落在裸 CODE 狀態（不在任何 STRING/TEMPLATE 內），
  // 完全不會被回報成 hit，等於「有掃但零偵測」，比「根本沒收進清單」更隱蔽。黑箱跑真正的
  // CLI 入口（child_process.spawnSync）才能一次驗到整條管線是否真的端到端正確，且不需要
  // 為了測試把內部 helper 硬 export 出去，維持與其餘 3 支既有 .mjs 一致的封裝慣例
  // （walk() 從未被其他模組 import 過）。
  const tmp = mkdtempSync(join(tmpdir(), 'cjk-guard-bug5-'));
  try {
    mkdirSync(join(tmp, 'web', 'static', 'js'), { recursive: true });
    mkdirSync(join(tmp, 'web', 'templates'), { recursive: true });
    writeFileSync(join(tmp, 'web', 'static', 'js', 'Probe.JS'), 'const s = "大寫副檔名內的中文";\n');
    writeFileSync(join(tmp, 'web', 'static', 'js', 'lower.js'), 'const s = "小寫對照組中文";\n');
    writeFileSync(join(tmp, 'web', 'templates', 'Probe.Html'), '<div>混合大小寫副檔名的中文</div>');

    const result = spawnSync(process.execPath, [GUARD_PATH, tmp], { encoding: 'utf8' });
    const output = `${result.stdout}\n${result.stderr}`;

    assert.match(output, /Probe\.JS:1\b/, '大寫 .JS 副檔名的檔案必須被掃到（walk 收檔這關不能漏）');
    assert.match(output, /lower\.js:1\b/, '小寫對照組必須仍正常被掃到（不因這次修法回歸）');
    assert.match(
      output,
      /Probe\.Html:1\b/,
      '混合大小寫 .Html 副檔名的檔案必須被掃到，且用正確的 HTML tokenizer 解析（而非被 dispatch 誤送去 tokenizeJS 導致零偵測）',
    );
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
});

test('〔6〕巢狀樣板字面 → hit（stack 而非單一旗標）', () => {
  const src = '`${ `內${1}層中文` }`;';
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 2, '「內」與「層中文」被 ${1} 隔開為兩個獨立 run');
  assert.equal(textOfHit(src, hits[0]).startsWith('內'), true);
  assert.equal(textOfHit(src, hits[1]).startsWith('層中文'), true);
});

test('〔7a〕<script> 內的 `//` 註解 → 無 hit（LINE_COMMENT 正確辨識，遞交 JS 子狀態機）', () => {
  const html = '<script>// 中文註解\nconst x=1;</script>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 0);
});

test('〔7b〕<script> 內的字串（非註解）→ hit（證明子狀態機真的在掃，不是整段跳過）', () => {
  const html = '<script>// 中文註解\nconst x = "測試中文";</script>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 1);
  assert.equal(lineOf(html, hits[0].offset), 2);
});

test('〔7c〕<script src="..."> 外部腳本 → body 不掃（即使 body 內含中文字面）', () => {
  const html = '<script src="/static/x.js">中文占位</script>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 0);
});

test('〔8〕Jinja {# #} 內含中文 → 無 hit', () => {
  const html = '<div>{# 這是中文註解 #}</div>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 0);
});

test('〔9a〕HTML 屬性值（非 JS-bearing）vs 屬性名：TEXT 內容有 hit，屬性名內容不算', () => {
  const html = '<div data-測試="ok">中文</div>';
  const hits = tokenizeHTML(html);
  // 屬性名 "data-測試" 不符合 ATTR_RE 的 name 字元類（\w 不含 CJK），故整條屬性不會被
  // 當成合法屬性掃描；唯一 hit 應來自 TEXT 內容「中文」。
  assert.equal(hits.length, 1);
  assert.equal(textOfHit(html, hits[0]).startsWith('中文'), true);
});

test('〔9b〕JS-bearing 屬性值（x-show 字串）→ hit', () => {
  const html = `<div x-show="foo === '測試中文'"></div>`;
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 1);
});

test('〔9c〕JS-bearing 屬性值內的 `//` 註解（x-data blob，跨行）→ 無 hit（子解析辨識為 LINE_COMMENT）', () => {
  // 比照 base.html:411-475 的 <body x-data="{...}"> 內嵌 JS blob 真實案例：註解在某行，
  // 下一行接續合法（無中文）程式碼——驗證 `//` 只吃到真實換行為止，不多吃、不少吃。
  const html = '<body x-data="{ open: false, // 開新分頁中文註解\n toggle(){ return 1; } }"></body>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 0);
});

test('〔9d〕非 JS-bearing 屬性值（class）含中文 → hit', () => {
  const html = '<div class="測試"></div>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 1);
});

// ---- 額外：console.* 呼叫範圍豁免標記（CD-3，非 lint 結果本身，是 tokenizer 事實回報）----
test('〔extra-a〕console.warn(...) 內的字串 → hit.exempt === "console"', () => {
  const src = "console.warn('中文診斷');";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  assert.equal(hits[0].exempt, 'console');
});

test('〔extra-b〕多行 console.warn(...) → hit.exempt === "console" 且行號正確（CD-3 核心案例）', () => {
  const src = "console.warn(\n    'a' + b +\n    '逾時中文診斷',\n);";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  assert.equal(hits[0].exempt, 'console');
  assert.equal(lineOf(src, hits[0].offset), 3);
});

test('〔extra-c〕非 console 呼叫（foo.warn）內的字串 → hit.exempt === null（不誤放行別的物件）', () => {
  const src = "foo.warn('中文');";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  assert.equal(hits[0].exempt, null);
});

test('〔extra-d〕巢狀呼叫：console.warn("a", foo("中文")) → 最內層呼叫非 console，不豁免', () => {
  const src = "console.warn('a', foo('中文'));";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  assert.equal(hits[0].exempt, null, '最內層函式呼叫是 foo，不是 console，不應豁免');
});

// ---- 額外：正則字面量辨識（§G.3 實測踩過的坑）----
test('〔extra-e〕.replace(/"/g, ...) 後的字串仍正確被辨識為字串（不被正則吞掉狀態）', () => {
  const src = "s.replace(/\"/g, x).replace('中文', y);";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1);
  assert.equal(textOfHit(src, hits[0]).startsWith('中文'), true);
});

// ---- 額外：註解變體逐一驗證（不誤報，表 2 層③）----
test('〔extra-f〕/* 區塊註解 */ 內含中文 → 無 hit', () => {
  const src = '/* 這是中文區塊註解 */ const x = 1;';
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 0);
});

test('〔extra-g〕HTML <!-- --> 註解內含中文 → 無 hit', () => {
  const html = '<div><!-- 這是中文 HTML 註解 --></div>';
  const hits = tokenizeHTML(html);
  assert.equal(hits.length, 0);
});

// ---- 額外：window.t 三元 fallback 豁免（跳過區間精確性，裁決 4）----
test('〔extra-h〕window.t ? window.t(\'k\') : \'中文\' fallback → 無 hit（已是 i18n 路徑）', () => {
  const src = "const label = window.t ? window.t('notif.title') : '通知';";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 0);
});

test('〔extra-i〕window.t fallback 同一行尾端另有不相干的字串中文 → 仍必須 hit（跳過區間不可溢出整行）', () => {
  const src = "const label = window.t ? window.t('notif.title') : '通知'; const other = '測試中文';";
  const hits = tokenizeJS(src);
  assert.equal(hits.length, 1, '跳過區間只該覆蓋三元式本身，不可放行同行其他字串');
  assert.equal(textOfHit(src, hits[0]).startsWith('測試中文'), true);
});
