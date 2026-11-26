import { describe, it, expect, afterEach, vi } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/testing/render';
import MusicMappingConfirm from '../MusicMappingConfirm.svelte';
import type { TrackPair } from '$lib/music/release';
import type { MatchKind } from '$lib/jobs/track-match';

const pair = (index: number, seconds: number | null, title: string, lengthMs: number | null, match: MatchKind) =>
	({
		disc: { index, expected_duration_seconds: seconds },
		mb: { title, length_ms: lengthMs },
		match
	}) as unknown as TrackPair;

const pairs: TrackPair[] = [
	pair(0, 101, 'So What', 100000, 'match'),
	pair(1, 205, 'Blue in Green', 200000, 'close'),
	pair(2, 500, 'All Blues', 300000, 'mismatch'),
	pair(3, 60, 'Flamenco Sketches', null, 'unknown')
];

function renderConfirm(overrides: { pairs?: TrackPair[]; onconfirm?: () => void; oncancel?: () => void } = {}) {
	return renderComponent(MusicMappingConfirm, {
		props: { pairs, onconfirm: vi.fn(), oncancel: vi.fn(), ...overrides }
	});
}

const bodyRows = (c: HTMLElement) => [...c.querySelectorAll('tbody tr')];
const cells = (row: Element) => [...row.querySelectorAll('td')].map((td) => td.textContent?.trim());

describe('MusicMappingConfirm', () => {
	afterEach(() => cleanup());

	it('shows the title', () => {
		renderConfirm();
		expect(screen.getByText('Confirm track title mapping')).toBeInTheDocument();
	});

	it('shows one row per pair with the disc track, release title and length', () => {
		const { container } = renderConfirm();
		const rows = bodyRows(container);
		expect(rows).toHaveLength(4);
		expect(cells(rows[0]).filter(Boolean)).toEqual(['Disc #0 (1:41)', 'So What', '1:40']);
		expect(cells(rows[1])[0]).toBe('Disc #1 (3:25)');
		expect(cells(rows[3])[2]).toBe('Flamenco Sketches');
	});

	it('shows a dash for a release track without a length', () => {
		const { container } = renderConfirm();
		expect(cells(bodyRows(container)[3])[3]).toBe('-');
	});

	it('tones each row by its match kind', () => {
		const { container } = renderConfirm();
		const tones = bodyRows(container).map((r) => r.querySelector('.music-search-match')?.getAttribute('data-tone'));
		expect(tones).toEqual(['success', 'warning', 'danger', 'muted']);
	});

	it('shows no rows for no pairs', () => {
		const { container } = renderConfirm({ pairs: [] });
		expect(bodyRows(container)).toHaveLength(0);
	});

	it('calls onconfirm from Apply titles', async () => {
		const onconfirm = vi.fn();
		const oncancel = vi.fn();
		renderConfirm({ onconfirm, oncancel });
		await fireEvent.click(screen.getByRole('button', { name: 'Apply titles' }));
		expect(onconfirm).toHaveBeenCalledOnce();
		expect(oncancel).not.toHaveBeenCalled();
	});

	it('calls oncancel from Cancel', async () => {
		const onconfirm = vi.fn();
		const oncancel = vi.fn();
		renderConfirm({ onconfirm, oncancel });
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(oncancel).toHaveBeenCalledOnce();
		expect(onconfirm).not.toHaveBeenCalled();
	});
});
