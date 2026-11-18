import { describe, it, expect, vi, beforeEach, afterEach, type Mock } from 'vitest';
import { renderComponent, screen, cleanup, waitFor } from '$lib/testing/render';

vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	return { page: writable({ params: { slug: 'a' }, url: new URL('http://localhost/help') }) };
});

vi.mock('$lib/help/api', async () => {
	const actual = await vi.importActual<typeof import('$lib/help/api')>('$lib/help/api');
	return {
		...actual,
		fetchDocsNav: vi.fn(),
		fetchDocsPage: vi.fn(),
		loadDocsSearch: vi.fn()
	};
});

import HelpPage from '../[...slug]/+page.svelte';
import { page } from '$app/stores';
import { fetchDocsNav, fetchDocsPage } from '$lib/help/api';

type Deferred<T> = { promise: Promise<T>; resolve: (v: T) => void; reject: (e: unknown) => void };

function deferred<T>(): Deferred<T> {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

function docPage(id: string, title: string) {
	return {
		id,
		title,
		html: `<h1 id="${id}">${title}</h1>`,
		toc: [],
		source: `docs/${id}.md`,
		editUrl: `https://github.com/o/r/edit/main/docs/${id}.md`
	};
}

function goTo(slug: string) {
	(page as unknown as { set: (v: unknown) => void }).set({
		params: { slug },
		url: new URL('http://localhost/help')
	});
}

let pending: Record<string, Deferred<ReturnType<typeof docPage>>>;
let main: HTMLElement;
let scrollTo: Mock<(x: number, y: number) => void>;

beforeEach(() => {
	goTo('a');
	pending = { a: deferred(), b: deferred() };
	vi.mocked(fetchDocsNav).mockResolvedValue([]);
	vi.mocked(fetchDocsPage).mockImplementation((id: string) => pending[id].promise);
	main = document.createElement('main');
	scrollTo = vi.fn<(x: number, y: number) => void>();
	main.scrollTo = scrollTo as unknown as typeof main.scrollTo;
	document.body.appendChild(main);
});
afterEach(() => {
	cleanup();
	main.remove();
	vi.clearAllMocks();
	window.location.hash = '';
});

describe('/help page when the route changes while mounted', () => {
	it('drops a page fetch that resolves after the route moved on', async () => {
		const { container } = renderComponent(HelpPage);
		await waitFor(() => expect(fetchDocsPage).toHaveBeenCalledWith('a'));
		goTo('b');
		await waitFor(() => expect(fetchDocsPage).toHaveBeenCalledWith('b'));

		pending.a.resolve(docPage('a', 'Page A'));
		await new Promise((r) => setTimeout(r, 20));
		expect(container.querySelector('article')).toBeNull();
		expect(screen.getByText('Loading')).toBeInTheDocument();
		expect(scrollTo).not.toHaveBeenCalled();

		pending.b.resolve(docPage('b', 'Page B'));
		await waitFor(() => expect(container.querySelector('article.docs-prose h1')?.textContent).toBe('Page B'));
		expect(document.title).toBe('ARM - Page B - Help');
		await waitFor(() => expect(scrollTo).toHaveBeenCalledTimes(1));
	});

	it('skips the fragment scroll when the route moves on right after the page rendered', async () => {
		const { container } = renderComponent(HelpPage);
		await waitFor(() => expect(fetchDocsPage).toHaveBeenCalledWith('a'));

		pending.a.resolve(docPage('a', 'Page A'));
		// One microtask lets the load's .then run up to its `await tick()`.
		await Promise.resolve();
		goTo('b');
		await waitFor(() => expect(fetchDocsPage).toHaveBeenCalledWith('b'));
		await new Promise((r) => setTimeout(r, 20));
		expect(scrollTo).not.toHaveBeenCalled();
		expect(container.querySelector('article')).toBeNull();

		pending.b.resolve(docPage('b', 'Page B'));
		await waitFor(() => expect(container.querySelector('article.docs-prose h1')?.textContent).toBe('Page B'));
		await waitFor(() => expect(scrollTo).toHaveBeenCalledTimes(1));
	});

	it('keeps the new page and shows no error when the old page fetch rejects late', async () => {
		const { container } = renderComponent(HelpPage);
		await waitFor(() => expect(fetchDocsPage).toHaveBeenCalledWith('a'));
		goTo('b');
		await waitFor(() => expect(fetchDocsPage).toHaveBeenCalledWith('b'));

		pending.b.resolve(docPage('b', 'Page B'));
		await waitFor(() => expect(container.querySelector('article.docs-prose h1')?.textContent).toBe('Page B'));

		pending.a.reject(new Error('network'));
		await new Promise((r) => setTimeout(r, 20));
		expect(container.querySelector('article.docs-prose h1')?.textContent).toBe('Page B');
		expect(screen.queryByText('Help is unavailable')).not.toBeInTheDocument();
		expect(screen.queryByText('Page not found')).not.toBeInTheDocument();
	});
});
