import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import RankedListField from '../RankedListField.svelte';
import type { ConfigFieldMeta } from '$lib/types/api.gen';

const f = (): ConfigFieldMeta => ({
	key: 'episode_sources',
	group: 'Metadata',
	tier: 'operator',
	label: 'Episode sources',
	help: 'Tried top to bottom.',
	type: 'ranked',
	editable: true,
	enum_values: ['tmdb', 'tvmaze', 'tvdb'],
	enum_labels: { tmdb: 'TMDb', tvmaze: 'TVmaze', tvdb: 'TVDB' },
	enum_requires: { tmdb: 'tmdb_api_key', tvdb: 'tvdb_api_key' }
});

const names = () =>
	Array.from(document.querySelectorAll('.list-row-main')).map((el) => el.firstElementChild?.textContent?.trim());

afterEach(() => cleanup());

describe('RankedListField', () => {
	it('lists on rows in rank order, then off rows; off rows have no move buttons', () => {
		renderComponent(RankedListField, { props: { field: f(), value: ['tvdb', 'tmdb'] } });
		expect(names()).toEqual(['TVDB', 'TMDb', 'TVmaze']);
		expect(screen.getByText('Not used')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Move TVmaze up' })).toBeNull();
	});

	it('checking appends to the ranking; unchecking moves to the off group', async () => {
		renderComponent(RankedListField, { props: { field: f(), value: ['tmdb'] } });
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Use TVDB' }));
		expect(names()).toEqual(['TMDb', 'TVDB', 'TVmaze']);
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Use TMDb' }));
		expect(names()).toEqual(['TVDB', 'TMDb', 'TVmaze']);
	});

	it('moves rows, disables the ends, keeps focus and announces', async () => {
		renderComponent(RankedListField, { props: { field: f(), value: ['tmdb', 'tvmaze'] } });
		expect(screen.getByRole('button', { name: 'Move TMDb up' })).toBeDisabled();
		const up = screen.getByRole('button', { name: 'Move TVmaze up' });
		up.focus();
		await fireEvent.click(up);
		expect(names()).toEqual(['TVmaze', 'TMDb', 'TVDB']);
		expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Move TVmaze down' }));
		expect(screen.getByText('TVmaze moved to rank 1')).toBeInTheDocument();
	});

	it('flags a missing key on any row, and treats a masked secret as set', () => {
		renderComponent(RankedListField, {
			props: { field: f(), value: ['tmdb'], config: { tmdb_api_key: '<hidden>', tvdb_api_key: '' } }
		});
		const chip = screen.getByRole('link', { name: /Needs TVDB key/ });
		expect(chip).toHaveAttribute('href', '#Metadata/tvdb_api_key');
		expect(screen.queryByRole('link', { name: /Needs TMDb key/ })).toBeNull();
	});

	it('renders all rows as not used for an empty value', () => {
		renderComponent(RankedListField, { props: { field: f(), value: [] } });
		expect(screen.getAllByText('Not used')).toHaveLength(3);
		expect(screen.queryAllByRole('button')).toHaveLength(0);
	});

	it('drops values the schema does not know', () => {
		renderComponent(RankedListField, { props: { field: f(), value: ['bogus', 'tvmaze'] } });
		expect(names()).toEqual(['TVmaze', 'TMDb', 'TVDB']);
	});
});
