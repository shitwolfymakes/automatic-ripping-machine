import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';
import TranscoderPage from '../+page.svelte';
import { setTranscoderEnabled, setTranscodeRuntimeEnabled } from '$lib/stores/config';
import {
	fetchTranscoderJobs,
	fetchTranscoderStats,
	retryTranscoderJob,
	deleteTranscoderJob
} from '$lib/api/transcoder';
import { fetchGpus } from '$lib/api/gpus';

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
	fetchTranscoderStats: vi.fn(() =>
		Promise.resolve({
			tasks_by_status: { queued: 2, in_progress: 1, done: 10, failed: 1 },
			total_tasks: 14,
			gpus_total: 1,
			gpus_available: 0,
			max_parallel: 2
		})
	),
	// v3 bare TranscodeTaskView[].
	fetchTranscoderJobs: vi.fn(() =>
		Promise.resolve([
			{
				id: 't-1',
				session_application_id: 'sap_1',
				job_id: 'job_abc',
				source_track_id: 'track-1',
				status: 'in_progress',
				output_path: '/media/transcode/movie1.mkv',
				progress_pct: 50,
				attempts: 0,
				claimed_by: 'gpu-0',
				claim_heartbeat_at: '2025-06-15T10:05:00Z',
				last_error: null,
				created_at: '2025-06-15T10:00:00Z',
				updated_at: '2025-06-15T10:05:00Z'
			},
			{
				id: 't-2',
				session_application_id: 'sap_2',
				job_id: null,
				source_track_id: 'track-2',
				status: 'failed',
				output_path: '/media/transcode/movie2.mkv',
				progress_pct: 0,
				attempts: 1,
				claimed_by: null,
				claim_heartbeat_at: null,
				last_error: 'boom',
				created_at: '2025-06-15T10:00:00Z',
				updated_at: '2025-06-15T10:05:00Z'
			}
		])
	),
	// v3 bare TranscodeWorkerView[].
	fetchTranscoderWorkers: vi.fn(() =>
		Promise.resolve([
			{
				task_id: 't-1',
				claimed_by: 'gpu-0',
				progress_pct: 50,
				claim_heartbeat_at: '2025-06-15T10:05:00Z',
				gpu_id: 'gpu-0',
				source_track_id: 'track-1',
				output_path: '/media/transcode/movie1.mkv'
			}
		])
	),
	retryTranscoderJob: vi.fn(),
	deleteTranscoderJob: vi.fn()
}));

let transcodeEventHandler: (() => void) | null = null;
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		start: vi.fn(),
		subscribe: vi.fn((topic: string, handler: () => void) => {
			if (topic === 'transcode.events') transcodeEventHandler = handler;
			return () => {};
		})
	}
}));

vi.mock('$lib/api/gpus', () => ({
	fetchGpus: vi.fn(() =>
		Promise.resolve([
			{
				id: 'gpu_1',
				vendor: 'nvenc',
				device_path: 'nvidia://0',
				encoder_kinds: ['h264', 'h265'],
				status: 'busy',
				enabled: true,
				claimed_by_task_id: 't-1',
				last_seen_at: null
			},
			{
				id: 'gpu_2',
				vendor: 'vaapi',
				device_path: '/dev/dri/renderD128',
				encoder_kinds: ['h264'],
				status: 'available',
				enabled: false,
				claimed_by_task_id: null,
				last_seen_at: null
			}
		])
	)
}));

vi.mock('$lib/api/logs', () => ({
	fetchStructuredTranscoderLogContent: vi.fn(() => Promise.resolve({ entries: [] })),
	fetchStructuredLogContent: vi.fn(() => Promise.resolve({ entries: [] }))
}));

vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	const store = writable({
		db_available: true,
		arm_online: true,
		active_jobs: [],
		drives_online: 0,
		drive_names: {},
		notification_count: 0,
		ripping_enabled: true,
		makemkv_key_valid: null,
		makemkv_key_checked_at: null,
		transcoder_online: true,
		transcoder_stats: null,
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

	describe('done task duration (D-202)', () => {
		const doneTask = {
			id: 't-3',
			session_application_id: 'sap_3',
			job_id: null,
			source_track_id: 'track-3',
			status: 'done',
			output_path: '/media/transcode/movie3.mkv',
			progress_pct: 100,
			attempts: 1,
			claimed_by: null,
			claim_heartbeat_at: null,
			last_error: null,
			created_at: '2025-06-15T09:00:00Z',
			updated_at: '2025-06-15T11:20:00Z'
		} as const;

		it('measures Took from the claim, not from when the task was queued', async () => {
			vi.mocked(fetchTranscoderJobs).mockResolvedValueOnce([{ ...doneTask, started_at: '2025-06-15T11:00:00Z' }]);
			renderComponent(TranscoderPage);
			await waitFor(() => expect(screen.getByText('Took 20m 0s')).toBeInTheDocument());
		});

		it('falls back to created_at for Took on tasks from before started_at existed', async () => {
			vi.mocked(fetchTranscoderJobs).mockResolvedValueOnce([{ ...doneTask, started_at: null }]);
			renderComponent(TranscoderPage);
			await waitFor(() => expect(screen.getByText('Took 2h 20m 0s')).toBeInTheDocument());
		});
	});

	describe('action failures (D-195)', () => {
		afterEach(() => vi.restoreAllMocks());

		it('shows a failed retry in the feedback banner and refreshes the list', async () => {
			vi.mocked(retryTranscoderJob).mockRejectedValueOnce(new Error('task is in status=queued, not failed'));
			renderComponent(TranscoderPage);
			await waitFor(() => expect(screen.getByText('Retry')).toBeInTheDocument());
			const before = vi.mocked(fetchTranscoderJobs).mock.calls.length;
			await fireEvent.click(screen.getByText('Retry'));
			await waitFor(() => expect(screen.getByText('task is in status=queued, not failed')).toBeInTheDocument());
			await waitFor(() => expect(vi.mocked(fetchTranscoderJobs).mock.calls.length).toBeGreaterThan(before));
			await fireEvent.click(screen.getByText('Dismiss'));
			expect(screen.queryByText('task is in status=queued, not failed')).not.toBeInTheDocument();
		});

		it('shows a failed delete in the feedback banner', async () => {
			vi.spyOn(window, 'confirm').mockReturnValue(true);
			vi.mocked(deleteTranscoderJob).mockRejectedValueOnce(new Error('transcode dispatcher unavailable'));
			renderComponent(TranscoderPage);
			await waitFor(() => expect(screen.getAllByText('Delete').length).toBeGreaterThan(0));
			await fireEvent.click(screen.getAllByText('Delete')[0]);
			await waitFor(() => expect(screen.getByText('transcode dispatcher unavailable')).toBeInTheDocument());
		});

		it('does not call delete when the confirm is declined', async () => {
			vi.spyOn(window, 'confirm').mockReturnValue(false);
			vi.mocked(deleteTranscoderJob).mockClear();
			renderComponent(TranscoderPage);
			await waitFor(() => expect(screen.getAllByText('Delete').length).toBeGreaterThan(0));
			await fireEvent.click(screen.getAllByText('Delete')[0]);
			expect(deleteTranscoderJob).not.toHaveBeenCalled();
		});
	});

	describe('disabled / not-capable states', () => {
		afterEach(() => {
			setTranscoderEnabled(true);
			setTranscodeRuntimeEnabled(true);
		});

		it('shows the disabled banner and keeps content visible when capable but runtime-disabled', async () => {
			setTranscodeRuntimeEnabled(false);
			renderComponent(TranscoderPage);
			expect(
				screen.getByText('Transcoding is disabled. Queued tasks are held and resume when it is re-enabled.')
			).toBeInTheDocument();
			// Drain semantics: the held queue must stay visible, not be hidden.
			await waitFor(() => expect(screen.getByText('movie1.mkv')).toBeInTheDocument());
		});

		it('does not show the disabled banner when transcoding is capable and enabled', () => {
			renderComponent(TranscoderPage);
			expect(
				screen.queryByText('Transcoding is disabled. Queued tasks are held and resume when it is re-enabled.')
			).not.toBeInTheDocument();
		});

		it('renders a full-page empty state and fetches no task list when not capable (ripper-only deep link)', async () => {
			setTranscoderEnabled(false);
			// Earlier tests in this file already invoked these fetchers; clear
			// their call history so this assertion only reflects this render.
			vi.mocked(fetchTranscoderJobs).mockClear();
			vi.mocked(fetchTranscoderStats).mockClear();
			vi.mocked(fetchGpus).mockClear();
			renderComponent(TranscoderPage);
			expect(
				screen.getByText('Transcoding is not available on this deployment (ripper-only install).')
			).toBeInTheDocument();
			expect(screen.queryByText('Transcode Jobs')).not.toBeInTheDocument();
			// Let any pending microtasks flush, then confirm nothing was fetched.
			await new Promise((r) => setTimeout(r, 0));
			expect(fetchTranscoderJobs).not.toHaveBeenCalled();
			expect(fetchGpus).not.toHaveBeenCalled();
			// Only the one-shot held-task count; none held, so no warning.
			expect(fetchTranscoderStats).toHaveBeenCalledTimes(1);
			expect(screen.queryByTestId('transcoder-held-encode-tasks')).not.toBeInTheDocument();
		});

		it('says how many encode tasks a ripper-only deployment is holding', async () => {
			setTranscoderEnabled(false);
			vi.mocked(fetchTranscoderStats).mockResolvedValueOnce({
				tasks_by_status: { queued: 3 },
				total_tasks: 3,
				gpus_total: 0,
				gpus_available: 0,
				max_parallel: 1,
				queued_encode_tasks: 2
			});
			renderComponent(TranscoderPage);
			await waitFor(() =>
				expect(screen.getByTestId('transcoder-held-encode-tasks')).toHaveTextContent(
					'2 encode tasks are held. Re-run setup without --ripper-only to resume them.'
				)
			);
		});
	});
});

it('renders per-GPU inventory rows with status and a manage link', async () => {
	renderComponent(TranscoderPage);
	await waitFor(() => expect(screen.getByTestId('gpu-rows')).toBeInTheDocument());
	const rows = screen.getByTestId('gpu-rows');
	expect(rows.textContent).toContain('NVENC');
	expect(rows.textContent).toContain('busy');
	expect(rows.textContent).toContain('VAAPI');
	expect(rows.textContent).toContain('disabled');
	expect(screen.getByText('Manage GPUs in Settings')).toHaveAttribute('href', '/settings#transcoding');
});

it('reloads the per-GPU rows on transcode events so they track claims (D-058)', async () => {
	cleanup();
	renderComponent(TranscoderPage);
	await waitFor(() => expect(screen.getByTestId('gpu-rows').textContent).toContain('busy'));
	vi.mocked(fetchGpus).mockResolvedValueOnce([
		{
			id: 'gpu_1',
			vendor: 'nvenc',
			device_path: 'nvidia://0',
			encoder_kinds: ['h264', 'h265'],
			status: 'available',
			enabled: true,
			claimed_by_task_id: null,
			last_seen_at: null
		}
	] as Awaited<ReturnType<typeof fetchGpus>>);
	expect(transcodeEventHandler).not.toBeNull();
	const before = vi.mocked(fetchGpus).mock.calls.length;
	// A batch of task events reloads the rows once, not once per event.
	for (let i = 0; i < 5; i++) transcodeEventHandler?.();
	await waitFor(() => expect(screen.getByTestId('gpu-rows').textContent).not.toContain('busy'));
	expect(screen.getByTestId('gpu-rows').textContent).toContain('available');
	await new Promise((r) => setTimeout(r, 400));
	expect(vi.mocked(fetchGpus).mock.calls.length - before).toBe(1);
});
