#!/usr/bin/env node
/**
 * css-guard.mjs — contextual/relational CSS-block guard（96c，zero-dep）
 *
 * 承接 stylelint 標準 rule 表達不了的 selector-scoped / relational / 存在性 /
 * 跨 media-block breakpoint 值對齊 / inline-style token 掃描（CD-96c-1〔b〕）。
 *
 * T1：骨架 + 兩 helper（stripCssComments / parseRuleBlocks，port 自
 * test_fluent_materials_guards.py 的 _strip_css_comments / _parse_rule_blocks）
 * + 空 RULES 表 + runner。實際規則於 T2–T4 落地（T2 fluent method、T3
 * poster-crop 家族 + handoff、T4 motion_lab inline）。
 *
 * 非 pytest（遵 CLAUDE.md「lint 守衛寫 lint config、不寫 pytest」）。串 `npm run lint`。
 */

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join, resolve } from 'node:path';

const __dirname = dirname(fileURLToPath(import.meta.url));
// 可傳 <scratch-root> 覆蓋 repo root（mutation 自驗指向 scratch 副本，不污染真檔，
// 比照 static_guard_lint.mjs <scratch-root> / i18n_lint.mjs <locale-dir> 房規）。
// 空殼 T1 下無 RULES 讀檔，故 arg 只需被接受即可（exit 0）；T2–T4 rule 透過
// CSS(rel) resolve target，scratch 副本自動生效。
const ROOT = process.argv[2] ? resolve(process.argv[2]) : join(__dirname, '..');
// rule 用此 resolve target CSS 檔（T2 起使用）
const CSS = (rel) => join(ROOT, 'web', 'static', 'css', rel);

let hadError = false;
function fail(msg) {
  console.error(`✗ css-guard: ${msg}`);
  hadError = true;
}

// ── ported helpers（忠實鏡射 Python，CD-96c-2；T2 起由 RULES 使用）──

// _strip_css_comments：移除 /* … */ 區塊註解（可跨行）
function stripCssComments(text) {
  return text.replace(/\/\*[\s\S]*?\*\//g, '');
}

// _parse_rule_blocks：逐字元走訪追 brace depth，depth 歸 0 時收 {selector, declarations}。
// @media wrapper 自然被當 depth-1 外層、回傳最內層 rule block（忠實鏡射 Python 逐字元
// 迴圈，非 regex 猜大括號配對）。
function parseRuleBlocks(cssText) {
  const blocks = [];
  let depth = 0;
  let start = 0;
  let selector = '';
  let blockStart = 0;
  for (let i = 0; i < cssText.length; i += 1) {
    const ch = cssText[i];
    if (ch === '{') {
      if (depth === 0) {
        selector = cssText.slice(start, i).trim();
        blockStart = i + 1;
      }
      depth += 1;
    } else if (ch === '}') {
      depth -= 1;
      if (depth === 0) {
        blocks.push({ selector, declarations: cssText.slice(blockStart, i) });
        start = i + 1;
      }
    }
  }
  return blocks;
}

// ── 表驅動 rule-set（T1 空殼；規則於 T2–T4 落地）──
const RULES = [];

// ── runner（收集全部違規再退，比照 i18n_lint hadError 累積器，非首條即退）──
for (const rule of RULES) {
  // T2–T4：讀 CSS(rule.file) → stripCssComments → parseRuleBlocks → 檢查 → fail()
  void rule;
  void CSS;
  void readFileSync;
  void stripCssComments;
  void parseRuleBlocks;
}

if (hadError) process.exit(1);
console.log(`✓ css-guard: ${RULES.length} 條 CSS-block guard 全過`);
