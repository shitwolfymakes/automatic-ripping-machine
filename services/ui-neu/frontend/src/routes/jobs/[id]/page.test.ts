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
	)
}));

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(() => Promise.resolve([]))
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

	it('renders filename, fingerprints, and music tracklist when data is present', async () => {
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

		// Music tracklist section renders the metadata_json track row.
		expect(screen.getByText('Tracklist')).toBeInTheDocument();
		expect(screen.getByText('Opening')).toBeInTheDocument();
	});
});
