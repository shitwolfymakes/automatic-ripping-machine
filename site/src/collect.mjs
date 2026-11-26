// Turns manifest.json into the ordered page list and the nav tree. Sections
// are listed explicitly in the manifest; a section's audience decides the
// page id prefix (user -> guide/, dev -> dev/) and whether the in-app help
// bundle carries it (user only). The GitHub wiki keeps its own _Sidebar.md.
import { readFileSync, globSync } from 'node:fs';
import { join, posix, sep } from 'node:path';

const toPosix = (p) => p.split(sep).join('/');

// Must match the app's id rule (services/ui-neu/frontend/src/lib/help/api.ts).
const ID_RE = /^[a-z0-9_-]+\/[a-z0-9_-]+$/;
const ID_PREFIX = { user: 'guide', dev: 'dev' };

export function loadManifest(siteDir) {
	return JSON.parse(readFileSync(join(siteDir, 'manifest.json'), 'utf8'));
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

// Reads a page's markdown from the repo and builds its page record, title included.
export function readPage(armRoot, { id, audience, slug, srcPath }) {
	const source = readFileSync(join(armRoot, srcPath), 'utf8');
	return { id, audience, slug, srcPath, title: titleOf(source, srcPath), source };
}

// The nav item for a manifest entry that links somewhere instead of naming a file.
export function linkItem(entry, section) {
	return {
		label: entry.label,
		target: entry.link,
		from: 'manifest.json',
		where: `manifest.json (${section.label})`
	};
}

// An error for each wiki page no section placed; files starting with _ (the wiki's sidebar and footer) are exempt.
export function unplacedWikiErrors(wikiFiles, placed) {
	return wikiFiles
		.filter((f) => !posix.basename(f).startsWith('_') && !placed.has(f))
		.map((f) => `manifest: ${f} is not placed in any section`);
}

export function collectPages(armRoot, manifest) {
	const pages = [];
	const nav = [];
	const errors = [];
	const byId = new Map();
	const placed = new Set();

	const add = (audience, srcPath, slugOverride) => {
		const slug = slugOverride ?? slugFor(srcPath);
		const id = `${ID_PREFIX[audience]}/${slug}`;
		if (!ID_RE.test(id)) {
			errors.push(`invalid page id ${id} from ${srcPath} (slugs may use a-z, 0-9, _ and -)`);
			return null;
		}
		if (byId.has(id)) {
			errors.push(`duplicate page id ${id}: ${byId.get(id).srcPath} and ${srcPath}`);
			return null;
		}
		const page = readPage(armRoot, { id, audience, slug, srcPath });
		byId.set(id, page);
		pages.push(page);
		return page;
	};
	const glob = (pattern) => globSync(pattern, { cwd: armRoot }).map(toPosix).sort();
	// One manifest entry's nav items: its link item, or one item per newly placed file its pattern matches.
	const entryItems = (entry, section) => {
		// typeof guard: strings inherit the legacy String.prototype.link method.
		if (typeof entry === 'object' && entry.link) return [linkItem(entry, section)];
		const pattern = typeof entry === 'string' ? entry : entry.file;
		const files = glob(pattern);
		if (!files.length) errors.push(`manifest: ${pattern} matched no files`);
		const items = [];
		for (const f of files) {
			if (placed.has(f)) continue;
			placed.add(f);
			const page = add(section.audience, f, entry.slug);
			if (page) items.push({ label: entry.label ?? page.title, pageId: page.id });
		}
		return items;
	};

	for (const section of manifest.sections) {
		if (!ID_PREFIX[section.audience]) {
			errors.push(`manifest: section ${section.id} has unknown audience ${section.audience} (use user or dev)`);
			continue;
		}
		const groups = section.groups.map((group) => ({
			label: group.label ?? null,
			items: group.files.flatMap((entry) => entryItems(entry, section))
		}));
		nav.push({ id: section.id, label: section.label, audience: section.audience, groups });
	}

	// Every user doc must be placed, so a new wiki page can't silently miss
	// the site and the app.
	errors.push(...unplacedWikiErrors(glob(`${manifest.wiki}/*.md`), placed));
	return { pages, nav, errors };
}
