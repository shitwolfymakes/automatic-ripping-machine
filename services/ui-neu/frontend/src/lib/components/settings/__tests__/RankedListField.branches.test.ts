import { describe, it, expect, afterEach } from 'vitest';
import { tick } from 'svelte';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/testing/render';
import RankedListField from '../RankedListField.svelte';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

// Branch pins for RankedListField, beside RankedListField.test.ts. No branch
// is left open: the double click below reaches move's early return.

const field = (extra: Partial<ConfigFieldMeta> = {}): ConfigFieldMeta => ({
	key: 'episode_sources',
	group: 'Identification',
	tier: 'operator',
	label: 'Episode sources',
	help: 'Tried top to bottom.',
	type: 'ranked',
	editable: true,
	enum_values: ['tmdb', 'tvmaze'],
	enum_labels: { tmdb: 'TMDb', tvmaze: 'TVmaze' },
	...extra
});

// Each row's checkbox is named after its entry, so their names give the
// rows in order.
const names = () => screen.getAllByRole('checkbox').map((box) => box.getAttribute('aria-label'));

afterEach(() => cleanup());

describe('RankedListField', () => {
	it('draws no rows for a field with no enum_values', () => {
		renderComponent(RankedListField, { props: { field: field({ enum_values: undefined }), value: ['tmdb'] } });
		expect(screen.getByRole('list', { name: 'Episode sources' })).toBeInTheDocument();
		expect(screen.queryAllByRole('listitem')).toHaveLength(0);
		expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
	});

	it('shows the key itself for a value with no enum_labels entry', () => {
		renderComponent(RankedListField, { props: { field: field({ enum_labels: { tmdb: 'TMDb' } }), value: ['tmdb'] } });
		expect(names()).toEqual(['Use TMDb', 'Use tvmaze']);
		expect(screen.getByText('tvmaze')).toBeInTheDocument();
	});

	it('moves the row by one rank when the same button is clicked twice before a redraw', async () => {
		renderComponent(RankedListField, { props: { field: field(), value: ['tmdb', 'tvmaze'] } });
		const down = screen.getByRole('button', { name: 'Move TMDb down' });
		fireEvent.click(down);
		fireEvent.click(down);
		await tick();
		await tick();
		expect(names()).toEqual(['Use TVmaze', 'Use TMDb']);
		expect(screen.getByText('Rank 1')).toBeInTheDocument();
		expect(screen.getByText('Rank 2')).toBeInTheDocument();
	});
});
