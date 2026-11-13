import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/docs/api', async () => {
	const actual = await vi.importActual<typeof import('$lib/docs/api')>('$lib/docs/api');
	return { ...actual, fetchDocsPage: vi.fn() };
});

import { fetchDocsPage, DocsNotFoundError, type DocsPage } from '$lib/docs/api';
import { HelpDoc } from '../help-doc.svelte';

const mockFetch = vi.mocked(fetchDocsPage);

function page(id: string): DocsPage {
	return { id, title: id, html: '<p>x</p>', toc: [], source: `${id}.md`, editUrl: `https://example.test/${id}` };
}

let route: string;
let helpDoc: HelpDoc;

beforeEach(() => {
	vi.resetAllMocks();
	route = 'guide/a';
	helpDoc = new HelpDoc(() => route);
});

describe('HelpDoc', () => {
	it('starts with no doc and a loading status', () => {
		expect(helpDoc.doc).toBeNull();
		expect(helpDoc.status).toBe('loading');
	});

	it('sets loading at once, even over a page already shown', async () => {
		mockFetch.mockResolvedValueOnce(page('guide/a'));
		await helpDoc.load('guide/a', async () => {});
		expect(helpDoc.status).toBe('ready');

		mockFetch.mockReturnValueOnce(new Promise(() => {}));
		void helpDoc.load('guide/a', async () => {});
		expect(helpDoc.status).toBe('loading');
	});

	it('shows a loaded page and then calls afterShow once', async () => {
		const p = page('guide/a');
		mockFetch.mockResolvedValueOnce(p);
		const afterShow = vi.fn(async () => {
			expect(helpDoc.doc).toEqual(p);
			expect(helpDoc.status).toBe('ready');
		});
		await helpDoc.load('guide/a', afterShow);
		expect(mockFetch).toHaveBeenCalledWith('guide/a');
		expect(afterShow).toHaveBeenCalledTimes(1);
		expect(helpDoc.doc).toEqual(p);
	});

	it('drops a page that resolves after the route moved on', async () => {
		mockFetch.mockResolvedValueOnce(page('guide/a'));
		const afterShow = vi.fn(async () => {});
		const loading = helpDoc.load('guide/a', afterShow);
		route = 'guide/b';
		await loading;
		expect(helpDoc.doc).toBeNull();
		expect(helpDoc.status).toBe('loading');
		expect(afterShow).not.toHaveBeenCalled();
	});

	it('sets missing for a DocsNotFoundError', async () => {
		mockFetch.mockRejectedValueOnce(new DocsNotFoundError('guide/a'));
		await helpDoc.load('guide/a', async () => {});
		expect(helpDoc.doc).toBeNull();
		expect(helpDoc.status).toBe('missing');
	});

	it('sets error for any other failure', async () => {
		mockFetch.mockRejectedValueOnce(new Error('boom'));
		await helpDoc.load('guide/a', async () => {});
		expect(helpDoc.doc).toBeNull();
		expect(helpDoc.status).toBe('error');
	});

	it('drops a failure that settles after the route moved on', async () => {
		mockFetch.mockRejectedValueOnce(new Error('boom'));
		const loading = helpDoc.load('guide/a', async () => {});
		route = 'guide/b';
		await loading;
		expect(helpDoc.doc).toBeNull();
		expect(helpDoc.status).toBe('loading');
	});

	it('lands in error with no doc when afterShow throws on the current page', async () => {
		mockFetch.mockResolvedValueOnce(page('guide/a'));
		await helpDoc.load('guide/a', async () => {
			throw new Error('scroll failed');
		});
		expect(helpDoc.doc).toBeNull();
		expect(helpDoc.status).toBe('error');
	});
});
