import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import { SEARCH_SOURCES } from '$lib/settings/search-providers';
import TitleSourcePicker from '../TitleSourcePicker.svelte';

const ALL_KEYED = { tmdb: true, omdb: true, tvdb: true };
const NONE_KEYED = { tmdb: false, omdb: false, tvdb: false };

function renderPicker(props: Record<string, unknown> = {}) {
	const onpick = vi.fn();
	const view = renderComponent(TitleSourcePicker, {
		options: SEARCH_SOURCES.tv,
		source: 'tmdb',
		keyed: ALL_KEYED,
		onpick,
		...props
	});
	return { onpick, view, select: screen.getByLabelText('Search with') as HTMLSelectElement };
}

describe('TitleSourcePicker', () => {
	afterEach(cleanup);

	it('lists the options in order with their labels', () => {
		const { select } = renderPicker();
		expect([...select.options].map((o) => o.textContent)).toEqual(['TMDb', 'OMDb', 'TVmaze', 'TVDB']);
		expect([...select.options].map((o) => o.value)).toEqual(['tmdb', 'omdb', 'tvmaze', 'tvdb']);
	});

	it('disables an unkeyed source and labels it as needing an API key', () => {
		const { select } = renderPicker({ keyed: { tmdb: true, omdb: false, tvdb: true } });
		const omdb = select.options[1];
		expect(omdb.disabled).toBe(true);
		expect(omdb.textContent).toBe('OMDb (needs API key)');
		expect(select.options[0].disabled).toBe(false);
	});

	it('never disables TVmaze, even with no keys saved', () => {
		const { select } = renderPicker({ keyed: NONE_KEYED });
		const tvmaze = [...select.options].find((o) => o.value === 'tvmaze')!;
		expect(tvmaze.disabled).toBe(false);
		expect(tvmaze.textContent).toBe('TVmaze');
	});

	it('selects the given source', () => {
		const { select } = renderPicker({ source: 'tvmaze' });
		expect(select.value).toBe('tvmaze');
	});

	it('calls onpick with the id of the chosen source', async () => {
		const { select, onpick } = renderPicker();
		await fireEvent.change(select, { target: { value: 'omdb' } });
		expect(onpick).toHaveBeenCalledWith('omdb');
	});

	it('re-enables a source when its key is saved later', async () => {
		const { view, select } = renderPicker({ keyed: NONE_KEYED });
		expect(select.options[0].disabled).toBe(true);
		await view.rerender({ keyed: ALL_KEYED });
		expect(select.options[0].disabled).toBe(false);
		expect(select.options[0].textContent).toBe('TMDb');
	});

	it('renders with an undefined source', () => {
		const { select } = renderPicker({ source: undefined });
		expect(select.options).toHaveLength(4);
	});
});
