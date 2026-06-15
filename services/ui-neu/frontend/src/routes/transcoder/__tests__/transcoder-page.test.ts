import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import TranscoderPage from '../+page.svelte';

vi.mock('$lib/api/transcoder', () => ({
	// v3 bare TranscodeStatsView.
	fetchTranscoderStats: vi.fn(() => Promise.resolve({
		tasks_by_status: { queued: 2, in_progress: 1, done: 10, failed: 0 },
		total_tasks: 13,
		gpus_total: 1,
		gpus_available: 0,
		max_parallel: 2
	})),
	// v3 bare TranscodeTaskView[].
	fetchTranscoderJobs: vi.fn(() => Promise.resolve([
		{
			id: 't-1', session_application_id: 'job-1', source_track_id: 'track-1',
			status: 'in_progress', output_path: '/media/transcode/movie1.mkv', progress_pct: 50,
			attempts: 0, claimed_by: 'gpu-0', claim_heartbeat_at: '2025-06-15T10:05:00Z',
			last_error: null, created_at: '2025-06-15T10:00:00Z', updated_at: '2025-06-15T10:05:00Z'
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

// Mock dashboard store with GPU data available
vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	const store = writable({
		db_available: true, arm_online: true, active_jobs: [], system_info: null,
		drives_online: 0, drive_names: {}, notification_count: 0, ripping_enabled: true,
		makemkv_key_valid: null, makemkv_key_checked_at: null,
		transcoder_online: true, transcoder_stats: null,
		transcoder_system_stats: {
			cpu_percent: 50,
			cpu_temp: 60,
			memory: { used_gb: 8, total_gb: 32, percent: 25 },
			storage: [],
			gpu: {
				vendor: 'nvidia',
				utilization_percent: 82,
				encoder_percent: 95,
				memory_used_mb: 4096,
				memory_total_mb: 8192,
				temperature_c: 72,
				power_draw_w: 200,
				power_limit_w: 300,
				clock_core_mhz: 1850,
				clock_memory_mhz: 7200
			}
		},
		active_transcodes: [], system_stats: null, transcoder_info: null
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

	describe('GPU stats card', () => {
		it('renders GPU card with vendor badge and metrics', () => {
			renderComponent(TranscoderPage);
			expect(screen.getByText('nvidia')).toBeInTheDocument();
			expect(screen.getByText('Load')).toBeInTheDocument();
			expect(screen.getByText('82%')).toBeInTheDocument();
			expect(screen.getByText('Encoder')).toBeInTheDocument();
			expect(screen.getByText('95%')).toBeInTheDocument();
			expect(screen.getByText('VRAM')).toBeInTheDocument();
			expect(screen.getByText('Temperature')).toBeInTheDocument();
			expect(screen.getByText('Power')).toBeInTheDocument();
			expect(screen.getByText('Core Clock')).toBeInTheDocument();
			expect(screen.getByText('Memory Clock')).toBeInTheDocument();
		});
	});
});
