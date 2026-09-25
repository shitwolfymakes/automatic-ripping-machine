import { copyFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { hrefFor } from './links.mjs';

export const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

export const editUrl = (repo, srcPath) => `https://github.com/${repo}/edit/main/${srcPath}`;

export function navFor(nav, ctx) {
	return nav.map((section) => ({
		id: section.id,
		label: section.label,
		groups: section.groups.map((g) => ({
			label: g.label,
			items: g.items.map((item) => ({
				label: item.label,
				href: hrefFor(item.resolved, ctx),
				external: item.resolved.kind === 'external' || item.resolved.kind === 'repo',
				pageId: item.resolved.kind === 'page' ? item.resolved.id : null
			}))
		}))
	}));
}

export function copyAssets(rendered, armRoot, destDir) {
	for (const path of new Set(rendered.flatMap((r) => r.assets))) {
		const dest = join(destDir, path);
		mkdirSync(dirname(dest), { recursive: true });
		copyFileSync(join(armRoot, path), dest);
	}
}

export function writeJson(file, value) {
	mkdirSync(dirname(file), { recursive: true });
	writeFileSync(file, JSON.stringify(value));
}
