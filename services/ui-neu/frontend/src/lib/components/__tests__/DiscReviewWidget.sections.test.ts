// The review card's rows, actions and error paths that DiscReviewWidget.test.ts
// and DiscReviewWidget.episodes.test.ts leave out. The apply dialog, the Info
// form, the episode panel and the media type switch are replaced by stand-ins
// that call the props the card passes; the countdown, the confirm dialog, the
// tracks table and the music search render for real.
//
// Branches the card cannot reach, so they are not forced here:
// - the empty-string status fallbacks in the start-rip and post-rip checks: a
//   job always has a status, and both checks are read only while the job is set
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';
import DiscReviewWidget from '../DiscReviewWidget.svelte';
import type { JobView, TrackView } from '$lib/types/api.gen';
import { createJob, createJobDetail, createTrack } from '../__fixtures__/job';

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

vi.mock('$lib/api/jobs', () => ({
	fetchJob: vi.fn(),
	fetchNamingPreview: vi.fn(),
	abandonJob: vi.fn(),
	deleteJob: vi.fn(),
	startWaitingJob: vi.fn(),
	pauseWaitingJob: vi.fn(),
	resolveJob: vi.fn(),
	acceptIdentitySuggestion: vi.fn(),
	updateTrack: vi.fn(),
	updateJobTitle: vi.fn(),
	clearTrackTitle: vi.fn(),
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	searchMusicMetadata: vi.fn(),
	fetchMusicDetail: vi.fn(),
	fetchNamingVariables: vi.fn(),
	namingPreview: vi.fn(),
	validatePattern: vi.fn()
}));

vi.mock('$lib/api/sessions', () => ({ fetchSessions: vi.fn() }));
vi.mock('$lib/api/iso', () => ({ cancelIsoRip: vi.fn() }));

vi.mock('$lib/stores/ripper-events.svelte', () => ({
	startRipperEvents: vi.fn(),
	onRipperEvent: () => () => {}
}));

vi.mock('../ApplySessionDialog.svelte', async () => ({
	default: (await import('../__fixtures__/ApplySessionDialogStub.svelte')).default
}));
vi.mock('../JobInfoForm.svelte', async () => ({
	default: (await import('../__fixtures__/JobInfoFormStub.svelte')).default
}));
vi.mock('../episodes/EpisodeMatchPanel.svelte', async () => ({
	default: (await import('../__fixtures__/EpisodeMatchPanelStub.svelte')).default
}));
vi.mock('../episodes/MediaTypeSwitch.svelte', async () => ({
	default: (await import('../__fixtures__/MediaTypeSwitchStub.svelte')).default
}));

import {
	abandonJob,
	deleteJob,
	fetchJob,
	fetchNamingPreview,
	pauseWaitingJob,
	resolveJob,
	startWaitingJob
} from '$lib/api/jobs';
import { fetchSessions } from '$lib/api/sessions';

const mockFetchJob = vi.mocked(fetchJob);
const mockPreview = vi.mocked(fetchNamingPreview);
const mockSessions = vi.mocked(fetchSessions);

async function setRole(role: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
	auth.__setRole(role);
}

interface CardOptions {
	tracks?: TrackView[];
	previousRip?: unknown;
	props?: Record<string, unknown>;
}

// The card for a job the Backend also returns on the detail load.
function renderCard(overrides: Partial<JobView> = {}, options: CardOptions = {}) {
	const job = createJob({ status: 'awaiting_review', ...overrides });
	mockFetchJob.mockResolvedValue({
		...createJobDetail({ tracks: options.tracks ?? [] }),
		job,
		previous_rip: options.previousRip ?? null
	} as never);
	const onrefresh = vi.fn();
	const ondismiss = vi.fn();
	renderComponent(DiscReviewWidget, {
		props: { job, driveNames: {}, paused: false, onrefresh, ondismiss, ...options.props }
	});
	return { onrefresh, ondismiss };
}

// A TV disc whose TMDb episode source answered, with `count` video titles of
// which the first `placed` have an episode number.
function tvTracks(count: number, placed: number): TrackView[] {
	return Array.from({ length: count }, (_, i) =>
		createTrack({ id: `trk_${i}`, index: i, episode_number: i < placed ? i + 1 : null })
	);
}

const TV_SOURCE_OK = {
	media_type: 'tv',
	has_series: true,
	metadata_json: { identity_claims: { sources: { episodes_tmdb: { status: 'ok' } } } }
} as Partial<JobView>;

const TV_SOURCE_FAILED = {
	media_type: 'tv',
	has_series: true,
	metadata_json: { identity_claims: { sources: { episodes_tvmaze: { status: 'error' } } } }
} as Partial<JobView>;

const statusRow = () => screen.findByTestId('episode-status');

describe('DiscReviewWidget sections', () => {
	beforeEach(() => {
		mockPreview.mockResolvedValue({ items: [] } as never);
		mockSessions.mockResolvedValue([]);
		vi.mocked(abandonJob).mockResolvedValue(createJob());
		vi.mocked(deleteJob).mockResolvedValue(undefined);
		vi.mocked(startWaitingJob).mockResolvedValue(createJob());
		vi.mocked(pauseWaitingJob).mockResolvedValue(createJob());
		vi.mocked(resolveJob).mockResolvedValue({} as never);
	});

	afterEach(async () => {
		cleanup();
		vi.clearAllMocks();
		await setRole('admin');
	});

	describe('rows', () => {
		it('shows the artist and album of a CD', async () => {
			renderCard({
				disc_type: 'cd',
				metadata_json: { music: { artist: 'Queen', album: 'Jazz' } } as never
			});
			expect(await screen.findByText('Artist')).toBeInTheDocument();
			expect(screen.getByText('Queen')).toBeInTheDocument();
			expect(screen.getByText('Album')).toBeInTheDocument();
			expect(screen.getByText('Jazz')).toBeInTheDocument();
		});

		it("opens the music search from a CD's Search button", async () => {
			renderCard({ disc_type: 'cd' });
			expect(screen.queryByPlaceholderText('Album or title...')).toBeNull();
			await fireEvent.click(await screen.findByRole('button', { name: 'Search' }));
			expect(await screen.findByPlaceholderText('Album or title...')).toBeInTheDocument();
		});

		it('leaves the year out of the title when the job has none', async () => {
			renderCard({ year: null });
			const heading = await screen.findByRole('heading', { name: 'Test Movie' });
			expect(heading).toHaveTextContent(/^Test Movie$/);
		});

		it('writes the disc number without a total when the total is unknown', async () => {
			renderCard({ disc_number: 2, disc_total: null });
			expect(await screen.findByText('Blu-ray, Disc 2')).toBeInTheDocument();
		});

		it('shows the track count in the disc line', async () => {
			renderCard({
				disc_number: 1,
				disc_total: 4,
				metadata_json: { scan_result: { titles: [{}, {}, {}] } } as never
			});
			expect(await screen.findByText('Blu-ray, Disc 1/4, 3 titles')).toBeInTheDocument();
		});

		it('names the loaded session of a pending session id', async () => {
			mockSessions.mockResolvedValue([{ id: 'ses_1', name: 'Movie session' }] as never);
			renderCard({ pending_session_id: 'ses_1' });
			expect(await screen.findByText('Movie session')).toBeInTheDocument();
		});

		it('falls back to the session id when the sessions fail to load', async () => {
			mockSessions.mockRejectedValue(new Error('offline'));
			renderCard({ pending_session_id: 'ses_1' });
			await waitFor(() => expect(mockSessions).toHaveBeenCalled());
			await new Promise((r) => setTimeout(r, 0));
			expect(screen.getByText('ses_1')).toBeInTheDocument();
			expect(screen.queryByText('Movie session')).toBeNull();
		});
	});

	describe('match row', () => {
		const IMDB = { identity: { external_ids: { imdb: 'tt0071049' } } };

		it('appends the series years when the show ran for several', async () => {
			renderCard({
				...TV_SOURCE_OK,
				year: 1974,
				metadata_json: { ...IMDB, identity: { ...IMDB.identity, facts: { end_year: 1975 } } } as never
			});
			expect(await screen.findByTestId('match-row')).toHaveTextContent('tt0071049 , TV Series, 1974-1975');
		});

		it('appends one year when the show ended the year it began', async () => {
			renderCard({
				...TV_SOURCE_OK,
				year: 1974,
				metadata_json: { identity: { ...IMDB.identity, facts: { end_year: 1974 } } } as never
			});
			expect(await screen.findByTestId('match-row')).toHaveTextContent('tt0071049 , TV Series, 1974');
			expect(screen.getByTestId('match-row')).not.toHaveTextContent('1974-');
		});

		it('appends no year when a series has none', async () => {
			renderCard({ ...TV_SOURCE_OK, year: null, metadata_json: IMDB as never });
			const row = await screen.findByTestId('match-row');
			expect(row).toHaveTextContent('tt0071049 , TV Series');
			expect(row).not.toHaveTextContent(/, \d{4}/);
		});

		it('appends nothing to an IMDb match that has no type or year', async () => {
			renderCard({ year: null, metadata_json: IMDB as never });
			const row = await screen.findByTestId('match-row');
			expect(within(row).getByText('tt0071049')).toBeInTheDocument();
			expect(row.querySelector('.disc-review-widget-muted')).toBeNull();
		});

		it('appends nothing to a hand-set title that has no type or year', async () => {
			renderCard({ year: null });
			const row = await screen.findByTestId('match-row');
			expect(within(row).getByText('Set by hand')).toBeInTheDocument();
			expect(row.querySelector('.disc-review-widget-muted')).toBeNull();
		});
	});

	describe('episodes row', () => {
		it('names the source and the title counts while matching', async () => {
			renderCard(TV_SOURCE_OK, { tracks: tvTracks(6, 4) });
			await fireEvent.click(await screen.findByRole('button', { name: 'Switch to TV' }));
			const row = await statusRow();
			expect(row).toHaveAttribute('data-state', 'matching');
			expect(row).toHaveTextContent('Matching episodes... TMDb, 4 of 6 titles');
		});

		it('names only the source while matching before the tracks load', async () => {
			renderCard(TV_SOURCE_OK);
			await fireEvent.click(await screen.findByRole('button', { name: 'Switch to TV' }));
			const row = await statusRow();
			await waitFor(() => expect(row).toHaveAttribute('data-state', 'matching'));
			expect(row).toHaveTextContent('Matching episodes... TMDb');
			expect(row).not.toHaveTextContent('titles');
		});

		it('adds no detail while matching with no source or tracks known', async () => {
			renderCard({ media_type: 'tv', has_series: true });
			const row = await statusRow();
			expect(row).toHaveAttribute('data-state', 'matching');
			expect(row.querySelector('.disc-review-widget-muted')).toBeNull();
		});

		it('says Episodes matched with no source when the operator placed every title', async () => {
			renderCard(TV_SOURCE_FAILED, { tracks: tvTracks(2, 2) });
			expect(await screen.findByRole('button', { name: 'Episodes matched' })).toBeInTheDocument();
			expect(screen.getByTestId('episode-status')).toHaveAttribute('data-state', 'matched');
		});

		it('opens the panel from the Review button of a guessed placement', async () => {
			renderCard({
				...TV_SOURCE_OK,
				episodes_unsure: true,
				metadata_json: { identity_claims: { sources: { episodes_tmdb: { status: 'ok', suggestion: true } } } } as never
			});
			const row = await statusRow();
			await waitFor(() => expect(row).toHaveAttribute('data-state', 'guess'));
			expect(screen.queryByTestId('episode-panel')).toBeNull();
			await fireEvent.click(within(row).getByRole('button', { name: 'Review' }));
			expect(screen.getByTestId('episode-panel')).toBeInTheDocument();
		});

		it('says Episodes need attention without counts when no tracks have loaded', async () => {
			renderCard(TV_SOURCE_FAILED);
			const row = await statusRow();
			await waitFor(() => expect(mockFetchJob).toHaveBeenCalled());
			expect(row).toHaveAttribute('data-state', 'attention');
			expect(row).toHaveTextContent('Episodes need attention, Review');
			expect(row).not.toHaveTextContent('unmatched');
		});
	});

	describe('media type', () => {
		it('hands the switch the count of tracks the user set by hand', async () => {
			const tracks = [
				createTrack({ id: 'a', identity_provenance: { episode_number: 'manual' } }),
				createTrack({ id: 'b', identity_provenance: { role: 'manual' } }),
				createTrack({ id: 'c', identity_provenance: { episode_number: 'episodes_tmdb' } }),
				createTrack({ id: 'd', identity_provenance: null }),
				createTrack({ id: 'e' })
			];
			renderCard({}, { tracks });
			await waitFor(() => expect(screen.getByTestId('hand-set-count')).toHaveTextContent('2'));
		});

		it('hands the switch no hand-set tracks when the detail fails to load', async () => {
			mockFetchJob.mockRejectedValue(new Error('offline'));
			renderComponent(DiscReviewWidget, {
				props: { job: createJob({ status: 'awaiting_review' }), driveNames: {}, paused: false }
			});
			await waitFor(() => expect(mockFetchJob).toHaveBeenCalled());
			await new Promise((r) => setTimeout(r, 0));
			expect(screen.getByTestId('hand-set-count')).toHaveTextContent('0');
		});

		it('stops matching, closes Episodes and reloads when the type becomes Movie', async () => {
			const { onrefresh } = renderCard(TV_SOURCE_OK);
			await fireEvent.click(await screen.findByRole('button', { name: 'Switch to TV' }));
			expect(await screen.findByTestId('episode-panel')).toBeInTheDocument();
			expect((await statusRow()).getAttribute('data-state')).toBe('matching');
			const loads = mockFetchJob.mock.calls.length;
			onrefresh.mockClear();

			await fireEvent.click(screen.getByRole('button', { name: 'Switch to Movie' }));
			expect(screen.queryByTestId('episode-panel')).toBeNull();
			expect(screen.queryByText('Matching episodes...')).toBeNull();
			expect(onrefresh).toHaveBeenCalled();
			await waitFor(() => expect(mockFetchJob.mock.calls.length).toBeGreaterThan(loads));
		});
	});

	describe('Episodes panel and Info form', () => {
		it('reloads the detail when the episode panel changes', async () => {
			renderCard(TV_SOURCE_FAILED);
			await fireEvent.click(await screen.findByRole('button', { name: 'Episodes' }));
			const loads = mockFetchJob.mock.calls.length;
			await fireEvent.click(screen.getByRole('button', { name: 'Stub panel changed' }));
			await waitFor(() => expect(mockFetchJob.mock.calls.length).toBeGreaterThan(loads));
		});

		it.each([['Saved season'], ['Saved disc']])('%s on a TV disc starts matching', async (label) => {
			renderCard(TV_SOURCE_OK);
			await fireEvent.click(await screen.findByRole('button', { name: 'Info' }));
			await waitFor(() => expect(screen.getByTestId('episode-status')).toHaveAttribute('data-state', 'matched'));
			await fireEvent.click(screen.getByRole('button', { name: label }));
			expect(screen.getByTestId('episode-status')).toHaveAttribute('data-state', 'matching');
		});

		it('another saved change on a TV disc leaves matching alone', async () => {
			renderCard(TV_SOURCE_OK);
			await fireEvent.click(await screen.findByRole('button', { name: 'Info' }));
			await waitFor(() => expect(screen.getByTestId('episode-status')).toHaveAttribute('data-state', 'matched'));
			await fireEvent.click(screen.getByRole('button', { name: 'Saved other' }));
			expect(screen.getByTestId('episode-status')).toHaveAttribute('data-state', 'matched');
		});

		it('a saved season on a movie disc shows no matching', async () => {
			renderCard();
			await fireEvent.click(await screen.findByRole('button', { name: 'Info' }));
			await fireEvent.click(screen.getByRole('button', { name: 'Saved season' }));
			expect(screen.queryByTestId('episode-status')).toBeNull();
		});
	});

	describe('naming preview', () => {
		const withTrack = [createTrack({ id: 'trk_1', index: 0 })];

		it("puts the preview's file names in the tracks table", async () => {
			mockPreview.mockResolvedValue({ items: [{ track_id: 'trk_1', output_name: 'Kolchak S01E01.mkv' }] } as never);
			renderCard({}, { tracks: withTrack });
			await fireEvent.click(await screen.findByRole('button', { name: 'Info' }));
			expect(await screen.findByTestId('track-generated-name')).toHaveTextContent('Kolchak S01E01.mkv');
		});

		it('shows no file names when the preview has no items', async () => {
			mockPreview.mockResolvedValue({} as never);
			renderCard({}, { tracks: withTrack });
			await waitFor(() => expect(mockPreview).toHaveBeenCalled());
			await new Promise((r) => setTimeout(r, 0));
			await fireEvent.click(await screen.findByRole('button', { name: 'Info' }));
			expect(await screen.findByRole('table')).toBeInTheDocument();
			expect(screen.queryByTestId('track-generated-name')).toBeNull();
		});
	});

	describe('apply session', () => {
		it('closes the dialog, refreshes the parent and reloads the detail when applied', async () => {
			const { onrefresh } = renderCard();
			await fireEvent.click(await screen.findByRole('button', { name: 'Apply session' }));
			const loads = mockFetchJob.mock.calls.length;
			await fireEvent.click(screen.getByRole('button', { name: 'Stub apply' }));
			expect(screen.queryByTestId('apply-session-stub')).toBeNull();
			expect(onrefresh).toHaveBeenCalledTimes(1);
			await waitFor(() => expect(mockFetchJob.mock.calls.length).toBeGreaterThan(loads));
		});

		it('closes the dialog without refreshing when closed', async () => {
			const { onrefresh } = renderCard();
			await fireEvent.click(await screen.findByRole('button', { name: 'Apply session' }));
			await fireEvent.click(screen.getByRole('button', { name: 'Stub close' }));
			expect(screen.queryByTestId('apply-session-stub')).toBeNull();
			expect(onrefresh).not.toHaveBeenCalled();
		});
	});

	describe('cancel and delete', () => {
		it('shows a generic message when Cancel fails with a non-Error, and the banner dismisses', async () => {
			vi.mocked(abandonJob).mockRejectedValue('nope');
			const { ondismiss } = renderCard();
			await fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
			expect(await screen.findByText('Failed to cancel the job')).toBeInTheDocument();
			expect(ondismiss).not.toHaveBeenCalled();
			await fireEvent.click(screen.getByRole('button', { name: '×' }));
			expect(screen.queryByText('Failed to cancel the job')).toBeNull();
		});

		async function confirmDelete() {
			await fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
			const buttons = screen.getAllByRole('button', { name: 'Delete' });
			await fireEvent.click(buttons[buttons.length - 1]);
		}

		it('shows the error message when Delete fails with an Error', async () => {
			vi.mocked(deleteJob).mockRejectedValue(new Error('409 job is busy'));
			const { ondismiss } = renderCard({ status: 'ripped' });
			await confirmDelete();
			expect(await screen.findByText('409 job is busy')).toBeInTheDocument();
			expect(ondismiss).not.toHaveBeenCalled();
		});

		it('shows a generic message when Delete fails with a non-Error', async () => {
			vi.mocked(deleteJob).mockRejectedValue('nope');
			renderCard({ status: 'ripped' });
			await confirmDelete();
			expect(await screen.findByText('Failed to delete the job')).toBeInTheDocument();
		});

		it('deletes nothing when the confirmation is cancelled', async () => {
			renderCard({ status: 'ripped' });
			await fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
			const question = 'Delete this job? The raw files stay on disk. This cannot be undone.';
			expect(screen.getByText(question)).toBeInTheDocument();
			await fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
			expect(screen.queryByText(question)).toBeNull();
			expect(deleteJob).not.toHaveBeenCalled();
		});
	});

	describe('start rip', () => {
		it('asks for a title and sends nothing when the job has none', async () => {
			renderCard({ title: null });
			await fireEvent.click(await screen.findByRole('button', { name: 'Start rip' }));
			expect(screen.getByText('A title is required to start. Open Info or Search to set one.')).toBeInTheDocument();
			expect(resolveJob).not.toHaveBeenCalled();
		});

		it('sends a null year for a job with none', async () => {
			const { ondismiss } = renderCard({ year: null });
			await fireEvent.click(await screen.findByRole('button', { name: 'Start rip' }));
			await waitFor(() => expect(ondismiss).toHaveBeenCalled());
			expect(resolveJob).toHaveBeenCalledWith('job_1', {
				title: 'Test Movie',
				year: null,
				disc_number: null,
				disc_total: null
			});
			expect(startWaitingJob).toHaveBeenCalledWith('job_1');
		});

		it('shows the error message when starting fails with an Error', async () => {
			vi.mocked(resolveJob).mockRejectedValue(new Error('409 already started'));
			const { ondismiss } = renderCard();
			await fireEvent.click(await screen.findByRole('button', { name: 'Start rip' }));
			expect(await screen.findByText('409 already started')).toBeInTheDocument();
			expect(ondismiss).not.toHaveBeenCalled();
		});

		it('shows a generic message when starting fails with a non-Error', async () => {
			vi.mocked(resolveJob).mockRejectedValue('nope');
			renderCard();
			await fireEvent.click(await screen.findByRole('button', { name: 'Start rip' }));
			expect(await screen.findByText('Failed to start the rip')).toBeInTheDocument();
		});
	});

	describe('pause toggle', () => {
		const counting = { wait_start_time: new Date().toISOString() };
		const pauseCase = { label: 'Pause timer', overrides: counting, paused: true };
		const resumeCase = { label: 'Resume timer', overrides: { ...counting, manual_pause: true }, paused: false };

		it.each([pauseCase, resumeCase])('$label toggles this disc and refreshes the parent', async (c) => {
			const { onrefresh } = renderCard(c.overrides);
			await fireEvent.click(await screen.findByRole('button', { name: c.label }));
			await waitFor(() => expect(pauseWaitingJob).toHaveBeenCalledWith('job_1', c.paused));
			await waitFor(() => expect(onrefresh).toHaveBeenCalled());
		});

		it.each([pauseCase, resumeCase])('$label shows the error message when it fails with an Error', async (c) => {
			vi.mocked(pauseWaitingJob).mockRejectedValue(new Error('503 try later'));
			renderCard(c.overrides);
			await fireEvent.click(await screen.findByRole('button', { name: c.label }));
			expect(await screen.findByText('503 try later')).toBeInTheDocument();
		});

		it.each([pauseCase, resumeCase])('$label shows a generic message when it fails with a non-Error', async (c) => {
			vi.mocked(pauseWaitingJob).mockRejectedValue('nope');
			renderCard(c.overrides);
			await fireEvent.click(await screen.findByRole('button', { name: c.label }));
			expect(await screen.findByText('Failed to update pause')).toBeInTheDocument();
		});

		it('does nothing for a guest', async () => {
			await setRole('guest');
			renderCard(counting);
			await fireEvent.click(await screen.findByRole('button', { name: 'Pause timer' }));
			expect(pauseWaitingJob).not.toHaveBeenCalled();
		});

		it('does nothing while the whole machine is paused', async () => {
			renderCard(counting, { props: { paused: true } });
			await fireEvent.click(await screen.findByRole('button', { name: 'Resume timer' }));
			expect(pauseWaitingJob).not.toHaveBeenCalled();
		});

		it('does nothing while a toggle is in flight', async () => {
			vi.mocked(pauseWaitingJob).mockReturnValue(new Promise(() => {}));
			renderCard(counting);
			const button = await screen.findByRole('button', { name: 'Pause timer' });
			await fireEvent.click(button);
			await fireEvent.click(button);
			expect(pauseWaitingJob).toHaveBeenCalledTimes(1);
		});
	});

	describe('previously ripped notice', () => {
		const held = {
			wait_start_time: null,
			metadata_json: { previously_ripped: { job_id: 'job_old' } } as never
		};
		const earlier = (over: Record<string, unknown>) => ({
			job_id: 'job_old',
			title: 'Resident Evil',
			year: 2012,
			status: 'ripped',
			ripped_at: null,
			outputs_present: true,
			...over
		});

		it('names an untitled earlier rip with no date, and says its files are gone', async () => {
			renderCard(held, { previousRip: earlier({ title: null, outputs_present: false }) });
			await screen.findByText('Some of its files are no longer in the library.');
			const notice = screen.getByTestId('previously-ripped');
			expect(notice).toHaveTextContent('ARM already ripped this disc as an untitled disc.');
			expect(notice).not.toHaveTextContent(' on ');
			expect(notice).toHaveTextContent('Some of its files are no longer in the library.');
		});

		it('says a partial earlier rip was partial, with its date, and that it has no transcoded files', async () => {
			renderCard(held, {
				previousRip: earlier({ status: 'ripped_partial', ripped_at: '2026-10-12T06:35:00Z', outputs_present: null })
			});
			await screen.findByText('It has no transcoded files.');
			const notice = screen.getByTestId('previously-ripped');
			expect(notice).toHaveTextContent(/ripped this disc as Resident Evil on .+, partially\./);
			expect(notice).toHaveTextContent('It has no transcoded files.');
		});
	});
});
