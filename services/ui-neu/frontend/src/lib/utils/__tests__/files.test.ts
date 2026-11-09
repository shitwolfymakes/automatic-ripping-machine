import { describe, it, expect } from 'vitest';
import { sortEntries, nextSort, sortRoots } from '../files';
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
