import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, cleanup } from '$lib/test-utils';
import MusicReleaseTracklist from '../MusicReleaseTracklist.svelte';
import type { MetadataReleaseTrack, TrackView } from '$lib/types/api.gen';

const disc = (seconds: number | null) => ({ expected_duration_seconds: seconds }) as TrackView;

const tracks: MetadataReleaseTrack[] = [
	{ position: 1, title: 'So What', length_ms: 100000 },
	{ position: 2, title: 'Blue in Green', length_ms: 200000 },
	{ position: 3, title: 'All Blues', length_ms: 300000 },
	{ position: 4, title: 'Flamenco Sketches', length_ms: 400000 }
];

type ListProps = {
	tracks: MetadataReleaseTrack[];
	discTracks: TrackView[];
	mbTotalMs: number;
	discTotalSec: number | null;
};

function renderList(overrides: Partial<ListProps> = {}) {
	const props: ListProps = {
		tracks,
		discTracks: [disc(101), disc(205), disc(330)],
		mbTotalMs: 1000000,
		discTotalSec: 1001,
		...overrides
	};
	return renderComponent(MusicReleaseTracklist, { props });
}

const headers = (c: HTMLElement) => [...c.querySelectorAll('thead th')].map((th) => th.textContent);
const cells = (row: Element) => [...row.querySelectorAll('td')].map((td) => td.textContent?.trim());
const bodyRows = (c: HTMLElement) => [...c.querySelectorAll('tbody tr')];
const tone = (row: Element) => row.querySelector('.music-search-match')?.getAttribute('data-tone');

describe('MusicReleaseTracklist', () => {
	afterEach(() => cleanup());

	describe('with disc tracks', () => {
		it('shows the five headers', () => {
			const { container } = renderList();
			expect(headers(container)).toEqual(['#', 'Title', 'Disc Length', 'Match Length', 'Match']);
		});

		it('shows each row disc length and length, with - past the last disc track', () => {
			const { container } = renderList();
			const rows = bodyRows(container);
			expect(rows).toHaveLength(4);
			expect([cells(rows[0])[2], cells(rows[0])[3]]).toEqual(['1:41', '1:40']);
			expect([cells(rows[1])[2], cells(rows[1])[3]]).toEqual(['3:25', '3:20']);
			expect([cells(rows[2])[2], cells(rows[2])[3]]).toEqual(['5:30', '5:00']);
			expect([cells(rows[3])[2], cells(rows[3])[3]]).toEqual(['-', '6:40']);
		});

		it('draws each match kind in its tone', () => {
			const { container } = renderList();
			const rows = bodyRows(container);
			expect(rows.map(tone)).toEqual(['success', 'warning', 'danger', 'muted']);
			expect(rows.map((r) => r.querySelector('.music-search-match')?.getAttribute('title'))).toEqual([
				'match',
				'close',
				'mismatch',
				'unknown'
			]);
		});

		it('shows the Total row with both totals and a match tone', () => {
			const { container } = renderList();
			const foot = container.querySelector('tfoot tr') as Element;
			expect(cells(foot).slice(0, 4)).toEqual(['Total', '', '16:41', '16:40']);
			expect(tone(foot)).toBe('success');
		});

		it('draws the Total row in the danger tone when the totals differ widely', () => {
			const { container } = renderList({ mbTotalMs: 2000000 });
			expect(tone(container.querySelector('tfoot tr') as Element)).toBe('danger');
		});

		it('shows - for the disc total when it is unknown', () => {
			const { container } = renderList({ discTotalSec: null });
			const foot = container.querySelector('tfoot tr') as Element;
			expect(cells(foot)[2]).toBe('-');
			expect(tone(foot)).toBe('muted');
		});
	});

	describe('without disc tracks', () => {
		it('shows the three headers and no Disc Length, Match or Total', () => {
			const { container } = renderList({ discTracks: [] });
			expect(headers(container)).toEqual(['#', 'Title', 'Duration']);
			expect(container.querySelector('tfoot')).toBeNull();
			expect(container.querySelector('.music-search-match')).toBeNull();
			expect(cells(bodyRows(container)[0])).toEqual(['1', 'So What', '1:40']);
		});
	});

	describe('rows', () => {
		it('falls back to the row number when the position is null', () => {
			const { container } = renderList({
				discTracks: [],
				tracks: [{ position: null, title: 'Untitled', length_ms: 60000 }]
			});
			expect(cells(bodyRows(container)[0])[0]).toBe('1');
		});

		it('shows - for a null length', () => {
			const { container } = renderList({
				discTracks: [],
				tracks: [{ position: 1, title: 'Silence', length_ms: null }]
			});
			expect(cells(bodyRows(container)[0])[2]).toBe('-');
		});
	});
});
