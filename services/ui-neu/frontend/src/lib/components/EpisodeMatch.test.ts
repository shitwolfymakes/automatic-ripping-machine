import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import EpisodeMatch from './EpisodeMatch.svelte';
import { createJobDetail, createTrack } from './__fixtures__/job';
import type { JobDetailView } from '$lib/types/api.gen';

vi.mock('$lib/api/jobs', () => ({
	tvdbMatch: vi.fn(() => Promise.resolve({
		success: true,
		matcher: 'runtime',
		season: 1,
		matches: [],
		match_count: 0,
		score: 0,
		alternatives: []
	})),
	fetchTvdbEpisodes: vi.fn(() => Promise.resolve({ episodes: [], tvdb_id: 12345, season: 1 })),
	updateTrack: vi.fn(() => Promise.resolve({ id: 'job_1' })),
	fetchNamingPreview: vi.fn(() =>
		Promise.resolve({ job_output_dir: '', job_output_name: '', items: [] })
	)
}));

/** Create a series JobDetailView with common defaults for EpisodeMatch tests. */
function seriesJob(overrides: { tracks?: JobDetailView['tracks'] } = {}): JobDetailView {
	return createJobDetail({
		title: 'Test Show',
		status: 'ripped',
		tracks: overrides.tracks ?? []
	} as Parameters<typeof createJobDetail>[0]);
}

// season / tvdb_id / imdb_id / disc are BFF-only — pass as component props now.
const seriesProps = { tvdbId: 12345 as number | null, imdbId: 'tt1234567' as string | null };

describe('EpisodeMatch', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('empty states', () => {
		it('renders "No IMDB or TVDB ID" message when both are null', () => {
			renderComponent(EpisodeMatch, {
				props: { job: seriesJob({ tracks: [] }), tvdbId: null, imdbId: null }
			});
			expect(screen.getByText(/No IMDB or TVDB ID set/)).toBeInTheDocument();
		});

		it('renders "No tracks found" when tvdb_id set but empty tracks', () => {
			renderComponent(EpisodeMatch, {
				props: { job: seriesJob({ tracks: [] }), tvdbId: 12345, imdbId: null }
			});
			expect(screen.getByText(/No tracks found/)).toBeInTheDocument();
		});
	});

	describe('controls bar', () => {
		it('renders Season, Disc, Tolerance labels', () => {
			renderComponent(EpisodeMatch, { props: { job: seriesJob(), ...seriesProps } });
			expect(screen.getByText('Season')).toBeInTheDocument();
			expect(screen.getByText('Disc')).toBeInTheDocument();
			expect(screen.getByText('Tolerance')).toBeInTheDocument();
		});

		it('renders Match button', () => {
			renderComponent(EpisodeMatch, { props: { job: seriesJob(), ...seriesProps } });
			expect(screen.getByText('Match')).toBeInTheDocument();
		});

		it('season input prefills from season prop', () => {
			const { container } = renderComponent(EpisodeMatch, {
				props: { job: seriesJob(), ...seriesProps, season: '3' }
			});
			const inputs = container.querySelectorAll('input[type="number"]');
			expect((inputs[0] as HTMLInputElement).value).toBe('3');
		});

		it('season input prefills from seasonAuto when season is null', () => {
			const { container } = renderComponent(EpisodeMatch, {
				props: { job: seriesJob(), ...seriesProps, season: null, seasonAuto: '2' }
			});
			const inputs = container.querySelectorAll('input[type="number"]');
			expect((inputs[0] as HTMLInputElement).value).toBe('2');
		});

		it('disc input prefills from discNumber prop', () => {
			const { container } = renderComponent(EpisodeMatch, {
				props: { job: seriesJob(), ...seriesProps, discNumber: 4 }
			});
			const inputs = container.querySelectorAll('input[type="number"]');
			expect((inputs[1] as HTMLInputElement).value).toBe('4');
		});

		it('disc total input prefills from discTotal prop', () => {
			const { container } = renderComponent(EpisodeMatch, {
				props: { job: seriesJob(), ...seriesProps, discTotal: 6 }
			});
			const inputs = container.querySelectorAll('input[type="number"]');
			expect((inputs[2] as HTMLInputElement).value).toBe('6');
		});

		it('tolerance defaults to 600', () => {
			const { container } = renderComponent(EpisodeMatch, {
				props: { job: seriesJob(), ...seriesProps }
			});
			const inputs = container.querySelectorAll('input[type="number"]');
			expect((inputs[3] as HTMLInputElement).value).toBe('600');
		});
	});

	describe('runtime conversion', () => {
		it('converts episode runtime from seconds to minutes in dropdowns', async () => {
			const { tvdbMatch, fetchTvdbEpisodes } = await import('$lib/api/jobs');
			vi.mocked(tvdbMatch).mockResolvedValueOnce({
				success: true,
				matcher: 'runtime',
				season: 1,
				matches: [
					{ track_number: '0', episode_number: 1, episode_name: 'Pilot', episode_runtime: 2700 }
				],
				match_count: 1,
				score: 100,
				alternatives: []
			} as never);
			// API returns runtime in seconds (2700 = 45 minutes)
			vi.mocked(fetchTvdbEpisodes).mockResolvedValueOnce({
				episodes: [
					{ number: 1, name: 'Pilot', runtime: 2700, aired: '2024-01-01' },
					{ number: 2, name: 'Episode 2', runtime: 3060, aired: '2024-01-08' }
				],
				tvdb_id: 12345,
				season: 1
			} as never);

			const { container } = renderComponent(EpisodeMatch, {
				props: { job: seriesJob({ tracks: [createTrack()] }), ...seriesProps }
			});

			// Wait for auto-match to complete
			await vi.waitFor(() => {
				const selects = container.querySelectorAll('select');
				expect(selects.length).toBeGreaterThan(0);
			});

			// Check dropdown options show minutes not seconds
			const select = container.querySelector('select')!;
			const options = Array.from(select.options);
			const pilotOption = options.find((o) => o.textContent?.includes('Pilot'));
			expect(pilotOption?.textContent).toContain('45m');
			expect(pilotOption?.textContent).not.toContain('2700m');
		});

		it('shows all season episodes in dropdowns, not just matched', async () => {
			const { tvdbMatch, fetchTvdbEpisodes } = await import('$lib/api/jobs');
			vi.mocked(tvdbMatch).mockResolvedValueOnce({
				success: true,
				matcher: 'runtime',
				season: 1,
				matches: [
					{ track_number: '0', episode_number: 3, episode_name: 'Episode 3', episode_runtime: 2700 }
				],
				match_count: 1,
				score: 100,
				alternatives: []
			} as never);
			vi.mocked(fetchTvdbEpisodes).mockResolvedValueOnce({
				episodes: [
					{ number: 1, name: 'Episode 1', runtime: 2700, aired: '' },
					{ number: 2, name: 'Episode 2', runtime: 2700, aired: '' },
					{ number: 3, name: 'Episode 3', runtime: 2700, aired: '' },
					{ number: 4, name: 'Episode 4', runtime: 2700, aired: '' },
					{ number: 5, name: 'Episode 5', runtime: 2700, aired: '' }
				],
				tvdb_id: 12345,
				season: 1
			} as never);

			const { container } = renderComponent(EpisodeMatch, {
				props: { job: seriesJob({ tracks: [createTrack()] }), ...seriesProps }
			});

			await vi.waitFor(() => {
				const selects = container.querySelectorAll('select');
				expect(selects.length).toBeGreaterThan(0);
			});

			// All 5 episodes should be in dropdown, not just matched episode 3
			const select = container.querySelector('select')!;
			const options = Array.from(select.options).filter((o) => o.value !== '');
			expect(options).toHaveLength(5);
			expect(options[0].textContent).toContain('E1');
			expect(options[4].textContent).toContain('E5');
		});

		it('deduplicates fallback episodes when fetchTvdbEpisodes fails', async () => {
			const { tvdbMatch, fetchTvdbEpisodes } = await import('$lib/api/jobs');
			vi.mocked(tvdbMatch).mockResolvedValueOnce({
				success: true,
				matcher: 'runtime',
				season: 1,
				matches: [
					{ track_number: '0', episode_number: 1, episode_name: 'Pilot', episode_runtime: 2700 },
					{ track_number: '1', episode_number: 2, episode_name: 'Ep 2', episode_runtime: 2700 }
				],
				match_count: 2,
				score: 100,
				alternatives: []
			} as never);
			vi.mocked(fetchTvdbEpisodes).mockRejectedValueOnce(new Error('No TVDB ID'));

			const tracks = [
				createTrack({ id: 'trk_1', index: 0, source_ref: 't00.mkv' }),
				createTrack({ id: 'trk_2', index: 1, source_ref: 't01.mkv' })
			];

			const { container } = renderComponent(EpisodeMatch, {
				props: { job: seriesJob({ tracks }), ...seriesProps }
			});

			await vi.waitFor(() => {
				const selects = container.querySelectorAll('select');
				expect(selects.length).toBeGreaterThan(0);
			});

			// Should have 2 fallback episodes from match results
			const select = container.querySelector('select')!;
			const options = Array.from(select.options).filter((o) => o.value !== '');
			expect(options).toHaveLength(2);
		});
	});
});
