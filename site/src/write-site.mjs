// build/site: the static site for GitHub Pages. Every URL is relative so the
// same files work under /arm-v3/, any other base path, and file://.
import { copyFileSync, cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { dirname, join, relative, sep } from 'node:path';
import { fillLinks, outPath, rootPrefix } from './links.mjs';
import { copyAssets, editUrl, escapeHtml, navFor } from './output.mjs';

const require = createRequire(import.meta.url);
const STYLES = 'services/ui-neu/frontend/src/lib/styles';
const BLOCKS = ['panel', 'button', 'alert', 'badge', 'code-block', 'table', 'nav', 'field', 'text', 'docs-prose'];

// minisearch's package.json omits an "exports" entry for "./package.json",
// so require.resolve('minisearch/package.json') throws under Node's ESM
// exports resolution. Resolve the "require" condition's entry file instead
// (dist/cjs/index.cjs) and walk up to the package root.
function minisearchRoot() {
	return dirname(dirname(dirname(require.resolve('minisearch'))));
}

function fillTemplate(template, vars) {
	return template.replace(/\{\{(\w+)\}\}/g, (_, key) => {
		if (!(key in vars)) throw new Error(`template: unknown placeholder {{${key}}}`);
		return vars[key];
	});
}

function renderNav(sections, activeId) {
	return sections
		.map((s) => {
			const groups = s.groups
				.map((g) => {
					const label = g.label ? `<p class="docs-nav-group">${escapeHtml(g.label)}</p>` : '';
					const items = g.items
						.map((i) => {
							const active = i.pageId === activeId ? ' data-active="true" aria-current="page"' : '';
							const ext = i.external ? ' target="_blank" rel="noopener"' : '';
							return `<a class="nav-item" href="${escapeHtml(i.href)}"${active}${ext}>${escapeHtml(i.label)}</a>`;
						})
						.join('');
					return label + items;
				})
				.join('');
			return `<div class="docs-nav-section"><p class="eyebrow docs-nav-heading">${escapeHtml(s.label)}</p>${groups}</div>`;
		})
		.join('');
}

function renderToc(toc) {
	if (toc.length < 2) return '';
	const links = toc.map((t) => `<a class="docs-toc-link" data-depth="${t.depth}" href="#${escapeHtml(t.id)}">${escapeHtml(t.text)}</a>`).join('');
	return `<nav class="docs-toc" aria-label="On this page"><p class="eyebrow">On this page</p>${links}</nav>`;
}

function compileCss(armRoot, siteDir, outFile) {
	const styles = join(armRoot, STYLES);
	if (!existsSync(join(styles, 'tokens.css'))) throw new Error(`ui-neu tokens not found at ${join(styles, 'tokens.css')} (set ARM_ROOT)`);
	// The entry lives inside site/ so `@import "tailwindcss"` resolves from
	// site/node_modules; ui-neu sheets are imported by relative path.
	const cacheDir = join(siteDir, '.cache');
	mkdirSync(cacheDir, { recursive: true });
	const rel = (p) => relative(cacheDir, p).split(sep).join('/');
	const entry = [
		'@import "tailwindcss" source(none);',
		...['tokens', 'base', 'layout', 'utilities'].map((n) => `@import "${rel(join(styles, `${n}.css`))}";`),
		...BLOCKS.map((b) => `@import "${rel(join(styles, 'components', `${b}.css`))}";`),
		`@import "${rel(join(siteDir, 'src/styles/site.css'))}";`
	].join('\n');
	writeFileSync(join(cacheDir, 'entry.css'), entry);
	execFileSync(join(siteDir, 'node_modules/.bin/tailwindcss'), ['-i', join(cacheDir, 'entry.css'), '-o', outFile, '--minify'], { cwd: siteDir, stdio: ['ignore', 'ignore', 'inherit'] });
	// ui-neu's base.css declares Rajdhani with root-absolute /fonts/ URLs;
	// site.css sits at the site root, so relative fonts/ resolves the same.
	writeFileSync(outFile, readFileSync(outFile, 'utf8').replace(/url\((['"]?)\/fonts\//g, 'url($1fonts/'));
}

export function writeSite({ outDir, armRoot, siteDir, rendered, nav, meta, manifest, search }) {
	rmSync(outDir, { recursive: true, force: true });
	mkdirSync(join(outDir, 'js'), { recursive: true });
	const template = readFileSync(join(siteDir, 'src/template.html'), 'utf8');

	for (const r of rendered) {
		const id = r.page.id;
		const ctx = { target: 'site', fromId: id, repo: manifest.repo };
		const html = fillTemplate(template, {
			root: rootPrefix(id),
			title: escapeHtml(r.page.title),
			repo: escapeHtml(manifest.repo),
			nav: renderNav(navFor(nav, ctx), id),
			toc: renderToc(r.toc),
			content: fillLinks(r.html, r, ctx),
			editUrl: escapeHtml(editUrl(manifest.repo, r.page.srcPath)),
			version: escapeHtml(meta.version),
			commit: escapeHtml(meta.commit)
		});
		const file = join(outDir, outPath(id));
		mkdirSync(dirname(file), { recursive: true });
		writeFileSync(file, html);
	}

	copyAssets(rendered, armRoot, join(outDir, 'assets'));
	compileCss(armRoot, siteDir, join(outDir, 'site.css'));
	cpSync(join(armRoot, 'services/ui-neu/frontend/static/fonts'), join(outDir, 'fonts'), { recursive: true });
	copyFileSync(join(armRoot, 'services/ui-neu/frontend/static/favicon.ico'), join(outDir, 'favicon.ico'));
	for (const f of ['theme.js', 'site.js']) copyFileSync(join(siteDir, 'src/client', f), join(outDir, 'js', f));
	copyFileSync(join(minisearchRoot(), 'dist/umd/index.js'), join(outDir, 'js/minisearch.js'));
	const pages = Object.fromEntries(rendered.map((r) => [r.page.id, { title: r.page.title, path: outPath(r.page.id) }]));
	writeFileSync(join(outDir, 'js/search-index.js'), `window.ARM_DOCS_SEARCH = ${JSON.stringify({ ...search, pages })};\n`);
}
