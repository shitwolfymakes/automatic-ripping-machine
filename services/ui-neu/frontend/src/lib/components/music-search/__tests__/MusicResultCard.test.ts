import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup } from '$lib/test-utils';
import MusicResultCard from '../MusicResultCard.svelte';
import type { MetadataCandidate, MetadataReleaseDetail, TrackView } from '$lib/types/api.gen';

const candidate = (overrides: Partial<MetadataCandidate> = {}): MetadataCandidate => ({
	title: 'Kind of Blue',
	kind: 'music',
	...overrides
});

const release = (overrides: Partial<MetadataReleaseDetail> = {}): MetadataReleaseDetail => ({
	release_id: 'r1',
	title: 'Back Title',
	artist: 'Miles Davis',
	tracks: [
		{ position: 1, title: 'So What', length_ms: 100000 },
		{ position: 2, title: 'Blue in Green', length_ms: null }
	],
	...overrides
});

const disc = (seconds: number | null) => ({ expected_duration_seconds: seconds }) as TrackView;

type CardProps = {
	candidate: MetadataCandidate;
	flipData: MetadataReleaseDetail | 'loading' | undefined;
	flipped: boolean;
	discTracks: TrackView[];
};

function renderCard(overrides: Partial<CardProps> = {}) {
	const onopen = vi.fn();
	const onflip = vi.fn();
	const props: CardProps = {
		candidate: candidate(),
		flipData: undefined,
		flipped: false,
		discTracks: [],
		...overrides
	};
	const view = renderComponent(MusicResultCard, { props: { ...props, onopen, onflip } });
	return { onopen, onflip, ...view };
}

const pill = (container: HTMLElement, kind: string) => container.querySelector(`[data-kind="${kind}"]`);

describe('MusicResultCard', () => {
	afterEach(() => cleanup());

	describe('front face', () => {
		it('shows the title and a poster image', () => {
			const { container } = renderCard({ candidate: candidate({ poster_url: '/poster.jpg' }) });
			expect(screen.getByText('Kind of Blue')).toBeTruthy();
			expect(container.querySelector('img[src="/poster.jpg"]')).toBeTruthy();
		});

		it('shows the year and every pill when the candidate has them', () => {
			const { container } = renderCard({
				candidate: candidate({ year: 1959, release_type: 'Album', format: 'CD', country: 'US', track_count: 5 })
			});
			expect(screen.getByText('1959')).toBeTruthy();
			expect(pill(container, 'type')?.textContent).toBe('Album');
			expect(pill(container, 'format')?.textContent).toBe('CD');
			expect(pill(container, 'country')?.textContent).toBe('US');
			expect(pill(container, 'tracks')?.textContent).toBe('5 tracks');
		});

		it('omits the year and the pills when the candidate lacks them', () => {
			const { container } = renderCard();
			expect(container.querySelector('.music-search-result-year')).toBeNull();
			expect(container.querySelector('.music-search-result-pill')).toBeNull();
		});

		it('opens the release when the front button is clicked', async () => {
			const { onopen, onflip } = renderCard();
			await fireEvent.click(screen.getByText('Kind of Blue'));
			expect(onopen).toHaveBeenCalledOnce();
			expect(onflip).not.toHaveBeenCalled();
		});
	});

	describe('flip button', () => {
		it('is absent without a track count', () => {
			renderCard();
			expect(screen.queryByTitle('Flip to see tracklist')).toBeNull();
		});

		it('flips the card without opening it, and stops the click reaching the parent', async () => {
			const { onopen, onflip } = renderCard({ candidate: candidate({ track_count: 7 }) });
			const parentClick = vi.fn();
			document.body.addEventListener('click', parentClick);
			await fireEvent.click(screen.getByTitle('Flip to see tracklist'));
			document.body.removeEventListener('click', parentClick);
			expect(onflip).toHaveBeenCalledOnce();
			expect(onopen).not.toHaveBeenCalled();
			expect(parentClick).not.toHaveBeenCalled();
		});
	});

	describe('flipped state', () => {
		it('sets data-flipped true when flipped', () => {
			const { container } = renderCard({ flipped: true });
			expect(container.querySelector('.music-search-poster-card')?.getAttribute('data-flipped')).toBe('true');
		});

		it('sets data-flipped false when not flipped', () => {
			const { container } = renderCard();
			expect(container.querySelector('.music-search-poster-card')?.getAttribute('data-flipped')).toBe('false');
		});
	});

	describe('back face', () => {
		it('shows Loading... while the tracklist loads', () => {
			renderCard({ flipData: 'loading' });
			expect(screen.getByText('Loading...')).toBeTruthy();
		});

		it('shows the header and a row per track, with - for a null length', () => {
			const { container } = renderCard({ flipData: release() });
			expect(screen.getByText('Back Title')).toBeTruthy();
			expect(screen.getByText('Miles Davis')).toBeTruthy();
			expect(screen.getByText('So What')).toBeTruthy();
			expect(screen.getByText('Blue in Green')).toBeTruthy();
			const rows = container.querySelectorAll('.music-search-back-row');
			expect(rows).toHaveLength(2);
			expect(rows[0].textContent).toContain('1:40');
			expect(rows[1].textContent).toContain('-');
		});

		it('shows an empty artist line when the release has no artist', () => {
			const { container } = renderCard({ flipData: release({ artist: null }) });
			expect(container.querySelector('.music-search-back-artist')?.textContent).toBe('');
		});

		it('omits the match column without disc tracks', () => {
			const { container } = renderCard({ flipData: release() });
			expect(container.querySelector('.music-search-match')).toBeNull();
		});

		it('shows each match kind in its tone when there are disc tracks', () => {
			const flipData = release({
				tracks: [
					{ position: 1, title: 'A', length_ms: 100000 },
					{ position: 2, title: 'B', length_ms: 100000 },
					{ position: 3, title: 'C', length_ms: 100000 },
					{ position: 4, title: 'D', length_ms: null }
				]
			});
			const { container } = renderCard({ flipData, discTracks: [disc(101), disc(106), disc(200), disc(100)] });
			const tones = [...container.querySelectorAll('.music-search-match')].map((c) => c.getAttribute('data-tone'));
			expect(tones).toEqual(['success', 'warning', 'danger', 'muted']);
		});

		it.each([
			['no flip data', undefined],
			['no tracks', release({ tracks: [] })],
			['a missing tracks field', release({ tracks: undefined })]
		])('shows No track data for %s', (_name, flipData) => {
			renderCard({ flipData });
			expect(screen.getByText('No track data')).toBeTruthy();
		});

		it('flips back, without opening or reaching the parent, when Back is clicked', async () => {
			const { onopen, onflip } = renderCard({ flipped: true });
			const parentClick = vi.fn();
			document.body.addEventListener('click', parentClick);
			await fireEvent.click(screen.getByTitle('Flip back'));
			document.body.removeEventListener('click', parentClick);
			expect(onflip).toHaveBeenCalledOnce();
			expect(onopen).not.toHaveBeenCalled();
			expect(parentClick).not.toHaveBeenCalled();
		});
	});
});
