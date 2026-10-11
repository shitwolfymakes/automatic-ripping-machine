import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

export function makeTree(files) {
	const root = mkdtempSync(join(tmpdir(), 'arm-docs-'));
	for (const [path, content] of Object.entries(files)) {
		const file = join(root, path);
		mkdirSync(dirname(file), { recursive: true });
		writeFileSync(file, content);
	}
	return root;
}

export const MANIFEST = JSON.parse(readFileSync(fileURLToPath(new URL('./fixture-manifest.json', import.meta.url)), 'utf8'));


export function fixtureTree(extra = {}) {
	return makeTree({
		'docs/user/_Sidebar.md': '**Wiki sidebar**\n  - [Home](Home)\n',
		'docs/user/Home.md': '# ARM Wiki\n\nStart with [Getting Started](Getting-Started).\n',
		'docs/user/Getting-Started.md': '# Getting Started\n\n## Install\n\nSee [options](Configuring-ARM#options).\n',
		'docs/user/Configuring-ARM.md': '# Configuring ARM\n\n## Options\n\nText.\n',
		'docs/developers/architecture/README.md': '# Architecture\n\nRead [the overview](01-architecture.md).\n',
		'docs/developers/architecture/01-architecture.md': '# Service topology\n\n## Backend\n\nText.\n',
		'CONTRIBUTING.md': '# Contributing\n\nSee [docs/developers/architecture/](docs/developers/architecture/) and [LICENSE](LICENSE).\n',
		LICENSE: 'MIT\n',
		...extra
	});
}
