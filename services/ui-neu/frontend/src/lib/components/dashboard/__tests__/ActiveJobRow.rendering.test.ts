import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import ActiveJobRow from '../ActiveJobRow.svelte';
import { createJob } from '../../../__fixtures__/job';

const live = vi.hoisted(() => ({ value: { rip: null, transcode: null } as Record<string, unknown> }));
vi.mock('$lib/stores/job-live.svelte', () => ({
	jobLive: { watch: vi.fn(() => () => {}), get: vi.fn(() => live.value) }
}));

const sample = (over: Record<string, unknown> = {}) => ({
	pct: 42,
	etaSeconds: null,
	fps: null,
	avgFps: null,
	pass: null,
	bytesDone: null,
	bytesTotal: null,
	rateBps: null,
	phase: null,
	...over
});

describe('ActiveJobRow', () => {
	beforeEach(() => {
		live.value = { rip: null, transcode: null };
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	describe('rendering', () => {
		it('renders job title', () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			expect(screen.getByText('Test Movie')).toBeInTheDocument();
		});

		it('renders Untitled when no title', () => {
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ title: null }) }
			});
			expect(screen.getAllByText('Untitled').length).toBeGreaterThan(0);
		});

		it('renders status badge', () => {
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ status: 'ripped' }) }
			});
			expect(screen.getAllByText('Ripped').length).toBeGreaterThan(0);
		});

		it('renders year when present', () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			expect(screen.getByText('2024')).toBeInTheDocument();
		});
	});

	describe('live progress', () => {
		it('shows the indeterminate bar when active with no live sample', () => {
			const { container } = renderComponent(ActiveJobRow, { props: { job: createJob({ status: 'ripping' }) } });
			expect(container.querySelector('[data-indeterminate="true"]')).not.toBeNull();
			expect(screen.queryByText('Waiting for the first progress report')).toBeNull();
		});

		it('renders a determinate bar from the rip sample', () => {
			live.value = { rip: sample(), transcode: null };
			renderComponent(ActiveJobRow, { props: { job: createJob({ status: 'ripping' }) } });
			expect(screen.getByText('42%')).toBeInTheDocument();
		});

		it('shows the ETA from the rip sample', () => {
			live.value = { rip: sample({ pct: 50, etaSeconds: 150 }), transcode: null };
			renderComponent(ActiveJobRow, { props: { job: createJob({ status: 'ripping' }) } });
			expect(screen.getByText('2m 30s left')).toBeInTheDocument();
		});

		it('shows the transfer line from the rip sample', () => {
			live.value = { rip: sample({ bytesDone: 1024 ** 3, bytesTotal: 2 * 1024 ** 3 }), transcode: null };
			const { container } = renderComponent(ActiveJobRow, { props: { job: createJob({ status: 'ripping' }) } });
			expect(container.querySelector('.mono')).toHaveTextContent('1 GB of 2 GB');
		});

		it('falls back to the transcode sample when nothing is ripping', () => {
			live.value = { rip: null, transcode: { ...sample({ pct: 77 }), taskId: 't1' } };
			renderComponent(ActiveJobRow, {
				props: {
					job: createJob({
						status: 'ripped',
						transcode_progress: {
							state: 'transcoding',
							tasks_total: 1,
							tasks_done: 0,
							tasks_failed: 0,
							percent: 10
						} as never
					})
				}
			});
			expect(screen.getByText('77%')).toBeInTheDocument();
		});

		const transcodingAt = (percent: number) =>
			createJob({
				status: 'ripped',
				transcode_progress: { state: 'transcoding', tasks_total: 1, tasks_done: 0, tasks_failed: 0, percent } as never
			});

		it('shows the snapshot percent for a transcoding job with no live sample, as the card does', () => {
			renderComponent(ActiveJobRow, { props: { job: transcodingAt(35) } });
			expect(screen.getByText('35%')).toBeInTheDocument();
			expect(screen.queryByText('Waiting for the first progress report')).not.toBeInTheDocument();
		});

		it('shows the snapshot percent when the live transcode sample has no percent', () => {
			live.value = { rip: null, transcode: { ...sample({ pct: null, etaSeconds: 150 }), taskId: 't1' } };
			renderComponent(ActiveJobRow, { props: { job: transcodingAt(35) } });
			expect(screen.getByText('35%')).toBeInTheDocument();
			expect(screen.getByText('2m 30s left')).toBeInTheDocument();
		});
	});

	describe('watching', () => {
		it('watches the job by id and status and releases on unmount', async () => {
			const { jobLive } = await import('$lib/stores/job-live.svelte');
			const off = vi.fn();
			vi.mocked(jobLive.watch).mockReturnValueOnce(off);
			const { unmount } = renderComponent(ActiveJobRow, {
				props: { job: createJob({ id: 'job_w', status: 'ripping' }) }
			});
			expect(jobLive.watch).toHaveBeenCalledWith({ id: 'job_w', status: 'ripping' });
			unmount();
			expect(off).toHaveBeenCalled();
		});

		it('does not watch a job without a status', async () => {
			const { jobLive } = await import('$lib/stores/job-live.svelte');
			vi.mocked(jobLive.watch).mockClear();
			renderComponent(ActiveJobRow, { props: { job: createJob({ status: undefined as never }) } });
			expect(jobLive.watch).not.toHaveBeenCalled();
		});

		it('does not watch while the job is missing', async () => {
			const { jobLive } = await import('$lib/stores/job-live.svelte');
			vi.mocked(jobLive.watch).mockClear();
			renderComponent(ActiveJobRow, { props: {} });
			expect(jobLive.watch).not.toHaveBeenCalled();
		});
	});

	describe('skeleton', () => {
		it('renders skeleton placeholder when job prop is omitted', () => {
			const { container } = renderComponent(ActiveJobRow, { props: {} });
			const placeholder = container.querySelector('[aria-busy="true"], [data-variant="line"]');
			expect(placeholder).not.toBeNull();
		});
	});
});
