import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent, within } from '$lib/test-utils';
import Page from '../[id]/+page.svelte';
import { createJob, createTrack } from '$lib/components/__fixtures__/job';
import type {
	ApplySessionResponse,
	JobDetailView,
	JobView,
	NamingPreviewItem,
	SessionView,
	TrackView
} from '$lib/types/api.gen';

// --- Mocks, modelled on [id]/page.test.ts ---

const mockGoto = vi.fn();
vi.mock('$app/navigation', () => ({ goto: (...args: unknown[]) => mockGoto(...args) }));

vi.mock('$app/stores', async () => {
	const { writable } = await import('svelte/store');
	const _page = writable<{ params: { id?: string } }>({ params: { id: 'job_42' } });
	return {
		page: { subscribe: _page.subscribe },
		// Test-only helper: simulate client-side navigation to another job.
		__setPageId: (id: string | undefined) => _page.set({ params: id === undefined ? {} : { id } })
	};
});

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper - not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/api/jobs', () => ({
	fetchJob: vi.fn(),
	fetchNamingPreview: vi.fn(),
	updateTrack: vi.fn(),
	clearTrackTitle: vi.fn(),
	resolveJob: vi.fn(),
	acceptIdentitySuggestion: vi.fn(),
	applySession: vi.fn(),
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	updateJobTitle: vi.fn(),
	searchMusicMetadata: vi.fn(),
	fetchMusicDetail: vi.fn(),
	setJobMediaType: vi.fn(),
	abandonJob: vi.fn(),
	deleteJob: vi.fn(),
	ripAgain: vi.fn()
}));

vi.mock('$lib/api/identity', () => ({
	fetchIdentity: vi.fn(() => new Promise(() => {})),
	matchIdentity: vi.fn(() => new Promise(() => {})),
	unpinIdentity: vi.fn(() => new Promise(() => {})),
	clearEpisodeMatch: vi.fn(() => new Promise(() => {})),
	fetchSeasons: vi.fn(() => new Promise(() => {})),
	fetchEpisodes: vi.fn(() => new Promise(() => {}))
}));

vi.mock('$lib/api/sessions', () => ({ fetchSessions: vi.fn() }));
vi.mock('$lib/api/rip-presets', () => ({ fetchRipPresets: vi.fn(() => Promise.resolve([])) }));
vi.mock('$lib/api/transcode-presets', () => ({ fetchTranscodePresets: vi.fn(() => Promise.resolve([])) }));

vi.mock('$lib/api/logs', () => ({
	fetchStructuredLogContent: vi.fn(() => Promise.resolve({ entries: [] })),
	fetchStructuredTranscoderLogContent: vi.fn(() => Promise.resolve({ entries: [] })),
	fetchTranscoderLogForArmJob: vi.fn(() => Promise.resolve({ found: false })),
	fetchLogContent: vi.fn(() => Promise.resolve({ content: '' })),
	fetchJobLog: vi.fn(() => Promise.resolve([])),
	jobLogDownloadUrl: (id: string) => `/api/logs/${id}.zip`
}));

vi.mock('$lib/api/ws', () => ({
	wsClient: { subscribe: vi.fn(() => vi.fn()), start: vi.fn(), stop: vi.fn() }
}));

vi.mock('$lib/api/settings', () => ({
	fetchSettings: vi.fn(() => Promise.resolve({ transcoder_config: { config: {} } }))
}));

type RipperListener = (jobIds: Set<string>, eventTypes: Map<string, Set<string>>) => void;
vi.mock('$lib/stores/ripper-events.svelte', () => ({
	startRipperEvents: vi.fn(),
	onRipperEvent: (fn: RipperListener) => {
		void fn;
		return () => {};
	}
}));

import {
	fetchJob,
	fetchNamingPreview,
	updateTrack,
	resolveJob,
	acceptIdentitySuggestion,
	applySession,
	searchMetadata,
	updateJobTitle,
	searchMusicMetadata,
	fetchMusicDetail,
	setJobMediaType,
	deleteJob,
	ripAgain
} from '$lib/api/jobs';
import { fetchSessions } from '$lib/api/sessions';
import { fetchIdentity, clearEpisodeMatch } from '$lib/api/identity';
import { wsClient } from '$lib/api/ws';
import { ApiError } from '$lib/api/client';
import { ripProgress, type RipLiveProgress } from '$lib/stores/rips.svelte';
import * as authStore from '$lib/stores/auth';
import * as storesModule from '$app/stores';

const mockFetchJob = vi.mocked(fetchJob);
const mockPreview = vi.mocked(fetchNamingPreview);
const mockUpdateTrack = vi.mocked(updateTrack);
const mockResolve = vi.mocked(resolveJob);

const setRole = (authStore as unknown as { __setRole: (r: string | null) => void }).__setRole;
const setPageId = (storesModule as unknown as { __setPageId: (id: string | undefined) => void }).__setPageId;

const JOB = 'job_42';

function detailOf(job: Partial<JobView> = {}, tracks?: TrackView[], extra: Partial<JobDetailView> = {}): JobDetailView {
	return {
		job: createJob({ id: JOB, title: 'Test Movie', year: 2024, status: 'ripped', disc_type: 'bluray', ...job }),
		tracks: tracks ?? [createTrack({ id: 'trk_1', status: 'done' })],
		fingerprints: [],
		...extra
	};
}

function tvDetail(job: Partial<JobView> = {}, tracks?: TrackView[]): JobDetailView {
	return detailOf({ media_type: 'tv', has_series: true, ...job }, tracks);
}

function previewItem(trackId: string, outputName: string): NamingPreviewItem {
	return {
		track_id: trackId,
		track_number: 1,
		output_path: `Dir/${outputName}`,
		output_dir: 'Dir',
		output_name: outputName
	};
}

function previewOf(...items: NamingPreviewItem[]) {
	return { job_output_dir: 'Dir', job_output_name: 'Dir', items };
}

function loadJobPage(detail: JobDetailView = detailOf()) {
	mockFetchJob.mockResolvedValue(detail);
	return renderComponent(Page);
}

const heading = (name: string) => screen.findByRole('heading', { name });

function trackRows(): HTMLElement[] {
	return Array.from(document.querySelectorAll<HTMLElement>('table')[0].querySelectorAll('tbody tr.table-row'));
}

function cellOf(row: HTMLElement, label: string): HTMLElement {
	return row.querySelector(`[data-label="${label}"]`) as HTMLElement;
}

const text = (el: HTMLElement) => (el.textContent ?? '').replace(/\s+/g, ' ').trim();

// A held identify suggestion: the banner's "Use this title" resolves the job.
function heldDetail(): JobDetailView {
	return detailOf({
		status: 'awaiting_review',
		title: 'MY_DISC',
		metadata_json: {
			identity_suggestion: {
				provider: 'tmdb',
				title: 'Iron Man',
				year: 2008,
				kind: 'movie',
				poster_url: null,
				external_ids: {},
				overview: null,
				payload: {},
				suggested_at: '2026-10-15T10:00:00Z'
			},
			flags: { unidentified: true }
		} as never
	});
}

beforeEach(() => {
	vi.resetAllMocks();
	mockFetchJob.mockResolvedValue(detailOf());
	mockPreview.mockResolvedValue(previewOf());
	mockUpdateTrack.mockResolvedValue(undefined as never);
	mockResolve.mockResolvedValue({ job: createJob({ id: JOB }), fan_out: [] } as never);
	vi.mocked(acceptIdentitySuggestion).mockResolvedValue({ job: createJob({ id: JOB }), fan_out: [] } as never);
	vi.mocked(fetchSessions).mockResolvedValue([]);
	vi.mocked(wsClient.subscribe).mockImplementation(() => vi.fn());
});

afterEach(() => {
	cleanup();
	vi.useRealTimers();
	setRole('admin');
	setPageId(JOB);
	ripProgress.value = {};
});

describe('loading', () => {
	it('shows the skeleton on the first load and the detail once it arrives', async () => {
		let resolve!: (d: JobDetailView) => void;
		mockFetchJob.mockReturnValue(new Promise((r) => (resolve = r)));
		renderComponent(Page);
		expect(document.querySelector('.skeleton-card-lines')).not.toBeNull();
		expect(screen.queryByRole('heading', { name: 'Test Movie' })).not.toBeInTheDocument();
		resolve(detailOf());
		await heading('Test Movie');
		expect(document.querySelector('.skeleton-card-lines')).toBeNull();
	});

	it('swaps a poll refresh in place without showing the skeleton again', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		mockFetchJob.mockResolvedValueOnce(detailOf({ status: 'ripping' }));
		let resolve!: (d: JobDetailView) => void;
		mockFetchJob.mockReturnValueOnce(new Promise((r) => (resolve = r)));
		renderComponent(Page);
		await heading('Test Movie');
		await vi.advanceTimersByTimeAsync(5000);
		await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
		expect(screen.getByRole('heading', { name: 'Test Movie' })).toBeInTheDocument();
		expect(document.querySelector('.skeleton-card-lines')).toBeNull();
		resolve(detailOf({ status: 'ripping', title: 'Renamed' }));
		await heading('Renamed');
		expect(document.querySelector('.skeleton-card-lines')).toBeNull();
	});

	it('shows the message of an Error the load fails with', async () => {
		mockFetchJob.mockRejectedValue(new Error('boom'));
		renderComponent(Page);
		expect(await screen.findByText('Failed to load: boom')).toBeInTheDocument();
		expect(mockGoto).not.toHaveBeenCalled();
	});

	it('shows a generic message when the load fails with something that is not an Error', async () => {
		mockFetchJob.mockRejectedValue('nope');
		renderComponent(Page);
		expect(await screen.findByText('Failed to load: Failed to load job')).toBeInTheDocument();
	});

	it('redirects home for any Error whose message mentions 404', async () => {
		mockFetchJob.mockRejectedValue(new Error('Request for job failed (404)'));
		renderComponent(Page);
		await waitFor(() => expect(mockGoto).toHaveBeenCalledWith('/'));
	});

	it('does not redirect for a 404 that is not an Error object', async () => {
		mockFetchJob.mockRejectedValue('404 Not Found');
		renderComponent(Page);
		expect(await screen.findByText('Failed to load: Failed to load job')).toBeInTheDocument();
		expect(mockGoto).not.toHaveBeenCalled();
	});
});

describe('naming preview', () => {
	it('shows the previewed output name against its track', async () => {
		mockPreview.mockResolvedValue(previewOf(previewItem('trk_1', 'Test Movie (2024).mkv')));
		loadJobPage();
		await screen.findByText('Tracks (1)');
		const cell = cellOf(trackRows()[0], 'Filename');
		expect(text(cell)).toBe('Test Movie (2024).mkv');
		expect(cell).toHaveAttribute('title', 'Test Movie (2024).mkv');
	});

	it('a 409 marks the job unrouted: the next five polls skip the preview and the sixth asks again', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		mockFetchJob.mockResolvedValue(detailOf({ status: 'ripping' }));
		mockPreview.mockRejectedValue(new ApiError(409, 'job has no output template', null));
		renderComponent(Page);
		await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(1));
		await vi.advanceTimersByTimeAsync(25_000);
		expect(mockFetchJob).toHaveBeenCalledTimes(6);
		expect(mockPreview).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(5_000);
		expect(mockFetchJob).toHaveBeenCalledTimes(7);
		expect(mockPreview).toHaveBeenCalledTimes(2);
	});

	it('another failure clears the items and the next poll asks again', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		mockFetchJob.mockResolvedValue(detailOf({ status: 'ripping' }));
		mockPreview.mockResolvedValueOnce(previewOf(previewItem('trk_1', 'Named.mkv')));
		mockPreview.mockRejectedValue(new Error('preview blip'));
		renderComponent(Page);
		await screen.findByText('Named.mkv');
		await vi.advanceTimersByTimeAsync(5_000);
		await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));
		await waitFor(() => expect(screen.queryByText('Named.mkv')).not.toBeInTheDocument());
		expect(text(cellOf(trackRows()[0], 'Filename'))).toBe('-');
		await vi.advanceTimersByTimeAsync(5_000);
		expect(mockPreview).toHaveBeenCalledTimes(3);
	});

	it('an explicit reload asks even while the job is marked unrouted', async () => {
		mockPreview.mockRejectedValue(new ApiError(409, 'job has no output template', null));
		loadJobPage();
		await screen.findByText('Tracks (1)');
		expect(mockPreview).toHaveBeenCalledTimes(1);
		await fireEvent.click(screen.getByRole('checkbox'));
		await waitFor(() => expect(mockPreview).toHaveBeenCalledTimes(2));
	});
});

describe('header', () => {
	it('shows the year and the status badge', async () => {
		loadJobPage();
		expect(await screen.findByText('(2024)')).toBeInTheDocument();
		expect(document.querySelector('.job-detail-title-bar .status-badge')).toHaveTextContent('Ripped');
	});

	it('omits the year when the job has none', async () => {
		loadJobPage(detailOf({ year: null }));
		await heading('Test Movie');
		expect(document.querySelector('.job-detail-year')).toBeNull();
	});

	it('links the IMDb badge in the title bar for a video disc but not for a CD', async () => {
		const md = { identity: { external_ids: { imdb: 'tt1234567' } } };
		loadJobPage(detailOf({ metadata_json: md as never }));
		await heading('Test Movie');
		const badge = document.querySelector('.job-detail-imdb-badge') as HTMLAnchorElement;
		expect(badge).toHaveAttribute('href', 'https://www.imdb.com/title/tt1234567');
		expect(badge).toHaveAttribute('target', '_blank');
		cleanup();
		loadJobPage(detailOf({ disc_type: 'cd', metadata_json: md as never }));
		await heading('Test Movie');
		expect(document.querySelector('.job-detail-imdb-badge')).toBeNull();
	});

	it('shows the Multi-Title badge', async () => {
		loadJobPage(detailOf({ metadata_json: { provider_raw: { arm_server: { multi_title: true } } } as never }));
		expect(await screen.findByText('Multi-Title')).toBeInTheDocument();
	});

	it.each([
		['iso', 'ISO', 'Folder'],
		['folder', 'Folder', 'ISO']
	])('shows the %s source badge and not the other one', async (sourceType, shown, hidden) => {
		loadJobPage(detailOf({ metadata_json: { provider_raw: { arm_server: { source_type: sourceType } } } as never }));
		expect(await screen.findByText(shown, { selector: '.job-detail-source-badge' })).toBeInTheDocument();
		expect(screen.queryByText(hidden, { selector: '.job-detail-source-badge' })).not.toBeInTheDocument();
	});

	it('shows no source badge for any other source type', async () => {
		loadJobPage(detailOf({ metadata_json: { provider_raw: { arm_server: { source_type: 'disc' } } } as never }));
		await heading('Test Movie');
		expect(document.querySelector('.job-detail-source-badge')).toBeNull();
	});

	it('shows an admin the Movie | TV switch, Apply session and the job actions', async () => {
		loadJobPage();
		expect(await screen.findByRole('radiogroup', { name: 'Media type' })).toBeInTheDocument();
		expect(screen.getByTestId('apply-open')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
		expect(screen.queryByTestId('media-type-text')).not.toBeInTheDocument();
	});

	it('shows a non-admin the type as text and none of the write controls', async () => {
		setRole('guest');
		loadJobPage();
		expect(await screen.findByTestId('media-type-text')).toHaveTextContent('Movie');
		expect(screen.queryByRole('radiogroup', { name: 'Media type' })).not.toBeInTheDocument();
		expect(screen.queryByTestId('apply-open')).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Edit Title' })).not.toBeInTheDocument();
	});

	it('does not show the media type text for a CD', async () => {
		setRole('guest');
		loadJobPage(detailOf({ disc_type: 'cd' }));
		await heading('Test Movie');
		expect(screen.queryByTestId('media-type-text')).not.toBeInTheDocument();
	});

	it('labels the dialog button Edit identity on a CD that already has an identity', async () => {
		loadJobPage(detailOf({ disc_type: 'cd' }));
		expect(await screen.findByTestId('identify-open')).toHaveTextContent('Edit identity');
	});

	it('labels the dialog button Identify disc while the disc awaits an identity', async () => {
		loadJobPage(detailOf({ status: 'awaiting_user_id' }));
		expect(await screen.findByTestId('identify-open')).toHaveTextContent('Identify disc');
	});

	it('hides Apply session and Identify when the job cannot be applied or resolved', async () => {
		loadJobPage(detailOf({ status: 'ripping' }));
		await heading('Test Movie');
		expect(screen.queryByTestId('apply-open')).not.toBeInTheDocument();
		expect(screen.queryByTestId('identify-open')).not.toBeInTheDocument();
	});

	it('does not show the identity suggestion banner without a held suggestion', async () => {
		loadJobPage();
		await heading('Test Movie');
		expect(screen.queryByTestId('identity-suggestion')).not.toBeInTheDocument();
	});

	it('shows the identity suggestion banner in the header', async () => {
		loadJobPage(heldDetail());
		const banner = await screen.findByTestId('identity-suggestion');
		expect(banner.closest('.job-detail-header-card')).not.toBeNull();
		expect(screen.getByText('Iron Man (2008)')).toBeInTheDocument();
	});

	it('shows Untitled for a job with no title', async () => {
		loadJobPage(detailOf({ title: null }));
		expect(await screen.findByRole('heading', { name: 'Untitled' })).toBeInTheDocument();
		expect(document.querySelector('.job-detail-breadcrumb-current')).toHaveTextContent('Untitled');
	});

	it('opens the identify dialog from the banner and closes it from the backdrop', async () => {
		loadJobPage(heldDetail());
		await fireEvent.click(await screen.findByRole('button', { name: 'Search instead' }));
		expect(await screen.findByRole('dialog')).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }));
		await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
	});

	it('closes the apply session dialog from its backdrop', async () => {
		loadJobPage();
		await fireEvent.click(await screen.findByTestId('apply-open'));
		await screen.findByTestId('apply-session-select');
		await fireEvent.click(screen.getByRole('button', { name: 'Close dialog' }));
		await waitFor(() => expect(screen.queryByTestId('apply-session-select')).not.toBeInTheDocument());
	});
});

describe('job actions', () => {
	it('Delete sends the user home', async () => {
		vi.spyOn(window, 'confirm').mockReturnValue(true);
		vi.mocked(deleteJob).mockResolvedValue(undefined as never);
		loadJobPage();
		await fireEvent.click(await screen.findByRole('button', { name: 'Delete' }));
		await waitFor(() => expect(mockGoto).toHaveBeenCalledWith('/'));
		expect(deleteJob).toHaveBeenCalledWith(JOB);
	});

	it('Rip again reloads the job', async () => {
		vi.mocked(ripAgain).mockResolvedValue({ started_job_id: null } as never);
		loadJobPage();
		await fireEvent.click(await screen.findByRole('button', { name: 'Rip again' }));
		await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
	});
});

describe('metadata grid', () => {
	it('renders an external id as a link and the other facts as plain values', async () => {
		loadJobPage(detailOf({ metadata_json: { identity: { external_ids: { tmdb: '603' } } } as never }));
		await heading('Test Movie');
		const link = screen.getByRole('link', { name: '603' });
		expect(link).toHaveAttribute('href', 'https://www.themoviedb.org/movie/603');
		expect(link).toHaveAttribute('target', '_blank');
		const cells = Array.from(document.querySelectorAll('.job-detail-metadata-cell'));
		const discType = cells.find((c) => c.textContent?.includes('Disc Type'))!;
		expect(discType).toHaveTextContent('Blu-ray');
		expect(discType.querySelector('a')).toBeNull();
	});

	it('titles a monospaced plain value with itself', async () => {
		loadJobPage();
		await heading('Test Movie');
		const mono = document.querySelector('.job-detail-metadata-cell .truncate') as HTMLElement;
		expect(mono).not.toBeNull();
		expect(mono.getAttribute('title')).toBe(text(mono));
	});

	it('pads the last row with empty cells', async () => {
		loadJobPage();
		await heading('Test Movie');
		const cells = Array.from(document.querySelectorAll('.job-detail-metadata-cell'));
		expect(cells.length % 4).toBe(0);
		expect(cells.some((c) => c.querySelector('.job-detail-metadata-label') === null)).toBe(true);
	});

	it('edits Year, Season, Disc # and Disc total in place for an admin, as number inputs', async () => {
		loadJobPage(tvDetail());
		await heading('Test Movie');
		for (const label of ['Year', 'Season', 'Disc #', 'Disc total']) {
			await fireEvent.click(screen.getByRole('button', { name: `Edit ${label}` }));
			expect(screen.getByLabelText(label)).toHaveAttribute('type', 'number');
			await fireEvent.keyDown(screen.getByLabelText(label), { key: 'Escape' });
		}
		await fireEvent.click(screen.getByRole('button', { name: 'Edit Title' }));
		expect(screen.getByLabelText('Title')).toHaveAttribute('type', 'text');
	});

	it('shows the editable facts as plain text to a non-admin', async () => {
		setRole('guest');
		loadJobPage(tvDetail());
		await heading('Test Movie');
		expect(screen.queryByRole('button', { name: 'Edit Year' })).not.toBeInTheDocument();
		expect(within(screen.getByTestId('fact-year')).getByText('2024')).toBeInTheDocument();
	});

	it('does not let a job that cannot be resolved edit its facts', async () => {
		loadJobPage(detailOf({ status: 'ripping' }));
		await heading('Test Movie');
		expect(screen.queryByRole('button', { name: 'Edit Year' })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Edit Title' })).not.toBeInTheDocument();
	});

	describe('saving a fact', () => {
		async function typeAndEnter(label: string, value: string) {
			await fireEvent.click(screen.getByRole('button', { name: `Edit ${label}` }));
			const input = screen.getByLabelText(label);
			await fireEvent.input(input, { target: { value } });
			await fireEvent.keyDown(input, { key: 'Enter' });
		}

		it('requires a title and does not call resolve without one', async () => {
			loadJobPage();
			await heading('Test Movie');
			await typeAndEnter('Title', '   ');
			expect(await screen.findByText('A title is required')).toBeInTheDocument();
			expect(mockResolve).not.toHaveBeenCalled();
		});

		it('restates the identity when the title changes, trimming it and keeping the year', async () => {
			loadJobPage();
			await heading('Test Movie');
			await typeAndEnter('Title', '  Renamed  ');
			await waitFor(() => expect(mockResolve).toHaveBeenCalledWith(JOB, { title: 'Renamed', year: 2024 }));
			await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
		});

		it('restates the identity when the year changes, keeping the title', async () => {
			loadJobPage();
			await heading('Test Movie');
			await typeAndEnter('Year', '2020');
			await waitFor(() => expect(mockResolve).toHaveBeenCalledWith(JOB, { title: 'Test Movie', year: 2020 }));
		});

		it('clears the year when it is blanked', async () => {
			loadJobPage();
			await heading('Test Movie');
			await typeAndEnter('Year', '');
			await waitFor(() => expect(mockResolve).toHaveBeenCalledWith(JOB, { title: 'Test Movie', year: null }));
		});

		it('sends an empty title and a null year for a job that has neither', async () => {
			loadJobPage(tvDetail({ title: null, year: null }));
			await heading('Untitled');
			await typeAndEnter('Disc total', '2');
			await waitFor(() => expect(mockResolve).toHaveBeenCalledWith(JOB, { title: '', year: null, disc_total: 2 }));
		});

		it('clears a classification when a number is blanked', async () => {
			loadJobPage(tvDetail({ season: 2 }));
			await heading('Test Movie');
			await typeAndEnter('Season', '');
			await waitFor(() =>
				expect(mockResolve).toHaveBeenCalledWith(JOB, { title: 'Test Movie', year: 2024, season: null })
			);
		});

		it('starts the episode match when a TV season changes', async () => {
			mockResolve.mockResolvedValue({ job: createJob({ id: JOB, media_type: 'tv', season: 3 }) } as never);
			loadJobPage(tvDetail());
			await fireEvent.click(await screen.findByRole('button', { name: 'Match Episodes' }));
			await typeAndEnter('Season', '3');
			await waitFor(() =>
				expect(mockResolve).toHaveBeenCalledWith(JOB, { title: 'Test Movie', year: 2024, season: 3 })
			);
			expect(await screen.findByText('Matching episodes...')).toBeInTheDocument();
		});

		it('starts the episode match when a TV disc number changes', async () => {
			mockResolve.mockResolvedValue({ job: createJob({ id: JOB, media_type: 'tv', disc_number: 2 }) } as never);
			loadJobPage(tvDetail());
			await fireEvent.click(await screen.findByRole('button', { name: 'Match Episodes' }));
			await typeAndEnter('Disc #', '2');
			expect(await screen.findByText('Matching episodes...')).toBeInTheDocument();
		});

		it('does not start the episode match when a TV season stays the same', async () => {
			mockResolve.mockResolvedValue({ job: createJob({ id: JOB, media_type: 'tv', season: 2 }) } as never);
			loadJobPage(tvDetail({ season: 2 }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Match Episodes' }));
			await typeAndEnter('Year', '2020');
			await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
			expect(screen.queryByText('Matching episodes...')).not.toBeInTheDocument();
		});

		it('does not start the episode match when the response carries no job', async () => {
			mockResolve.mockResolvedValue(undefined as never);
			loadJobPage(tvDetail());
			await fireEvent.click(await screen.findByRole('button', { name: 'Match Episodes' }));
			await typeAndEnter('Season', '3');
			await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
			expect(screen.queryByText('Matching episodes...')).not.toBeInTheDocument();
		});

		it('does not start the episode match for a movie, even if the season moved', async () => {
			mockResolve.mockResolvedValue({ job: createJob({ id: JOB, media_type: 'movie', season: 5 }) } as never);
			mockFetchJob.mockResolvedValueOnce(detailOf());
			mockFetchJob.mockResolvedValue(tvDetail());
			renderComponent(Page);
			await heading('Test Movie');
			await typeAndEnter('Year', '2020');
			await fireEvent.click(await screen.findByRole('button', { name: 'Match Episodes' }));
			expect(screen.queryByText('Matching episodes...')).not.toBeInTheDocument();
		});
	});
});

describe('panels', () => {
	it('toggles the title search from its tab', async () => {
		loadJobPage();
		const tab = await screen.findByRole('button', { name: /Poster & metadata search/ });
		expect(tab).toHaveAttribute('aria-pressed', 'false');
		await fireEvent.click(tab);
		expect(tab).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
		await fireEvent.click(tab);
		expect(tab).toHaveAttribute('aria-pressed', 'false');
		expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
	});

	it('opens the title search on the movie sources for a movie job', async () => {
		loadJobPage();
		await fireEvent.click(await screen.findByRole('button', { name: /Poster & metadata search/ }));
		const select = screen.getByRole('combobox', { name: 'Search with' }) as HTMLSelectElement;
		expect(Array.from(select.options).map((o) => o.value)).toEqual(['tmdb', 'omdb']);
	});

	it('toggles the episode panel and the title search independently of each other', async () => {
		loadJobPage(tvDetail());
		const episodes = await screen.findByRole('button', { name: 'Match Episodes' });
		await fireEvent.click(episodes);
		expect(episodes).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByRole('region', { name: 'Match episodes' })).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /Poster & metadata search/ }));
		expect(episodes).toHaveAttribute('aria-pressed', 'false');
		expect(screen.queryByRole('region', { name: 'Match episodes' })).not.toBeInTheDocument();
		await fireEvent.click(screen.getByRole('button', { name: /Poster & metadata search/ }));
		await fireEvent.click(episodes);
		await fireEvent.click(episodes);
		expect(screen.queryByRole('region', { name: 'Match episodes' })).not.toBeInTheDocument();
	});

	it('opens the title search on the TV sources when the episode panel asks to search for the series', async () => {
		loadJobPage(detailOf({ media_type: 'tv', has_series: false }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Match Episodes' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Search for the series' }));
		const select = screen.getByRole('combobox', { name: 'Search with' }) as HTMLSelectElement;
		expect(Array.from(select.options).map((o) => o.value)).toEqual(['tmdb', 'omdb', 'tvmaze', 'tvdb']);
		expect(screen.getByRole('button', { name: /Poster & metadata search/ })).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByRole('button', { name: 'Match Episodes' })).toHaveAttribute('aria-pressed', 'false');
	});

	it('reloads the job when the episode panel reports a change', async () => {
		vi.mocked(fetchIdentity).mockResolvedValue({
			sources: { episodes_tmdb: { status: 'ok' } },
			pin: {},
			tracks: [
				{
					track_id: 'trk_1',
					source_ref: 't00.mkv',
					role: 'episode',
					season: 1,
					episode_number: 1,
					episode_name: 'Ep 1',
					identity_provenance: { episode_number: 'episodes_tmdb' },
					proposals: { episodes_tmdb: { episode: 1, confidence: 0.9 } }
				}
			]
		} as never);
		vi.mocked(clearEpisodeMatch).mockResolvedValue({ sources: {}, pin: {}, tracks: [] });
		loadJobPage(tvDetail());
		await fireEvent.click(await screen.findByRole('button', { name: 'Match Episodes' }));
		await fireEvent.click(await screen.findByRole('button', { name: 'Clear episodes' }));
		await waitFor(() => expect(clearEpisodeMatch).toHaveBeenCalledWith(JOB));
		await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
	});

	it('shows the Match CD tab and toggles the music search for a CD', async () => {
		loadJobPage(detailOf({ disc_type: 'cd' }));
		const tab = await screen.findByRole('button', { name: 'Match CD' });
		await fireEvent.click(tab);
		expect(tab).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByPlaceholderText('Album or title...')).toBeInTheDocument();
		await fireEvent.click(tab);
		expect(screen.queryByPlaceholderText('Album or title...')).not.toBeInTheDocument();
	});

	it('shows no panel tabs for a data disc', async () => {
		loadJobPage(detailOf({ disc_type: 'data' }));
		await heading('Test Movie');
		expect(screen.queryByRole('button', { name: /Poster & metadata search/ })).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Match CD' })).not.toBeInTheDocument();
	});

	describe('applying', () => {
		const matrix = { title: 'The Matrix', year: 1999, kind: 'movie', poster_url: null, provider_id: 'tt0133093' };

		async function searchAndUse() {
			await fireEvent.click(await screen.findByRole('button', { name: /Poster & metadata search/ }));
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await screen.findByRole('heading', { name: 'The Matrix' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
		}

		it('a movie match from the title search closes the panel and reloads the job', async () => {
			vi.mocked(searchMetadata).mockResolvedValue({ candidates: [matrix] });
			vi.mocked(updateJobTitle).mockResolvedValue(undefined as never);
			loadJobPage();
			await searchAndUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			await waitFor(() =>
				expect(screen.getByRole('button', { name: /Poster & metadata search/ })).toHaveAttribute(
					'aria-pressed',
					'false'
				)
			);
			await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
		});

		it('a series match opens the episode panel, starts matching and reloads the job', async () => {
			vi.mocked(searchMetadata).mockResolvedValue({ candidates: [{ ...matrix, title: 'The Matrix', kind: 'tv' }] });
			vi.mocked(updateJobTitle).mockResolvedValue(undefined as never);
			mockFetchJob.mockResolvedValueOnce(detailOf());
			mockFetchJob.mockResolvedValue(tvDetail());
			renderComponent(Page);
			await searchAndUse();
			await waitFor(() =>
				expect(screen.getByRole('button', { name: 'Match Episodes' })).toHaveAttribute('aria-pressed', 'true')
			);
			expect(await screen.findByText('Matching episodes...')).toBeInTheDocument();
			expect(mockFetchJob).toHaveBeenCalledTimes(2);
		});

		it('a CD match from the music search closes the panel and reloads the job', async () => {
			vi.mocked(searchMusicMetadata).mockResolvedValue({
				candidates: [{ title: 'Wall Remaster', year: 1979, kind: 'music', poster_url: null, provider_id: 'rel-1' }]
			});
			vi.mocked(fetchMusicDetail).mockResolvedValue({
				release_id: 'rel-1',
				title: 'The Wall',
				artist: 'Pink Floyd',
				year: 1979,
				poster_url: null,
				disc_count: 1,
				track_count: 1,
				tracks: [{ position: 1, title: 'In the Flesh?', length_ms: 213000, disc_number: 1 }]
			} as never);
			loadJobPage(detailOf({ disc_type: 'cd', title: 'The Wall' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Match CD' }));
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByText('Wall Remaster'));
			await screen.findByText('In the Flesh?');
			await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			await waitFor(() => expect(screen.queryByPlaceholderText('Album or title...')).not.toBeInTheDocument());
			expect(screen.getByRole('button', { name: 'Match CD' })).toHaveAttribute('aria-pressed', 'false');
			await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
		});
	});

	describe('media type switch', () => {
		it('switching to TV starts matching and opens the episode panel', async () => {
			vi.mocked(setJobMediaType).mockResolvedValue(createJob({ id: JOB, media_type: 'tv' }));
			mockFetchJob.mockResolvedValueOnce(detailOf());
			mockFetchJob.mockResolvedValue(tvDetail());
			renderComponent(Page);
			await fireEvent.click(await screen.findByRole('radio', { name: 'TV' }));
			await waitFor(() =>
				expect(screen.getByRole('button', { name: 'Match Episodes' })).toHaveAttribute('aria-pressed', 'true')
			);
			expect(await screen.findByText('Matching episodes...')).toBeInTheDocument();
		});

		it('switching to Movie stops matching, closes the panels and reloads the job', async () => {
			vi.mocked(setJobMediaType).mockResolvedValue(createJob({ id: JOB, media_type: 'movie' }));
			mockFetchJob.mockResolvedValueOnce(tvDetail());
			mockFetchJob.mockResolvedValue(detailOf());
			renderComponent(Page);
			await fireEvent.click(await screen.findByRole('button', { name: 'Match Episodes' }));
			await fireEvent.click(await screen.findByRole('radio', { name: 'Movie' }));
			await waitFor(() => expect(screen.queryByRole('button', { name: 'Match Episodes' })).not.toBeInTheDocument());
			expect(screen.queryByRole('region', { name: 'Match episodes' })).not.toBeInTheDocument();
			expect(mockFetchJob).toHaveBeenCalledTimes(2);
		});
	});
});

describe('action note', () => {
	const session: SessionView = {
		id: 'ses_1',
		name: 'My Plex',
		media_type: 'movie',
		is_builtin: false,
		rip_preset_id: 'rpr_1',
		transcode_preset_id: null,
		output_path_template: '{title}/{title}.mkv',
		overrides_json: null,
		created_by_user_id: null,
		created_at: null,
		updated_at: null
	};

	async function applyVia(resp: ApplySessionResponse) {
		vi.mocked(fetchSessions).mockResolvedValue([session]);
		vi.mocked(applySession).mockResolvedValue(resp);
		await fireEvent.click(await screen.findByTestId('apply-open'));
		const select = await screen.findByTestId('apply-session-select');
		await waitFor(() => expect(select.querySelector('option[value="ses_1"]')).not.toBeNull());
		await fireEvent.change(select, { target: { value: 'ses_1' } });
		await waitFor(() => expect(screen.getByTestId('apply-session-apply')).not.toBeDisabled());
		await fireEvent.click(screen.getByTestId('apply-session-apply'));
	}

	const accept = async () => fireEvent.click(await screen.findByRole('button', { name: 'Use this title' }));
	const resumed = (n: number) =>
		vi.mocked(acceptIdentitySuggestion).mockResolvedValueOnce({
			job: createJob({ id: JOB }),
			fan_out: Array.from({ length: n }, () => ({}))
		} as never);

	it('says one session resumed after identify', async () => {
		resumed(1);
		loadJobPage(heldDetail());
		await accept();
		expect(await screen.findByTestId('action-note')).toHaveTextContent('1 session resumed');
		expect(screen.getByTestId('action-note').textContent).not.toContain('sessions');
	});

	it('says several sessions resumed after identify', async () => {
		resumed(3);
		loadJobPage(heldDetail());
		await accept();
		expect(await screen.findByTestId('action-note')).toHaveTextContent('3 sessions resumed');
	});

	it('shows no note after identify when no session resumed', async () => {
		resumed(0);
		loadJobPage(heldDetail());
		await accept();
		await waitFor(() => expect(acceptIdentitySuggestion).toHaveBeenCalled());
		await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
		expect(screen.queryByTestId('action-note')).not.toBeInTheDocument();
	});

	it('shows no note after identify when the response has no fan_out', async () => {
		vi.mocked(acceptIdentitySuggestion).mockResolvedValueOnce({ job: createJob({ id: JOB }) } as never);
		loadJobPage(heldDetail());
		await accept();
		await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
		expect(screen.queryByTestId('action-note')).not.toBeInTheDocument();
	});

	it('says a pre-rip apply is parked until the rip finishes', async () => {
		loadJobPage(detailOf({ status: 'awaiting_review' }));
		await applyVia({
			session_application: { status: 'waiting_identify' },
			tasks: []
		} as unknown as ApplySessionResponse);
		expect(await screen.findByTestId('action-note')).toHaveTextContent('Session parked; applies when the rip finishes');
		expect(screen.queryByTestId('apply-session-select')).not.toBeInTheDocument();
	});

	it('says a post-rip apply is parked and waiting', async () => {
		loadJobPage(detailOf({ status: 'ripped_awaiting_identify' }));
		await applyVia({
			session_application: { status: 'waiting_identify' },
			tasks: []
		} as unknown as ApplySessionResponse);
		expect(await screen.findByTestId('action-note')).toHaveTextContent('Session parked; waiting');
	});

	it('says one transcode task was queued', async () => {
		loadJobPage();
		await applyVia({
			session_application: { status: 'queued' },
			tasks: [{ id: 'tsk_1' }]
		} as unknown as ApplySessionResponse);
		const note = await screen.findByTestId('action-note');
		expect(note).toHaveTextContent('1 transcode task queued');
		expect(note.textContent).not.toContain('tasks');
	});

	it('says several transcode tasks were queued', async () => {
		loadJobPage();
		await applyVia({
			session_application: { status: 'queued' },
			tasks: [{ id: 'tsk_1' }, { id: 'tsk_2' }]
		} as unknown as ApplySessionResponse);
		expect(await screen.findByTestId('action-note')).toHaveTextContent('2 transcode tasks queued');
	});

	it('says no tasks were queued when the response lists none', async () => {
		loadJobPage();
		await applyVia({ session_application: { status: 'queued' } } as unknown as ApplySessionResponse);
		expect(await screen.findByTestId('action-note')).toHaveTextContent('0 transcode tasks queued');
	});

	it('says tasks were queued when the response has no session application', async () => {
		loadJobPage();
		await applyVia({ tasks: [{ id: 'tsk_1' }] } as unknown as ApplySessionResponse);
		expect(await screen.findByTestId('action-note')).toHaveTextContent('1 transcode task queued');
	});

	describe('timer', () => {
		it('clears the note after 6 seconds', async () => {
			vi.useFakeTimers({ shouldAdvanceTime: true });
			resumed(2);
			loadJobPage(heldDetail());
			await accept();
			expect(await screen.findByTestId('action-note')).toBeInTheDocument();
			await vi.advanceTimersByTimeAsync(5900);
			expect(screen.getByTestId('action-note')).toBeInTheDocument();
			await vi.advanceTimersByTimeAsync(200);
			await waitFor(() => expect(screen.queryByTestId('action-note')).not.toBeInTheDocument());
		});

		it('restarts the 6 second timer when a second note replaces the first', async () => {
			vi.useFakeTimers({ shouldAdvanceTime: true });
			resumed(2);
			resumed(1);
			loadJobPage(heldDetail());
			await accept();
			expect(await screen.findByTestId('action-note')).toHaveTextContent('2 sessions resumed');
			await vi.advanceTimersByTimeAsync(4000);
			await accept();
			await waitFor(() => expect(screen.getByTestId('action-note')).toHaveTextContent('1 session resumed'));
			// 6.5s after the first note, 2.5s after the second: still shown.
			await vi.advanceTimersByTimeAsync(2500);
			expect(screen.getByTestId('action-note')).toBeInTheDocument();
			await vi.advanceTimersByTimeAsync(3700);
			await waitFor(() => expect(screen.queryByTestId('action-note')).not.toBeInTheDocument());
		});
	});
});

describe('rip progress', () => {
	const live = (over: Partial<RipLiveProgress> = {}): RipLiveProgress => ({
		track_id: 'trk_1',
		progress_pct: 42,
		eta_seconds: null,
		bytes_done: null,
		bytes_total: null,
		rate_bps: null,
		phase: null,
		...over
	});
	const ripping = () => detailOf({ status: 'ripping' });
	const subscribedTopics = () => vi.mocked(wsClient.subscribe).mock.calls.map(([topic]) => topic);

	it('waits for the first progress report while ripping, and subscribes to this job', async () => {
		loadJobPage(ripping());
		const section = await screen.findByTestId('job-rip-progress');
		expect(within(section).getByRole('heading', { name: 'Ripping' })).toBeInTheDocument();
		expect(within(section).getByText('Waiting for the first progress report from the ripper.')).toBeInTheDocument();
		expect(subscribedTopics()).toContain(`ripper.progress.${JOB}`);
	});

	it('shows the progress without an ETA or a transfer line when neither was reported', async () => {
		loadJobPage(ripping());
		const section = await screen.findByTestId('job-rip-progress');
		ripProgress.value = { [JOB]: live() };
		expect(await within(section).findByText('42%')).toBeInTheDocument();
		expect(within(section).queryByText(/left$/)).not.toBeInTheDocument();
		expect(section.querySelector('.mono')).toBeNull();
		expect(
			within(section).queryByText('Waiting for the first progress report from the ripper.')
		).not.toBeInTheDocument();
	});

	it('shows the ETA and the byte transfer with its rate', async () => {
		loadJobPage(ripping());
		const section = await screen.findByTestId('job-rip-progress');
		ripProgress.value = {
			[JOB]: live({ eta_seconds: 600, bytes_done: 1_000_000_000, bytes_total: 2_000_000_000, rate_bps: 50_000_000 })
		};
		expect(await within(section).findByText('10m left')).toBeInTheDocument();
		const transfer = section.querySelector('.mono') as HTMLElement;
		expect(text(transfer)).toMatch(/ of .* · .*\/s$/);
	});

	it('shows the byte transfer without a rate when none was reported', async () => {
		loadJobPage(ripping());
		const section = await screen.findByTestId('job-rip-progress');
		ripProgress.value = { [JOB]: live({ bytes_done: 1_000_000_000 }) };
		await waitFor(() => expect(section.querySelector('.mono')).not.toBeNull());
		expect(text(section.querySelector('.mono') as HTMLElement)).not.toContain('/s');
	});

	it('says the files are being verified once the rip is done copying', async () => {
		loadJobPage(ripping());
		const section = await screen.findByTestId('job-rip-progress');
		ripProgress.value = { [JOB]: live({ phase: 'verifying' }) };
		expect(await within(section).findByRole('heading', { name: 'Verifying ripped files' })).toBeInTheDocument();
	});

	it('shows no rip section and does not subscribe when the job is not ripping', async () => {
		loadJobPage();
		await heading('Test Movie');
		expect(screen.queryByTestId('job-rip-progress')).not.toBeInTheDocument();
		expect(subscribedTopics()).not.toContain(`ripper.progress.${JOB}`);
	});

	it('unsubscribes once the job stops ripping', async () => {
		vi.useFakeTimers({ shouldAdvanceTime: true });
		const unsubscribe = vi.fn();
		vi.mocked(wsClient.subscribe).mockImplementation(() => unsubscribe);
		mockFetchJob.mockResolvedValueOnce(ripping());
		mockFetchJob.mockResolvedValue(detailOf());
		renderComponent(Page);
		await screen.findByTestId('job-rip-progress');
		await vi.advanceTimersByTimeAsync(5000);
		await waitFor(() => expect(screen.queryByTestId('job-rip-progress')).not.toBeInTheDocument());
		expect(unsubscribe).toHaveBeenCalled();
	});
});

describe('tracks table', () => {
	const series = () => [
		createTrack({
			id: 'trk_1',
			index: 1,
			kind: 'video_title',
			title: 'Pilot',
			year: 2008,
			imdb_id: 'tt0959621',
			edition: 'Extended',
			role: 'episode',
			poster_url: 'https://example.test/p.jpg',
			episode_number: 1,
			episode_name: 'First',
			duration_seconds: 2750,
			size_bytes: 1_000_000_000,
			status: 'done',
			attempts: 2,
			custom_filename: 'my-pilot',
			transcode_status: 'in_progress',
			transcode_fps: 12.5,
			transcode_avg_fps: 10
		}),
		createTrack({
			id: 'trk_2',
			index: 2,
			title: null,
			episode_number: 2,
			episode_name: null,
			duration_seconds: null,
			expected_duration_seconds: 600,
			excluded: true,
			status: 'failed',
			last_error: 'MakeMKV exited 1',
			attempts: 1
		}),
		createTrack({
			id: 'trk_3',
			index: 3,
			title: null,
			episode_number: null,
			duration_seconds: null,
			expected_duration_seconds: null,
			role: 'episode',
			status: 'done'
		})
	];

	it('has the Episode column only when a track is part of a series', async () => {
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
		expect(headers.slice(0, 5)).toEqual(['#', 'Kind', 'Title', 'Episode', 'Filename']);
		cleanup();
		loadJobPage(detailOf({}, [createTrack({ id: 'trk_1', status: 'done' })]));
		await screen.findByText('Tracks (1)');
		expect(screen.queryByRole('columnheader', { name: 'Episode' })).not.toBeInTheDocument();
	});

	it('shows a titled track with its poster, year, IMDb link, edition and role', async () => {
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		const cell = cellOf(trackRows()[0], 'Title');
		expect(text(cell)).toContain('Pilot (2008)');
		expect(cell.querySelector('img[data-poster]')).not.toBeNull();
		expect(within(cell).getByRole('link', { name: 'IMDb' })).toHaveAttribute(
			'href',
			'https://www.imdb.com/title/tt0959621'
		);
		expect(within(cell).getByText('Extended')).toBeInTheDocument();
		expect(within(cell).getByText('episode')).toBeInTheDocument();
	});

	it('swaps a broken track poster for the placeholder', async () => {
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		const img = cellOf(trackRows()[0], 'Title').querySelector('img[data-poster]') as HTMLImageElement;
		await fireEvent.error(img);
		expect(img.src).toContain('poster-placeholder.svg');
	});

	it('shows an untitled track under the job title and year', async () => {
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		const cell = cellOf(trackRows()[1], 'Title');
		// The year follows the title with no space: pinned as rendered today.
		expect(text(cell)).toBe('Test Movie(2024)');
		expect(cell.querySelector('img')).toBeNull();
	});

	it('shows an untitled track under Untitled when the job has no title or year', async () => {
		loadJobPage(detailOf({ title: null, year: null }, [createTrack({ id: 'trk_1', status: 'done' })]));
		await screen.findByText('Tracks (1)');
		expect(text(cellOf(trackRows()[0], 'Title'))).toBe('Untitled');
	});

	it('shows a titled track without a poster, year, IMDb id, edition or role as just its title', async () => {
		loadJobPage(detailOf({}, [createTrack({ id: 'trk_1', status: 'done', title: 'Bare' })]));
		await screen.findByText('Tracks (1)');
		const cell = cellOf(trackRows()[0], 'Title');
		expect(text(cell)).toBe('Bare');
		expect(cell.querySelector('img')).toBeNull();
		expect(cell.querySelector('a')).toBeNull();
	});

	it('clicking a track IMDb link does not open the title search', async () => {
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		const link = within(cellOf(trackRows()[0], 'Title')).getByRole('link', { name: 'IMDb' });
		link.addEventListener('click', (e) => e.preventDefault());
		await fireEvent.click(link);
		expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
	});

	it('names the episode from the preview, else by number and name, else a dash', async () => {
		mockPreview.mockResolvedValue(previewOf(previewItem('trk_1', 'Show - S01E01.mkv')));
		const tracks = [...series(), createTrack({ id: 'trk_4', index: 4, episode_number: 4, episode_name: 'Fourth' })];
		loadJobPage(tvDetail({}, tracks));
		await screen.findByText('Tracks (4)');
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Episode'))).toBe('Show - S01E01.mkv');
		expect(text(cellOf(rows[1], 'Episode'))).toBe('2');
		expect(text(cellOf(rows[3], 'Episode'))).toBe('4 Fourth');
		expect(text(cellOf(rows[2], 'Episode'))).toBe('-');
	});

	it('shows the preview name with a custom badge, else excluded, else a dash, in Filename', async () => {
		mockPreview.mockResolvedValue(
			previewOf(previewItem('trk_1', 'Show - S01E01.mkv'), previewItem('trk_3', 'Show - S01E03.mkv'))
		);
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Filename'))).toBe('Show - S01E01.mkv custom');
		expect(text(cellOf(rows[2], 'Filename'))).toBe('Show - S01E03.mkv');
		expect(within(cellOf(rows[2], 'Filename')).queryByText('custom')).not.toBeInTheDocument();
		expect(text(cellOf(rows[1], 'Filename'))).toBe('excluded');
	});

	it('shows a dash in Filename for a track the preview does not name and that is included', async () => {
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		expect(text(cellOf(trackRows()[2], 'Filename'))).toBe('-');
	});

	it('shows the duration, else the expected duration with a tilde, else a dash', async () => {
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Length'))).toBe('45:50');
		expect(text(cellOf(rows[1], 'Length'))).toBe('~10:00');
		expect(text(cellOf(rows[2], 'Length'))).toBe('-');
	});

	it('pads the seconds of a duration to two digits', async () => {
		loadJobPage(detailOf({}, [createTrack({ id: 'trk_1', status: 'done', duration_seconds: 65 })]));
		await screen.findByText('Tracks (1)');
		expect(text(cellOf(trackRows()[0], 'Length'))).toBe('1:05');
	});

	it('shows rip status, with the attempt count only after a retry', async () => {
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Rip'))).toContain('x2');
		expect(text(cellOf(rows[1], 'Rip'))).not.toContain('x1');
		expect(text(cellOf(rows[1], 'Rip'))).toContain('Failed');
	});

	it('shows transcode status with the encoder fps only while in progress, else a dash', async () => {
		loadJobPage(tvDetail({}, series()));
		await screen.findByText('Tracks (3)');
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Transcode'))).toContain('12.5 fps (avg 10.0)');
		expect(text(cellOf(rows[1], 'Transcode'))).toBe('-');
	});

	it('shows transcode status without fps when the encoder has not reported a rate', async () => {
		loadJobPage(
			detailOf({}, [
				createTrack({ id: 'trk_1', status: 'done', transcode_status: 'in_progress', transcode_fps: null }),
				createTrack({ id: 'trk_2', index: 1, status: 'done', transcode_status: 'done', transcode_fps: 30 })
			])
		);
		await screen.findByText('Tracks (2)');
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Transcode'))).not.toContain('fps');
		expect(text(cellOf(rows[1], 'Transcode'))).not.toContain('fps');
	});

	it("shows a failed track's last error under its row, and nothing for other failures or errors", async () => {
		loadJobPage(
			tvDetail({}, [
				...series(),
				createTrack({ id: 'trk_4', index: 4, status: 'failed', last_error: null }),
				createTrack({ id: 'trk_5', index: 5, status: 'done', last_error: 'stale error' })
			])
		);
		await screen.findByText('Tracks (5)');
		expect(screen.getByText('MakeMKV exited 1')).toBeInTheDocument();
		expect(screen.getAllByText('Error:')).toHaveLength(1);
		expect(screen.queryByText('stale error')).not.toBeInTheDocument();
	});

	describe('the Include column', () => {
		it('lets an admin exclude a track and reloads the job', async () => {
			loadJobPage(tvDetail({}, series()));
			await screen.findByText('Tracks (3)');
			const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
			expect(boxes.map((b) => b.checked)).toEqual([true, false, true]);
			await fireEvent.click(boxes[0]);
			await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledWith(JOB, 'trk_1', { excluded: true }));
			await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
		});

		it('includes an excluded track again', async () => {
			loadJobPage(tvDetail({}, series()));
			await screen.findByText('Tracks (3)');
			await fireEvent.click(screen.getAllByRole('checkbox')[1]);
			await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledWith(JOB, 'trk_2', { excluded: false }));
		});

		// Pins today's behaviour: the failure escapes as an unhandled rejection
		// (#543). The test swaps in its own listener so vitest does not fail the
		// run on it, and puts vitest's back afterwards.
		it('reloads the job even when the update fails, and leaves the failure unhandled', async () => {
			const rejections: unknown[] = [];
			const previous = process.listeners('unhandledRejection');
			process.removeAllListeners('unhandledRejection');
			process.on('unhandledRejection', (r) => rejections.push(r));
			try {
				mockUpdateTrack.mockRejectedValue(new Error('update failed'));
				loadJobPage();
				await screen.findByText('Tracks (1)');
				await fireEvent.click(screen.getByRole('checkbox'));
				await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
				await waitFor(() => expect(rejections).toHaveLength(1));
				expect((rejections[0] as Error).message).toBe('update failed');
			} finally {
				process.removeAllListeners('unhandledRejection');
				previous.forEach((l) => process.on('unhandledRejection', l));
			}
		});

		it('shows a non-admin Included or Excluded as text', async () => {
			setRole('guest');
			loadJobPage(tvDetail({}, series()));
			await screen.findByText('Tracks (3)');
			expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
			const rows = trackRows();
			expect(text(cellOf(rows[0], 'Include'))).toBe('Included');
			expect(text(cellOf(rows[1], 'Include'))).toBe('Excluded');
		});
	});

	describe('per-track title search', () => {
		const picked = { title: 'Picked', year: 2001, kind: 'movie', poster_url: null, provider_id: 'tt3333' };

		it('opens under the row when an admin clicks the title cell and closes on the next click', async () => {
			loadJobPage();
			await screen.findByText('Tracks (1)');
			const cell = cellOf(trackRows()[0], 'Title');
			await fireEvent.click(cell);
			expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
			await fireEvent.click(cell);
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});

		it('moves from one track to another when a second title cell is clicked', async () => {
			loadJobPage(detailOf({}, [createTrack({ id: 'trk_1', status: 'done' }), createTrack({ id: 'trk_2', index: 1 })]));
			await screen.findByText('Tracks (2)');
			const rows = trackRows();
			await fireEvent.click(cellOf(rows[0], 'Title'));
			await fireEvent.click(cellOf(rows[1], 'Title'));
			expect(screen.getAllByRole('button', { name: 'Search' })).toHaveLength(1);
		});

		it('closes from its close button', async () => {
			loadJobPage();
			await screen.findByText('Tracks (1)');
			await fireEvent.click(cellOf(trackRows()[0], 'Title'));
			await fireEvent.click(screen.getByTitle('Close'));
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});

		it('applying a match closes it and reloads the job', async () => {
			vi.mocked(searchMetadata).mockResolvedValue({ candidates: [picked] });
			mockUpdateTrack.mockResolvedValue(undefined as never);
			loadJobPage();
			await screen.findByText('Tracks (1)');
			await fireEvent.click(cellOf(trackRows()[0], 'Title'));
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByText('Picked'));
			await fireEvent.click(await screen.findByRole('button', { name: 'Apply' }));
			await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalled());
			await waitFor(() => expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument());
			await waitFor(() => expect(mockFetchJob).toHaveBeenCalledTimes(2));
		});

		it('does nothing when a non-admin clicks the title cell', async () => {
			setRole('guest');
			loadJobPage();
			await screen.findByText('Tracks (1)');
			const cell = cellOf(trackRows()[0], 'Title');
			expect(cell).not.toHaveClass('job-detail-track-title-cell');
			await fireEvent.click(cell);
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});
	});
});

describe('below the tracks', () => {
	it('lists the disc fingerprints', async () => {
		loadJobPage(detailOf({}, undefined, { fingerprints: [{ algo: 'crc64', value: 'ABCDEF0123456789' }] }));
		expect(await screen.findByText('Disc fingerprints')).toBeInTheDocument();
		expect(screen.getByText('crc64')).toBeInTheDocument();
		expect(screen.getByText('ABCDEF0123456789')).toHaveAttribute('title', 'ABCDEF0123456789');
	});

	it('omits the fingerprints section when there are none', async () => {
		loadJobPage();
		await heading('Test Movie');
		expect(screen.queryByText('Disc fingerprints')).not.toBeInTheDocument();
	});

	it('omits the fingerprints section when the response has none at all', async () => {
		loadJobPage(detailOf({}, undefined, { fingerprints: undefined }));
		await heading('Test Movie');
		expect(screen.queryByText('Disc fingerprints')).not.toBeInTheDocument();
	});

	const cdWithMusic = (tracks: TrackView[]) =>
		detailOf(
			{
				disc_type: 'cd',
				title: 'Test Album',
				metadata_json: { music: { tracks: [{ title: 'Opening', length_ms: 95000 }] } } as never
			},
			tracks
		);

	it('shows the CD tracklist when there are no track rows', async () => {
		loadJobPage(cdWithMusic([]));
		expect(await screen.findByText('Tracklist')).toBeInTheDocument();
		expect(screen.getByText('(1 tracks via MusicBrainz)')).toBeInTheDocument();
		expect(screen.getByText('Opening')).toBeInTheDocument();
		expect(screen.queryByText(/^Tracks \(/)).not.toBeInTheDocument();
	});

	it('hides the CD tracklist once track rows exist', async () => {
		loadJobPage(cdWithMusic([createTrack({ id: 'trk_1', kind: 'audio_track', status: 'done' })]));
		await screen.findByText('Tracks (1)');
		expect(screen.queryByText('Tracklist')).not.toBeInTheDocument();
	});

	it('shows neither table for a job with no tracks and no tracklist', async () => {
		loadJobPage(detailOf({}, []));
		await heading('Test Movie');
		expect(screen.queryByText('Tracklist')).not.toBeInTheDocument();
		expect(screen.queryByText(/^Tracks \(/)).not.toBeInTheDocument();
	});

	it('toggles the raw metadata tree from its button', async () => {
		loadJobPage(detailOf({ metadata_json: { custom_key: 'custom value' } as never }));
		const toggle = await screen.findByRole('button', { name: 'Raw metadata' });
		expect(toggle).toHaveAttribute('aria-expanded', 'false');
		expect(screen.queryByText('custom_key')).not.toBeInTheDocument();
		await fireEvent.click(toggle);
		expect(toggle).toHaveAttribute('aria-expanded', 'true');
		expect(screen.getByText('custom_key')).toBeInTheDocument();
		await fireEvent.click(toggle);
		expect(screen.queryByText('custom_key')).not.toBeInTheDocument();
	});
});

describe('navigation between jobs', () => {
	it('reloads the page for the new job when the route id changes under the mounted page', async () => {
		loadJobPage();
		await heading('Test Movie');
		mockFetchJob.mockResolvedValue(detailOf({ id: 'job_43', title: 'Other Movie' }));
		setPageId('job_43');
		await heading('Other Movie');
		expect(mockFetchJob).toHaveBeenLastCalledWith('job_43');
	});

	it('does not reload when the route id stays the same', async () => {
		loadJobPage();
		await heading('Test Movie');
		setPageId(JOB);
		await new Promise((r) => setTimeout(r, 20));
		expect(mockFetchJob).toHaveBeenCalledTimes(1);
	});

	it('does not reload when the route loses its id', async () => {
		loadJobPage();
		await heading('Test Movie');
		setPageId(undefined);
		await new Promise((r) => setTimeout(r, 20));
		expect(mockFetchJob).toHaveBeenCalledTimes(1);
	});

	it('loads with an empty id when the route has none', async () => {
		setPageId(undefined);
		loadJobPage();
		await heading('Test Movie');
		expect(mockFetchJob).toHaveBeenCalledWith('');
	});

	it('updates a track against an empty id when the route has none', async () => {
		setPageId(undefined);
		loadJobPage();
		await screen.findByText('Tracks (1)');
		await fireEvent.click(screen.getByRole('checkbox'));
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledWith('', 'trk_1', { excluded: true }));
	});
});
