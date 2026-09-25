// Link resolution is target-independent: a link resolves once to a page, a
// repo file, an anchor or an external URL, and each output (site/app) turns
// that into its own href. The renderer leaves @@doclink:N@@ placeholders
// that fillLinks substitutes per target.
import { existsSync, statSync } from 'node:fs';
import { join, posix } from 'node:path';

const SCHEME = /^[a-z][a-z0-9+.-]*:/i;
const HOME = 'guide/home';

export const outPath = (id) => (id === HOME ? 'index.html' : `${id}.html`);
export const appRoute = (id) => (id === HOME ? '/help' : `/help/${id}`);
export function rootPrefix(id) {
	const up = posix.relative(posix.dirname(outPath(id)), '.');
	return up ? `${up}/` : '';
}

export const escapeAttr = (s) => String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function decode(s) {
	try {
		return decodeURIComponent(s);
	} catch {
		return null;
	}
}

export function createResolver({ armRoot, pages, manifest }) {
	const byPath = new Map(pages.map((p) => [p.srcPath, p]));
	const repos = new Set([manifest.repo, ...(manifest.repoAliases ?? [])].map((r) => r.toLowerCase()));
	const wikiDir = manifest.sections.find((s) => s.wiki)?.wiki;

	function repoPath(p, fragment) {
		let path = posix.normalize(p).replace(/\/+$/, '') || '.';
		if (path.startsWith('..') || posix.isAbsolute(path)) return { kind: 'error', message: `link escapes the repo: ${p}` };
		const abs = join(armRoot, path);
		if (!existsSync(abs)) return { kind: 'error', message: `link target not found: ${path}` };
		if (statSync(abs).isDirectory()) {
			if (!existsSync(join(abs, 'README.md'))) return { kind: 'repo', path, fragment };
			path = path === '.' ? 'README.md' : `${path}/README.md`;
		}
		const page = byPath.get(path);
		return page ? { kind: 'page', id: page.id, fragment } : { kind: 'repo', path, fragment };
	}

	function resolve(target, from) {
		if (target.startsWith('#')) {
			const fragment = decode(target.slice(1));
			return fragment === null ? { kind: 'error', message: `malformed link: ${target}` } : { kind: 'anchor', fragment };
		}
		if (SCHEME.test(target)) {
			let url;
			try {
				url = new URL(target);
			} catch {
				return { kind: 'external', url: target };
			}
			if (url.hostname === 'github.com') {
				const [owner, name, kind, ...rest] = url.pathname.split('/').filter(Boolean);
				const fragment = decode(url.hash.slice(1)) ?? '';
				if (owner && name && repos.has(`${owner}/${name}`.toLowerCase())) {
					if (kind === 'wiki') return repoPath(`${wikiDir}/${decode(rest[0] ?? 'Home')}.md`, fragment);
					if (kind === 'blob' && rest[0] === 'main' && rest.length > 1) return repoPath(rest.slice(1).map(decode).join('/'), fragment);
				}
			}
			return { kind: 'external', url: target };
		}
		const at = target.indexOf('#');
		const pathPart = decode(at === -1 ? target : target.slice(0, at));
		const fragment = at === -1 ? '' : decode(target.slice(at + 1));
		if (pathPart === null || fragment === null) return { kind: 'error', message: `malformed link: ${target}` };
		// GitHub wiki links are bare page names ("Getting-Started").
		if (wikiDir && posix.dirname(from) === wikiDir && /^[A-Za-z0-9_-]+$/.test(pathPart) && existsSync(join(armRoot, wikiDir, `${pathPart}.md`))) {
			return repoPath(`${wikiDir}/${pathPart}.md`, fragment);
		}
		return repoPath(posix.join(posix.dirname(from), pathPart), fragment);
	}

	function resolveAsset(src, from) {
		if (SCHEME.test(src)) return { kind: 'external', url: src };
		const decoded = decode(src.split('#')[0]);
		if (decoded === null) return { kind: 'error', message: `malformed image path: ${src}` };
		const path = posix.normalize(posix.join(posix.dirname(from), decoded));
		if (path.startsWith('..')) return { kind: 'error', message: `image escapes the repo: ${src}` };
		if (!existsSync(join(armRoot, path))) return { kind: 'error', message: `image not found: ${path}` };
		return { kind: 'asset', path };
	}

	return { resolve, resolveAsset };
}

export function hrefFor(resolved, { target, fromId, repo }) {
	const frag = resolved.fragment ? `#${resolved.fragment}` : '';
	switch (resolved.kind) {
		case 'anchor':
			return frag;
		case 'external':
			return resolved.url;
		case 'repo':
			return `https://github.com/${repo}/blob/main/${resolved.path}${frag}`;
		case 'page':
			if (target === 'app') return `${appRoute(resolved.id)}${frag}`;
			return `${posix.relative(posix.dirname(outPath(fromId)), outPath(resolved.id))}${frag}`;
		default:
			throw new Error(`hrefFor: unresolvable link ${JSON.stringify(resolved)}`);
	}
}

export function assetHref(path, { target, fromId }) {
	if (target === 'app') return `/docs-data/assets/${path}`;
	return posix.relative(posix.dirname(outPath(fromId)), `assets/${path}`);
}

export function checkFragments(rendered) {
	const ids = new Map(rendered.map((r) => [r.page.id, r.headingIds]));
	const errors = [];
	for (const r of rendered) {
		for (const { line, resolved } of r.links) {
			if (!resolved.fragment) continue;
			const targetId = resolved.kind === 'anchor' ? r.page.id : resolved.kind === 'page' ? resolved.id : null;
			if (targetId && !ids.get(targetId)?.has(resolved.fragment)) {
				errors.push(`${r.page.srcPath}:${line}: missing anchor #${resolved.fragment} in ${targetId}`);
			}
		}
	}
	return errors;
}

export function fillLinks(html, { links, assets }, ctx) {
	return html
		.replace(/@@doclink:(\d+)@@/g, (_, n) => escapeAttr(hrefFor(links[n].resolved, ctx)))
		.replace(/@@docasset:(\d+)@@/g, (_, n) => escapeAttr(assetHref(assets[n], ctx)));
}
