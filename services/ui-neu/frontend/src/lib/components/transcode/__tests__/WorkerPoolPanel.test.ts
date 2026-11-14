import { describe, it, expect, afterEach, beforeEach, vi } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import type { GpuView, TranscodeStatsView, TranscodeWorkerView } from '$lib/types/api.gen';
import WorkerPoolPanel from '../WorkerPoolPanel.svelte';

function makeWorker(overrides: Partial<TranscodeWorkerView> = {}): TranscodeWorkerView {
	return {
		task_id: 't-1',
		claimed_by: 'gpu-0',
		progress_pct: 50,
		claim_heartbeat_at: '2025-06-15T10:05:00Z',
		gpu_id: 'gpu-0',
		source_track_id: 'track-1',
		output_path: '/media/transcode/movie1.mkv',
		...overrides
	} as TranscodeWorkerView;
}

function makeStats(overrides: Partial<TranscodeStatsView> = {}): TranscodeStatsView {
	return {
		tasks_by_status: {},
		total_tasks: 0,
		gpus_total: 1,
		gpus_available: 1,
		max_parallel: 2,
		...overrides
	} as TranscodeStatsView;
}

function makeGpu(overrides: Partial<GpuView> = {}): GpuView {
	return {
		id: 'gpu-0',
		vendor: 'nvenc',
		device_path: '/dev/nvidia0',
		encoder_kinds: ['h264'],
		status: 'available',
		enabled: true,
		...overrides
	} as GpuView;
}

function renderPanel(props: { workers?: TranscodeWorkerView[]; stats?: TranscodeStatsView; gpus?: GpuView[] } = {}) {
	return renderComponent(WorkerPoolPanel, {
		workers: [],
		stats: makeStats(),
		gpus: [],
		...props
	});
}

beforeEach(() => {
	vi.useFakeTimers({ toFake: ['Date'] });
	vi.setSystemTime(new Date('2025-06-15T10:05:30Z'));
});

afterEach(() => {
	cleanup();
	vi.useRealTimers();
});

describe('WorkerPoolPanel', () => {
	it('shows the worker count against max_parallel', () => {
		renderPanel({ workers: [makeWorker()], stats: makeStats({ max_parallel: 3 }) });
		expect(screen.getByText(/Workers 1\/3 active/)).toBeInTheDocument();
	});

	it('marks the dot active when there is at least one worker', () => {
		const { container } = renderPanel({ workers: [makeWorker()] });
		expect(container.querySelector('.transcoder-page-worker-dot')).toHaveAttribute('data-active', 'true');
	});

	it('marks the dot inactive when there are no workers', () => {
		const { container } = renderPanel();
		expect(container.querySelector('.transcoder-page-worker-dot')).toHaveAttribute('data-active', 'false');
	});

	it('shows the GPU availability and the queued count', () => {
		renderPanel({ stats: makeStats({ gpus_available: 1, gpus_total: 2, tasks_by_status: { queued: 4 } }) });
		expect(screen.getByText(/GPUs: 1\/2 available/)).toHaveTextContent('Queue: 4 queued');
	});

	it('shows 0 queued when tasks_by_status has no queued entry', () => {
		renderPanel();
		expect(screen.getByText(/GPUs:/)).toHaveTextContent('Queue: 0 queued');
	});

	it('shows the GPU rows and the manage link for a non-empty gpus list', () => {
		renderPanel({ gpus: [makeGpu(), makeGpu({ id: 'gpu-1', device_path: '/dev/nvidia1' })] });
		expect(screen.getByTestId('gpu-rows')).toBeInTheDocument();
		expect(screen.getByText('/dev/nvidia0')).toBeInTheDocument();
		expect(screen.getByText('/dev/nvidia1')).toBeInTheDocument();
		expect(screen.getByText('Manage GPUs in Settings')).toHaveAttribute('href', '/settings#transcoding');
	});

	it('hides the GPU rows and the manage link for an empty gpus list', () => {
		renderPanel();
		expect(screen.queryByTestId('gpu-rows')).not.toBeInTheDocument();
		expect(screen.queryByText('Manage GPUs in Settings')).not.toBeInTheDocument();
	});

	it('renders no worker grid when there are no workers', () => {
		const { container } = renderPanel();
		expect(container.querySelector('.grid')).not.toBeInTheDocument();
	});

	it('uses multi-column grid classes when max_parallel is above 1', () => {
		const { container } = renderPanel({ workers: [makeWorker()], stats: makeStats({ max_parallel: 2 }) });
		const grid = container.querySelector('.grid');
		expect(grid).toHaveClass('sm:grid-cols-2', 'lg:grid-cols-3');
	});

	it('uses a single-column grid when max_parallel is 1', () => {
		const { container } = renderPanel({ workers: [makeWorker()], stats: makeStats({ max_parallel: 1 }) });
		const grid = container.querySelector('.grid');
		expect(grid).not.toHaveClass('sm:grid-cols-2');
		expect(grid).not.toHaveClass('lg:grid-cols-3');
	});

	it('shows the claimed_by name after the task number', () => {
		renderPanel({ workers: [makeWorker({ claimed_by: 'gpu-7' })] });
		expect(screen.getByText(/Task #t-1/)).toBeInTheDocument();
		expect(screen.getByText(/gpu-7/)).toHaveTextContent('— gpu-7');
	});

	it('omits the claimed_by part when the worker has none', () => {
		const { container } = renderPanel({ workers: [makeWorker({ claimed_by: null })] });
		expect(container.querySelector('.transcoder-page-worker-claimed')).not.toBeInTheDocument();
	});

	it('uses output_path as the task title', () => {
		const { container } = renderPanel({ workers: [makeWorker()] });
		expect(container.querySelector('.transcoder-page-worker-task')).toHaveAttribute(
			'title',
			'/media/transcode/movie1.mkv'
		);
	});

	it('falls back to source_track_id for the task title without an output_path', () => {
		const { container } = renderPanel({ workers: [makeWorker({ output_path: null })] });
		expect(container.querySelector('.transcoder-page-worker-task')).toHaveAttribute('title', 'track-1');
	});

	it('shows the percentage and the time since the heartbeat', () => {
		renderPanel({ workers: [makeWorker({ progress_pct: 42 })] });
		expect(screen.getByText(/42%/)).toHaveTextContent('42%· 30s since heartbeat');
	});

	it('shows only the percentage when the heartbeat cannot be parsed', () => {
		renderPanel({ workers: [makeWorker({ progress_pct: 42, claim_heartbeat_at: 'not-a-date' })] });
		const line = screen.getByText(/42%/);
		expect(line).toHaveClass('transcoder-page-worker-heartbeat');
		expect(line).not.toHaveTextContent('since heartbeat');
	});

	it('shows the idle percentage line when there is no heartbeat', () => {
		renderPanel({ workers: [makeWorker({ progress_pct: 7, claim_heartbeat_at: null })] });
		const line = screen.getByText('7%');
		expect(line).toHaveClass('transcoder-page-worker-heartbeat-idle');
	});
});
