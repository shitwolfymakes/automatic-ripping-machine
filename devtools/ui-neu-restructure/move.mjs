#!/usr/bin/env node
// Moves/renames files under services/ui-neu/frontend from a mapping and rewrites every reference to them.
// See README.md. Node built-ins only. All paths inside this module are repo-relative POSIX paths.
import { execFileSync } from 'node:child_process';
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { posix, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const FRONTEND = 'services/ui-neu/frontend';
const SKIP_DIRS = new Set(['node_modules', '.git', '.svelte-kit', 'coverage', 'test-results', 'build', 'dist']);
const CODE_EXT = /\.(ts|js|mjs|svelte)$/;
const TEXT_EXT = /\.(md|mjs|js|sh)$/;
const SPEC = String.raw`(?:\$lib\/|\.\.?\/)[^'"` + '`' + String.raw`\s]*`;

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const stripCodeExt = (p) => p.replace(/\.(ts|js)$/, '');

// ---------------------------------------------------------------- file discovery

function walk(repoRoot, dir, out = []) {
	const abs = resolve(repoRoot, dir);
	if (!existsSync(abs)) return out;
	for (const e of readdirSync(abs, { withFileTypes: true })) {
		const rel = posix.join(dir, e.name);
		if (e.isDirectory()) {
			if (!SKIP_DIRS.has(e.name)) walk(repoRoot, rel, out);
		} else out.push(rel);
	}
	return out;
}

function listScanFiles(repoRoot) {
	const inScope = (p) => /^(src|tests|site)\/|^[^/]+$/.test(p.slice(FRONTEND.length + 1));
	const code = walk(repoRoot, FRONTEND).filter((p) => CODE_EXT.test(p) && inScope(p));
	const text = [
		...walk(repoRoot, 'docs'),
		...walk(repoRoot, 'devtools').filter((p) => !p.startsWith('devtools/ui-neu-restructure/')),
		...walk(repoRoot, '.claude/memory'),
		...walk(repoRoot, 'site'),
		'CLAUDE.md',
	].filter((p) => (TEXT_EXT.test(p) || p === 'CLAUDE.md') && existsSync(resolve(repoRoot, p)));
	return [...code.map((path) => ({ path, mode: 'code' })), ...text.map((path) => ({ path, mode: 'text' }))];
}

// ---------------------------------------------------------------- mapping

function filesUnder(oldFiles, dir) {
	return [...oldFiles].filter((f) => f.startsWith(`${dir}/`));
}

function expandEntry(entry, oldFiles, explicit) {
	const from = `${FRONTEND}/${entry.from}`.replace(/\/$/, '');
	const to = `${FRONTEND}/${entry.to}`.replace(/\/$/, '');
	if (oldFiles.has(from)) return { files: [{ from, to }], folder: null };
	const under = filesUnder(oldFiles, from);
	if (!under.length) throw new Error(`mapping: no such file or folder: ${entry.from}`);
	const files = under.filter((f) => !explicit.has(f)).map((f) => ({ from: f, to: to + f.slice(from.length) }));
	return { files, folder: { from, to } };
}

export function expandMoves(mapping, oldFiles) {
	const entries = mapping.moves;
	const explicit = new Set(entries.map((e) => `${FRONTEND}/${e.from}`));
	const expanded = entries.map((e) => expandEntry(e, oldFiles, explicit));
	return { files: expanded.flatMap((x) => x.files), folders: expanded.map((x) => x.folder).filter(Boolean) };
}

export function validateMoves(files, oldFiles) {
	const froms = new Set(files.map((m) => m.from));
	const tos = new Set();
	for (const m of files) {
		if (tos.has(m.to)) throw new Error(`mapping: two files move to ${m.to}`);
		tos.add(m.to);
		if (oldFiles.has(m.to) || froms.has(m.to)) {
			if (m.to !== m.from) throw new Error(`mapping: ${m.to} already exists or is itself moved (chained moves are not supported)`);
		}
	}
}

// ---------------------------------------------------------------- specifier resolution

const dirOf = (p) => posix.dirname(p);
const withDot = (r) => (r === '' ? '.' : r.startsWith('.') ? r : `./${r}`);

export function resolveSpecifier(spec, importer, files) {
	const query = (spec.match(/[?#].*$/) ?? [''])[0];
	const pathPart = spec.slice(0, spec.length - query.length).replace(/\/$/, '');
	const alias = pathPart.startsWith('$lib/');
	const base = alias ? posix.join(`${FRONTEND}/src/lib`, pathPart.slice(5)) : posix.join(dirOf(importer), pathPart);
	const candidates = [
		[base, 'full'],
		[base.replace(/\.js$/, '.ts'), 'js-for-ts'],
		[`${base}.ts`, 'noext'],
		[`${base}.js`, 'noext'],
		[`${base}/index.ts`, 'dir'],
		[`${base}/index.js`, 'dir'],
	];
	const hit = candidates.find(([c, kind]) => files.has(c) && (kind !== 'js-for-ts' || base.endsWith('.js')));
	return hit ? { target: hit[0], kind: hit[1], alias, query } : null;
}

const FORMATTERS = {
	full: (t) => t,
	noext: stripCodeExt,
	dir: (t) => (/\/index\.(ts|js)$/.test(t) ? dirOf(t) : stripCodeExt(t)),
	'js-for-ts': (t) => t.replace(/\.ts$/, '.js'),
};

export function formatSpecifier(resolved, newTarget, newImporter) {
	const p = FORMATTERS[resolved.kind](newTarget);
	if (resolved.alias) {
		const rel = posix.relative(`${FRONTEND}/src/lib`, p);
		if (rel.startsWith('..')) throw new Error(`${newTarget} moves out of src/lib; its $lib import cannot be kept`);
		return `$lib/${rel}${resolved.query}`;
	}
	return withDot(posix.relative(dirOf(newImporter), p)) + resolved.query;
}

function rewriteSpecifier(spec, importer, ctx) {
	const resolved = resolveSpecifier(spec, importer, ctx.oldFiles);
	if (!resolved) return spec;
	const newTarget = ctx.moveMap.get(resolved.target) ?? resolved.target;
	const newImporter = ctx.moveMap.get(importer) ?? importer;
	const unchanged = newTarget === resolved.target && (resolved.alias || newImporter === importer);
	return unchanged ? spec : formatSpecifier(resolved, newTarget, newImporter);
}

// ---------------------------------------------------------------- text path forms

export function pathForms(p) {
	const lib = `${FRONTEND}/src/lib/`;
	const inFrontend = p.startsWith(`${FRONTEND}/`);
	const inLib = p.startsWith(lib);
	return [
		p,
		inFrontend ? p.slice(FRONTEND.length + 1) : null,
		inLib ? `$lib/${p.slice(lib.length)}` : null,
		inLib ? `$lib/${stripCodeExt(p.slice(lib.length))}` : null,
	];
}

export function buildFormMap(files, folders) {
	const map = new Map();
	for (const m of [...files, ...folders]) {
		const [olds, news] = [pathForms(m.from), pathForms(m.to)];
		olds.forEach((o, i) => o && news[i] && o !== news[i] && map.set(o, news[i]));
	}
	return map;
}

function textPattern(forms) {
	if (!forms.length) return null;
	const alt = [...forms].sort((a, b) => b.length - a.length).map(escapeRe).join('|');
	return String.raw`(?<![\w-]|\w\/)(?:${alt})(?![\w-]|\.\w)`;
}

function combinedRegex(forms, withSpecs) {
	const parts = [];
	if (withSpecs) parts.push(String.raw`(?<q>['"` + '`' + String.raw`])(?<spec>${SPEC})\k<q>`);
	const text = textPattern(forms);
	if (text) parts.push(`(?<text>${text})`);
	return parts.length ? new RegExp(parts.join('|'), 'g') : null;
}

export function rewriteContent(content, file, mode, ctx) {
	const re = combinedRegex([...ctx.formMap.keys()], mode === 'code');
	if (!re) return content;
	return content.replace(re, (m, ...args) => {
		const g = args[args.length - 1];
		if (g.text !== undefined) return ctx.formMap.get(g.text) ?? g.text;
		return `${g.q}${rewriteSpecifier(g.spec, file, ctx)}${g.q}`;
	});
}

// ---------------------------------------------------------------- survivors

function specSurvivors(path, content, finalFiles, goneFiles) {
	const out = [];
	for (const m of content.matchAll(new RegExp(String.raw`(['"` + '`' + String.raw`])(${SPEC})\1`, 'g'))) {
		if (resolveSpecifier(m[2], path, finalFiles)) continue;
		if (resolveSpecifier(m[2], path, goneFiles)) out.push(`${path}: ${m[2]}`);
	}
	return out;
}

function textSurvivors(path, content, oldForms) {
	const text = textPattern(oldForms);
	if (!text) return [];
	return [...content.matchAll(new RegExp(text, 'g'))].map((m) => `${path}: ${m[0]}`);
}

export function findSurvivors(entries, finalFiles, moves, formMap) {
	const goneFiles = new Set(moves.map((m) => m.from).filter((f) => !finalFiles.has(f)));
	const newForms = new Set(formMap.values());
	const oldForms = [...formMap.keys()].filter((f) => !newForms.has(f));
	const found = entries.flatMap(({ path, mode, content }) => [
		...(mode === 'code' ? specSurvivors(path, content, finalFiles, goneFiles) : []),
		...textSurvivors(path, content, oldForms),
	]);
	return [...new Set(found)];
}

// ---------------------------------------------------------------- plan / apply

export function buildPlan(repoRoot, mapping) {
	const oldFiles = new Set(walk(repoRoot, FRONTEND));
	const { files: moves, folders } = expandMoves(mapping, oldFiles);
	validateMoves(moves, oldFiles);
	const ctx = {
		oldFiles,
		moveMap: new Map(moves.map((m) => [m.from, m.to])),
		formMap: buildFormMap(moves, folders),
	};
	const entries = listScanFiles(repoRoot).map(({ path, mode }) => {
		const before = readFileSync(resolve(repoRoot, path), 'utf8');
		return { path, mode, before, content: rewriteContent(before, path, mode, ctx) };
	});
	const finalFiles = new Set([...oldFiles].map((f) => ctx.moveMap.get(f) ?? f));
	return { moves, folders, entries, finalFiles, ctx };
}

export function gitCommandsFor(move, index = 0) {
	if (move.from !== move.to && move.from.toLowerCase() === move.to.toLowerCase()) {
		const tmp = `${move.to}.codemod-tmp-${index}`;
		return [['mv', move.from, tmp], ['mv', tmp, move.to]];
	}
	return [['mv', move.from, move.to]];
}

export function applyPlan(repoRoot, plan, run = (args) => execFileSync('git', args, { cwd: repoRoot, stdio: 'pipe' })) {
	plan.moves.forEach((m, i) => {
		mkdirSync(resolve(repoRoot, dirOf(m.to)), { recursive: true });
		gitCommandsFor(m, i).forEach(run);
	});
	for (const e of plan.entries.filter((x) => x.content !== x.before)) {
		writeFileSync(resolve(repoRoot, plan.ctx.moveMap.get(e.path) ?? e.path), e.content);
	}
}

export function survivorsOnDisk(repoRoot, plan) {
	const entries = listScanFiles(repoRoot).map((f) => ({ ...f, content: readFileSync(resolve(repoRoot, f.path), 'utf8') }));
	const finalFiles = new Set(walk(repoRoot, FRONTEND));
	return findSurvivors(entries, finalFiles, plan.moves, plan.ctx.formMap);
}

function survivorsInPlan(plan) {
	const entries = plan.entries.map((e) => ({ ...e, path: plan.ctx.moveMap.get(e.path) ?? e.path }));
	return findSurvivors(entries, plan.finalFiles, plan.moves, plan.ctx.formMap);
}

export function run({ mapping, frontendRoot, dryRun = false, log = console.log }) {
	const repoRoot = resolve(frontendRoot, '../../..');
	const plan = buildPlan(repoRoot, mapping);
	const changed = plan.entries.filter((e) => e.content !== e.before);
	log(`${dryRun ? 'plan' : 'moving'}: ${plan.moves.length} file(s), ${changed.length} file(s) with rewritten references`);
	plan.moves.forEach((m) => log(`  ${m.from} -> ${m.to}`));
	changed.forEach((e) => log(`  rewrite ${e.path}`));
	if (!dryRun) applyPlan(repoRoot, plan);
	const survivors = dryRun ? survivorsInPlan(plan) : survivorsOnDisk(repoRoot, plan);
	survivors.forEach((s) => log(`SURVIVOR ${s}`));
	return { plan, survivors };
}

// ---------------------------------------------------------------- CLI

export function parseArgs(argv, defaultRoot) {
	const rest = argv.filter((a) => a !== '--dry-run');
	const rootAt = rest.indexOf('--root');
	const frontendRoot = rootAt >= 0 ? resolve(rest.splice(rootAt, 2)[1]) : defaultRoot;
	return { mappingFile: rest[0], dryRun: argv.includes('--dry-run'), frontendRoot };
}

function main() {
	const defaultRoot = resolve(fileURLToPath(import.meta.url), '../../..', FRONTEND);
	const { mappingFile, dryRun, frontendRoot } = parseArgs(process.argv.slice(2), defaultRoot);
	if (!mappingFile) {
		console.error('usage: move.mjs <mapping.json> [--dry-run] [--root <frontend dir>]');
		process.exit(2);
	}
	try {
		const mapping = JSON.parse(readFileSync(mappingFile, 'utf8'));
		const { survivors } = run({ mapping, frontendRoot, dryRun });
		process.exit(survivors.length ? 1 : 0);
	} catch (err) {
		console.error(`error: ${err.message}`);
		process.exit(2);
	}
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
