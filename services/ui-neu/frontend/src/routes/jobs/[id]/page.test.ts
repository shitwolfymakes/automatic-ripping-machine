import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';
import Page from './+page.svelte';
import { createJob, createTrack } from '$lib/components/__fixtures__/job';

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
	applySession: vi.fn(() =>
		Promise.resolve({ session_application: {}, tasks: [], collisions: [], idempotent: false })
	),
	searchMusicMetadata: vi.fn(() => Promise.resolve({ candidates: [] })),
	fetchMusicDetail: vi.fn(() => Promise.resolve({}))
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
	fetchLogContent: vi.fn(() => Promise.resolve({ content: '' }))
}));

vi.mock('$lib/api/settings', () => ({
	fetchSettings: vi.fn(() => Promise.resolve({ transcoder_config: { config: {} } }))
}));

import { fetchJob, updateTrack, fetchNamingPreview } from '$lib/api/jobs';
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
		await waitFor(() =>
			expect(screen.getByRole('button', { name: 'Match CD' })).toBeInTheDocument()
		);
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
				metadata_json: { tracks: [{ title: 'Opening', duration_ms: 95000 }] }
			}),
			tracks: [createTrack({ id: 'trk_1', kind: 'audio_track', status: 'done' })],
			fingerprints: [{ algo: 'crc64', value: 'ABCDEF0123456789' }]
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
				metadata_json: { tracks: [{ title: 'Opening', duration_ms: 95000 }] }
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
				metadata_json: { imdb_id: 'tt9999999', scan_result: { titles: [{ index: 0 }] } }
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
		expect(document.querySelector('img[src="/api/images/proxy?url=https%3A%2F%2Fexample.test%2Fp.jpg"]')).not.toBeNull();
	});

	it('renders an Episode column only when a track is a series', async () => {
		mockFetchJob.mockResolvedValue({
			job: createJob({ id: 'job_42', title: 'Show', status: 'ripped' }),
			tracks: [
				createTrack({
					id: 'trk_1',
					status: 'done',
					video_type: 'series',
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
				metadata_json: { imdb_id: 'tt7777777', multi_title: true, source_type: 'iso' }
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
			job: createJob({ id: 'job_42', status: 'ripped' }),
			tracks: [createTrack({ id: 'trk_1', source_ref: 'title_01.mkv', status: 'done', transcode_status: 'failed' } as any)],
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
		// The track's Transcode cell shows an em-dash (no transcode task yet).
		// Scope to the Transcode <td> (data-label="Transcode") — other cells also
		// render "—", so a global getByText('—') is ambiguous.
		await waitFor(() => expect(screen.getByText('Done')).toBeInTheDocument());
		const transcodeCell = document.querySelector('td[data-label="Transcode"]');
		expect(transcodeCell?.textContent?.trim()).toBe('—');
	});
});
