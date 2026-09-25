import { test, before } from 'node:test';
import assert from 'node:assert/strict';
import { collectPages } from '../src/collect.mjs';
import { createResolver } from '../src/links.mjs';
import { createRenderer } from '../src/render.mjs';
import { fixtureTree, MANIFEST } from './helpers.mjs';

let renderer;
before(async () => {
	renderer = await createRenderer();
});

function renderSource(source, srcPath = 'docs/arch/README.md') {
	const armRoot = fixtureTree({ [srcPath]: source });
	const { pages } = collectPages(armRoot, MANIFEST);
	const resolver = createResolver({ armRoot, pages, manifest: MANIFEST });
	return renderer.render(pages.find((p) => p.srcPath === srcPath), resolver);
}

test('GitHub-compatible heading ids, duplicates suffixed, toc holds h2/h3 only', () => {
	const r = renderSource('# Title\n\n## Install\n\n### Step one\n\n## Install\n\n#### Deep\n');
	assert.match(r.html, /<h2 id="install">Install<\/h2>/);
	assert.match(r.html, /<h2 id="install-1">Install<\/h2>/);
	assert.deepEqual(r.toc, [
		{ depth: 2, id: 'install', text: 'Install' },
		{ depth: 3, id: 'step-one', text: 'Step one' },
		{ depth: 2, id: 'install-1', text: 'Install' }
	]);
	assert.ok(r.headingIds.has('deep'));
});

test('links become placeholders; externals open in a new tab; bad links are line-numbered errors', () => {
	const r = renderSource('# T\n\nSee [topo](01-architecture.md#backend) and [mk](https://www.makemkv.com/).\n\n[gone](nope.md)\n');
	assert.match(r.html, /<a href="@@doclink:0@@">topo<\/a>/);
	assert.match(r.html, /<a href="@@doclink:1@@" target="_blank" rel="noopener">mk<\/a>/);
	assert.deepEqual(r.links[0], { line: 3, raw: '01-architecture.md#backend', resolved: { kind: 'page', id: 'dev/01-architecture', fragment: 'backend' } });
	assert.deepEqual(r.errors, ['docs/arch/README.md:5: link target not found: docs/arch/nope.md']);
});

test('images become asset placeholders', () => {
	const armRoot = fixtureTree({ 'docs/arch/README.md': '# T\n\n![topo](img/t.png)\n', 'docs/arch/img/t.png': 'png' });
	const { pages } = collectPages(armRoot, MANIFEST);
	const r = renderer.render(pages.find((p) => p.id === 'dev/arch'), createResolver({ armRoot, pages, manifest: MANIFEST }));
	assert.match(r.html, /<img src="@@docasset:0@@" alt="topo">/);
	assert.deepEqual(r.assets, ['docs/arch/img/t.png']);
});

test('tables are wrapped and carry table block classes', () => {
	const r = renderSource('# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n');
	assert.match(r.html, /<div class="docs-table-scroll"><table class="table">/);
	assert.match(r.html, /<th class="table-header">a<\/th>/);
	assert.match(r.html, /<tr class="table-row">\s*<td class="table-cell">1<\/td>/);
});

test('GitHub alerts and bold-lead blockquotes map to the alert block', () => {
	const r = renderSource('# T\n\n> [!WARNING]\n> Back up first.\n\n> **Note** plain note.\n\n> just a quote\n');
	assert.match(r.html, /<div class="alert alert-warning docs-alert" role="note"><p class="alert-title">Warning<\/p>\s*<p>Back up first.<\/p>\s*<\/div>/);
	assert.match(r.html, /<div class="alert alert-info docs-alert" role="note">\s*<p><strong>Note<\/strong> plain note.<\/p>\s*<\/div>/);
	assert.match(r.html, /<blockquote>\s*<p>just a quote<\/p>\s*<\/blockquote>/);
});

test('fenced code is highlighted with light/dark variables; unknown languages fall back to text', () => {
	const r = renderSource('# T\n\n```bash\necho hi\n```\n\n```makemkvcon\nCINFO:1,2\n```\n');
	assert.match(r.html, /<pre class="shiki shiki-themes github-light github-dark code-block"/);
	assert.match(r.html, /--shiki-light:/);
	assert.match(r.html, /CINFO:1,2/);
});

test('raw HTML is escaped, never passed through', () => {
	const r = renderSource('# T\n\nThis is <b>bold</b> and <script>alert(1)</script>.\n');
	assert.doesNotMatch(r.html, /<b>|<script>/);
	assert.match(r.html, /&lt;b&gt;bold&lt;\/b&gt;/);
});

test('no Tailwind utility classes in fragments', () => {
	const r = renderSource('# T\n\n| a |\n|---|\n| 1 |\n\n> [!NOTE]\n> n\n\n```json\n{}\n```\n');
	const classes = [...r.html.matchAll(/class="([^"]+)"/g)].flatMap((m) => m[1].split(/\s+/));
	const allowed = /^(docs-[a-z-]+|table|table-[a-z]+|alert|alert-[a-z]+|code-block|shiki|shiki-themes|github-light|github-dark|line)$/;
	assert.deepEqual(classes.filter((c) => !allowed.test(c)), []);
});

test('search text collects prose', () => {
	const r = renderSource('# Title\n\nAlpha beta.\n\n## Gamma\n');
	assert.match(r.text, /Alpha beta\./);
	assert.match(r.text, /Gamma/);
});
