import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { lintSource } from './ui-neu-style-lint.mjs';

const scriptPath = fileURLToPath(new URL('./ui-neu-style-lint.mjs', import.meta.url));

const fx = (n) => readFileSync(new URL(`./ui-neu-style-lint-fixtures/${n}.svelte`, import.meta.url), 'utf8');

test('allowed fixture has no violations', () => {
	assert.deepEqual(lintSource(fx('allowed'), 'allowed.svelte'), []);
});

test('banned fixture reports every category', () => {
	const kinds = new Set(lintSource(fx('banned'), 'banned.svelte').map((v) => v.kind.split(':')[0]));
	for (const k of ['style-attr', 'style-directive', 'banned-utility', 'class-directive', 'global-without-comment', 'raw-colour-in-style']) assert.ok(kinds.has(k), k);
});

test('flyout position directives are allowlisted', () => {
	const src = '<div style:top="{y}px" style:left="{x}px" style:max-height="{h}px"></div>';
	assert.deepEqual(lintSource(src, 'src/lib/components/Flyout.svelte'), []);
	assert.equal(lintSource(src, 'src/lib/components/Other.svelte').length, 3);
});

test('custom property directives are always allowed', () => {
	assert.deepEqual(lintSource('<div style:--progress="{p}%"></div>', 'x.svelte'), []);
});

test('utilities inside class expressions are checked', () => {
	const v = lintSource('<div class="panel {open ? \'text-red-600\' : \'\'}"></div>', 'x.svelte');
	assert.equal(v.length, 1);
	assert.equal(v[0].kind, 'banned-utility:text-red-600');
});

test('variant-prefixed utilities are checked and flagged', () => {
	const v = lintSource('<div class="hover:bg-red-50 dark:text-white"></div>', 'x.svelte');
	assert.equal(v.length, 2);
});

test('responsive prefixes on allowed utilities are not flagged', () => {
	assert.deepEqual(lintSource('<div class="sm:gap-4 md:hidden"></div>', 'x.svelte'), []);
});

test('class={} bindings are linted via their string literals, including script literals', () => {
	const src = "<div class={labelClass}></div><script>const labelClass = 'text-sm font-medium text-gray-700';</script>";
	const v = lintSource(src, 'x.svelte');
	assert.equal(v.length, 3);
	assert.deepEqual(v.map((x) => x.kind).sort(), ['banned-utility:font-medium', 'banned-utility:text-gray-700', 'banned-utility:text-sm'].sort());
	for (const violation of v) assert.match(violation.detail, /^script literal: /);
});

test('single-quoted class attributes are linted', () => {
	const v = lintSource("<div class='rounded-lg'></div>", 'x.svelte');
	assert.equal(v.length, 1);
	assert.equal(v[0].kind, 'banned-utility:rounded-lg');
});

test('prose words in script literals are never flagged', () => {
	assert.deepEqual(lintSource("<script>const msg = 'Enter the text and border style';</script>", 'x.svelte'), []);
});

test('class={} ternaries of plain vocabulary classes are not flagged', () => {
	assert.deepEqual(lintSource("<div class={cond ? 'btn btn-sm' : 'btn'}></div>", 'x.svelte'), []);
});

test('grid-cols and grid-rows with a plain count are allowed', () => {
	assert.deepEqual(lintSource('<div class="sm:grid-cols-2 grid-rows-3"></div>', 'x.svelte'), []);
});

test('arbitrary-value grid-cols is still banned', () => {
	const v = lintSource('<div class="grid-cols-[44px_1fr]"></div>', 'x.svelte');
	assert.equal(v.length, 1);
	assert.equal(v[0].kind, 'banned-utility:grid-cols-[44px_1fr]');
});

test('responsive-prefixed table display utilities are banned (table/table-row/table-cell)', () => {
	const v = lintSource('<div class="sm:table md:table-row lg:table-cell"></div>', 'x.svelte');
	assert.equal(v.length, 3);
	assert.deepEqual(v.map((x) => x.kind).sort(), ['banned-utility:lg:table-cell', 'banned-utility:md:table-row', 'banned-utility:sm:table'].sort());
});

test('the table block\'s own unprefixed class names are still allowed', () => {
	assert.deepEqual(lintSource('<table class="table"><tr class="table-row"><td class="table-cell table-header table-sort table-right table-compact"></td></tr></table>', 'x.svelte'), []);
});

test(':global( with a trailing same-line comment needs no separate comment line', () => {
	const src = '<style>:global(.x) { color: red; } /* lucide svg */</style>';
	assert.deepEqual(lintSource(src, 'x.svelte'), []);
});

test('raw-colour-in-style flags a literal rgb() value', () => {
	const src = '<style>.a { background: rgb(1 2 3); }</style>';
	const v = lintSource(src, 'x.svelte');
	assert.equal(v.length, 1);
	assert.equal(v[0].kind, 'raw-colour-in-style');
});

test('raw-colour-in-style does not flag var(), color-mix() against a token, or transparent', () => {
	const src = '<style>.a { color: var(--color-text); background: color-mix(in srgb, var(--color-danger) 30%, transparent); border-color: transparent; }</style>';
	assert.deepEqual(lintSource(src, 'x.svelte'), []);
});

test('--report prints exactly one line: a JSON object with files, violations, byKind', () => {
	const out = execFileSync(process.execPath, [scriptPath, '--files', fileURLToPath(new URL('./ui-neu-style-lint-fixtures/banned.svelte', import.meta.url)), '--report'], { encoding: 'utf8' });
	const lines = out.split('\n').filter(Boolean);
	assert.equal(lines.length, 1);
	const parsed = JSON.parse(lines[0]);
	assert.equal(parsed.files, 1);
	assert.equal(typeof parsed.violations, 'number');
	assert.ok(parsed.violations > 0);
	assert.equal(typeof parsed.byKind, 'object');
});
