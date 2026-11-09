import { describe, it, expect } from 'vitest';
import {
	sortEntries,
	nextSort,
	sortRoots,
	childSubpath,
	selectionKey,
	parseSelectionKey,
	moveTargetFolders,
	orderForDelete,
	bulkResultFeedback,
	cleanupFeedback,
	fixedPermissionsMessage
} from '../files';
import type { FileEntry, FileRoot } from '$lib/api/files';

const file = (name: string, size?: number, modified?: string): FileEntry =>
	({ name, type: 'file', size, modified }) as FileEntry;
const dir = (name: string): FileEntry => ({ name, type: 'directory' }) as FileEntry;
const names = (entries: FileEntry[]) => entries.map((e) => e.name);

describe('sortEntries', () => {
	const entries = [
		file('b', 20, '2024-02'),
		dir('zdir'),
		file('a', 30, '2024-03'),
		file('c', 10, '2024-01'),
		dir('adir')
	];

	it('sorts by name ascending with directories first', () => {
		expect(names(sortEntries(entries, 'name', 'asc'))).toEqual(['adir', 'zdir', 'a', 'b', 'c']);
	});
	it('sorts by name descending with directories still first', () => {
		expect(names(sortEntries(entries, 'name', 'desc'))).toEqual(['zdir', 'adir', 'c', 'b', 'a']);
	});
	it('sorts by size in both directions', () => {
		expect(names(sortEntries(entries, 'size', 'asc')).slice(2)).toEqual(['c', 'b', 'a']);
		expect(names(sortEntries(entries, 'size', 'desc')).slice(0, 2)).toHaveLength(2);
		expect(names(sortEntries(entries, 'size', 'desc')).slice(2)).toEqual(['a', 'b', 'c']);
	});
	it('sorts by modified in both directions', () => {
		expect(names(sortEntries(entries, 'modified', 'asc')).slice(2)).toEqual(['c', 'b', 'a']);
		expect(names(sortEntries(entries, 'modified', 'desc')).slice(2)).toEqual(['a', 'b', 'c']);
	});
	it('keeps directories before files in both directions', () => {
		for (const d of ['asc', 'desc'] as const) {
			expect(
				sortEntries(entries, 'size', d)
					.slice(0, 2)
					.every((e) => e.type === 'directory')
			).toBe(true);
		}
	});
	it('treats a missing size as 0 and a missing date as empty', () => {
		const list = [file('big', 5, '2024'), file('none')];
		expect(names(sortEntries(list, 'size', 'asc'))).toEqual(['none', 'big']);
		expect(names(sortEntries(list, 'modified', 'asc'))).toEqual(['none', 'big']);
	});
	it('compares names case-insensitively', () => {
		expect(names(sortEntries([file('b'), file('A'), file('a2')], 'name', 'asc'))).toEqual(['A', 'a2', 'b']);
	});
	it('returns a new array and leaves the input untouched', () => {
		const input = [file('b'), file('a')];
		const out = sortEntries(input, 'name', 'asc');
		expect(out).not.toBe(input);
		expect(names(input)).toEqual(['b', 'a']);
	});
});

describe('nextSort', () => {
	it('flips direction when the same column is clicked', () => {
		expect(nextSort('name', 'asc', 'name')).toEqual({ key: 'name', dir: 'desc' });
		expect(nextSort('name', 'desc', 'name')).toEqual({ key: 'name', dir: 'asc' });
	});
	it('starts a new modified column descending', () => {
		expect(nextSort('name', 'asc', 'modified')).toEqual({ key: 'modified', dir: 'desc' });
	});
	it('starts any other new column ascending', () => {
		expect(nextSort('modified', 'desc', 'size')).toEqual({ key: 'size', dir: 'asc' });
	});
});

describe('sortRoots', () => {
	const root = (key?: string) => ({ key }) as FileRoot;
	it('orders known roots first, then unknown and missing keys', () => {
		const out = sortRoots([root('other'), root('music'), root(), root('raw'), root('completed'), root('transcode')]);
		expect(out.map((r) => r.key)).toEqual(['raw', 'transcode', 'completed', 'music', 'other', undefined]);
	});
	it('sorts in place and returns the same array', () => {
		const input = [root('music'), root('raw')];
		expect(sortRoots(input)).toBe(input);
	});
});

describe('childSubpath', () => {
	it('is just the name at the top of a root', () => {
		expect(childSubpath('', 'a')).toBe('a');
	});

	it('joins the parent and the name below the top', () => {
		expect(childSubpath('x/y', 'a')).toBe('x/y/a');
	});
});

describe('selectionKey and parseSelectionKey', () => {
	it('round-trips an ordinary path', () => {
		const key = selectionKey('raw', 'x/y');
		expect(key).toBe('raw::x/y');
		expect(parseSelectionKey(key)).toEqual({ root: 'raw', subpath: 'x/y' });
	});

	it('cuts a name containing :: at the second separator (bug #535)', () => {
		// Pins today's split; the fix belongs to #535
		expect(parseSelectionKey('raw::a::b')).toEqual({ root: 'raw', subpath: 'a' });
	});
});

describe('moveTargetFolders', () => {
	const entries = [dir('movies'), file('notes.txt'), dir('shows')];
	const selected = new Set(['raw::movies', 'raw::notes.txt']);

	it('keeps only directories when the picker is elsewhere', () => {
		expect(names(moveTargetFolders(entries, selected, false))).toEqual(['movies', 'shows']);
	});

	it('hides the selected names when the picker shows the source directory', () => {
		expect(names(moveTargetFolders(entries, selected, true))).toEqual(['shows']);
	});

	it('hides the last segment of a nested selected path', () => {
		expect(names(moveTargetFolders(entries, new Set(['raw::deep/er/shows']), true))).toEqual(['movies']);
	});
});

describe('orderForDelete', () => {
	it('puts longer subpaths first so children precede parents', () => {
		const items = [{ subpath: 'a' }, { subpath: 'a/b/c' }, { subpath: 'a/b' }];
		expect(orderForDelete(items).map((i) => i.subpath)).toEqual(['a/b/c', 'a/b', 'a']);
	});

	it('keeps equal-length paths in their original order and does not mutate', () => {
		const items = [{ subpath: 'bb' }, { subpath: 'aa' }, { subpath: 'c' }];
		const ordered = orderForDelete(items);
		expect(ordered.map((i) => i.subpath)).toEqual(['bb', 'aa', 'c']);
		expect(ordered).not.toBe(items);
		expect(items[0].subpath).toBe('bb');
	});
});

describe('bulkResultFeedback', () => {
	it('reports failures as an error for both verbs', () => {
		expect(bulkResultFeedback('Moved', 2, 1)).toEqual({ type: 'error', message: 'Moved 2, failed 1' });
		expect(bulkResultFeedback('Deleted', 0, 3)).toEqual({ type: 'error', message: 'Deleted 0, failed 3' });
	});

	it('reports a singular success', () => {
		expect(bulkResultFeedback('Deleted', 1, 0)).toEqual({ type: 'success', message: 'Deleted 1 item' });
	});

	it('reports a plural success', () => {
		expect(bulkResultFeedback('Moved', 3, 0)).toEqual({ type: 'success', message: 'Moved 3 items' });
		expect(bulkResultFeedback('Moved', 0, 0)).toEqual({ type: 'success', message: 'Moved 0 items' });
	});
});

describe('cleanupFeedback', () => {
	it('words a clean singular and plural success', () => {
		expect(cleanupFeedback(1, 'folder', 0)).toEqual({ type: 'success', message: 'Deleted 1 folder' });
		expect(cleanupFeedback(2, 'transcoder job', 0)).toEqual({
			type: 'success',
			message: 'Deleted 2 transcoder jobs'
		});
	});

	it('adds the error count and tone when there were errors', () => {
		expect(cleanupFeedback(1, 'folder', 2)).toEqual({ type: 'error', message: 'Deleted 1 folder, 2 error(s)' });
	});
});

describe('fixedPermissionsMessage', () => {
	it('words the singular and plural count', () => {
		expect(fixedPermissionsMessage('Movie', 1)).toBe('Fixed permissions on Movie (1 item)');
		expect(fixedPermissionsMessage('Movie', 4)).toBe('Fixed permissions on Movie (4 items)');
	});
});
