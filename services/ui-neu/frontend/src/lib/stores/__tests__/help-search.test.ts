import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('$lib/docs/api', async () => {
	const actual = await vi.importActual<typeof import('$lib/docs/api')>('$lib/docs/api');
	return { ...actual, loadDocsSearch: vi.fn() };
});

import { HelpSearch } from '../help-search.svelte';
import { loadDocsSearch } from '$lib/docs/api';
import MiniSearch from 'minisearch';

function index(): MiniSearch {
	const ms = new MiniSearch({ idField: 'id', fields: ['title', 'headings', 'text'], storeFields: ['title'] });
	ms.addAll([{ id: 'guide/makemkv', title: 'MakeMKV', headings: '', text: 'key' }]);
	return ms;
}

beforeEach(() => {
	vi.mocked(loadDocsSearch).mockReset();
	vi.mocked(loadDocsSearch).mockResolvedValue(index());
});

afterEach(() => {
	vi.restoreAllMocks();
});

describe('HelpSearch', () => {
	it('starts with an empty query and no hits', () => {
		const s = new HelpSearch();
		expect(s.query).toBe('');
		expect(s.hits).toEqual([]);
	});

	it('keeps the query and lists the hits for a matching query', async () => {
		const s = new HelpSearch();
		await s.run('makemkv');
		expect(s.query).toBe('makemkv');
		expect(s.hits).toEqual([{ id: 'guide/makemkv', title: 'MakeMKV', href: '/help/guide/makemkv' }]);
	});

	it('has no hits for a query that matches nothing', async () => {
		const s = new HelpSearch();
		await s.run('zzz');
		expect(s.query).toBe('zzz');
		expect(s.hits).toEqual([]);
	});

	it('loads the index once across two searches', async () => {
		const s = new HelpSearch();
		await s.run('makemkv');
		await s.run('make');
		expect(loadDocsSearch).toHaveBeenCalledTimes(1);
		expect(s.hits).toHaveLength(1);
	});

	it.each(['', '   '])('clears the hits for the blank query %j without loading the index', async (blank) => {
		const s = new HelpSearch();
		await s.run('makemkv');
		vi.mocked(loadDocsSearch).mockClear();
		await s.run(blank);
		expect(s.query).toBe(blank);
		expect(s.hits).toEqual([]);
		expect(loadDocsSearch).not.toHaveBeenCalled();
	});

	it('warns and has no hits when the index cannot be loaded, keeping the query', async () => {
		vi.mocked(loadDocsSearch).mockRejectedValue(new Error('search.json'));
		const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
		const s = new HelpSearch();
		await s.run('makemkv');
		expect(warn).toHaveBeenCalledWith('help: search.json unavailable');
		expect(s.query).toBe('makemkv');
		expect(s.hits).toEqual([]);
	});

	it('resets the query and the hits on clear', async () => {
		const s = new HelpSearch();
		await s.run('makemkv');
		s.clear();
		expect(s.query).toBe('');
		expect(s.hits).toEqual([]);
	});
});
