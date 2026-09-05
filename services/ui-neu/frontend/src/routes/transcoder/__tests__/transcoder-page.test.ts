import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor } from '$lib/test-utils';
import TranscoderPage from '../+page.svelte';

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

vi.mock('$lib/api/transcoder', () => ({
	// v3 bare TranscodeStatsView.
	fetchTranscoderStats: vi.fn(() => Promise.resolve({
		tasks_by_status: { queued: 2, in_progress: 1, done: 10, failed: 1 },
		total_tasks: 14,
		gpus_total: 1,
		gpus_available: 0,
		max_parallel: 2
	})),
	// v3 bare TranscodeTaskView[].
	fetchTranscoderJobs: vi.fn(() => Promise.resolve([
		{
			id: 't-1', session_application_id: 'sap_1', job_id: 'job_abc', source_track_id: 'track-1',
			status: 'in_progress', output_path: '/media/transcode/movie1.mkv', progress_pct: 50,
			attempts: 0, claimed_by: 'gpu-0', claim_heartbeat_at: '2025-06-15T10:05:00Z',
			last_error: null, created_at: '2025-06-15T10:00:00Z', updated_at: '2025-06-15T10:05:00Z'
		},
		{
			id: 't-2', session_application_id: 'sap_2', job_id: null, source_track_id: 'track-2',
			status: 'failed', output_path: '/media/transcode/movie2.mkv', progress_pct: 0,
			attempts: 1, claimed_by: null, claim_heartbeat_at: null,
			last_error: 'boom', created_at: '2025-06-15T10:00:00Z', updated_at: '2025-06-15T10:05:00Z'
		}
	])),
	// v3 bare TranscodeWorkerView[].
	fetchTranscoderWorkers: vi.fn(() => Promise.resolve([
		{
			task_id: 't-1', claimed_by: 'gpu-0', progress_pct: 50,
			claim_heartbeat_at: '2025-06-15T10:05:00Z', gpu_id: 'gpu-0',
			source_track_id: 'track-1', output_path: '/media/transcode/movie1.mkv'
		}
	])),
	retryTranscoderJob: vi.fn(),
	deleteTranscoderJob: vi.fn(),
	retranscodeTranscoderJob: vi.fn()
}));

vi.mock('$lib/api/logs', () => ({
	fetchStructuredTranscoderLogContent: vi.fn(() => Promise.resolve({ entries: [] })),
	fetchStructuredLogContent: vi.fn(() => Promise.resolve({ entries: [] }))
}));

vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	const store = writable({
		db_available: true, arm_online: true, active_jobs: [],
		drives_online: 0, drive_names: {}, notification_count: 0, ripping_enabled: true,
		makemkv_key_valid: null, makemkv_key_checked_at: null,
		transcoder_online: true, transcoder_stats: null,
		active_transcodes: []
	});
	return { dashboard: { ...store, start: vi.fn(), stop: vi.fn(), error: writable(null) } };
});

describe('Transcoder Page', () => {
	afterEach(() => cleanup());

	describe('rendering', () => {
		it('renders page title', () => {
			renderComponent(TranscoderPage);
			expect(screen.getByText('Transcoder')).toBeInTheDocument();
		});

		it('renders without crashing', () => {
			const { container } = renderComponent(TranscoderPage);
			expect(container).toBeInTheDocument();
		});
	});

	describe('guest write-control gating', () => {
		afterEach(async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('admin');
		});

		it('hides Retry and Delete buttons for guests', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('guest');
			renderComponent(TranscoderPage);
			await waitFor(() => expect(screen.getByText('Transcode Jobs')).toBeInTheDocument());
			await waitFor(() => expect(screen.queryByText('movie1.mkv')).toBeInTheDocument());
			expect(screen.queryByText('Retry')).not.toBeInTheDocument();
			expect(screen.queryByText('Delete')).not.toBeInTheDocument();
		});

		it('shows Retry and Delete buttons for admins', async () => {
			renderComponent(TranscoderPage);
			await waitFor(() => expect(screen.getByText('movie1.mkv')).toBeInTheDocument());
			expect(screen.getByText('Retry')).toBeInTheDocument();
			expect(screen.getAllByText('Delete').length).toBeGreaterThan(0);
		});

		it('links the card to the resolved job id, not the session application id', async () => {
			renderComponent(TranscoderPage);
			await waitFor(() => expect(screen.getByText('movie1.mkv')).toBeInTheDocument());
			const links = screen.getAllByTestId('transcode-job-link');
			expect(links).toHaveLength(1);
			expect(links[0]).toHaveAttribute('href', '/jobs/job_abc');
			expect(document.querySelector('a[href="/jobs/sap_1"]')).toBeNull();
			expect(screen.getByText('No job')).toBeInTheDocument();
		});
	});
});
