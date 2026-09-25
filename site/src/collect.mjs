// Turns manifest.json into the ordered page list and the nav tree. The wiki
// section's nav comes from arm_wiki/_Sidebar.md so the site and the GitHub
// wiki share one table of contents.
import { readFileSync, existsSync, globSync } from 'node:fs';
import { join, posix, sep } from 'node:path';

const toPosix = (p) => p.split(sep).join('/');

export function loadManifest(siteDir) {
	return JSON.parse(readFileSync(join(siteDir, 'manifest.json'), 'utf8'));
}

// A bold line is a group heading; "- [label](target)" lines are its items.
// A bold line that is itself a link ("**[Home](url)**") is an item in an
// unlabelled group of its own.
export function parseSidebar(md) {
	const groups = [];
	const link = /\[([^\]]+)\]\(([^)\s]+)\)/;
	let current = null;
	md.split('\n').forEach((raw, i) => {
		const line = raw.trim();
		const bold = line.match(/^\*\*(.+)\*\*$/);
		if (bold) {
			const l = bold[1].match(link);
			if (l) {
				current = null;
				groups.push({ label: null, items: [{ label: l[1], target: l[2], line: i + 1 }] });
			} else {
				current = { label: bold[1], items: [] };
				groups.push(current);
			}
			return;
		}
		const item = line.match(/^[-*]\s+(.*)$/);
		const l = item && item[1].match(link);
		if (l && current) current.items.push({ label: l[1], target: l[2], line: i + 1 });
	});
	return groups;
}

export function slugFor(srcPath) {
	const stem = posix.basename(srcPath, '.md');
	const name = stem.toLowerCase() === 'readme' ? posix.basename(posix.dirname(srcPath)) : stem;
	return name.toLowerCase();
}

function titleOf(source, srcPath) {
	let fenced = false;
	for (const line of source.split('\n')) {
		if (/^\s*(```|~~~)/.test(line)) fenced = !fenced;
		if (fenced) continue;
		const m = line.match(/^#\s+(.+?)\s*#*\s*$/);
		if (m) return m[1];
	}
	return posix.basename(srcPath, '.md').replace(/[-_]+/g, ' ');
}

export function collectPages(armRoot, manifest) {
	const pages = [];
	const nav = [];
	const errors = [];
	const byId = new Map();
	const taken = new Set();

	const add = (section, srcPath) => {
		const slug = slugFor(srcPath);
		const id = `${section}/${slug}`;
		if (byId.has(id)) {
			errors.push(`duplicate page id ${id}: ${byId.get(id).srcPath} and ${srcPath}`);
			return null;
		}
		const source = readFileSync(join(armRoot, srcPath), 'utf8');
		const page = { id, section, slug, srcPath, title: titleOf(source, srcPath), source };
		byId.set(id, page);
		taken.add(srcPath);
		pages.push(page);
		return page;
	};
	const glob = (pattern) => globSync(pattern, { cwd: armRoot }).map(toPosix).sort();

	for (const section of manifest.sections) {
		if (section.wiki) {
			const files = glob(`${section.wiki}/*.md`).filter((f) => !posix.basename(f).startsWith('_'));
			if (!files.length) errors.push(`manifest: ${section.wiki}/*.md matched no files`);
			files.forEach((f) => add(section.id, f));
			let groups = [];
			if (existsSync(join(armRoot, section.sidebar))) {
				groups = parseSidebar(readFileSync(join(armRoot, section.sidebar), 'utf8')).map((g) => ({
					label: g.label,
					items: g.items.map((item) => ({ ...item, from: section.sidebar }))
				}));
			} else {
				errors.push(`manifest: sidebar ${section.sidebar} not found`);
			}
			nav.push({ id: section.id, label: section.label, groups });
			continue;
		}
		const groups = [];
		for (const group of section.groups) {
			const items = [];
			for (const pattern of group.files) {
				const files = glob(pattern);
				if (!files.length) errors.push(`manifest: ${pattern} matched no files`);
				for (const f of files) {
					if (taken.has(f)) continue;
					const page = add(section.id, f);
					if (page) items.push({ label: page.title, pageId: page.id });
				}
			}
			groups.push({ label: group.label, items });
		}
		nav.push({ id: section.id, label: section.label, groups });
	}
	return { pages, nav, errors };
}
