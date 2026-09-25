// Client for the in-app help bundle that site/ builds into the image at
// /docs-data/ (nav.json, pages/<section>/<slug>.json, search.json).
import MiniSearch, { type Options } from 'minisearch';

export const DOCS_BASE = '/docs-data';
export const HOME_ID = 'guide/home';

export interface DocsTocEntry {
	depth: number;
	id: string;
	text: string;
}
export interface DocsPage {
	id: string;
	title: string;
	html: string;
	toc: DocsTocEntry[];
	source: string;
	editUrl: string;
}
export interface DocsNavItem {
	label: string;
	href: string;
	external: boolean;
	pageId: string | null;
}
export interface DocsNavGroup {
	label: string | null;
	items: DocsNavItem[];
}
export interface DocsNavSection {
	id: string;
	label: string;
	groups: DocsNavGroup[];
}
export interface DocsSearchHit {
	id: string;
	title: string;
	href: string;
}

export class DocsNotFoundError extends Error {}

const ID = /^[a-z0-9_-]+\/[a-z0-9_-]+$/;

export function slugToId(slug: string | undefined): string {
	const clean = (slug ?? '').replace(/^\/+|\/+$/g, '').toLowerCase();
	return clean === '' ? HOME_ID : clean;
}

export function idToRoute(id: string): string {
	return id === HOME_ID ? '/help' : `/help/${id}`;
}

// nginx answers a missing /docs-data/ file with a real 404, but vite dev (and
// any path that slips past it) hands back the SPA's index.html with a 200,
// so a non-JSON body counts as missing too.
async function getJson<T>(path: string): Promise<T> {
	const res = await fetch(`${DOCS_BASE}/${path}`);
	const type = res.headers.get('content-type') ?? '';
	if (!res.ok || !type.includes('application/json')) throw new DocsNotFoundError(path);
	try {
		return (await res.json()) as T;
	} catch {
		// A 200 application/json response with an unparsable body is just as
		// missing as a real 404 or the SPA fallback.
		throw new DocsNotFoundError(path);
	}
}

export function fetchDocsPage(id: string): Promise<DocsPage> {
	if (!ID.test(id)) return Promise.reject(new DocsNotFoundError(id));
	return getJson<DocsPage>(`pages/${id}.json`);
}

export function fetchDocsNav(): Promise<DocsNavSection[]> {
	return getJson<DocsNavSection[]>('nav.json');
}

let searchPromise: Promise<MiniSearch> | null = null;

export function loadDocsSearch(): Promise<MiniSearch> {
	searchPromise ??= getJson<{ options: Options; index: Parameters<typeof MiniSearch.loadJS>[0] }>('search.json')
		.then((d) => MiniSearch.loadJS(d.index, d.options))
		.catch((e) => {
			searchPromise = null;
			throw e;
		});
	return searchPromise;
}

export function searchDocs(ms: MiniSearch, query: string, limit = 8): DocsSearchHit[] {
	if (!query.trim()) return [];
	return ms
		.search(query, { prefix: true, fuzzy: 0.2, boost: { title: 3, headings: 2 } })
		.slice(0, limit)
		.map((r) => ({ id: String(r.id), title: String(r.title), href: idToRoute(String(r.id)) }));
}
