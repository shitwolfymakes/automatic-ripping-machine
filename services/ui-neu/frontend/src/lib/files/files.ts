// Pure rules for the Files page: how a directory listing is sorted, how the
// roots are ordered, how selection keys are built and split, which folders
// the move picker offers, the bulk delete order, and the wording of the
// result banners.
import type { FileEntry, FileRoot } from '$lib/api/files';
import type { BulkFeedback } from '$lib/dashboard/bulk-delete-feedback';
import { plural } from '$lib/utils/plural';

export type SortKey = 'name' | 'size' | 'modified';
export type SortDir = 'asc' | 'desc';

const rootOrder: Record<string, number> = { raw: 0, transcode: 1, completed: 2, music: 3 };

// Directories first whatever the direction, then by the chosen column
export function sortEntries(entries: readonly FileEntry[], key: SortKey, dir: SortDir): FileEntry[] {
	return [...entries].sort((a, b) => {
		if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
		let cmp: number;
		if (key === 'size') {
			cmp = (a.size ?? 0) - (b.size ?? 0);
		} else if (key === 'modified') {
			cmp = (a.modified ?? '').localeCompare(b.modified ?? '');
		} else {
			cmp = a.name.toLowerCase().localeCompare(b.name.toLowerCase());
		}
		return dir === 'asc' ? cmp : -cmp;
	});
}

// The same column flips direction; a new column starts descending for
// modified, ascending otherwise
export function nextSort(key: SortKey, dir: SortDir, clicked: SortKey): { key: SortKey; dir: SortDir } {
	if (key === clicked) return { key, dir: dir === 'asc' ? 'desc' : 'asc' };
	return { key: clicked, dir: clicked === 'modified' ? 'desc' : 'asc' };
}

// Known roots in a fixed order, any other key (or none) after them
export function sortRoots(roots: FileRoot[]): FileRoot[] {
	return roots.sort((a, b) => (rootOrder[a.key ?? ''] ?? 99) - (rootOrder[b.key ?? ''] ?? 99));
}

// The subpath of a named entry inside a directory: `parent/name`, or just
// `name` at the top of the root
export function childSubpath(parent: string, name: string): string {
	return parent ? `${parent}/${name}` : name;
}

// A selected item is identified across roots by `root::subpath`
export function selectionKey(root: string, subpath: string): string {
	return `${root}::${subpath}`;
}

// Splits a selection key back into its root and subpath. It splits on every
// `::`, so a name that itself contains `::` loses everything after it; that
// is bug #535 and is fixed there, not here.
export function parseSelectionKey(key: string): { root: string; subpath: string } {
	const [root, subpath] = key.split('::');
	return { root, subpath };
}

// The folders the move picker offers: the directories among its entries. When
// the picker shows the source directory (sameDir) the selected items' own
// names are hidden, since an item cannot be moved into itself. When it shows
// another directory none of the source selection applies.
export function moveTargetFolders(
	entries: readonly FileEntry[],
	selectedKeys: ReadonlySet<string>,
	sameDir: boolean
): FileEntry[] {
	const movingNames = sameDir
		? new Set([...selectedKeys].map((k) => parseSelectionKey(k).subpath.split('/').pop()))
		: new Set<string | undefined>();
	return entries.filter((e) => e.type === 'directory' && !movingNames.has(e.name));
}

// Bulk delete order: longest subpath first, so children go before their
// parents. Returns a new array; the sort is stable.
export function orderForDelete<T extends { subpath: string }>(items: readonly T[]): T[] {
	return [...items].sort((a, b) => b.subpath.length - a.subpath.length);
}

// The banner after a bulk move or delete: an error naming the failures when
// any failed, else a success with the item count.
export function bulkResultFeedback(verb: 'Moved' | 'Deleted', done: number, failed: number): BulkFeedback {
	if (failed > 0) return { type: 'error', message: `${verb} ${done}, failed ${failed}` };
	return { type: 'success', message: `${verb} ${done} ${plural(done, 'item')}` };
}

// The banner after a cleanup that removes `count` of `noun`: the error tone
// and an error count are added when there were errors.
export function cleanupFeedback(count: number, noun: string, errors: number): BulkFeedback {
	return {
		type: errors ? 'error' : 'success',
		message: `Deleted ${count} ${plural(count, noun)}${errors ? `, ${errors} error(s)` : ''}`
	};
}

export function fixedPermissionsMessage(name: string, fixed: number): string {
	return `Fixed permissions on ${name} (${fixed} ${plural(fixed, 'item')})`;
}
