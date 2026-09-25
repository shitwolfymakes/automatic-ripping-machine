// build/app: the bundle the ui-neu /help route fetches from /docs-data/.
import { rmSync } from 'node:fs';
import { join } from 'node:path';
import { fillLinks } from './links.mjs';
import { copyAssets, editUrl, navFor, writeJson } from './output.mjs';

export function writeApp({ outDir, armRoot, rendered, nav, meta, manifest, search }) {
	rmSync(outDir, { recursive: true, force: true });
	const ctx = (fromId) => ({ target: 'app', fromId, repo: manifest.repo });
	for (const r of rendered) {
		writeJson(join(outDir, 'pages', `${r.page.id}.json`), {
			id: r.page.id,
			title: r.page.title,
			html: fillLinks(r.html, r, ctx(r.page.id)),
			toc: r.toc,
			source: r.page.srcPath,
			editUrl: editUrl(manifest.repo, r.page.srcPath)
		});
	}
	writeJson(join(outDir, 'nav.json'), navFor(nav, ctx(null)));
	copyAssets(rendered, armRoot, join(outDir, 'assets'));
	writeJson(join(outDir, 'search.json'), search);
	writeJson(join(outDir, 'meta.json'), meta);
}
