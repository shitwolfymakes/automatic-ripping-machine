import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor } from '$lib/test-utils';
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
	updateTrack: vi.fn()
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

import { fetchJob } from '$lib/api/jobs';
const mockFetchJob = vi.mocked(fetchJob);

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
			expect(screen.getByText('title_01.mkv')).toBeInTheDocument();
		});
		expect(screen.getByText('Tracks (1)')).toBeInTheDocument();
	});

	it('redirects to home on 404', async () => {
		mockFetchJob.mockRejectedValueOnce(new Error('404 Not Found'));
		renderComponent(Page);
		await waitFor(() => {
			expect(mockGoto).toHaveBeenCalledWith('/');
		});
	});
});
