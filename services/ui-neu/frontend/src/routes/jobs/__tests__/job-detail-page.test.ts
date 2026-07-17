import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor } from '$lib/test-utils';
import JobDetailPage from '../[id]/+page.svelte';
import { createJob, createTrack } from '$lib/components/__fixtures__/job';
import type { JobView, JobDetailView } from '$lib/types/api.gen';

vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ params: { id: 'job_1' } }) };
});

vi.mock('$app/navigation', () => ({
	goto: vi.fn()
}));

const { buildDetail } = vi.hoisted(() => {
	return {
		buildDetail: (jobOverrides: Partial<JobView> = {}): JobDetailView => ({
			job: createJob({
				id: 'job_1',
				title: 'Test Movie',
				status: 'ripped',
				year: 2024,
				disc_type: 'bluray',
				...jobOverrides
			}),
			tracks: [
				createTrack({
					id: 'trk_1',
					index: 1,
					source_ref: 'title_01.mkv',
					status: 'done'
				})
			],
			fingerprints: []
		})
	};
});

vi.mock('$lib/api/jobs', () => ({
	fetchJob: vi.fn(() => Promise.resolve(buildDetail())),
	fetchNamingPreview: vi.fn(() =>
		Promise.resolve({ job_output_dir: '', job_output_name: '', items: [] })
	),
	updateTrack: vi.fn(() => Promise.resolve()),
	resolveJob: vi.fn(() => Promise.resolve({ job: {}, fan_out: [] })),
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
	fetchTranscoderLogForArmJob: vi.fn(() => Promise.resolve(null))
}));

vi.mock('$lib/api/settings', () => ({
	fetchSettings: vi.fn(() => Promise.resolve({ transcoder_config: { config: {} } }))
}));

describe('Job Detail Page', () => {
	afterEach(() => cleanup());

	describe('rendering', () => {
		it('renders job title after loading', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByRole('heading', { name: 'Test Movie' })).toBeInTheDocument();
			});
		});

		it('renders breadcrumb navigation', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByText('Dashboard')).toBeInTheDocument();
			});
		});

		it('renders disc type', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByText('Blu-ray')).toBeInTheDocument();
			});
		});

		it('renders tracks table', async () => {
			renderComponent(JobDetailPage);
			// Source column was replaced by Kind + Filename; assert on the Kind header.
			await waitFor(() => {
				expect(screen.getByRole('columnheader', { name: 'Kind' })).toBeInTheDocument();
			});
		});

		it('renders without crashing', () => {
			const { container } = renderComponent(JobDetailPage);
			expect(container).toBeInTheDocument();
		});

		it('shows the poster/metadata-search tab for video discs', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(
					screen.getByRole('button', { name: /Poster & metadata search/ })
				).toBeInTheDocument();
			});
		});

		it('hides the poster/metadata-search tab for non-video discs', async () => {
			const { fetchJob } = await import('$lib/api/jobs');
			const detail = buildDetail({ id: 'job_2', title: 'Data Disc', disc_type: 'data' });
			detail.tracks = [];
			vi.mocked(fetchJob).mockResolvedValueOnce(detail as never);

			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByRole('heading', { name: 'Data Disc' })).toBeInTheDocument();
			});
			expect(
				screen.queryByRole('button', { name: /Poster & metadata search/ })
			).not.toBeInTheDocument();
		});

		it('shows the Identify (resolve) and Apply session buttons for a resolvable status', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByTestId('identify-open')).toBeInTheDocument();
			});
			expect(screen.getByTestId('apply-open')).toBeInTheDocument();
		});
	});

	describe('error handling', () => {
		it('redirects to home on 404', async () => {
			const { fetchJob } = await import('$lib/api/jobs');
			const { goto } = await import('$app/navigation');
			vi.mocked(fetchJob).mockRejectedValueOnce(new Error('404 Not Found'));

			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(goto).toHaveBeenCalledWith('/');
			});
		});
	});
});
