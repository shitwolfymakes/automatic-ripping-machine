import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor } from '$lib/test-utils';

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
import { fetchNamingPreview, updateTrack } from '$lib/api/jobs';
import { fetchEpisodes, matchIdentity, unpinIdentity } from '$lib/api/identity';
import type { IdentityView, JobView, MatchPreview, TrackView } from '$lib/types/api.gen';

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

const tvmazePreview: MatchPreview = {
	outcomes: [
		{
			source_id: 'episodes_tvmaze',
			matches: [{ source_ref: 't00', season: 1, episode: 2, episode_name: 'Ep 2', confidence: 0.81 }]
		}
	]
};

async function openRerun() {
	await fireEvent.click(await screen.findByRole('button', { name: /Re-run/ }));
}

describe('EpisodeMatchPanel actions', () => {
	it('previews then applies & pins', async () => {
		vi.mocked(matchIdentity).mockResolvedValueOnce(tvmazePreview).mockResolvedValueOnce({ outcomes: [] });
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await openRerun();
		await fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'tvmaze' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		expect(matchIdentity).toHaveBeenCalledWith(
			'job_1',
			expect.objectContaining({ source: 'tvmaze', season: 1, disc_number: 1, apply: false })
		);
		expect(vi.mocked(matchIdentity).mock.calls[0][1]).not.toHaveProperty('tolerance');
		expect(await screen.findByText(/1 track changes if you apply TVmaze/)).toBeInTheDocument();
		expect(screen.getByText('Nothing is saved yet.', { exact: false })).toBeInTheDocument();
		expect(screen.getByRole('columnheader', { name: 'Proposed · TVmaze' })).toBeInTheDocument();
		expect(screen.getAllByText('CHANGED')).toHaveLength(1);
		const before = fetchIdentity.mock.calls.length;
		await fireEvent.click(screen.getByRole('button', { name: 'Apply & pin TVmaze' }));
		expect(matchIdentity).toHaveBeenLastCalledWith('job_1', expect.objectContaining({ source: 'tvmaze', apply: true }));
		await waitFor(() => expect(fetchIdentity.mock.calls.length).toBe(before + 1));
		expect(screen.queryByText(/tracks? changes? if you apply/)).toBeNull();
	});

	it('sends the tolerance only when one is given', async () => {
		vi.mocked(matchIdentity).mockResolvedValueOnce(tvmazePreview);
		renderComponent(EpisodeMatchPanel, {
			props: { job: job({ season: 2, disc_number: 3 }), tracks, matching: false }
		});
		await openRerun();
		await fireEvent.input(screen.getByLabelText('Tolerance (s)'), { target: { value: '120' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		expect(matchIdentity).toHaveBeenCalledWith('job_1', {
			source: 'tmdb',
			season: 2,
			disc_number: 3,
			tolerance: 120,
			apply: false
		});
	});

	it('discard and field changes drop the preview', async () => {
		vi.mocked(matchIdentity).mockResolvedValue(tvmazePreview);
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await screen.findByText(/1 track changes/);
		await fireEvent.click(screen.getByRole('button', { name: 'Discard' }));
		expect(screen.queryByText(/1 track changes/)).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await screen.findByText(/1 track changes/);
		await fireEvent.input(screen.getByLabelText('Season'), { target: { value: '2' } });
		await waitFor(() => expect(screen.queryByText(/1 track changes/)).toBeNull());
	});

	it('disables a source that is not configured', async () => {
		fetchIdentity.mockResolvedValue({
			...applied,
			sources: { ...applied.sources, episodes_tvdb: { status: 'skipped', detail: 'TVDB not configured' } }
		});
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await openRerun();
		const tvdb = screen.getByRole('option', { name: /TVDB/ }) as HTMLOptionElement;
		expect(tvdb.disabled).toBe(true);
		expect((screen.getByRole('option', { name: /TVmaze/ }) as HTMLOptionElement).disabled).toBe(false);
	});

	it('keeps the current placement when preview fails', async () => {
		vi.mocked(matchIdentity).mockRejectedValueOnce(new Error('HTTP 502')).mockResolvedValueOnce(tvmazePreview);
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await openRerun();
		await fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'tvmaze' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		const alert = await screen.findByRole('alert');
		expect(alert).toHaveTextContent("TVmaze didn't answer (HTTP 502)");
		expect(alert).toHaveTextContent("still TMDb's");
		expect(screen.getAllByText('S01E01').length).toBeGreaterThan(0);
		await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
		expect(matchIdentity).toHaveBeenCalledTimes(2);
		expect(vi.mocked(matchIdentity).mock.calls[1]).toEqual(vi.mocked(matchIdentity).mock.calls[0]);
		expect(await screen.findByText(/1 track changes/)).toBeInTheDocument();
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it('accepts a suggestion by pinning its source', async () => {
		fetchIdentity.mockResolvedValue({ ...applied, sources: { episodes_tmdb: { status: 'ok', suggestion: true } } });
		let resolve: (v: MatchPreview) => void = () => {};
		vi.mocked(matchIdentity).mockReturnValue(new Promise((r) => (resolve = r)));
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await fireEvent.click(await screen.findByRole('button', { name: 'Accept suggestion' }));
		expect(matchIdentity).toHaveBeenCalledWith('job_1', { source: 'tmdb', apply: true });
		expect(screen.getByRole('button', { name: 'Accepting…' })).toBeDisabled();
		const before = fetchIdentity.mock.calls.length;
		resolve({ outcomes: [] });
		await waitFor(() => expect(fetchIdentity.mock.calls.length).toBe(before + 1));
	});

	it('unpin asks inline first', async () => {
		fetchIdentity.mockResolvedValue({ ...applied, pin: { episode: 'episodes_tmdb' } });
		vi.mocked(unpinIdentity).mockResolvedValue({ ...applied, pin: {} });
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await fireEvent.click(await screen.findByRole('button', { name: 'Unpin…' }));
		expect(unpinIdentity).not.toHaveBeenCalled();
		expect(screen.getByText('Unpin and let ARM pick the source again?')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
		expect(screen.queryByText('Unpin and let ARM pick the source again?')).toBeNull();
		await fireEvent.click(screen.getByRole('button', { name: 'Unpin…' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Unpin' }));
		expect(unpinIdentity).toHaveBeenCalledWith('job_1');
		expect(await screen.findByText('Applied automatically')).toBeInTheDocument();
	});

	it('guests get no accept or unpin', async () => {
		await setRole('guest');
		fetchIdentity.mockResolvedValue({ ...applied, pin: { episode: 'episodes_tmdb' } });
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('TMDb is pinned.')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /Unpin/ })).toBeNull();
		cleanup();
		fetchIdentity.mockResolvedValue({ ...applied, sources: { episodes_tmdb: { status: 'ok', suggestion: true } } });
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('Suggestion, not applied')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /Accept/ })).toBeNull();
	});

	it('shows the preview inline with the old placement struck through on a phone', async () => {
		const real = globalThis.matchMedia;
		globalThis.matchMedia = ((q: string) => ({ ...real(q), matches: q.includes('max-width: 639px') })) as typeof real;
		vi.mocked(matchIdentity).mockResolvedValueOnce(tvmazePreview);
		try {
			renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
			await openRerun();
			await fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'tvmaze' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
			await screen.findByText(/1 track changes/);
			expect(screen.getByText('S01E01').closest('s')).not.toBeNull();
			expect(screen.getByText('S01E02', { selector: '.episode-rows-proposed *' })).toBeInTheDocument();
		} finally {
			globalThis.matchMedia = real;
		}
	});
});

const kolchakS1 = {
	source_id: 'episodes_tmdb',
	show_id: '5084',
	season: 1,
	episodes: [
		{ number: 4, name: 'The Vampire', runtime_s: 3060 },
		{ number: 1, name: 'The Night Stalker', runtime_s: 4440, special: true }
	]
};

describe('EpisodeMatchPanel set by hand', () => {
	beforeEach(() => vi.mocked(fetchEpisodes).mockResolvedValue(kolchakS1));

	it('sets a track to Extra by hand', async () => {
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		const select = await screen.findByLabelText('Set placement for t04');
		await waitFor(() => expect(screen.getAllByText(/E04 The Vampire · 51m/).length).toBeGreaterThan(0));
		const before = fetchIdentity.mock.calls.length;
		await fireEvent.change(select, { target: { value: 'extra' } });
		expect(updateTrack).toHaveBeenCalledWith('job_1', 'trk_4', { role: 'extra' });
		await waitFor(() => expect(fetchIdentity.mock.calls.length).toBe(before + 1));
	});

	it('picks an episode by hand', async () => {
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		const select = await screen.findByLabelText('Set placement for t03');
		await waitFor(() => expect(screen.getAllByText(/E04 The Vampire/).length).toBeGreaterThan(0));
		await fireEvent.change(select, { target: { value: 's1e4' } });
		expect(updateTrack).toHaveBeenCalledWith('job_1', 'trk_3', {
			role: 'episode',
			season: 1,
			episode_number: 4,
			episode_name: 'The Vampire'
		});
	});

	it('lists specials as season 0 and offers Extra / Trailer / Other', async () => {
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		const select = (await screen.findByLabelText('Set placement for t00')) as HTMLSelectElement;
		await waitFor(() => expect(select.options.length).toBe(6));
		expect([...select.options].map((o) => [o.value, o.text])).toEqual([
			['', 'Change…'],
			['s1e4', 'E04 The Vampire · 51m'],
			['s0e1', 'S00E01 The Night Stalker · 74m · special'],
			['extra', 'Extra'],
			['trailer', 'Trailer'],
			['other', 'Other']
		]);
		await fireEvent.change(select, { target: { value: 's0e1' } });
		expect(updateTrack).toHaveBeenCalledWith('job_1', 'trk_0', {
			role: 'episode',
			season: 0,
			episode_number: 1,
			episode_name: 'The Night Stalker'
		});
	});

	it('loads the episode list once per source and season', async () => {
		const { component } = renderComponent(EpisodeMatchPanel, {
			props: { job: job({ season: 2 }), tracks, matching: false }
		});
		await screen.findByLabelText('Set placement for t00');
		await (component as unknown as { reload: () => Promise<void> }).reload();
		await waitFor(() => expect(fetchEpisodes).toHaveBeenCalledTimes(1));
		expect(fetchEpisodes).toHaveBeenCalledWith('job_1', 'tmdb', 2);
	});

	it('reverts a hand-set row', async () => {
		const handSet = structuredClone(applied);
		handSet.tracks![5].identity_provenance = { role: 'manual' };
		fetchIdentity.mockResolvedValue(handSet);
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await fireEvent.click(await screen.findByRole('button', { name: 'Revert' }));
		expect(updateTrack).toHaveBeenCalledWith('job_1', 'trk_5', {
			revert_fields: ['role', 'season', 'episode_number', 'episode_number_end', 'episode_name']
		});
	});

	it('hides the pickers while a preview is shown', async () => {
		vi.mocked(matchIdentity).mockResolvedValueOnce(tvmazePreview);
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await screen.findByLabelText('Set placement for t00');
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await screen.findByText(/1 track changes/);
		expect(screen.queryByLabelText(/Set placement for/)).toBeNull();
	});

	it('guests get no picker or revert', async () => {
		await setRole('guest');
		const handSet = structuredClone(applied);
		handSet.tracks![5].identity_provenance = { role: 'manual' };
		fetchIdentity.mockResolvedValue(handSet);
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(await screen.findByText('Set by you')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Revert' })).toBeNull();
		expect(screen.queryByLabelText(/Set placement for/)).toBeNull();
		expect(fetchEpisodes).not.toHaveBeenCalled();
	});

	it('renders a full-width picker in phone cards', async () => {
		const real = globalThis.matchMedia;
		globalThis.matchMedia = ((q: string) => ({ ...real(q), matches: q.includes('max-width: 639px') })) as typeof real;
		try {
			renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
			const select = await screen.findByLabelText('Set placement for t04');
			expect(select.closest('li')).not.toBeNull();
		} finally {
			globalThis.matchMedia = real;
		}
	});
});

function deferred<T>() {
	let resolve: (v: T) => void = () => {};
	const promise = new Promise<T>((r) => (resolve = r));
	return { promise, resolve };
}

describe('EpisodeMatchPanel fix round 1', () => {
	it('shows a neutral loading line, not "unavailable", before the first fetch settles', async () => {
		const first = deferred<IdentityView>();
		fetchIdentity.mockReturnValue(first.promise);
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		expect(screen.getByText('Loading episodes…')).toBeInTheDocument();
		expect(screen.queryByText('No episode source is set up')).toBeNull();
		first.resolve(applied);
		expect(await screen.findByText('Applied automatically')).toBeInTheDocument();
		expect(screen.queryByText('Loading episodes…')).toBeNull();
	});

	it('ignores a late identity for the previous job', async () => {
		const forA = deferred<IdentityView>();
		fetchIdentity.mockImplementation((id: string) => (id === 'job_A' ? forA.promise : Promise.resolve(applied)));
		const { rerender } = renderComponent(EpisodeMatchPanel, {
			props: { job: job({ id: 'job_A' }), tracks, matching: false }
		});
		await rerender({ job: job({ id: 'job_B' }), tracks, matching: false });
		expect(await screen.findByText('Applied automatically')).toBeInTheDocument();
		forA.resolve({ ...applied, sources: { episodes_tmdb: { status: 'ok', suggestion: true } } });
		await new Promise((r) => setTimeout(r, 0));
		expect(screen.queryByText('Suggestion, not applied')).toBeNull();
		expect(screen.getByText('Applied automatically')).toBeInTheDocument();
	});

	it('resets the re-run panel and preview when the job changes', async () => {
		vi.mocked(matchIdentity).mockResolvedValueOnce(tvmazePreview);
		const { rerender } = renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await screen.findByText(/1 track changes/);
		await rerender({ job: job({ id: 'job_2' }), tracks, matching: false });
		await screen.findByText('Applied automatically');
		expect(screen.queryByText(/1 track changes/)).toBeNull();
		expect(screen.queryByLabelText('Source')).toBeNull();
	});

	it('drops a preview whose form changed while it was in flight; apply sends the previewed request', async () => {
		const slow = deferred<MatchPreview>();
		vi.mocked(matchIdentity).mockReturnValueOnce(slow.promise);
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await openRerun();
		await fireEvent.change(screen.getByLabelText('Source'), { target: { value: 'tvmaze' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await fireEvent.input(screen.getByLabelText('Season'), { target: { value: '2' } });
		slow.resolve(tvmazePreview);
		await new Promise((r) => setTimeout(r, 0));
		expect(screen.queryByText(/track changes? if you apply/)).toBeNull();

		vi.mocked(matchIdentity).mockResolvedValueOnce(tvmazePreview).mockResolvedValueOnce({ outcomes: [] });
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await screen.findByText(/1 track changes if you apply TVmaze/);
		const previewed = vi.mocked(matchIdentity).mock.calls[1][1];
		expect(previewed).toEqual({ source: 'tvmaze', season: 2, disc_number: 1, apply: false });
		await fireEvent.click(screen.getByRole('button', { name: 'Apply & pin TVmaze' }));
		expect(vi.mocked(matchIdentity).mock.calls[2][1]).toEqual({ ...previewed, apply: true });
	});

	it('drops the preview when matching starts', async () => {
		vi.mocked(matchIdentity).mockResolvedValueOnce(tvmazePreview);
		const { rerender } = renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await screen.findByText(/1 track changes/);
		await rerender({ job: job(), tracks, matching: true });
		await rerender({ job: job(), tracks, matching: false });
		expect(screen.queryByText(/1 track changes/)).toBeNull();
		expect(screen.queryByText('CHANGED')).toBeNull();
	});

	it('disables Unpin while the request runs', async () => {
		fetchIdentity.mockResolvedValue({ ...applied, pin: { episode: 'episodes_tmdb' } });
		const slow = deferred<IdentityView>();
		vi.mocked(unpinIdentity).mockReturnValue(slow.promise);
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await fireEvent.click(await screen.findByRole('button', { name: 'Unpin…' }));
		const button = screen.getByRole('button', { name: 'Unpin' });
		await fireEvent.click(button);
		expect(button).toBeDisabled();
		await fireEvent.click(button);
		expect(unpinIdentity).toHaveBeenCalledTimes(1);
		slow.resolve({ ...applied, pin: {} });
		expect(await screen.findByText('Applied automatically')).toBeInTheDocument();
	});

	it('labels Accept as accepting even with the re-run panel open', async () => {
		fetchIdentity.mockResolvedValue({ ...applied, sources: { episodes_tmdb: { status: 'ok', suggestion: true } } });
		vi.mocked(matchIdentity).mockReturnValue(new Promise(() => {}));
		renderComponent(EpisodeMatchPanel, { props: { job: job(), tracks, matching: false } });
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Accept suggestion' }));
		expect(screen.getByRole('button', { name: 'Accepting…' })).toBeDisabled();
	});
});
