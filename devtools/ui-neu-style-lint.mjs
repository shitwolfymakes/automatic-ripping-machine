#!/usr/bin/env node
// Styling lint for ui-neu: markup carries block classes, state attributes,
// and layout-only utilities; everything else lives in CSS (spec 6.4, 10).
import { readFileSync, globSync } from 'node:fs';
import { resolve, dirname, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const FRONTEND = resolve(here, '../services/ui-neu/frontend');

const ALLOWED = [
	/^-?(m|mx|my|mt|mr|mb|ml|p|px|py|pt|pr|pb|pl)-(\d+(\.\d+)?|px|auto)$/,
	/^(gap|gap-x|gap-y|space-x|space-y)-\d+(\.\d+)?$/,
	/^(flex|inline-flex|grid|inline-grid|contents|block|inline|inline-block|hidden)$/,
	/^(flex-row|flex-col|flex-wrap|flex-nowrap|flex-1|flex-auto|flex-none|grow|grow-0|shrink|shrink-0)$/,
	/^(items|justify|self|place-items|place-content)-[a-z]+$/,
	/^(col-span|row-span|col-start|col-end|order)-\d+$/,
	/^(grid-cols|grid-rows)-\d+$/,
	/^(w-full|h-full|min-w-0|min-h-0|max-w-(xs|sm|md|lg|xl|2xl|3xl|4xl|5xl|6xl|prose|full|none)|w-auto|h-auto)$/,
	/^(truncate|whitespace-[a-z-]+|break-[a-z]+|overflow-(auto|hidden|visible|scroll|x-auto|y-auto|x-hidden|y-hidden))$/,
	/^sr-only$/,
	/^(relative|absolute|inset-0|inset-x-0|inset-y-0|top-0|right-0|bottom-0|left-0)$/
];
const RESPONSIVE = /^(sm|md|lg|xl):/;
const BANNED_FAMILIES = /^(bg|text|border|ring|fill|stroke|from|to|via|divide|outline|shadow|rounded|font|tracking|leading|uppercase|lowercase|capitalize|italic|underline|transition|duration|ease|animate|opacity|cursor|z|dark|hover|focus|focus-visible|group-hover|disabled|active|placeholder)(-|:|$)/;
// table/table-row/table-cell are also Tailwind's own auto-generated
// display-* utility class names (display: table/table-row/table-cell are
// valid CSS keyword values) - Task 11 fix round 1 found these silently
// beat the table block's own @layer components rules regardless of
// selector specificity, since Tailwind's utilities land in a
// higher-priority cascade layer (fix round 2 moved the affected rules
// into that same layer rather than fighting it). The block's own bare
// `table`/`table-row`/`table-cell` classes are legitimate (that IS the
// vocabulary), but a RESPONSIVE-prefixed one (`sm:table-cell`,
// `md:table-row`, ...) is always the bare Tailwind display utility -
// this app's own table block never emits a responsive-prefixed variant
// of its own class names - so only the prefixed form is banned, keeping
// the block names the only legal (unprefixed) use.
const BANNED_TABLE_DISPLAY = /^(sm|md|lg|xl):(table|table-row|table-cell)$/;

const FLYOUT_ALLOW = new Set(['top', 'left', 'right', 'bottom', 'max-height']);
const CLASS_DIRECTIVE_ALLOW = new Set([]);

// Lints the whitespace-separated tokens of a class-attribute body (the text
// that would sit between the quotes of class="..."), reporting bare classes
// and utilities from the banned families. Expression fragments (the {...}
// scaffolding of a template ternary) are skipped; string literals already
// nested inside {...} are unwrapped by the caller before this runs.
function lintClassBody(body, filename, push) {
	const tokens = body.replace(/\{[^}]*\}/g, (expr) => expr.replace(/['"`]([^'"`]*)['"`]/g, ' $1 ')).split(/\s+/).filter(Boolean);
	for (const t of tokens) {
		if (t === ':' || t === '?') continue;
		if (/[{}?()=><!&|]/.test(t)) continue; // expression fragments
		const bare = t.replace(RESPONSIVE, '');
		if (ALLOWED.some((re) => re.test(bare))) continue;
		if (BANNED_TABLE_DISPLAY.test(t)) { push(`banned-utility:${t}`, body.slice(0, 80)); continue; }
		if (BANNED_FAMILIES.test(t) || BANNED_FAMILIES.test(bare) || /\[.*\]/.test(t)) push(`banned-utility:${t}`, body.slice(0, 80));
		// anything else is a vocabulary or local class: allowed
	}
}

export function lintSource(src, filename) {
	const out = [];
	const push = (kind, detail) => out.push({ file: filename, kind, detail });
	// 1. style="..." string attributes
	for (const m of src.matchAll(/\sstyle="([^"]*)"/g)) push('style-attr', m[1]);
	// 2. style:prop directives
	for (const m of src.matchAll(/\sstyle:([a-zA-Z-]+)=/g)) {
		const prop = m[1];
		if (prop.startsWith('--')) continue;
		if (/Flyout\.svelte$/.test(filename) && FLYOUT_ALLOW.has(prop)) continue;
		push('style-directive', prop);
	}
	// 3. class: directives
	for (const m of src.matchAll(/\sclass:([a-zA-Z0-9_-]+)/g)) {
		if (CLASS_DIRECTIVE_ALLOW.has(m[1])) continue;
		push('class-directive', m[1]);
	}
	// 4a. utilities in class="..." attributes (including string literals inside {...})
	for (const m of src.matchAll(/\sclass="([^"]*)"/g)) lintClassBody(m[1], filename, push);
	// 4b. utilities in class='...' attributes (single-quoted)
	for (const m of src.matchAll(/\sclass='([^']*)'/g)) lintClassBody(m[1], filename, push);
	// 4c. utilities in class={...} bindings: lint the string literals inside the braces
	for (const m of src.matchAll(/\sclass=\{([^}]*)\}/g)) {
		for (const lit of m[1].matchAll(/['"`]([^'"`]*)['"`]/g)) lintClassBody(lit[1], filename, push);
	}
	// 4d. utilities inside string literals in <script> blocks: a token counts only
	// when it looks class-shaped (contains '-' or ':'), so prose is never flagged.
	for (const script of src.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)) {
		for (const lit of script[1].matchAll(/['"`]([^'"`]*)['"`]/g)) {
			const tokens = lit[1].split(/\s+/).filter(Boolean);
			for (const t of tokens) {
				if (!/[-:]/.test(t)) continue;
				if (t === ':' || t === '?') continue;
				if (/[{}?()=><!&|]/.test(t)) continue;
				const bare = t.replace(RESPONSIVE, '');
				if (ALLOWED.some((re) => re.test(bare))) continue;
				if (BANNED_TABLE_DISPLAY.test(t)) { push(`banned-utility:${t}`, `script literal: ${lit[1].slice(0, 60)}`); continue; }
				if (BANNED_FAMILIES.test(t) || BANNED_FAMILIES.test(bare) || /\[.*\]/.test(t)) push(`banned-utility:${t}`, `script literal: ${lit[1].slice(0, 60)}`);
			}
		}
	}
	// 5. :global( without a comment on the previous line or trailing on the same line
	const style = src.match(/<style[^>]*>([\s\S]*?)<\/style>/);
	if (style) {
		const lines = style[1].split('\n');
		lines.forEach((line, i) => {
			if (!line.includes(':global(')) return;
			const prevIsComment = (lines[i - 1] || '').trim().startsWith('/*');
			const lineStartsComment = line.trim().startsWith('/*');
			const lineHasTrailingComment = /\/\*.*\*\//.test(line);
			if (!prevIsComment && !lineStartsComment && !lineHasTrailingComment) push('global-without-comment', line.trim());
		});
	}
	// 6. raw-colour-in-style: literal colours as CSS values inside <style>
	// blocks are banned (spec's strict token set - only var(--color-*) and
	// color-mix(...) against a token, plus the keywords transparent/
	// currentColor, are allowed). Strip comments first so a measurement note
	// like "baseline rgb(1,2,3)" is never flagged, then scan each
	// declaration's value (the text after ':' up to ';' or '}') for a hex
	// colour, an rgb()/rgba()/hsl()/hsla() function, or a bare white/black
	// keyword used as a value.
	if (style) {
		const noComments = style[1].replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, ' '));
		for (const decl of noComments.matchAll(/:\s*([^;{}]+)[;}]/g)) {
			const value = decl[1];
			const hexMatch = value.match(/#[0-9a-fA-F]{3,8}\b/);
			if (hexMatch) push('raw-colour-in-style', hexMatch[0]);
			const fnMatch = value.match(/\b(rgb|rgba|hsl|hsla)\(/);
			if (fnMatch) push('raw-colour-in-style', value.trim().slice(0, 60));
			const kwMatch = value.match(/\b(white|black)\b/);
			if (kwMatch) push('raw-colour-in-style', value.trim().slice(0, 60));
		}
	}
	return out;
}

function main() {
	const args = process.argv.slice(2);
	const report = args.includes('--report');
	const fi = args.indexOf('--files');
	const files = fi >= 0 ? args.slice(fi + 1).filter((a) => !a.startsWith('--')) : globSync('src/**/*.svelte', { cwd: FRONTEND }).map((f) => resolve(FRONTEND, f));
	const all = files.flatMap((f) => lintSource(readFileSync(f, 'utf8'), f));
	const byKind = {};
	for (const v of all) byKind[v.kind.split(':')[0]] = (byKind[v.kind.split(':')[0]] || 0) + 1;
	if (report) {
		console.log(JSON.stringify({ files: files.length, violations: all.length, byKind }));
		return;
	}
	for (const v of all) console.log(`${relative(FRONTEND, v.file)}: ${v.kind}  ${v.detail}`);
	console.log(`\n${all.length} violation(s) in ${files.length} file(s)`, byKind);
	process.exit(all.length ? 1 : 0);
}

if (process.argv[1] && fileURLToPath(import.meta.url) === resolve(process.argv[1])) main();
