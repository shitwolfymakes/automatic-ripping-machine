import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent, waitFor, within } from '$lib/test-utils';

// Branch pins for EpisodeMatchPanel's loading and match actions, beside
// EpisodeMatchPanel.test.ts. These branches and lines cannot be reached from
// the rendered panel, so nothing here forces them:
// - labelOf's two fallbacks (`?? id ?? ''`): every label it is asked for is
//   one of the three sources.
// - shortId's `?? ''`: it is only called with a source, never null.
// - failed's `: []`: only the no-match alert reads it, and that state needs an
//   identity.
// - `req.source ?? null` in run: every request the panel sends has a source.
// - applyPreview with no preview request: Apply only shows with a preview on
//   screen.
// - the `bind:form` setter on RerunPanel: RerunPanel changes the form's fields
//   and never reassigns it.
// - held's `: null` (when the panel is not showing a guess): the derived is
//   read only inside `view === 'unsure' && held`, and an unsure view always
//   has an identity, so it is never evaluated in any other state.

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper, not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});
const fetchIdentity = vi.fn();
vi.mock('$lib/api/identity', () => ({
	fetchIdentity: (...a: unknown[]) => fetchIdentity(...a),
	matchIdentity: vi.fn(),
	unpinIdentity: vi.fn(),
	clearEpisodeMatch: vi.fn(),
	fetchEpisodes: vi.fn(),
	fetchSeasons: vi.fn()
}));
vi.mock('$lib/api/jobs', () => ({
	fetchNamingPreview: vi.fn(),
	updateTrack: vi.fn()
}));

import EpisodeMatchPanel from '../EpisodeMatchPanel.svelte';
import { fetchNamingPreview } from '$lib/api/jobs';
import { clearEpisodeMatch, fetchEpisodes, fetchSeasons, matchIdentity } from '$lib/api/identity';
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
const held = (summary: Record<string, unknown> = {}): IdentityView => ({
	...applied,
	sources: { episodes_tmdb: { status: 'ok', suggestion: true, ...summary } }
});
const NOT_SET_UP = { status: 'skipped', detail: 'not configured' } as const;
const NO_MATCH: IdentityView = { sources: { episodes_tmdb: { status: 'miss' } }, pin: {}, tracks: [] };
const tvmazePreview: MatchPreview = {
	outcomes: [
		{
			source_id: 'episodes_tvmaze',
			matches: [{ source_ref: 't00', season: 1, episode: 2, episode_name: 'Ep 2', confidence: 0.81 }]
		}
	]
};

function deferred<T>() {
	let resolve: (v: T) => void = () => {};
	let reject: (e: unknown) => void = () => {};
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}
const settle = () => new Promise((r) => setTimeout(r, 0));

async function setRole(r: string | null) {
	((await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void }).__setRole(r);
}
async function openRerun() {
	await fireEvent.click(await screen.findByRole('button', { name: 'Fix match' }));
}
async function rerunSeasonOption(name: string) {
	return within(await screen.findByLabelText('Season')).findByRole('option', { name });
}
const formSource = () => (screen.getByLabelText('Source') as HTMLSelectElement).value;
const formSeason = () => (screen.getByLabelText('Season') as HTMLSelectElement).value;
const panelProps = (o: Partial<JobView> = {}) => ({ job: job(o), tracks, matching: false });

beforeEach(() => {
	vi.resetAllMocks();
	fetchIdentity.mockResolvedValue(applied);
	vi.mocked(fetchNamingPreview).mockResolvedValue({ job_output_dir: '', job_output_name: '', items: [] });
	vi.mocked(fetchEpisodes).mockResolvedValue({ source_id: 'episodes_tmdb', show_id: '5084', season: 1, episodes: [] });
	vi.mocked(fetchSeasons).mockResolvedValue({ source_id: 'episodes_tmdb', show_id: '5084', seasons: [1, 2, 3] });
});
afterEach(async () => {
	cleanup();
	await setRole('admin');
});

describe('EpisodeMatchPanel reload branches', () => {
	it('shows no load error for either job when the identity fetch rejects after the job changed', async () => {
		const forA = deferred<IdentityView>();
		fetchIdentity.mockImplementation((id: string) => (id === 'job_A' ? forA.promise : Promise.resolve(applied)));
		const { rerender } = renderComponent(EpisodeMatchPanel, { props: panelProps({ id: 'job_A' }) });
		await rerender({ job: job({ id: 'job_B' }), tracks, matching: false });
		expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
		forA.reject(new Error('HTTP 500'));
		await settle();
		expect(screen.queryByText('Could not load the episode match')).toBeNull();
		expect(screen.queryByText('HTTP 500')).toBeNull();
		expect(screen.getByText('6 of 6 tracks placed')).toBeInTheDocument();
	});

	it('says "Could not load episodes" when the identity fetch rejects with something that is not an Error', async () => {
		fetchIdentity.mockRejectedValue('boom');
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		expect(await screen.findByText('Could not load the episode match')).toBeInTheDocument();
		expect(screen.getByText('Could not load episodes')).toBeInTheDocument();
	});

	it('does not show the naming preview file names of a job it was handed away from', async () => {
		const forA = deferred<{ job_output_dir: string; job_output_name: string; items: unknown[] }>();
		vi.mocked(fetchNamingPreview).mockImplementation(((id: string) =>
			id === 'job_A'
				? forA.promise
				: Promise.resolve({ job_output_dir: '', job_output_name: '', items: [] })) as never);
		const { rerender } = renderComponent(EpisodeMatchPanel, { props: panelProps({ id: 'job_A' }) });
		// Job A's identity has landed; only its naming preview is still pending.
		expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
		await rerender({ job: job({ id: 'job_B' }), tracks, matching: false });
		forA.resolve({
			job_output_dir: '/media/tv',
			job_output_name: 'Kolchak',
			items: [
				{
					track_id: 'trk_3',
					output_path: '/media/tv/Kolchak - S01E04.mkv',
					output_dir: '/media/tv',
					output_name: 'Kolchak - S01E04.mkv'
				}
			]
		});
		await settle();
		expect(screen.queryByText('Kolchak - S01E04.mkv')).toBeNull();
	});

	it('shows no file names and no error when the naming preview has no items', async () => {
		vi.mocked(fetchNamingPreview).mockResolvedValue({ job_output_dir: '', job_output_name: '' } as never);
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
		await settle();
		expect(screen.queryByRole('alert')).toBeNull();
		expect(screen.queryByText(/\.mkv/)).toBeNull();
	});
});

describe('EpisodeMatchPanel status line and sources', () => {
	it('shows the source id on the chip when the active source is not one of the three', async () => {
		fetchIdentity.mockResolvedValue({
			...applied,
			pin: { episode: 'episodes_foo' },
			sources: { episodes_foo: { status: 'ok' }, episodes_tmdb: { status: 'ok' } }
		});
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		const chip = await screen.findByText('episodes_foo');
		expect(chip).toHaveClass('chip-info');
	});

	it('View sources words a missing status as matched, an unknown status as itself, and drops a missing detail', async () => {
		fetchIdentity.mockResolvedValue({
			...applied,
			sources: {
				episodes_tmdb: { status: 'ok' },
				episodes_tvmaze: {},
				episodes_tvdb: { status: 'weird', detail: 'odd reply' },
				episodes_foo: { status: 'weird' }
			}
		});
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await fireEvent.click(await screen.findByRole('button', { name: /View sources/ }));
		const items = screen.getAllByRole('listitem').map((li) => li.textContent?.replace(/\s+/g, ' ').trim());
		expect(items).toEqual(['TVmaze: matched', 'TVDB: weird, odd reply', 'episodes_foo: weird']);
	});

	it('lists a failed source with no detail as "<label> failed" with no colon', async () => {
		fetchIdentity.mockResolvedValue({ sources: { episodes_tmdb: { status: 'error' } }, pin: {}, tracks: [] });
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		const line = await screen.findByText('TMDb failed');
		expect(line.textContent).not.toContain(':');
	});
});

describe('EpisodeMatchPanel Fix match seed', () => {
	it('closes the form when Fix match is clicked again', async () => {
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await openRerun();
		expect(screen.getByLabelText('Source')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Fix match' }));
		expect(screen.queryByLabelText('Source')).toBeNull();
		expect(screen.getByRole('button', { name: 'Fix match' })).toHaveAttribute('aria-expanded', 'false');
	});

	it('with no active source opens on the first source that is not off', async () => {
		fetchIdentity.mockResolvedValue({
			sources: { episodes_tmdb: NOT_SET_UP, episodes_tvmaze: { status: 'miss' } },
			pin: {},
			tracks: []
		});
		renderComponent(EpisodeMatchPanel, { props: panelProps({ season: 2 }) });
		await openRerun();
		await rerunSeasonOption('Season 2');
		expect(formSource()).toBe('tvmaze');
		expect(formSeason()).toBe('2');
	});

	it('treats a skipped source with no detail as on, not as off', async () => {
		fetchIdentity.mockResolvedValue({
			sources: { episodes_tmdb: { status: 'skipped' }, episodes_tvmaze: { status: 'miss' } },
			pin: {},
			tracks: []
		});
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await openRerun();
		expect(formSource()).toBe('tmdb');
		expect(screen.getByRole('option', { name: 'TMDb' })).not.toBeDisabled();
	});

	it('opens on TMDb when all three sources are off but another source ran ok', async () => {
		fetchIdentity.mockResolvedValue({
			...applied,
			sources: {
				episodes_tmdb: NOT_SET_UP,
				episodes_tvmaze: NOT_SET_UP,
				episodes_tvdb: NOT_SET_UP,
				episodes_foo: { status: 'ok' }
			}
		});
		renderComponent(EpisodeMatchPanel, { props: panelProps({ season: 3 }) });
		await openRerun();
		await rerunSeasonOption('Season 3');
		expect(formSource()).toBe('tmdb');
		expect(formSeason()).toBe('3');
	});

	it('opens on the first source that is not off when the active source is outside the three', async () => {
		fetchIdentity.mockResolvedValue({
			...applied,
			pin: { episode: 'episodes_foo' },
			sources: { episodes_foo: { status: 'ok' }, episodes_tmdb: NOT_SET_UP, episodes_tvmaze: { status: 'ok' } }
		});
		renderComponent(EpisodeMatchPanel, { props: panelProps({ season: 1 }) });
		await openRerun();
		await rerunSeasonOption('Season 1');
		expect(formSource()).toBe('tvmaze');
		expect(formSeason()).toBe('1');
	});
});

describe('EpisodeMatchPanel held result', () => {
	it('reads "Specials, <m> of <t> titles" when the held result is in season 0', async () => {
		const id = held();
		id.tracks = id.tracks!.map((t) => ({ ...t, proposals: { episodes_tmdb: { season: 0, episode: 1 } } }));
		fetchIdentity.mockResolvedValue(id);
		renderComponent(EpisodeMatchPanel, { props: panelProps({ episodes_unsure: true }) });
		expect(await screen.findByTestId('season-fit')).toHaveTextContent('Specials, 6 of 6 titles');
	});

	it('starts the alert line "This match is a guess" when no track has a proposal', async () => {
		const id = held();
		id.tracks = id.tracks!.map((t) => ({ ...t, proposals: {} }));
		fetchIdentity.mockResolvedValue(id);
		renderComponent(EpisodeMatchPanel, { props: panelProps({ episodes_unsure: true }) });
		expect(await screen.findByText(/^This match is a guess/)).toBeInTheDocument();
		expect(screen.queryByTestId('season-fit')).toBeNull();
	});
});

describe('EpisodeMatchPanel Clear episodes branches', () => {
	const cleared: IdentityView = { sources: {}, pin: {}, tracks: [] };

	it('keeps the new job state and skips onchanged when the clear resolves after the job changed', async () => {
		const slow = deferred<IdentityView>();
		vi.mocked(clearEpisodeMatch).mockReturnValue(slow.promise);
		const onchanged = vi.fn();
		const { rerender } = renderComponent(EpisodeMatchPanel, {
			props: { ...panelProps({ id: 'job_A' }), onchanged }
		});
		await fireEvent.click(await screen.findByRole('button', { name: 'Clear episodes' }));
		await rerender({ job: job({ id: 'job_B' }), tracks, matching: false, onchanged });
		expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
		slow.resolve(cleared);
		await settle();
		expect(screen.getByText('6 of 6 tracks placed')).toBeInTheDocument();
		expect(screen.queryByText('No match')).toBeNull();
		expect(onchanged).not.toHaveBeenCalled();
	});

	it('shows "Could not clear the episodes (<message>)." when the clear rejects with an Error', async () => {
		vi.mocked(clearEpisodeMatch).mockRejectedValue(new Error('HTTP 500'));
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await fireEvent.click(await screen.findByRole('button', { name: 'Clear episodes' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('Could not clear the episodes (HTTP 500).');
	});

	it('shows "Could not clear the episodes (error)." when the clear rejects with something that is not an Error', async () => {
		vi.mocked(clearEpisodeMatch).mockRejectedValue('boom');
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await fireEvent.click(await screen.findByRole('button', { name: 'Clear episodes' }));
		expect(await screen.findByRole('alert')).toHaveTextContent('Could not clear the episodes (error).');
	});

	it('shows no error line when the clear rejects after the job changed', async () => {
		const slow = deferred<IdentityView>();
		vi.mocked(clearEpisodeMatch).mockReturnValue(slow.promise);
		const { rerender } = renderComponent(EpisodeMatchPanel, { props: panelProps({ id: 'job_A' }) });
		await fireEvent.click(await screen.findByRole('button', { name: 'Clear episodes' }));
		await rerender({ job: job({ id: 'job_B' }), tracks, matching: false });
		expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
		slow.reject(new Error('HTTP 500'));
		await settle();
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it('Try again after a failed clear with no match run calls neither matchIdentity nor clearEpisodeMatch', async () => {
		vi.mocked(clearEpisodeMatch).mockRejectedValue(new Error('HTTP 500'));
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await fireEvent.click(await screen.findByRole('button', { name: 'Clear episodes' }));
		await screen.findByText('Could not clear the episodes (HTTP 500).');
		expect(clearEpisodeMatch).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
		await settle();
		expect(matchIdentity).not.toHaveBeenCalled();
		expect(clearEpisodeMatch).toHaveBeenCalledTimes(1);
		expect(screen.getByRole('alert')).toHaveTextContent('Could not clear the episodes (HTTP 500).');
	});

	it('Try again after a failed preview and a failed clear reruns the preview request, not the clear', async () => {
		vi.mocked(matchIdentity).mockRejectedValueOnce(new Error('HTTP 502')).mockResolvedValueOnce(tvmazePreview);
		vi.mocked(clearEpisodeMatch).mockRejectedValue(new Error('HTTP 500'));
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await screen.findByText(/TMDb didn't answer \(HTTP 502\)/);
		await fireEvent.click(screen.getByRole('button', { name: 'Clear episodes' }));
		await screen.findByText('Could not clear the episodes (HTTP 500).');
		expect(clearEpisodeMatch).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
		await screen.findByText(/1 track changes if you apply TMDb/);
		expect(matchIdentity).toHaveBeenCalledTimes(2);
		expect(vi.mocked(matchIdentity).mock.calls[1]).toEqual(['job_1', { source: 'tmdb', apply: false }]);
		expect(clearEpisodeMatch).toHaveBeenCalledTimes(1);
	});
});

describe('EpisodeMatchPanel run branches', () => {
	it('reports a preview outcome with status error by source and detail without refetching the identity', async () => {
		vi.mocked(matchIdentity).mockResolvedValueOnce({
			outcomes: [{ source_id: 'episodes_tmdb', status: 'error', detail: 'HTTP 503' }]
		} as MatchPreview);
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await openRerun();
		const before = fetchIdentity.mock.calls.length;
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		expect(await screen.findByRole('alert')).toHaveTextContent(
			"TMDb didn't answer (HTTP 503). Nothing changed; the placement below is still TMDb's."
		);
		expect(fetchIdentity).toHaveBeenCalledTimes(before);
	});

	it('words a failed outcome with no detail as "(error)"', async () => {
		vi.mocked(matchIdentity).mockResolvedValueOnce({
			outcomes: [{ source_id: 'episodes_tmdb', status: 'error' }]
		} as MatchPreview);
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		expect(await screen.findByRole('alert')).toHaveTextContent("TMDb didn't answer (error).");
	});

	it('shows no error line when a failed apply reloads after the job changed', async () => {
		vi.mocked(matchIdentity)
			.mockResolvedValueOnce(tvmazePreview)
			.mockResolvedValueOnce({
				outcomes: [{ source_id: 'episodes_tmdb', status: 'error', detail: 'HTTP 503' }]
			} as MatchPreview);
		const onchanged = vi.fn();
		const { rerender } = renderComponent(EpisodeMatchPanel, {
			props: { ...panelProps({ id: 'job_A' }), onchanged }
		});
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await screen.findByText(/1 track changes if you apply TMDb/);
		const gate = deferred<IdentityView>();
		fetchIdentity.mockImplementation((id: string) => (id === 'job_A' ? gate.promise : Promise.resolve(applied)));
		const before = fetchIdentity.mock.calls.length;
		await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
		await waitFor(() => expect(fetchIdentity).toHaveBeenCalledTimes(before + 1));
		await rerender({ job: job({ id: 'job_B' }), tracks, matching: false, onchanged });
		expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
		gate.resolve(applied);
		await settle();
		expect(screen.queryByRole('alert')).toBeNull();
		expect(screen.queryByText(/didn't answer/)).toBeNull();
	});

	it('shows no error line when a run rejects after the job changed', async () => {
		const slow = deferred<MatchPreview>();
		vi.mocked(matchIdentity).mockReturnValue(slow.promise);
		const { rerender } = renderComponent(EpisodeMatchPanel, { props: panelProps({ id: 'job_A' }) });
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		await rerender({ job: job({ id: 'job_B' }), tracks, matching: false });
		expect(await screen.findByText('6 of 6 tracks placed')).toBeInTheDocument();
		slow.reject(new Error('HTTP 502'));
		await settle();
		expect(screen.queryByRole('alert')).toBeNull();
	});

	it('ends the line "the placement below is unchanged." when a run rejects with no source on screen', async () => {
		fetchIdentity.mockResolvedValue(NO_MATCH);
		vi.mocked(matchIdentity).mockRejectedValueOnce(new Error('HTTP 502'));
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		const alert = await screen.findByText(/didn't answer/);
		expect(alert).toHaveTextContent(
			"TMDb didn't answer (HTTP 502). Nothing changed; the placement below is unchanged."
		);
		expect(alert.textContent).toMatch(/Nothing changed; the placement below is unchanged\.$/);
	});

	it('words a run that rejects with something that is not an Error as "(error)"', async () => {
		vi.mocked(matchIdentity).mockRejectedValueOnce('boom');
		renderComponent(EpisodeMatchPanel, { props: panelProps() });
		await openRerun();
		await fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
		expect(await screen.findByRole('alert')).toHaveTextContent("TMDb didn't answer (error).");
	});
});
