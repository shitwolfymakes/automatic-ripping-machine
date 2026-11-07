#!/usr/bin/env node
// Builds the ARM docs from the repo's markdown. See site/README.md.
import { existsSync, readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadManifest } from './collect.mjs';
import { parseOptions } from './options.mjs';
import { buildDocs, repoLinkLines } from './pipeline.mjs';
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

async function main() {
	const options = parseOptions(process.argv.slice(2), siteDir);
	const armRoot = resolve(process.env.ARM_ROOT ?? join(siteDir, '..'));
	const manifest = process.env.DOCS_MANIFEST ? JSON.parse(readFileSync(process.env.DOCS_MANIFEST, 'utf8')) : loadManifest(siteDir);
	if (!existsSync(join(armRoot, manifest.wiki))) {
		console.error(`error: ARM root not found at ${armRoot} (set ARM_ROOT)`);
		process.exit(1);
	}

	const { pages, rendered, nav: resolvedNav, errors } = await buildDocs(armRoot, manifest);
	if (errors.length) {
		for (const e of errors) console.error(`error: ${e}`);
		console.error(`${errors.length} error(s); nothing written`);
		process.exit(1);
	}

	const repoLinks = repoLinkLines(rendered);
	console.log(`info: ${pages.length} pages; ${repoLinks.length} links point at unpublished repo files (GitHub)${options.verbose ? '' : ', --verbose to list'}`);
	if (options.verbose) repoLinks.forEach((l) => console.log(`info:   ${l}`));

	const meta = readMeta(armRoot);
	// The site carries every page; the in-app help carries user docs only.
	if (options.target !== 'app') {
		writeSite({ armRoot, rendered, nav: resolvedNav, meta, manifest, search: buildSearchIndex(rendered), siteDir, outDir: join(options.out, 'site') });
		console.log(`site: ${join(options.out, 'site')}`);
	}
	if (options.target !== 'site') {
		const appRendered = rendered.filter((r) => r.page.audience === 'user');
		const appNav = resolvedNav.filter((s) => s.audience === 'user');
		writeApp({ armRoot, rendered: appRendered, nav: appNav, meta, manifest, search: buildSearchIndex(appRendered), outDir: options.appOut });
		console.log(`app: ${options.appOut}`);
	}
}

main().catch((e) => {
	console.error(`error: ${e.stack ?? e}`);
	process.exit(1);
});
