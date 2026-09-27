import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';

const params = vi.hoisted(() => ({ slug: '' }));

vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ params, url: new URL('http://localhost/help') }) };
});

vi.mock('$lib/docs/api', async () => {
	const actual = await vi.importActual<typeof import('$lib/docs/api')>('$lib/docs/api');
	return {
		...actual,
		fetchDocsNav: vi.fn(),
		fetchDocsPage: vi.fn(),
		loadDocsSearch: vi.fn()
	};
});

import HelpPage from '../[...slug]/+page.svelte';
import { fetchDocsNav, fetchDocsPage, loadDocsSearch, DocsNotFoundError } from '$lib/docs/api';
import MiniSearch from 'minisearch';

const NAV = [
	{
		id: 'guide',
		label: 'Guide',
		groups: [
			{
				label: 'Getting Started',
				items: [
					{ label: 'Home', href: '/help', external: false, pageId: 'guide/home' },
					{
						label: 'Getting Started',
						href: '/help/guide/getting-started',
						external: false,
						pageId: 'guide/getting-started'
					},
					{ label: 'Open an issue', href: 'https://github.com/o/r/issues', external: true, pageId: null }
				]
			}
		]
	}
];
const PAGE = {
	id: 'guide/getting-started',
	title: 'Getting Started',
	html: '<h1 id="getting-started">Getting Started</h1><p>See <a href="/help/guide/configuring-arm#options">options</a>.</p>',
	toc: [
		{ depth: 2, id: 'a', text: 'A' },
		{ depth: 2, id: 'b', text: 'B' }
	],
	source: 'docs/user/Getting-Started.md',
	editUrl: 'https://github.com/o/r/edit/main/docs/user/Getting-Started.md'
};

beforeEach(() => {
	params.slug = 'guide/getting-started';
	vi.mocked(fetchDocsNav).mockResolvedValue(NAV);
	vi.mocked(fetchDocsPage).mockResolvedValue(PAGE);
});
afterEach(() => {
	cleanup();
	vi.clearAllMocks();
	// Navigation tests set window.location.hash; jsdom persists it across
	// tests, so reset it back to the default (no hash).
	window.location.hash = '';
});

describe('/help page', () => {
	it('renders the page fragment inside docs-prose with internal links as /help routes', async () => {
		const { container } = renderComponent(HelpPage);
		await waitFor(() => expect(container.querySelector('article.docs-prose h1')?.textContent).toBe('Getting Started'));
		expect(container.querySelector('article.docs-prose a')?.getAttribute('href')).toBe(
			'/help/guide/configuring-arm#options'
		);
		expect(fetchDocsPage).toHaveBeenCalledWith('guide/getting-started');
		expect(screen.getByText('Edit this page on GitHub').getAttribute('href')).toBe(PAGE.editUrl);
	});

	it('marks the active nav item and opens external items in a new tab', async () => {
		renderComponent(HelpPage);
		const active = await screen.findByRole('link', { name: 'Getting Started' });
		expect(active.getAttribute('data-active')).toBe('true');
		expect(screen.getByRole('link', { name: 'Open an issue' }).getAttribute('target')).toBe('_blank');
	});

	it('loads the guide home for the bare /help route', async () => {
		params.slug = '';
		renderComponent(HelpPage);
		await waitFor(() => expect(fetchDocsPage).toHaveBeenCalledWith('guide/home'));
	});

	it('shows a not-found state for a missing page', async () => {
		vi.mocked(fetchDocsPage).mockRejectedValue(new DocsNotFoundError('x'));
		renderComponent(HelpPage);
		expect(await screen.findByText('Page not found')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: 'Back to Help' }).getAttribute('href')).toBe('/help');
	});

	it('shows an unavailable state when loading fails for another reason', async () => {
		vi.mocked(fetchDocsPage).mockRejectedValue(new Error('network'));
		renderComponent(HelpPage);
		expect(await screen.findByText('Help is unavailable')).toBeInTheDocument();
	});

	it('still renders the page when nav.json is unavailable', async () => {
		vi.mocked(fetchDocsNav).mockRejectedValue(new DocsNotFoundError('nav.json'));
		const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
		const { container } = renderComponent(HelpPage);
		await waitFor(() => expect(container.querySelector('article.docs-prose h1')).not.toBeNull());
		expect(warn).toHaveBeenCalled();
	});

	it('searches and lists hits as /help links', async () => {
		const ms = new MiniSearch({ idField: 'id', fields: ['title', 'headings', 'text'], storeFields: ['title'] });
		ms.addAll([{ id: 'guide/makemkv', title: 'MakeMKV', headings: '', text: 'key' }]);
		vi.mocked(loadDocsSearch).mockResolvedValue(ms);
		renderComponent(HelpPage);
		await fireEvent.input(screen.getByLabelText('Search help'), { target: { value: 'makemkv' } });
		const hit = await screen.findByRole('link', { name: 'MakeMKV' });
		expect(hit.getAttribute('href')).toBe('/help/guide/makemkv');
	});

	it('shows No matches for a query with no hits', async () => {
		const ms = new MiniSearch({ idField: 'id', fields: ['title'], storeFields: ['title'] });
		vi.mocked(loadDocsSearch).mockResolvedValue(ms);
		renderComponent(HelpPage);
		await fireEvent.input(screen.getByLabelText('Search help'), { target: { value: 'zzz' } });
		expect(await screen.findByText('No matches')).toBeInTheDocument();
	});

	it('scrolls the main scroll container to top after a page loads with no hash', async () => {
		window.location.hash = '';
		const main = document.createElement('main');
		const scrollTo = vi.fn();
		main.scrollTo = scrollTo;
		document.body.appendChild(main);
		try {
			renderComponent(HelpPage);
			await waitFor(() => expect(scrollTo).toHaveBeenCalledWith(0, 0));
		} finally {
			main.remove();
		}
	});

	it('renders the article for a malformed location hash instead of showing it unavailable', async () => {
		window.location.hash = '#%E0%A4%A';
		const { container } = renderComponent(HelpPage);
		await waitFor(() => expect(container.querySelector('article.docs-prose h1')?.textContent).toBe('Getting Started'));
		// A pre-fix decode failure surfaces asynchronously (it's caught by a
		// later .catch), after this article has already rendered once, so
		// give that a chance to run before asserting the state held.
		await new Promise((r) => setTimeout(r, 20));
		expect(container.querySelector('article.docs-prose h1')?.textContent).toBe('Getting Started');
		expect(screen.queryByText('Help is unavailable')).not.toBeInTheDocument();
	});
});
