import { mkdtempSync, mkdirSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';

export function makeTree(files) {
	const root = mkdtempSync(join(tmpdir(), 'arm-docs-'));
	for (const [path, content] of Object.entries(files)) {
		const file = join(root, path);
		mkdirSync(dirname(file), { recursive: true });
		writeFileSync(file, content);
	}
	return root;
}

export const MANIFEST = {
	repo: 'uprightbass360/arm-v3',
	repoAliases: ['automatic-ripping-machine/automatic-ripping-machine'],
	sections: [
		{ id: 'guide', label: 'Guide', wiki: 'arm_wiki', sidebar: 'arm_wiki/_Sidebar.md' },
		{
			id: 'dev',
			label: 'Developers',
			groups: [
				{ label: 'Architecture', files: ['docs/arch/README.md', 'docs/arch/[0-9]*.md'] },
				{ label: 'Contributing', files: ['CONTRIBUTING.md'] }
			]
		}
	]
};

const UPSTREAM = 'https://github.com/automatic-ripping-machine/automatic-ripping-machine';

export function fixtureTree(extra = {}) {
	return makeTree({
		'arm_wiki/_Sidebar.md': [
			`**[Home](${UPSTREAM}/wiki)**`,
			'',
			'**Getting Started**',
			'  - [Getting Started](Getting-Started)',
			'  - [Configuration](Configuring-ARM)',
			'',
			'**Project**',
			`  - [Architecture docs](${UPSTREAM}/blob/main/docs/arch/README.md)`,
			`  - [Open an issue](${UPSTREAM}/issues/new/choose)`,
			''
		].join('\n'),
		'arm_wiki/Home.md': '# ARM Wiki\n\nStart with [Getting Started](Getting-Started).\n',
		'arm_wiki/Getting-Started.md': '# Getting Started\n\n## Install\n\nSee [options](Configuring-ARM#options).\n',
		'arm_wiki/Configuring-ARM.md': '# Configuring ARM\n\n## Options\n\nText.\n',
		'docs/arch/README.md': '# Architecture\n\nRead [the overview](01-architecture.md).\n',
		'docs/arch/01-architecture.md': '# Service topology\n\n## Backend\n\nText.\n',
		'CONTRIBUTING.md': '# Contributing\n\nSee [docs/arch/](docs/arch/) and [LICENSE](LICENSE).\n',
		LICENSE: 'MIT\n',
		...extra
	});
}
