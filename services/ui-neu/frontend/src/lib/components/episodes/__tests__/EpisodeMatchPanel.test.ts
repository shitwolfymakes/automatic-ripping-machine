import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});
const fetchIdentity = vi.fn();
vi.mock('$lib/api/identity', () => ({
	fetchIdentity: (...a: unknown[]) => fetchIdentity(...a),
	matchIdentity: vi.fn(),
	unpinIdentity: vi.fn(),
	fetchEpisodes: vi.fn(() => Promise.resolve({ source_id: 'episodes_tmdb', show_id: '5084', season: 1, episodes: [] }))
}));
vi.mock('$lib/api/jobs', () => ({
	fetchNamingPreview: vi.fn(() => Promise.resolve({ job_output_dir: '', job_output_name: '', items: [] })),
	updateTrack: vi.fn()
}));

import EpisodeMatchPanel from '../EpisodeMatchPanel.svelte';
import { fetchNamingPreview } from '$lib/api/jobs';
import type { IdentityView, JobView, TrackView } from '$lib/types/api.gen';

const LENGTHS = [3093, 3033, 3092, 3070, 3078, 542];
const tracks = LENGTHS.map((d, i) => ({ id: `trk_${i}`, source_ref: `t0${i}`, duration_seconds: d }) as TrackView);
const job = (o: Partial<JobView> = {}) => ({ id: 'job_1', has_series: true, media_type: 'tv', ...o }) as JobView;
const applied: IdentityView = {
	sources: { episodes_tmdb: { status: 'ok' }, episodes_tvmaze: { status: 'ok', detail: 'matched 5 of 6' } },
	pin: {},
	tracks: LENGTHS.map((_, i) => ({
		track_id: `trk_${i}`,
		source_ref: `t0${i}`,
		role: i === 5 ? 'extra' : 'episode',
		season: 1,
		episode_number: i === 5 ? null : i + 1,
		episode_name: i === 5 ? null : `Ep ${i + 1}`,
		identity_provenance: (i === 5 ? {} : { episode_number: 'episodes_tmdb' }) as Record<string, string>,
		proposals: { episodes_tmdb: { episode: i + 1, confidence: 0.9 } }
	}))
};

async function setRole(r: string | null) {
	((await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void }).__setRole(r);
}

beforeEach(() => {
	vi.clearAllMocks();
	fetchIdentity.mockResolvedValue(applied);
});
afterEach(async () => {
	cleanup();
	await setRole('admin');
});

describe('EpisodeMatchPanel', () => {
	it('applied: status line, rows and origin', async () => {
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('Applied automatically')).toBeInTheDocument();
		expect(screen.getByText('6 of 6 tracks placed')).toBeInTheDocument();
		expect(screen.getAllByText('S01E04')[0]).toBeInTheDocument();
		expect(screen.getAllByText('Auto · TMDb').length).toBeGreaterThan(0);
		expect(screen.getAllByText('0.90').length).toBeGreaterThan(0);
	});

	it('shows each track’s file name from the naming preview', async () => {
		vi.mocked(fetchNamingPreview).mockResolvedValueOnce({
			job_output_dir: '/media/tv',
			job_output_name: 'Kolchak',
			items: [
				{
					track_id: 'trk_3',
					output_path: '/media/tv/Kolchak/Season 01/Kolchak - S01E04 - Ep 4.mkv',
					output_dir: '/media/tv/Kolchak/Season 01',
					output_name: 'Kolchak - S01E04 - Ep 4.mkv'
				}
			]
		});
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		const name = await screen.findByText('Kolchak - S01E04 - Ep 4.mkv');
		expect(name).toHaveAttribute('title', '/media/tv/Kolchak/Season 01/Kolchak - S01E04 - Ep 4.mkv');
	});

	it('other sources open inline', async () => {
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		const toggle = await screen.findByRole('button', { name: /Other sources/ });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(screen.queryByText(/matched 5 of 6/)).toBeNull();
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		expect(screen.getByText(/matched 5 of 6/)).toBeInTheDocument();
	});

	it('other sources leave out non-episode keys like manual', async () => {
		fetchIdentity.mockResolvedValue({ ...applied, sources: { ...applied.sources, manual: { status: 'ok' } } });
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await fireEvent.click(await screen.findByRole('button', { name: /Other sources/ }));
		expect(screen.getAllByRole('listitem')).toHaveLength(1);
		expect(screen.queryByText(/manual/i)).toBeNull();
	});

	it('pick the series first when the job has no series', async () => {
		const onsearchseries = vi.fn();
		renderComponent(EpisodeMatchPanel, {
			props: { job: job({ has_series: false }), tracks, matching: false, onsearchseries }
		});
		expect(screen.getByText('Pick the series first')).toBeInTheDocument();
		await fireEvent.click(await screen.findByRole('button', { name: 'Search for the series' }));
		expect(onsearchseries).toHaveBeenCalled();
		expect(fetchIdentity).not.toHaveBeenCalled();
	});

	it('hides pickers and re-run while matching', async () => {
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: true } });
		expect(await screen.findByText(/Matching episodes/)).toBeInTheDocument();
		expect(screen.getAllByText('Waiting for matcher').length).toBe(tracks.length);
		expect(screen.queryByRole('button', { name: /Re-run/ })).toBeNull();
		expect(screen.queryByLabelText(/Set placement for/)).toBeNull();
	});

	it('guest sees rows but no controls', async () => {
		await setRole('guest');
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
		expect(screen.getByText(/View only/)).toBeInTheDocument();
		expect(screen.getByRole('button', { name: /Other sources/ })).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /Re-run/ })).toBeNull();
		expect(screen.queryByLabelText(/Set placement for/)).toBeNull();
	});

	it('guest never sees the series search button', async () => {
		await setRole('guest');
		renderComponent(EpisodeMatchPanel, { props: { job: job({ has_series: false }), tracks, matching: false } });
		expect(screen.getByText('Pick the series first')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Search for the series' })).toBeNull();
	});

	it('unavailable when no episode source ran', async () => {
		fetchIdentity.mockResolvedValue({ sources: {}, pin: {}, tracks: [] });
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('No episode source is set up')).toBeInTheDocument();
		expect(screen.getByRole('link', { name: /Settings/ })).toHaveAttribute('href', '/settings#metadata');
	});

	it('suggestion and pinned banners', async () => {
		fetchIdentity.mockResolvedValue({ ...applied, sources: { episodes_tmdb: { status: 'ok', suggestion: true } } });
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText("TMDb's best match is too uncertain to apply on its own")).toBeInTheDocument();
		expect(screen.getByText('Suggestion, not applied')).toBeInTheDocument();
		cleanup();
		fetchIdentity.mockResolvedValue({ ...applied, pin: { episode: 'episodes_tmdb' } });
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('TMDb is pinned.')).toBeInTheDocument();
		expect(screen.getByText('Pinned by you')).toBeInTheDocument();
	});

	it('no match names the sources that failed', async () => {
		fetchIdentity.mockResolvedValue({
			sources: {
				episodes_tmdb: { status: 'miss', detail: 'no runtimes matched' },
				episodes_tvmaze: { status: 'error', detail: 'HTTP 502' }
			},
			pin: {},
			tracks: []
		});
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('No source could place these tracks')).toBeInTheDocument();
		expect(screen.getByText('No match')).toBeInTheDocument();
		expect(screen.getByText('TVmaze failed: HTTP 502')).toBeInTheDocument();
		expect(screen.getByText('0 of 6 tracks placed')).toBeInTheDocument();
	});

	it('stacks the rows as cards on a phone', async () => {
		const real = globalThis.matchMedia;
		globalThis.matchMedia = ((q: string) => ({ ...real(q), matches: q.includes('max-width: 639px') })) as typeof real;
		try {
			renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
			expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
			expect(screen.queryByRole('table')).toBeNull();
			expect(screen.getAllByText('S01E04')[0].closest('li')).not.toBeNull();
		} finally {
			globalThis.matchMedia = real;
		}
	});

	it('reload() refetches the identity', async () => {
		const { component } = renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await screen.findByText('Applied automatically');
		const before = fetchIdentity.mock.calls.length;
		await (component as unknown as { reload: () => Promise<void> }).reload();
		expect(fetchIdentity.mock.calls.length).toBe(before + 1);
	});
});
