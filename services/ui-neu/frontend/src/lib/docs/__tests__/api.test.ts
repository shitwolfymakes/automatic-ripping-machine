import { describe, it, expect, vi, afterEach } from 'vitest';
import MiniSearch from 'minisearch';
import { slugToId, idToRoute, fetchDocsPage, searchDocs, DocsNotFoundError } from '../api';

afterEach(() => vi.unstubAllGlobals());

function stubFetch(body: string, init: { status?: number; type?: string } = {}) {
	const fetchMock = vi.fn(
		async () =>
			new Response(body, { status: init.status ?? 200, headers: { 'content-type': init.type ?? 'application/json' } })
	);
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

describe('slugToId', () => {
	it('maps the empty slug to the guide home', () => {
		expect(slugToId('')).toBe('guide/home');
		expect(slugToId(undefined)).toBe('guide/home');
	});
	it('trims slashes and lowercases', () => {
		expect(slugToId('guide/getting-started/')).toBe('guide/getting-started');
		expect(slugToId('Guide/Getting-Started')).toBe('guide/getting-started');
	});
});

describe('idToRoute', () => {
	it('routes home to /help and others under it', () => {
		expect(idToRoute('guide/home')).toBe('/help');
		expect(idToRoute('dev/arch')).toBe('/help/dev/arch');
	});
});

describe('fetchDocsPage', () => {
	it('loads a page from /docs-data/pages', async () => {
		const fetchMock = stubFetch(
			JSON.stringify({ id: 'dev/arch', title: 'Architecture', html: '<p>x</p>', toc: [], source: 's', editUrl: 'e' })
		);
		const page = await fetchDocsPage('dev/arch');
		expect(page.title).toBe('Architecture');
		expect(fetchMock).toHaveBeenCalledWith('/docs-data/pages/dev/arch.json');
	});
	it('treats a 404 as not found', async () => {
		stubFetch('nope', { status: 404, type: 'text/plain' });
		await expect(fetchDocsPage('dev/none')).rejects.toBeInstanceOf(DocsNotFoundError);
	});
	it('treats the SPA fallback (200 text/html) as not found', async () => {
		stubFetch('<!doctype html>', { type: 'text/html' });
		await expect(fetchDocsPage('dev/none')).rejects.toBeInstanceOf(DocsNotFoundError);
	});
	it('rejects ids that are not section/slug without fetching', async () => {
		const fetchMock = stubFetch('{}');
		await expect(fetchDocsPage('guide/../x')).rejects.toBeInstanceOf(DocsNotFoundError);
		await expect(fetchDocsPage('a/b/c')).rejects.toBeInstanceOf(DocsNotFoundError);
		expect(fetchMock).not.toHaveBeenCalled();
	});
	it('treats malformed JSON in a 200 application/json response as not found', async () => {
		stubFetch('{not json', { type: 'application/json' });
		await expect(fetchDocsPage('dev/arch')).rejects.toBeInstanceOf(DocsNotFoundError);
	});
});

describe('searchDocs', () => {
	const ms = new MiniSearch({ idField: 'id', fields: ['title', 'headings', 'text'], storeFields: ['title'] });
	ms.addAll([
		{ id: 'guide/makemkv', title: 'MakeMKV', headings: 'Keys', text: 'beta key' },
		{ id: 'guide/home', title: 'ARM Wiki', headings: '', text: 'welcome' }
	]);
	it('returns hits with app routes', () => {
		expect(searchDocs(ms, 'makemkv')).toEqual([{ id: 'guide/makemkv', title: 'MakeMKV', href: '/help/guide/makemkv' }]);
	});
	it('returns nothing for a blank query', () => {
		expect(searchDocs(ms, '   ')).toEqual([]);
	});
});
