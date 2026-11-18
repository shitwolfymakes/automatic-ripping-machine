// Tests for ui-neu's own ESLint rules. Run with `node --test eslint-rules/`.
import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { RuleTester } from 'eslint';
import svelteParser from 'svelte-eslint-parser';
import tsParser from '@typescript-eslint/parser';

import plugin from './index.js';
import noBannedCopyChars, { adviceFor, findBannedChar } from './no-banned-copy-chars.js';
import noInlineGlyph, { copiedGlyph, parseGlyphPaths } from './no-inline-glyph.js';

RuleTester.describe = describe;
RuleTester.it = it;

const svelte = new RuleTester({ languageOptions: { parser: svelteParser } });
const ts = new RuleTester({ languageOptions: { parser: tsParser } });

describe('plugin', () => {
	it('exposes both rules', () => {
		assert.deepEqual(Object.keys(plugin.rules).sort(), ['no-banned-copy-chars', 'no-inline-glyph']);
	});
});

describe('findBannedChar', () => {
	it('passes ASCII, accented letters, the no-break space and the degree sign', () => {
		assert.equal(findBannedChar('Plain text, 61°C ok'), null);
		assert.equal(findBannedChar('Volapük, Français, Norsk bokmål'), null);
	});

	it('returns the first banned character', () => {
		assert.equal(findBannedChar('a · b — c'), '·');
	});
});

describe('adviceFor', () => {
	it('names a replacement for known characters and a Glyph for anything else', () => {
		assert.equal(adviceFor('…'), 'use "..."');
		assert.equal(adviceFor('★'), 'use a <Glyph> icon');
	});
});

ts.run('no-banned-copy-chars (TS)', noBannedCopyChars, {
	valid: [
		"const a = 'Paused | 3 new lines';",
		'const b = `${x}-${y}`;',
		'// a comment may say anything — even this\nconst c = 1;',
		"const d = 'Volapük';",
		// an invalid escape in a tagged template has no cooked value
		'tag`\\unicode`;'
	],
	invalid: [
		{
			code: "const a = 'Paused · 3 new';",
			errors: [
				{ messageId: 'banned', data: { ch: '·', code: 'U+00B7', advice: 'use "|" between fields, or "," in prose' } }
			]
		},
		{ code: 'const b = `${x}–${y}`;', errors: [{ messageId: 'banned' }] },
		{ code: "const c = '\\u2014';", errors: [{ messageId: 'banned' }] }
	]
});

svelte.run('no-banned-copy-chars (Svelte)', noBannedCopyChars, {
	valid: [
		{ code: '<p title="a | b">Showing 1-20 of 40</p>', filename: 'a.svelte' },
		{ code: '<!-- comment — fine --><p>ok</p>', filename: 'a.svelte' },
		{ code: '<p>&nbsp;61&deg;C &amp; &lt;</p>', filename: 'a.svelte' },
		{ code: '<style>/* note — fine */ p { color: red; }</style>', filename: 'a.svelte' }
	],
	invalid: [
		{
			code: '<p>Custom&hellip;</p>',
			filename: 'a.svelte',
			errors: [{ messageId: 'banned', data: { ch: '…', code: 'U+2026', advice: 'use "..."' } }]
		},
		{ code: '<p title="a &rarr; b">x</p>', filename: 'a.svelte', errors: [{ messageId: 'banned' }] },
		{ code: '<button>&times;</button>', filename: 'a.svelte', errors: [{ messageId: 'banned' }] },
		{ code: '<span>★ 7.5</span>', filename: 'a.svelte', errors: [{ messageId: 'banned' }] }
	]
});

const GLYPHS = `export type GlyphName = 'check' | 'gear';
export const GLYPH_PATHS: Record<GlyphName, string> = {
	check: 'M5 13l4 4L19 7',
	// a comment between entries
	gear:
		'M1 1h2M3 3h4'
};`;
const glyphFile = join(mkdtempSync(join(tmpdir(), 'glyphs-')), 'glyph-names.ts');
writeFileSync(glyphFile, GLYPHS);
const options = [{ glyphFile }];

describe('parseGlyphPaths', () => {
	it('reads single-line and wrapped entries and skips comments and the type union', () => {
		assert.deepEqual(
			[...parseGlyphPaths(GLYPHS)],
			[
				['M5 13l4 4L19 7', 'check'],
				['M1 1h2M3 3h4', 'gear']
			]
		);
	});

	it('reads every glyph from the real table', () => {
		const real = parseGlyphPaths(readFileSync(new URL('../src/lib/ui/glyph-names.ts', import.meta.url), 'utf8'));
		assert.ok(real.size >= 30);
		assert.equal(real.get('M9 5l7 7-7 7'), 'chevron-right');
	});
});

describe('copiedGlyph', () => {
	it('is null for an svg with no paths', () => {
		assert.equal(copiedGlyph({ children: [] }, new Map()), null);
	});
});

svelte.run('no-inline-glyph', noInlineGlyph, {
	valid: [
		{ code: '<svg viewBox="0 0 24 24"><path d="M0 0h1" /></svg>', filename: 'a.svelte', options },
		{ code: '<svg viewBox="0 0 24 24"><circle cx="1" cy="1" r="1" /></svg>', filename: 'a.svelte', options },
		{ code: '<svg viewBox="0 0 24 24"><path d={dynamic} /></svg>', filename: 'a.svelte', options },
		{ code: '<svg><path d="M5 13l4 4L19 7" /><path d={x} /></svg>', filename: 'a.svelte', options },
		{ code: '<path d="M5 13l4 4L19 7" />', filename: 'a.svelte', options },
		{ code: '<svg>\n\t<path />\n\t{label}\n</svg>', filename: 'a.svelte', options }
	],
	invalid: [
		{
			code: '<svg viewBox="0 0 24 24"><path stroke-width="2" d="M5 13l4 4L19 7" /></svg>',
			filename: 'a.svelte',
			options,
			errors: [{ messageId: 'copy', data: { name: 'check' } }]
		},
		{
			code: '<button><svg><g><path d="M1 1h2" /><path d="M3 3h4" /></g></svg></button>',
			filename: 'a.svelte',
			options,
			errors: [{ messageId: 'copy', data: { name: 'gear' } }]
		}
	]
});

svelte.run('no-inline-glyph (default glyph file)', noInlineGlyph, {
	valid: [{ code: '<svg><path d="M0 0h1" /></svg>', filename: 'a.svelte' }],
	invalid: [
		{
			code: '<svg><path d="M9 5l7 7-7 7" /></svg>',
			filename: 'a.svelte',
			errors: [{ messageId: 'copy', data: { name: 'chevron-right' } }]
		}
	]
});
