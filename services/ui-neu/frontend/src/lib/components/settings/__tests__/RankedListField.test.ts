import { describe, it, expect, afterEach } from 'vitest';
import { tick } from 'svelte';
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

	it('announces a rank on check and keeps focus on that row, then announces "not used" and keeps focus on uncheck', async () => {
		renderComponent(RankedListField, { props: { field: f(), value: ['tmdb'] } });
		const tvdbCheckbox = screen.getByRole('checkbox', { name: 'Use TVDB' });
		tvdbCheckbox.focus();
		await fireEvent.click(tvdbCheckbox);
		await tick();
		expect(screen.getByText('TVDB added at rank 2')).toBeInTheDocument();
		expect(document.activeElement).toBe(tvdbCheckbox);

		await fireEvent.click(tvdbCheckbox);
		await tick();
		expect(screen.getByText('TVDB not used')).toBeInTheDocument();
		expect(document.activeElement).toBe(tvdbCheckbox);
	});

	it('moves rows, disables the ends, keeps focus and announces', async () => {
		renderComponent(RankedListField, { props: { field: f(), value: ['tmdb', 'tvmaze'] } });
		expect(screen.getByRole('button', { name: 'Move TMDb up' })).toBeDisabled();
		const up = screen.getByRole('button', { name: 'Move TVmaze up' });
		up.focus();
		await fireEvent.click(up);
		// move() clears the live region and sets it again on its own tick, so
		// give the component one more tick to settle before reading its result.
		await tick();
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

	it('dedupes a repeated value, rendering it once', () => {
		renderComponent(RankedListField, { props: { field: f(), value: ['tvmaze', 'tvmaze', 'tmdb'] } });
		expect(names()).toEqual(['TVmaze', 'TMDb', 'TVDB']);
	});

	it('describes the list by the field help text id when helpId is passed', () => {
		renderComponent(RankedListField, {
			props: { field: f(), value: ['tmdb'], helpId: 'setting-help-episode_sources' }
		});
		expect(screen.getByRole('list', { name: 'Episode sources' })).toHaveAttribute(
			'aria-describedby',
			'setting-help-episode_sources'
		);
	});

	it('renders the lead control as a plain checkbox, not a bordered field-control', () => {
		renderComponent(RankedListField, { props: { field: f(), value: ['tmdb'] } });
		const checkbox = screen.getByRole('checkbox', { name: 'Use TMDb' });
		expect(checkbox).not.toHaveClass('field-control');
	});

	it('re-announces a move even when it produces the same wording as an earlier one', async () => {
		renderComponent(RankedListField, { props: { field: f(), value: ['tmdb', 'tvmaze', 'tvdb'] } });

		await fireEvent.click(screen.getByRole('button', { name: 'Move TVDB up' }));
		await tick();
		expect(screen.getByText('TVDB moved to rank 2')).toBeInTheDocument();

		// Uncheck a row with no move, so the live region's text is untouched but
		// TVDB's rank shifts from under it.
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Use TMDb' }));

		const live = document.querySelector('[aria-live="polite"]') as HTMLElement;
		const seen: string[] = [];
		const observer = new MutationObserver(() => seen.push(live.textContent ?? ''));
		observer.observe(live, { childList: true, characterData: true, subtree: true });

		// Same wording as the first move ("TVDB moved to rank 2"): without a
		// clear-then-set, Svelte would skip the DOM text update entirely.
		await fireEvent.click(screen.getByRole('button', { name: 'Move TVDB down' }));
		await tick();
		observer.disconnect();

		expect(seen).toContain('');
		expect(seen.at(-1)).toBe('TVDB moved to rank 2');
	});
});
