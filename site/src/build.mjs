#!/usr/bin/env node
// Builds the ARM docs from the repo's markdown. See site/README.md.
import { existsSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';
import { collectPages, loadManifest } from './collect.mjs';
import { createResolver, checkFragments } from './links.mjs';
import { createRenderer } from './render.mjs';
import { buildSearchIndex } from './search.mjs';
import { writeApp } from './write-app.mjs';
import { writeSite } from './write-site.mjs';

const siteDir = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function readMeta(armRoot) {
	const versionFile = join(armRoot, 'VERSION');
	const version = existsSync(versionFile) ? readFileSync(versionFile, 'utf8').trim() : 'unknown';
	let commit = process.env.ARM_COMMIT;
	if (!commit) {
		try {
			commit = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: armRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim();
		} catch {
			commit = 'unknown';
		}
	}
	return { version, commit: /^[0-9a-f]{40}$/.test(commit) ? commit.slice(0, 12) : commit, builtAt: new Date().toISOString() };
}

const NAV_SCHEMES = new Set(['http', 'https', 'mailto']);

function resolveNav(nav, resolver, errors, headingIdsById) {
	return nav.map((section) => ({
		...section,
		groups: section.groups.map((g) => ({
			...g,
			items: g.items.flatMap((item) => {
				if (item.pageId) return [{ label: item.label, resolved: { kind: 'page', id: item.pageId, fragment: '' } }];
				const resolved = resolver.resolve(item.target, item.from);
				if (resolved.kind === 'error') {
					errors.push(`${item.from}:${item.line}: ${resolved.message}`);
					return [];
				}
				if (resolved.kind === 'external' && !NAV_SCHEMES.has(resolved.url.split(':')[0].toLowerCase())) {
					errors.push(`${item.from}:${item.line}: unsupported link scheme: ${item.target}`);
					return [];
				}
				if (resolved.kind === 'page' && resolved.fragment && !headingIdsById.get(resolved.id)?.has(resolved.fragment)) {
					errors.push(`${item.from}:${item.line}: missing anchor #${resolved.fragment} in ${resolved.id}`);
					return [];
				}
				return [{ label: item.label, resolved }];
			})
		}))
	}));
}

async function main() {
	const { values } = parseArgs({
		options: {
			target: { type: 'string', default: 'all' },
			out: { type: 'string', default: join(siteDir, 'build') },
			'app-out': { type: 'string' },
			verbose: { type: 'boolean', default: false }
		}
	});
	const target = values.target;
	if (!['all', 'site', 'app'].includes(target)) throw new Error(`--target must be all, site or app (got ${target})`);
	const armRoot = resolve(process.env.ARM_ROOT ?? join(siteDir, '..'));
	if (!existsSync(join(armRoot, 'arm_wiki'))) {
		console.error(`error: ARM root not found at ${armRoot} (set ARM_ROOT)`);
		process.exit(1);
	}
	const manifest = process.env.DOCS_MANIFEST ? JSON.parse(readFileSync(process.env.DOCS_MANIFEST, 'utf8')) : loadManifest(siteDir);

	const { pages, nav, errors } = collectPages(armRoot, manifest);
	const resolver = createResolver({ armRoot, pages, manifest });
	const renderer = await createRenderer();
	const rendered = pages.map((p) => renderer.render(p, resolver));
	errors.push(...rendered.flatMap((r) => r.errors), ...checkFragments(rendered));
	const headingIdsById = new Map(rendered.map((r) => [r.page.id, r.headingIds]));
	const resolvedNav = resolveNav(nav, resolver, errors, headingIdsById);
	if (errors.length) {
		for (const e of errors) console.error(`error: ${e}`);
		console.error(`${errors.length} error(s); nothing written`);
		process.exit(1);
	}

	const repoLinks = rendered.flatMap((r) => r.links.filter((l) => l.resolved.kind === 'repo').map((l) => `${r.page.srcPath}:${l.line}: ${l.raw}`));
	console.log(`info: ${pages.length} pages; ${repoLinks.length} links point at unpublished repo files (GitHub)${values.verbose ? '' : ', --verbose to list'}`);
	if (values.verbose) repoLinks.forEach((l) => console.log(`info:   ${l}`));

	const meta = readMeta(armRoot);
	const search = buildSearchIndex(rendered);
	const common = { armRoot, rendered, nav: resolvedNav, meta, manifest, search };
	const out = resolve(values.out);
	if (target !== 'app') {
		writeSite({ ...common, siteDir, outDir: join(out, 'site') });
		console.log(`site: ${join(out, 'site')}`);
	}
	if (target !== 'site') {
		const appOut = resolve(values['app-out'] ?? join(out, 'app'));
		writeApp({ ...common, outDir: appOut });
		console.log(`app: ${appOut}`);
	}
}

main().catch((e) => {
	console.error(`error: ${e.stack ?? e}`);
	process.exit(1);
});
