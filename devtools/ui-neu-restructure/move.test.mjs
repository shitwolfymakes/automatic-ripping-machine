import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, mkdirSync, readFileSync, writeFileSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cli, pathForms, buildFormMap, run, buildPlan, applyPlan, survivorsOnDisk, findSurvivors, parseArgs, gitCommandsFor, resolveSpecifier, formatSpecifier, expandMoves, validateMoves } from './move.mjs';

const F = 'services/ui-neu/frontend';
const script = fileURLToPath(new URL('./move.mjs', import.meta.url));

function fixture(files) {
	const root = mkdtempSync(join(tmpdir(), 'move-test-'));
	const git = (...a) => execFileSync('git', a, { cwd: root, stdio: 'pipe' });
	git('init', '-q');
	git('config', 'user.email', 't@example.com');
	git('config', 'user.name', 't');
	for (const [p, c] of Object.entries(files)) {
		mkdirSync(dirname(join(root, p)), { recursive: true });
		writeFileSync(join(root, p), c);
	}
	git('add', '-A');
	git('commit', '-q', '-m', 'fixture');
	const read = (p) => readFileSync(join(root, p), 'utf8');
	return { root, git, read, exists: (p) => existsSync(join(root, p)), frontendRoot: join(root, F), done: () => rmSync(root, { recursive: true, force: true }) };
}

const lib = (p) => `${F}/src/lib/${p}`;
const go = (fx, moves, opts = {}) => run({ mapping: { moves }, frontendRoot: fx.frontendRoot, log: () => {}, ...opts });

test('rewrites $lib imports with and without extension, keeping each style', () => {
	const fx = fixture({
		[lib('utils/session-routes.ts')]: 'export const a = 1;\n',
		[lib('a.ts')]: "import { a } from '$lib/utils/session-routes';\nimport { a as b } from '$lib/utils/session-routes.ts';\nimport { a as c } from '$lib/utils/session-routes.js';\n",
	});
	const { survivors } = go(fx, [{ from: 'src/lib/utils/session-routes.ts', to: 'src/lib/sessions/routes.ts' }]);
	assert.deepEqual(survivors, []);
	assert.equal(
		fx.read(lib('a.ts')),
		"import { a } from '$lib/sessions/routes';\nimport { a as b } from '$lib/sessions/routes.ts';\nimport { a as c } from '$lib/sessions/routes.js';\n",
	);
	assert.ok(fx.exists(lib('sessions/routes.ts')));
	assert.ok(!fx.exists(lib('utils/session-routes.ts')));
	assert.match(fx.git('status', '--porcelain').toString(), /^R/m);
	fx.done();
});

test('rewrites relative imports from a sibling and from a parent folder, in both directions', () => {
	const fx = fixture({
		[lib('utils/helper.ts')]: 'export const h = 1;\n',
		[lib('utils/sibling.ts')]: "import { h } from './helper';\nimport { x } from '../other/x';\n",
		[lib('other/x.ts')]: "export const x = 1;\nimport { h } from '../utils/helper.ts';\n",
		[lib('top.ts')]: "import { h } from './utils/helper';\n",
	});
	go(fx, [
		{ from: 'src/lib/utils/helper.ts', to: 'src/lib/shared/deep/helper.ts' },
		{ from: 'src/lib/utils/sibling.ts', to: 'src/lib/moved/sibling.ts' },
	]);
	assert.equal(fx.read(lib('other/x.ts')), "export const x = 1;\nimport { h } from '../shared/deep/helper.ts';\n");
	assert.equal(fx.read(lib('top.ts')), "import { h } from './shared/deep/helper';\n");
	assert.equal(fx.read(lib('moved/sibling.ts')), "import { h } from '../shared/deep/helper';\nimport { x } from '../other/x';\n");
	fx.done();
});

test('a moved importer keeps its relative imports of unmoved files pointing at them', () => {
	const fx = fixture({
		[lib('a/one.ts')]: "import { t } from './two';\nimport s from '../styles/s.css?raw';\n",
		[lib('a/two.ts')]: 'export const t = 1;\n',
		[lib('styles/s.css')]: 'x{}\n',
	});
	go(fx, [{ from: 'src/lib/a/one.ts', to: 'src/lib/b/c/one.ts' }]);
	assert.equal(fx.read(lib('b/c/one.ts')), "import { t } from '../../a/two';\nimport s from '../../styles/s.css?raw';\n");
	fx.done();
});

test('rewrites vi.mock, vi.importActual, dynamic import and re-export strings', () => {
	const fx = fixture({
		[lib('stores/x.ts')]: 'export const x = 1;\n',
		[lib('__tests__/x.test.ts')]: [
			"vi.mock('$lib/stores/x', () => ({}));",
			"const real = await vi.importActual('$lib/stores/x');",
			"const lazy = await import('../stores/x');",
			"export * from '../stores/x';",
			"export { x } from \"../stores/x\";",
			'const t = await import(`$lib/stores/x`);',
			'',
		].join('\n'),
	});
	const { survivors } = go(fx, [{ from: 'src/lib/stores/x.ts', to: 'src/lib/stores/ex.ts' }]);
	assert.deepEqual(survivors, []);
	assert.equal(
		fx.read(lib('__tests__/x.test.ts')),
		[
			"vi.mock('$lib/stores/ex', () => ({}));",
			"const real = await vi.importActual('$lib/stores/ex');",
			"const lazy = await import('../stores/ex');",
			"export * from '../stores/ex';",
			'export { x } from "../stores/ex";',
			'const t = await import(`$lib/stores/ex`);',
			'',
		].join('\n'),
	);
	fx.done();
});

test('handles .svelte.ts rune modules and .svelte components', () => {
	const fx = fixture({
		[lib('stores/handbrakeSchema.svelte.ts')]: 'export const s = $state(1);\n',
		[`${F}/src/lib/components/Card.svelte`]: "<script>\n\timport { s } from '$lib/stores/handbrakeSchema.svelte';\n\timport Box from './Box.svelte';\n</script>\n",
		[`${F}/src/lib/components/Box.svelte`]: '<div />\n',
	});
	go(fx, [
		{ from: 'src/lib/stores/handbrakeSchema.svelte.ts', to: 'src/lib/handbrake/schema.svelte.ts' },
		{ from: 'src/lib/components/Box.svelte', to: 'src/lib/components/ui/Box.svelte' },
	]);
	assert.equal(
		fx.read(`${F}/src/lib/components/Card.svelte`),
		"<script>\n\timport { s } from '$lib/handbrake/schema.svelte';\n\timport Box from './ui/Box.svelte';\n</script>\n",
	);
	fx.done();
});

test('resolves directory imports through index files and keeps the style', () => {
	const fx = fixture({
		[lib('pkg/index.ts')]: 'export const p = 1;\n',
		[lib('use.ts')]: "import { p } from './pkg';\nimport { q } from '$lib/pkg/';\n",
	});
	go(fx, [{ from: 'src/lib/pkg', to: 'src/lib/renamed' }]);
	assert.equal(fx.read(lib('use.ts')), "import { p } from './renamed';\nimport { q } from '$lib/renamed';\n");
	fx.done();
});

test('case-only rename goes through a temporary name and rewrites imports', () => {
	assert.deepEqual(gitCommandsFor({ from: 'a/Foo.ts', to: 'a/foo.ts' }, 3), [
		['mv', 'a/Foo.ts', 'a/foo.ts.codemod-tmp-3'],
		['mv', 'a/foo.ts.codemod-tmp-3', 'a/foo.ts'],
	]);
	assert.deepEqual(gitCommandsFor({ from: 'a/x.ts', to: 'b/x.ts' }), [['mv', 'a/x.ts', 'b/x.ts']]);
	const fx = fixture({ [lib('Foo.ts')]: 'export const f = 1;\n', [lib('u.ts')]: "import { f } from '$lib/Foo';\n" });
	go(fx, [{ from: 'src/lib/Foo.ts', to: 'src/lib/foo.ts' }]);
	assert.equal(fx.read(lib('u.ts')), "import { f } from '$lib/foo';\n");
	assert.ok(fx.exists(lib('foo.ts')));
	fx.done();
});

test('a folder entry moves everything under it, nested folders included', () => {
	const fx = fixture({
		[lib('utils/a.ts')]: 'export const a = 1;\n',
		[lib('utils/deep/b.ts')]: "import { a } from '../a';\nexport const b = a;\n",
		[lib('use.ts')]: "import { a } from '$lib/utils/a';\nimport { b } from './utils/deep/b';\n",
	});
	const { survivors } = go(fx, [{ from: 'src/lib/utils', to: 'src/lib/generic' }]);
	assert.deepEqual(survivors, []);
	assert.equal(fx.read(lib('use.ts')), "import { a } from '$lib/generic/a';\nimport { b } from './generic/deep/b';\n");
	assert.equal(fx.read(lib('generic/deep/b.ts')), "import { a } from '../a';\nexport const b = a;\n");
	fx.done();
});

test('an explicit file entry wins over its enclosing folder entry', () => {
	const oldFiles = new Set([`${F}/src/lib/u/a.ts`, `${F}/src/lib/u/b.ts`]);
	const { files } = expandMoves({ moves: [{ from: 'src/lib/u/a.ts', to: 'src/lib/x/a.ts' }, { from: 'src/lib/u', to: 'src/lib/v' }] }, oldFiles);
	assert.deepEqual(files.map((m) => m.to.slice(F.length + 9)), ['x/a.ts', 'v/b.ts']);
});

test('rewrites path references in markdown, CLAUDE.md, memory, site and comments', () => {
	const fx = fixture({
		[lib('utils/session-routes.ts')]: '// see src/lib/utils/session-routes.ts\nexport const a = 1;\n',
		'docs/dev.md': [
			'See `services/ui-neu/frontend/src/lib/utils/session-routes.ts`, `src/lib/utils/session-routes.ts`,',
			'`$lib/utils/session-routes` and `$lib/utils/session-routes.ts`. Not `src/lib/utils/session-routes.test.ts`.',
			'',
		].join('\n'),
		'CLAUDE.md': 'Edit src/lib/utils/session-routes.ts.\n',
		'.claude/memory/m.md': '../../services/ui-neu/frontend/src/lib/utils/session-routes.ts\n',
		'devtools/note.md': 'folder src/lib/utils/ here\n',
		'site/src/s.mjs': "const p = 'services/ui-neu/frontend/src/lib/utils/session-routes.ts';\n",
	});
	const { survivors } = go(fx, [{ from: 'src/lib/utils/session-routes.ts', to: 'src/lib/sessions/routes.ts' }]);
	assert.deepEqual(survivors, []);
	assert.equal(
		fx.read('docs/dev.md'),
		[
			'See `services/ui-neu/frontend/src/lib/sessions/routes.ts`, `src/lib/sessions/routes.ts`,',
			'`$lib/sessions/routes` and `$lib/sessions/routes.ts`. Not `src/lib/utils/session-routes.test.ts`.',
			'',
		].join('\n'),
	);
	assert.equal(fx.read('CLAUDE.md'), 'Edit src/lib/sessions/routes.ts.\n');
	assert.equal(fx.read('.claude/memory/m.md'), '../../services/ui-neu/frontend/src/lib/sessions/routes.ts\n');
	assert.equal(fx.read('site/src/s.mjs'), "const p = 'services/ui-neu/frontend/src/lib/sessions/routes.ts';\n");
	assert.equal(fx.read(lib('sessions/routes.ts')), '// see src/lib/sessions/routes.ts\nexport const a = 1;\n');
	fx.done();
});

test('folder references in markdown follow a folder move', () => {
	const fx = fixture({ [lib('utils/a.ts')]: 'export {};\n', 'docs/d.md': 'the src/lib/utils/ folder and src/lib/utils-extra stay\n' });
	go(fx, [{ from: 'src/lib/utils', to: 'src/lib/generic' }]);
	assert.equal(fx.read('docs/d.md'), 'the src/lib/generic/ folder and src/lib/utils-extra stay\n');
	fx.done();
});

test('survivor detection finds an old specifier or path left on disk', () => {
	const fx = fixture({ [lib('a.ts')]: 'export const a = 1;\n', [lib('u.ts')]: "import '$lib/a';\nimport { a } from './a';\n", 'docs/d.md': 'src/lib/a.ts\n' });
	const plan = buildPlan(fx.root, { moves: [{ from: 'src/lib/a.ts', to: 'src/lib/z.ts' }] });
	for (const e of plan.entries) e.content = e.before; // simulate a rewrite that missed everything
	applyPlan(fx.root, plan);
	const survivors = survivorsOnDisk(fx.root, plan);
	assert.deepEqual(survivors.sort(), [`${lib('u.ts')}: $lib/a`, `${lib('u.ts')}: ./a`, 'docs/d.md: src/lib/a.ts'].sort());
	fx.done();
});

test('findSurvivors ignores specifiers that still resolve and unrelated strings', () => {
	const entries = [{ path: `${F}/src/x.ts`, mode: 'code', content: "import './keep';\nconst s = '.';\nconst t = './missing';\n" }];
	const finalFiles = new Set([`${F}/src/keep.ts`]);
	assert.deepEqual(findSurvivors(entries, finalFiles, [], new Map()), []);
});

test('dry run prints the plan and changes nothing', () => {
	const fx = fixture({ [lib('a.ts')]: 'export const a = 1;\n', [lib('u.ts')]: "import '$lib/a';\n", 'docs/d.md': 'src/lib/a.ts\n' });
	const lines = [];
	const { plan, survivors } = go(fx, [{ from: 'src/lib/a.ts', to: 'src/lib/z.ts' }], { dryRun: true, log: (l) => lines.push(l) });
	assert.deepEqual(survivors, []);
	assert.equal(plan.moves.length, 1);
	assert.equal(fx.git('status', '--porcelain').toString(), '');
	assert.ok(fx.exists(lib('a.ts')));
	assert.ok(!fx.exists(lib('z.ts')));
	assert.match(lines.join('\n'), /plan: 1 file\(s\), 2 file\(s\) with rewritten references/);
	assert.match(lines.join('\n'), /src\/lib\/a\.ts -> .*src\/lib\/z\.ts/);
	fx.done();
});

test('CLI: real run, dry run, usage and mapping errors set the exit code', () => {
	const fx = fixture({ [lib('a.ts')]: 'export const a = 1;\n', [lib('u.ts')]: "import '$lib/a';\n" });
	const map = join(fx.root, 'map.json');
	writeFileSync(map, JSON.stringify({ moves: [{ from: 'src/lib/a.ts', to: 'src/lib/z.ts' }] }));
	const cli = (...a) => {
		try {
			return { code: 0, out: execFileSync('node', [script, ...a], { stdio: 'pipe' }).toString() };
		} catch (e) {
			return { code: e.status, out: String(e.stderr) };
		}
	};
	assert.equal(cli(map, '--dry-run', '--root', fx.frontendRoot).code, 0);
	assert.ok(fx.exists(lib('a.ts')));
	assert.equal(cli().code, 2);
	writeFileSync(join(fx.root, 'bad.json'), JSON.stringify({ moves: [{ from: 'src/lib/nope.ts', to: 'src/lib/q.ts' }] }));
	const bad = cli(join(fx.root, 'bad.json'), '--root', fx.frontendRoot);
	assert.equal(bad.code, 2);
	assert.match(bad.out, /no such file or folder: src\/lib\/nope\.ts/);
	assert.equal(cli(map, '--root', fx.frontendRoot).code, 0);
	assert.ok(fx.exists(lib('z.ts')));
	assert.equal(fx.read(lib('u.ts')), "import '$lib/z';\n");
	fx.done();
});

test('scans tests/, root config files and the frontend site folder as code', () => {
	const fx = fixture({
		[lib('a.ts')]: 'export const a = 1;\n',
		[`${F}/tests/fixtures/f.ts`]: "import { a } from '../../src/lib/a';\n",
		[`${F}/vitest.config.ts`]: "import { a } from './src/lib/a';\n",
		[`${F}/site/s.ts`]: "import { a } from '../src/lib/a';\n",
		[`${F}/e2e/untouched.ts`]: "import { a } from '../src/lib/a';\n",
	});
	go(fx, [{ from: 'src/lib/a.ts', to: 'src/lib/z.ts' }]);
	assert.equal(fx.read(`${F}/tests/fixtures/f.ts`), "import { a } from '../../src/lib/z';\n");
	assert.equal(fx.read(`${F}/vitest.config.ts`), "import { a } from './src/lib/z';\n");
	assert.equal(fx.read(`${F}/site/s.ts`), "import { a } from '../src/lib/z';\n");
	fx.done();
});

test('resolveSpecifier and formatSpecifier cover extension, js-for-ts and query styles', () => {
	const files = new Set([`${F}/src/lib/a.ts`, `${F}/src/lib/b.js`]);
	const imp = `${F}/src/lib/i.ts`;
	assert.equal(resolveSpecifier('./a.js', imp, files).kind, 'js-for-ts');
	assert.equal(resolveSpecifier('./b.js', imp, files).kind, 'full');
	assert.equal(resolveSpecifier('./nope', imp, files), null);
	assert.equal(resolveSpecifier('../../../../../../x', imp, files), null);
	const r = resolveSpecifier('./a.js?x=1', imp, files);
	assert.equal(formatSpecifier(r, `${F}/src/lib/m/z.ts`, imp), './m/z.js?x=1');
	assert.throws(
		() => formatSpecifier({ kind: 'full', alias: true, query: '' }, `${F}/src/other/z.ts`, imp),
		/moves out of src\/lib/,
	);
	assert.equal(formatSpecifier({ kind: 'dir', alias: false, query: '' }, `${F}/src/lib/p.ts`, imp), './p');
	assert.equal(formatSpecifier({ kind: 'dir', alias: false, query: '' }, `${F}/src/lib/i.ts`, imp), './i');
});

test('validateMoves rejects duplicate targets, existing targets and chained moves', () => {
	const old = new Set(['x/a', 'x/b', 'x/c']);
	assert.throws(() => validateMoves([{ from: 'x/a', to: 'y' }, { from: 'x/b', to: 'y' }], old), /two files move to y/);
	assert.throws(() => validateMoves([{ from: 'x/a', to: 'x/c' }], old), /already exists/);
	assert.throws(() => validateMoves([{ from: 'x/a', to: 'x/b' }, { from: 'x/b', to: 'x/q' }], old), /chained/);
	assert.doesNotThrow(() => validateMoves([{ from: 'x/a', to: 'x/a' }], old));
});

test('parseArgs reads the mapping file, --dry-run and --root in any order', () => {
	assert.deepEqual(parseArgs(['--dry-run', 'm.json'], '/d'), { mappingFile: 'm.json', dryRun: true, frontendRoot: '/d' });
	const p = parseArgs(['--root', '/r', 'm.json'], '/d');
	assert.equal(p.frontendRoot, '/r');
	assert.equal(p.mappingFile, 'm.json');
	assert.equal(p.dryRun, false);
});

test('a mapping that moves nothing referenced leaves content untouched', () => {
	const fx = fixture({ [lib('a.ts')]: "import './b';\n", [lib('b.ts')]: 'export {};\n', [lib('c.ts')]: 'export {};\n' });
	const { plan } = go(fx, [{ from: 'src/lib/c.ts', to: 'src/lib/d.ts' }]);
	assert.equal(plan.entries.filter((e) => e.content !== e.before).length, 0);
	fx.done();
});

test('an empty mapping is a no-op, text files and CLAUDE.md included', () => {
	const fx = fixture({ [lib('a.ts')]: 'export {};\n', 'docs/d.md': 'src/lib/a.ts\n', 'CLAUDE.md': 'x\n' });
	const { plan, survivors } = go(fx, []);
	assert.equal(plan.moves.length, 0);
	assert.deepEqual(survivors, []);
	fx.done();
});

test('pathForms and buildFormMap only pair forms that exist on both sides', () => {
	assert.deepEqual(pathForms('docs/x.md'), ['docs/x.md', null, null, null]);
	assert.deepEqual(pathForms(`${F}/src/routes/r.ts`), [`${F}/src/routes/r.ts`, 'src/routes/r.ts', null, null]);
	const map = buildFormMap([{ from: `${F}/src/lib/a.ts`, to: `${F}/src/other/a.ts` }], []);
	assert.deepEqual([...map.keys()], [`${F}/src/lib/a.ts`, 'src/lib/a.ts']);
});

test('strings that look like specifiers but resolve to nothing are left alone', () => {
	const src = "const g = import.meta.glob('../steps/*.svelte');\nconst up = '../../../../../../..';\nconst ok = '$lib/none';\n";
	const fx = fixture({ [lib('a.ts')]: 'export {};\n', [lib('g.ts')]: src });
	go(fx, [{ from: 'src/lib/a.ts', to: 'src/lib/b.ts' }]);
	assert.equal(fx.read(lib('g.ts')), src);
	fx.done();
});

test('a moved importer landing in the folder it imports gets a dot specifier', () => {
	const fx = fixture({ [lib('a/one.ts')]: "import { p } from './pkg';\n", [lib('a/pkg/index.ts')]: 'export const p = 1;\n' });
	go(fx, [{ from: 'src/lib/a/one.ts', to: 'src/lib/a/pkg/one.ts' }]);
	assert.equal(fx.read(lib('a/pkg/one.ts')), "import { p } from '.';\n");
	fx.done();
});

test('css files are scanned for @import specifiers', () => {
	const fx = fixture({ [lib('styles/a.css')]: 'a{}\n', [`${F}/src/app.css`]: "@import './lib/styles/a.css';\n" });
	go(fx, [{ from: 'src/lib/styles/a.css', to: 'src/lib/styles/base.css' }]);
	assert.equal(fx.read(`${F}/src/app.css`), "@import './lib/styles/base.css';\n");
	fx.done();
});

test('moving a folder into its own descendant reports no false survivors', () => {
	const fx = fixture({ [lib('c/a.ts')]: 'export {};\n', 'docs/d.md': 'folder src/lib/c and src/lib/c/a.ts\n' });
	const { survivors } = go(fx, [{ from: 'src/lib/c', to: 'src/lib/c/sub' }]);
	assert.deepEqual(survivors, []);
	assert.equal(fx.read('docs/d.md'), 'folder src/lib/c/sub and src/lib/c/sub/a.ts\n');
	fx.done();
});

test('run reports a survivor through the log and cli exits 1', () => {
	const fx = fixture({ [lib('a.ts')]: 'export {};\n', [lib('p.ts')]: "const path = './src/lib/a.ts';\n" });
	const lines = [];
	const { survivors } = go(fx, [{ from: 'src/lib/a.ts', to: 'src/lib/z.ts' }], { log: (l) => lines.push(l) });
	assert.deepEqual(survivors, [`${lib('p.ts')}: src/lib/a.ts`]);
	assert.ok(lines.includes(`SURVIVOR ${lib('p.ts')}: src/lib/a.ts`));
	fx.done();

	const fx2 = fixture({ [lib('a.ts')]: 'export {};\n', [lib('p.ts')]: "const path = './src/lib/a.ts';\n" });
	const map = join(fx2.root, 'map.json');
	writeFileSync(map, JSON.stringify({ moves: [{ from: 'src/lib/a.ts', to: 'src/lib/z.ts' }] }));
	const out = [];
	assert.equal(cli([map, '--root', fx2.frontendRoot], '/unused', { log: (l) => out.push(l), error: () => {} }), 1);
	assert.ok(out.some((l) => l.startsWith('SURVIVOR ')));
	fx2.done();
});

test('cli returns 2 for a missing mapping, a missing --root value and an unreadable mapping', () => {
	const errors = [];
	const io = { log: () => {}, error: (e) => errors.push(e) };
	assert.equal(cli([], '/d', io), 2);
	assert.equal(cli(['m.json', '--root'], '/d', io), 2);
	assert.equal(cli(['/nonexistent/m.json'], '/d', io), 2);
	assert.match(errors[0], /usage: move\.mjs/);
	assert.match(errors[1], /--root needs a directory/);
});

test('cli returns 0 for a clean run', () => {
	const fx = fixture({ [lib('a.ts')]: 'export {};\n' });
	const map = join(fx.root, 'map.json');
	writeFileSync(map, JSON.stringify({ moves: [{ from: 'src/lib/a.ts', to: 'src/lib/z.ts' }] }));
	assert.equal(cli([map, '--root', fx.frontendRoot, '--dry-run'], '/d', { log: () => {}, error: () => {} }), 0);
	fx.done();
});
