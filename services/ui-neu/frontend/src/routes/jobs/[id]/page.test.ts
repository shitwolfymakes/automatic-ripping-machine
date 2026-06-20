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
	updateTrack: vi.fn(),
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
});
