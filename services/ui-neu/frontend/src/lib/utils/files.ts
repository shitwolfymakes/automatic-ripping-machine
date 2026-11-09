// Pure rules for the Files page: how a directory listing is sorted and how
// the roots are ordered.
import type { FileEntry, FileRoot } from '$lib/api/files';

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
