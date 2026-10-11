import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';
import Page from './+page.svelte';
import { createJob, createJobDetail, createTrack } from '$lib/components/__fixtures__/job';
import type { IdentityView, JobView, TrackView } from '$lib/types/api.gen';

// --- Mocks ---

const mockGoto = vi.fn();
vi.mock('$app/navigation', () => ({ goto: (...args: unknown[]) => mockGoto(...args) }));

vi.mock('$app/stores', () => ({
	page: {
		subscribe: (fn: (val: { params: { id: string } }) => void) => {
			fn({ params: { id: 'job_42' } });
			return () => {};
		}
	}
}));

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

vi.mock('$lib/api/jobs', () => ({
	fetchJob: vi.fn(() =>
		Promise.resolve({
			job: createJob({
				id: 'job_42',
				title: 'Test Movie',
				year: 2024,
				status: 'ripped',
				disc_type: 'bluray'
			}),
			tracks: [createTrack({ id: 'trk_1', source_ref: 'title_01.mkv', status: 'done' })],
			fingerprints: []
		})
	),
	updateTrack: vi.fn(() => Promise.resolve()),
	fetchNamingPreview: vi.fn(() => Promise.resolve({ job_output_dir: '', job_output_name: '', items: [] })),
	resolveJob: vi.fn(() => Promise.resolve({ job: createJob({ id: 'job_42' }), fan_out: [] })),
	applySession: vi.fn(() => Promise.resolve({ session_application: {}, tasks: [], collisions: [], idempotent: false })),
	searchMusicMetadata: vi.fn(() => Promise.resolve({ candidates: [] })),
	fetchMusicDetail: vi.fn(() => Promise.resolve({})),
	setJobMediaType: vi.fn(() => Promise.resolve(createJob({ id: 'job_42' })))
}));

// The Match Episodes panel reads the job's identity on mount.
vi.mock('$lib/api/identity', () => ({
	fetchIdentity: vi.fn(() => new Promise(() => {})),
	matchIdentity: vi.fn(() => new Promise(() => {})),
	unpinIdentity: vi.fn(() => new Promise(() => {})),
	fetchEpisodes: vi.fn(() => new Promise(() => {}))
}));

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(() => Promise.resolve([]))
}));

// ApplySessionDialog fetches the preset lists to enrich its recipe preview.
vi.mock('$lib/api/ripPresets', () => ({
	fetchRipPresets: vi.fn(() => Promise.resolve([]))
}));

vi.mock('$lib/api/transcodePresets', () => ({
	fetchTranscodePresets: vi.fn(() => Promise.resolve([]))
}));

vi.mock('$lib/api/logs', () => ({
	fetchStructuredLogContent: vi.fn(() => Promise.resolve({ entries: [] })),
	fetchStructuredTranscoderLogContent: vi.fn(() => Promise.resolve({ entries: [] })),
	fetchTranscoderLogForArmJob: vi.fn(() => Promise.resolve({ found: false })),
	fetchLogContent: vi.fn(() => Promise.resolve({ content: '' })),
	fetchJobLog: vi.fn(() => Promise.resolve([])),
	jobLogDownloadUrl: (id: string) => `/api/logs/${id}.zip`
}));

// The job log panel opens its own WS subscription for an active job (this
// suite's fixture job is 'ripped', a terminal status, so it never subscribes
// in practice) - stub the client so no real WebSocket gets created in jsdom.
vi.mock('$lib/api/ws', () => ({
	wsClient: { subscribe: vi.fn(() => vi.fn()), start: vi.fn(), stop: vi.fn() }
}));

// Capture the page's ripper-event listener so a test can fire an event for this job.
type RipperListener = (jobIds: Set<string>, eventTypes: Map<string, Set<string>>) => void;
const ripperListeners: RipperListener[] = [];
function fireRipperEvent(jobId: string, eventType: string) {
	ripperListeners.forEach((fn) => fn(new Set([jobId]), new Map([[jobId, new Set([eventType])]])));
}
vi.mock('$lib/stores/ripperEvents.svelte', () => ({
	startRipperEvents: vi.fn(),
	onRipperEvent: (fn: RipperListener) => {
		ripperListeners.push(fn);
		return () => ripperListeners.splice(ripperListeners.indexOf(fn), 1);
	}
}));

vi.mock('$lib/api/settings', () => ({
	fetchSettings: vi.fn(() => Promise.resolve({ transcoder_config: { config: {} } }))
}));

import { fetchJob, updateTrack, fetchNamingPreview, setJobMediaType } from '$lib/api/jobs';
import * as authStore from '$lib/stores/auth';
import { fetchIdentity } from '$lib/api/identity';
const mockFetchJob = vi.mocked(fetchJob);
const mockUpdateTrack = vi.mocked(updateTrack);
const mockFetchNamingPreview = vi.mocked(fetchNamingPreview);

describe('Job detail page (v3)', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('renders the job title from the JobDetailView job', async () => {
		renderComponent(Page);
		await waitFor(() => {
			expect(screen.getByRole('heading', { name: 'Test Movie' })).toBeInTheDocument();
		});
	});

	it('renders the breadcrumb', async () => {
		renderComponent(Page);
		await waitFor(() => {
			expect(screen.getByText('Dashboard')).toBeInTheDocument();
		});
	});

	it('renders the year from the job', async () => {
		renderComponent(Page);
		await waitFor(() => {
			expect(screen.getByText('(2024)')).toBeInTheDocument();
		});
	});

	it('renders tracks from JobDetailView.tracks', async () => {
		renderComponent(Page);
		await waitFor(() => {
			expect(screen.getByText('Tracks (1)')).toBeInTheDocument();
		});
		// Source column was replaced by Kind + Filename; assert on the Kind header.
		expect(screen.getByRole('columnheader', { name: 'Kind' })).toBeInTheDocument();
	});

	it('renders the JobLogPanel with a link to the full job log', async () => {
		renderComponent(Page);
		await waitFor(() => {
			expect(screen.getByTestId('job-log-open')).toHaveAttribute('href', '/logs/job_42');
		});
	});

	it('redirects to home on 404', async () => {
		mockFetchJob.mockRejectedValueOnce(new Error('404 Not Found'));
		renderComponent(Page);
		await waitFor(() => {
			expect(mockGoto).toHaveBeenCalledWith('/');
		});
	});

	it('shows the Identify (Edit identity) button for a resolvable status', async () => {
		renderComponent(Page);
		await waitFor(() => {
			expect(screen.getByTestId('identify-open')).toBeInTheDocument();
		});
	});

	it('opens the IdentifyDialog when the Identify button is clicked', async () => {
		renderComponent(Page);
		const btn = await screen.findByTestId('identify-open');
		await fireEvent.click(btn);
		await waitFor(() => {
			expect(screen.getByRole('dialog')).toBeInTheDocument();
			expect(screen.getByTestId('identify-submit')).toBeInTheDocument();
		});
	});

	it('shows the Apply session button and opens the ApplySessionDialog', async () => {
		renderComponent(Page);
		const btn = await screen.findByTestId('apply-open');
		await fireEvent.click(btn);
		await waitFor(() => {
			expect(screen.getByTestId('apply-session-select')).toBeInTheDocument();
		});
	});

	it('shows the Match CD tab only for cd jobs', async () => {
		mockFetchJob.mockResolvedValueOnce({
			job: createJob({ id: 'job_cd', disc_type: 'cd', status: 'ripped', title: 'Abbey Road' }),
			tracks: [],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByRole('button', { name: 'Match CD' })).toBeInTheDocument());
	});

	it('does not show the Match CD tab for video jobs', async () => {
		renderComponent(Page);
		await waitFor(() => {
			expect(screen.getByRole('heading', { name: 'Test Movie' })).toBeInTheDocument();
		});
		expect(screen.queryByRole('button', { name: 'Match CD' })).not.toBeInTheDocument();
	});

	it('excludes a track via the Rip checkbox', async () => {
		renderComponent(Page);
		await waitFor(() => {
			expect(screen.getByText('Tracks (1)')).toBeInTheDocument();
		});
		// Single track row → exactly one Rip checkbox, checked for a non-excluded track.
		const checkbox = screen.getByRole('checkbox') as HTMLInputElement;
		expect(checkbox.checked).toBe(true);
		await fireEvent.click(checkbox);
		await waitFor(() => {
			expect(mockUpdateTrack).toHaveBeenCalledWith('job_42', 'trk_1', { excluded: true });
		});
	});

	it('renders filename and fingerprints; hides the fallback Tracklist when track rows exist', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({
				id: 'job_42',
				title: 'Test Album',
				disc_type: 'cd',
				status: 'ripped',
				metadata_json: { music: { tracks: [{ title: 'Opening', length_ms: 95000 }] } }
			}),
			tracks: [createTrack({ id: 'trk_1', kind: 'audio_track', status: 'done' })],
			fingerprints: [
				{ algo: 'crc64', value: 'ABCDEF0123456789' },
				{ algo: 'matrix256', value: 'c0ffee' + 'ab'.repeat(29) }
			]
		});
		mockFetchNamingPreview.mockResolvedValue({
			job_output_dir: 'Album',
			job_output_name: 'Album',
			items: [
				{
					track_id: 'trk_1',
					track_number: 1,
					output_path: 'Album/01 Opening.flac',
					output_dir: 'Album',
					output_name: '01 Opening.flac'
				}
			]
		});

		renderComponent(Page);

		// Disc fingerprints section renders its populated row.
		await waitFor(() => {
			expect(screen.getByText('Disc fingerprints')).toBeInTheDocument();
		});
		expect(screen.getByText('ABCDEF0123456789')).toBeInTheDocument();
		// matrix256 rides the same generic algo/value table as every other algo.
		expect(screen.getByText('matrix256')).toBeInTheDocument();
		expect(screen.getByText('c0ffee' + 'ab'.repeat(29))).toBeInTheDocument();

		// Filename cell renders the naming-preview output_name.
		expect(screen.getByText('01 Opening.flac')).toBeInTheDocument();

		// The metadata_json Tracklist is a FALLBACK: with real track rows present
		// it must NOT render (the Tracks table is authoritative), matching neu.
		expect(screen.queryByText('Tracklist')).not.toBeInTheDocument();
	});

	it('renders the fallback Tracklist when there are no track rows', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({
				id: 'job_42',
				title: 'Test Album',
				disc_type: 'cd',
				status: 'ripped',
				metadata_json: { music: { tracks: [{ title: 'Opening', length_ms: 95000 }] } }
			}),
			tracks: [],
			fingerprints: []
		});

		renderComponent(Page);

		// With no Track rows, the MusicBrainz tracklist is shown as a fallback.
		await waitFor(() => {
			expect(screen.getByText('Tracklist')).toBeInTheDocument();
		});
		expect(screen.getByText('Opening')).toBeInTheDocument();
	});

	it('renders the Raw metadata as a collapsible JSON tree', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({
				id: 'job_42',
				title: 'Test Movie',
				status: 'ripped',
				metadata_json: {
					imdb_id: 'tt9999999',
					scan_result: { disc_type: 'bluray', titles: [{ index: 0, duration_seconds: 0 }] }
				}
			}),
			tracks: [],
			fingerprints: []
		});
		renderComponent(Page);

		const toggle = await screen.findByRole('button', { name: 'Raw metadata' });
		// Collapsed initially: the top-level keys are not yet shown.
		expect(screen.queryByText('scan_result')).not.toBeInTheDocument();
		await fireEvent.click(toggle);
		await waitFor(() => {
			// Top-level keys render as tree node names.
			expect(screen.getByText('imdb_id')).toBeInTheDocument();
			expect(screen.getByText('scan_result')).toBeInTheDocument();
			// scan_result is open one level (depth 1) → its child "titles" disclosure shows.
			expect(screen.getByText('titles')).toBeInTheDocument();
		});
	});

	it('omits the Raw metadata section when metadata_json is empty', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({ id: 'job_42', title: 'Bare', status: 'ripped', metadata_json: {} }),
			tracks: [],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByRole('heading', { name: 'Bare' })).toBeInTheDocument());
		expect(screen.queryByRole('button', { name: 'Raw metadata' })).not.toBeInTheDocument();
	});

	it('renders a track poster thumbnail and IMDb link when present', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({ id: 'job_42', title: 'Test Movie', status: 'ripped' }),
			tracks: [
				createTrack({
					id: 'trk_1',
					status: 'done',
					title: 'Feature',
					imdb_id: 'tt5555555',
					poster_url: 'https://example.test/p.jpg'
				})
			],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByText('Tracks (1)')).toBeInTheDocument());
		const imdb = screen.getByRole('link', { name: 'IMDb' });
		expect(imdb.getAttribute('href')).toBe('https://www.imdb.com/title/tt5555555');
		expect(
			document.querySelector('img[src="/api/images/proxy?url=https%3A%2F%2Fexample.test%2Fp.jpg"]')
		).not.toBeNull();
	});

	it('renders an Episode column only when a track is a series', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({ id: 'job_42', title: 'Show', status: 'ripped' }),
			tracks: [
				createTrack({
					id: 'trk_1',
					status: 'done',
					role: 'episode',
					episode_number: 3,
					episode_name: 'The One With The Test'
				})
			],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByText('Tracks (1)')).toBeInTheDocument());
		expect(screen.getByRole('columnheader', { name: 'Episode' })).toBeInTheDocument();
		expect(screen.getByText('The One With The Test')).toBeInTheDocument();
	});

	it('omits the Episode column for non-series tracks', async () => {
		// default mockFetchJob: one non-series track
		mockFetchJob.mockResolvedValue({
			job: createJob({ id: 'job_42', title: 'Test Movie', status: 'ripped' }),
			tracks: [createTrack({ id: 'trk_1', status: 'done' })],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByText('Tracks (1)')).toBeInTheDocument());
		expect(screen.queryByRole('columnheader', { name: 'Episode' })).not.toBeInTheDocument();
	});

	it('shows the Episode column for a TV job whose tracks have no role and no episode_number yet', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({ id: 'job_42', title: 'Show', status: 'ripped', media_type: 'tv' }),
			tracks: [createTrack({ id: 'trk_1', status: 'done', role: null })],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByText('Tracks (1)')).toBeInTheDocument());
		expect(screen.getByRole('columnheader', { name: 'Episode' })).toBeInTheDocument();
	});

	it('omits the Episode column for a TV job whose only track is role main', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({ id: 'job_42', title: 'Show', status: 'ripped', media_type: 'tv' }),
			tracks: [createTrack({ id: 'trk_1', status: 'done', role: 'main' })],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByText('Tracks (1)')).toBeInTheDocument());
		expect(screen.queryByRole('columnheader', { name: 'Episode' })).not.toBeInTheDocument();
	});

	it('renders an edition badge when set', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({ id: 'job_42', title: 'Test Movie', status: 'ripped' }),
			tracks: [createTrack({ id: 'trk_1', status: 'done', title: 'Feature', edition: "Director's Cut" })],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByText('Tracks (1)')).toBeInTheDocument());
		expect(screen.getByText("Director's Cut")).toBeInTheDocument();
	});

	it('renders IMDb, Multi-Title, and Source badges in the title bar when present', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({
				id: 'job_42',
				title: 'Test Movie',
				status: 'ripped',
				disc_type: 'bluray',
				metadata_json: {
					identity: { provider: 'tmdb', external_ids: { imdb: 'tt7777777' } },
					provider_raw: { arm_server: { multi_title: true, source_type: 'iso' } }
				}
			}),
			tracks: [],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByRole('heading', { name: 'Test Movie' })).toBeInTheDocument());
		// IMDb appears both as a grid link and a header pill — at least one link to the title page.
		const imdbLinks = screen.getAllByRole('link', { name: 'IMDb' });
		expect(imdbLinks.some((a) => a.getAttribute('href') === 'https://www.imdb.com/title/tt7777777')).toBe(true);
		expect(screen.getByText('Multi-Title')).toBeInTheDocument();
		expect(screen.getByText('ISO')).toBeInTheDocument();
	});

	it('omits header badges when metadata_json lacks them', async () => {
		// explicit empty metadata_json — no badge data present
		mockFetchJob.mockResolvedValue({
			job: createJob({ id: 'job_42', title: 'Test Movie', status: 'ripped', disc_type: 'bluray', metadata_json: {} }),
			tracks: [],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByRole('heading', { name: 'Test Movie' })).toBeInTheDocument());
		expect(screen.queryByText('Multi-Title')).not.toBeInTheDocument();
		expect(screen.queryByText('ISO')).not.toBeInTheDocument();
		expect(screen.queryByText('Folder')).not.toBeInTheDocument();
	});

	it('does not show the IMDb header pill for a music disc', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({
				id: 'job_42',
				title: 'Abbey Road',
				status: 'ripped',
				disc_type: 'cd',
				metadata_json: { imdb_id: 'tt0000000' }
			}),
			tracks: [],
			fingerprints: []
		});
		renderComponent(Page);
		await waitFor(() => expect(screen.getByRole('heading', { name: 'Abbey Road' })).toBeInTheDocument());
		// No IMDb pill/link for music (grid also suppresses it via not-music gate in neu; here disc_type cd).
		expect(screen.queryByRole('link', { name: 'IMDb' })).not.toBeInTheDocument();
	});

	it('shows a Transcode badge when the track has a transcode_status', async () => {
		mockFetchJob.mockResolvedValueOnce({
			job: createJob({
				id: 'job_42',
				status: 'ripped',
				// Not live: a live job opens the log panel, which has its own "Transcode" label.
				transcode_progress: { state: 'done', tasks_total: 1, tasks_done: 1, tasks_failed: 0, percent: 100 }
			}),
			tracks: [
				createTrack({ id: 'trk_1', source_ref: 'title_01.mkv', status: 'done', transcode_status: 'failed' } as any)
			],
			fingerprints: []
		} as any);
		renderComponent(Page);
		// "Transcode" is the column header; the track's Transcode cell renders the
		// failed badge.
		await waitFor(() => expect(screen.getByText('Transcode')).toBeInTheDocument());
		expect(screen.getByText('Failed')).toBeInTheDocument();
	});

	it('shows only the rip badge when transcode_status is null', async () => {
		mockFetchJob.mockResolvedValueOnce({
			job: createJob({ id: 'job_42', status: 'ripped' }),
			tracks: [createTrack({ id: 'trk_2', source_ref: 'title_02.mkv', status: 'done', transcode_status: null } as any)],
			fingerprints: []
		} as any);
		renderComponent(Page);
		// The track's Transcode cell shows a dash (no transcode task yet).
		// Scope to the Transcode <td> (data-label="Transcode") — other cells also
		// render "-", so a global getByText('—') is ambiguous.
		await waitFor(() => expect(screen.getByText('Done')).toBeInTheDocument());
		const transcodeCell = document.querySelector('td[data-label="Transcode"]');
		expect(transcodeCell?.textContent?.trim()).toBe('-');
	});
	describe('TV episode matching', () => {
		afterEach(() => {
			(authStore as unknown as { __setRole: (r: string | null) => void }).__setRole('admin');
			vi.mocked(fetchIdentity).mockImplementation(() => new Promise(() => {}));
		});

		const tvJob = ({ tracks = [], ...job }: Partial<JobView> & { tracks?: TrackView[] } = {}) => ({
			...createJobDetail({ tracks }),
			job: createJob({
				id: 'job_42',
				media_type: 'tv',
				disc_type: 'bluray',
				has_series: true,
				status: 'ripped',
				...job
			})
		});

		it('shows Match Episodes only for TV jobs', async () => {
			mockFetchJob.mockResolvedValue(tvJob());
			renderComponent(Page);
			expect(await screen.findByRole('button', { name: 'Match Episodes' })).toBeInTheDocument();
		});

		it('puts the Movie | TV switch, as one control, right before Edit identity', async () => {
			mockFetchJob.mockResolvedValue(tvJob());
			renderComponent(Page);
			const editIdentity = await screen.findByTestId('identify-open');
			const group = screen.getByRole('radiogroup', { name: 'Media type' });
			expect(group).toContainElement(screen.getByRole('radio', { name: 'Movie' }));
			expect(group).toContainElement(screen.getByRole('radio', { name: 'TV' }));
			const switchRoot = group.parentElement!;
			expect(switchRoot.parentElement).toBe(editIdentity.parentElement);
			expect(switchRoot.nextElementSibling).toBe(editIdentity);
		});

		it('hides Match Episodes for a movie job', async () => {
			mockFetchJob.mockResolvedValue(tvJob({ media_type: 'movie', has_series: false }));
			renderComponent(Page);
			await screen.findByRole('button', { name: /Poster/ });
			expect(screen.queryByRole('button', { name: 'Match Episodes' })).not.toBeInTheDocument();
		});

		it('the header switch flips a movie to TV and opens episode matching', async () => {
			// First load is the movie; the refresh after the flip returns the TV job.
			mockFetchJob.mockResolvedValueOnce(tvJob({ media_type: 'movie', has_series: false }));
			mockFetchJob.mockResolvedValue(tvJob());
			vi.mocked(setJobMediaType).mockResolvedValue(createJob({ id: 'job_42', media_type: 'tv' }));
			renderComponent(Page);
			await fireEvent.click(await screen.findByRole('radio', { name: 'TV' }));
			expect(setJobMediaType).toHaveBeenCalledWith('job_42', 'tv');
			await waitFor(() =>
				expect(screen.getByRole('button', { name: 'Match Episodes' })).toHaveAttribute('aria-pressed', 'true')
			);
		});

		it('shows matching after the flip until job.identity_updated arrives for the job', async () => {
			mockFetchJob.mockResolvedValueOnce(tvJob({ media_type: 'movie', has_series: false }));
			mockFetchJob.mockResolvedValue(tvJob());
			renderComponent(Page);
			await fireEvent.click(await screen.findByRole('radio', { name: 'TV' }));
			expect(await screen.findByText('Matching episodes…')).toBeInTheDocument();
			// The page awaits the panel's reload before clearing, so the identity must load.
			vi.mocked(fetchIdentity).mockResolvedValue({ sources: {}, pin: null } as unknown as IdentityView);
			const identityCalls = vi.mocked(fetchIdentity).mock.calls.length;
			// Another job's identity update leaves it matching.
			fireRipperEvent('job_other', 'job.identity_updated');
			expect(screen.getByText('Matching episodes…')).toBeInTheDocument();
			// The resolve's own event refreshes the job but the stage is still running.
			const fetches = mockFetchJob.mock.calls.length;
			fireRipperEvent('job_42', 'rip.identify_resolved');
			await waitFor(() => expect(mockFetchJob.mock.calls.length).toBeGreaterThan(fetches));
			await waitFor(() => expect(vi.mocked(fetchIdentity).mock.calls.length).toBeGreaterThan(identityCalls));
			// Let the refresh fully settle before checking the state stuck.
			await new Promise((r) => setTimeout(r, 50));
			expect(screen.getByText('Matching episodes…')).toBeInTheDocument();
			fireRipperEvent('job_42', 'job.identity_updated');
			await waitFor(() => expect(screen.queryByText('Matching episodes…')).not.toBeInTheDocument());
			expect(vi.mocked(fetchIdentity).mock.calls.length).toBeGreaterThan(identityCalls);
		});

		it('clears matching after a bounded timeout when no event arrives', async () => {
			vi.useFakeTimers({ shouldAdvanceTime: true });
			try {
				mockFetchJob.mockResolvedValueOnce(tvJob({ media_type: 'movie', has_series: false }));
				mockFetchJob.mockResolvedValue(tvJob());
				renderComponent(Page);
				await fireEvent.click(await screen.findByRole('radio', { name: 'TV' }));
				expect(await screen.findByText('Matching episodes…')).toBeInTheDocument();
				await vi.advanceTimersByTimeAsync(60_000);
				await waitFor(() => expect(screen.queryByText('Matching episodes…')).not.toBeInTheDocument());
			} finally {
				vi.useRealTimers();
			}
		});

		it('keeps the type and shows an alert when the switch fails', async () => {
			mockFetchJob.mockResolvedValue(tvJob({ media_type: 'movie', has_series: false }));
			vi.mocked(setJobMediaType).mockRejectedValueOnce(new Error('409 Conflict'));
			renderComponent(Page);
			await fireEvent.click(await screen.findByRole('radio', { name: 'TV' }));
			expect(await screen.findByRole('alert')).toHaveTextContent('409 Conflict');
			expect(screen.getByRole('radio', { name: 'TV' })).toHaveAttribute('aria-checked', 'false');
			expect(screen.getByRole('radio', { name: 'Movie' })).toHaveAttribute('aria-checked', 'true');
			expect(screen.queryByRole('button', { name: 'Match Episodes' })).not.toBeInTheDocument();
		});

		it('asks before switching a job with hand-set episodes to Movie', async () => {
			const tracks = [createTrack({ id: 'trk_1', identity_provenance: { episode_number: 'manual' } })];
			mockFetchJob.mockResolvedValue(tvJob({ tracks }));
			renderComponent(Page);
			await fireEvent.click(await screen.findByRole('radio', { name: 'Movie' }));
			expect(setJobMediaType).not.toHaveBeenCalled();
			expect(screen.getByText('1 track has episodes you set by hand. Switch to Movie anyway?')).toBeInTheDocument();
			await fireEvent.click(screen.getByRole('button', { name: 'Switch to Movie' }));
			await waitFor(() => expect(setJobMediaType).toHaveBeenCalledWith('job_42', 'movie'));
		});

		it('pluralises the confirm message for several hand-set tracks', async () => {
			const tracks = [
				createTrack({ id: 'trk_1', identity_provenance: { episode_number: 'manual' } }),
				createTrack({ id: 'trk_2', identity_provenance: { role: 'manual' } }),
				createTrack({ id: 'trk_3', identity_provenance: { episode_number: 'auto' } })
			];
			mockFetchJob.mockResolvedValue(tvJob({ tracks }));
			renderComponent(Page);
			await fireEvent.click(await screen.findByRole('radio', { name: 'Movie' }));
			expect(screen.getByText('2 tracks have episodes you set by hand. Switch to Movie anyway?')).toBeInTheDocument();
		});

		it('switches straight to Movie when no episodes were set by hand', async () => {
			mockFetchJob.mockResolvedValue(tvJob());
			renderComponent(Page);
			await fireEvent.click(await screen.findByRole('radio', { name: 'Movie' }));
			await waitFor(() => expect(setJobMediaType).toHaveBeenCalledWith('job_42', 'movie'));
		});

		it('guests see the type as text, not a switch, and can still open Match Episodes', async () => {
			(authStore as unknown as { __setRole: (r: string | null) => void }).__setRole('guest');
			mockFetchJob.mockResolvedValue(tvJob());
			renderComponent(Page);
			expect(await screen.findByRole('button', { name: 'Match Episodes' })).toBeInTheDocument();
			expect(screen.queryByRole('radiogroup', { name: 'Media type' })).not.toBeInTheDocument();
			expect(screen.getByTestId('media-type-text')).toHaveTextContent('TV');
			expect(screen.getByTestId('media-type-text')).toHaveClass('badge');
		});
	});
});
