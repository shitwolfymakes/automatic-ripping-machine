import MiniSearch from 'minisearch';

export const SEARCH_OPTIONS = { idField: 'id', fields: ['title', 'headings', 'text'], storeFields: ['title'] };

export function buildSearchIndex(rendered) {
	const ms = new MiniSearch(SEARCH_OPTIONS);
	ms.addAll(rendered.map((r) => ({ id: r.page.id, title: r.page.title, headings: r.toc.map((t) => t.text).join(' '), text: r.text })));
	return { options: SEARCH_OPTIONS, index: ms.toJSON() };
}
