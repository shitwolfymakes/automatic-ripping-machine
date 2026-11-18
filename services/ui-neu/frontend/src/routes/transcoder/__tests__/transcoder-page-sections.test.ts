// Pins the Transcoder page's remaining sections before the page is split
// into helpers, classes and components. transcoder-page.test.ts covers the
// happy paths; this file covers the gaps it leaves.
//
// State isolation: `transcoderStats`, `transcoderWorkers` and the jobs cache
// are module-level, so every test calls vi.resetModules() and dynamically
// imports the page, the stores and the mocked API again (see `harness`).
// vitest keeps the mock functions themselves across a reset, so `harness`
// also resets each one to its default.
import { describe, it, expect, vi, afterEach } from 'vitest';
import type { TranscodeTaskView, TranscodeWorkerView, TranscodeStatsView } from '$lib/types/api.gen';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin')
	};
});

vi.mock('$lib/api/transcoder', () => ({
	fetchTranscoderStats: vi.fn(() =>
		Promise.resolve({
			tasks_by_status: { queued: 2, in_progress: 1, done: 10, failed: 1 },
			total_tasks: 14,
			gpus_total: 1,
			gpus_available: 0,
			max_parallel: 2
		})
	),
	fetchTranscoderJobs: vi.fn(() => Promise.resolve([])),
	fetchTranscoderWorkers: vi.fn(() => Promise.resolve([])),
	retryTranscoderJob: vi.fn(),
	deleteTranscoderJob: vi.fn()
}));

vi.mock('$lib/api/ws', () => ({
	wsClient: {
		start: vi.fn(),
		subscribe: vi.fn(() => () => {})
	}
}));

vi.mock('$lib/api/gpus', () => ({
	fetchGpus: vi.fn(() => Promise.resolve([]))
}));

vi.mock('$lib/api/logs', () => ({
	fetchStructuredTranscoderLogContent: vi.fn(() => Promise.resolve({ entries: [] })),
	fetchStructuredLogContent: vi.fn(() => Promise.resolve({ entries: [] }))
}));

vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	const store = writable({});
	return { dashboard: { ...store, start: vi.fn(), stop: vi.fn(), error: writable(null) } };
});

function makeTask(overrides: Partial<TranscodeTaskView> = {}): TranscodeTaskView {
	return {
		id: 't-1',
		session_application_id: 'sap_1',
		job_id: 'job_abc',
		source_track_id: 'track-1',
		status: 'queued',
		output_path: '/media/transcode/movie1.mkv',
		progress_pct: 0,
		attempts: 0,
		claimed_by: null,
		claim_heartbeat_at: null,
		last_error: null,
		created_at: '2025-06-15T10:00:00Z',
		updated_at: '2025-06-15T10:05:00Z',
		...overrides
	} as TranscodeTaskView;
}

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

function deferred<T>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

async function harness() {
	vi.resetModules();
	const utils = await import('$lib/testing/render');
	const Page = (await import('../+page.svelte')).default;
	const api = await import('$lib/api/transcoder');
	const gpus = await import('$lib/api/gpus');
	const ws = await import('$lib/api/ws');
	const config = await import('$lib/stores/config');
	const stores = await import('$lib/stores/transcoder');
	// vitest keeps one instance of each mock across resetModules, so put the
	// mocks back to their defaults (and drop their call history) here too.
	const fetchStats = vi.mocked(api.fetchTranscoderStats);
	const fetchJobs = vi.mocked(api.fetchTranscoderJobs);
	const fetchWorkers = vi.mocked(api.fetchTranscoderWorkers);
	const retryJob = vi.mocked(api.retryTranscoderJob);
	const fetchGpus = vi.mocked(gpus.fetchGpus);
	const subscribe = vi.mocked(ws.wsClient.subscribe);
	fetchStats
		.mockReset()
		.mockImplementation(() =>
			Promise.resolve(
				makeStats({ tasks_by_status: { queued: 2, in_progress: 1, done: 10, failed: 1 }, total_tasks: 14 })
			)
		);
	fetchJobs.mockReset().mockImplementation(() => Promise.resolve([]));
	fetchWorkers.mockReset().mockImplementation(() => Promise.resolve([]));
	retryJob.mockReset();
	fetchGpus.mockReset().mockImplementation(() => Promise.resolve([]));
	subscribe.mockReset().mockImplementation(() => () => {});
	return {
		...utils,
		Page,
		fetchStats,
		fetchJobs,
		fetchWorkers,
		retryJob,
		fetchGpus,
		subscribe,
		refreshStats: stores.transcoderStats.refresh,
		setTranscoderEnabled: config.setTranscoderEnabled
	};
}

type Harness = Awaited<ReturnType<typeof harness>>;

let current: Harness | null = null;

async function setup(): Promise<Harness> {
	current = await harness();
	return current;
}

function transcodeEventHandler(h: Harness): () => void {
	const call = h.subscribe.mock.calls.find((c) => c[0] === 'transcode.events');
	return call![1] as () => void;
}

function isSkeletonShown(): boolean {
	return document.querySelector('[aria-busy="true"]') !== null;
}

function jobMeta(): string {
	return document.querySelector('.transcoder-page-job-meta-sm')?.textContent ?? '';
}

afterEach(() => {
	current?.cleanup();
	current = null;
	vi.useRealTimers();
});

describe('formatDuration through the worker pool', () => {
	it('shows seconds under a minute, and minutes without hours', async () => {
		vi.useFakeTimers({ toFake: ['Date'] });
		vi.setSystemTime(new Date('2025-06-15T10:06:00Z'));
		const h = await setup();
		h.fetchWorkers.mockResolvedValue([
			makeWorker({ task_id: 'w-1', claim_heartbeat_at: '2025-06-15T10:05:30Z' }),
			makeWorker({ task_id: 'w-2', claim_heartbeat_at: '2025-06-15T10:04:30Z' })
		]);
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(document.querySelectorAll('.transcoder-page-worker-card')).toHaveLength(2));
		const text = document.body.textContent ?? '';
		expect(text).toMatch(/50%\s*·\s*30s since heartbeat/);
		expect(text).toMatch(/50%\s*·\s*1m 30s since heartbeat/);
	});

	it('omits "since heartbeat" when the heartbeat is unparsable', async () => {
		const h = await setup();
		h.fetchWorkers.mockResolvedValue([makeWorker({ claim_heartbeat_at: 'not-a-date' })]);
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(document.querySelectorAll('.transcoder-page-worker-card')).toHaveLength(1));
		const heartbeat = document.querySelector('.transcoder-page-worker-heartbeat');
		expect(heartbeat?.textContent?.trim()).toBe('50%');
		expect(document.body.textContent).not.toContain('since heartbeat');
	});

	it('shows no Took when a done task start is unparsable', async () => {
		const h = await setup();
		h.fetchJobs.mockResolvedValue([makeTask({ status: 'done', started_at: 'garbage' })]);
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.screen.getByText('movie1.mkv', { selector: 'h3' })).toBeInTheDocument());
		expect(jobMeta()).not.toContain('Took');
	});

	it('shows no Took when a done task end is unparsable', async () => {
		const h = await setup();
		h.fetchJobs.mockResolvedValue([
			makeTask({ status: 'done', started_at: '2025-06-15T10:00:00Z', updated_at: 'garbage' })
		]);
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.screen.getByText('movie1.mkv', { selector: 'h3' })).toBeInTheDocument());
		expect(jobMeta()).not.toContain('Took');
	});
});

describe('worker pool', () => {
	it('renders no worker cards when there are no workers', async () => {
		const h = await setup();
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.screen.getByText(/Workers 0\/2 active/)).toBeInTheDocument());
		expect(document.querySelector('.transcoder-page-worker-card')).toBeNull();
	});

	it('shows a worker with its claimant, and one without', async () => {
		const h = await setup();
		h.fetchWorkers.mockResolvedValue([
			makeWorker({ task_id: 'w-1', claimed_by: 'gpu-7' }),
			makeWorker({ task_id: 'w-2', claimed_by: null, output_path: null, source_track_id: 'track-9' })
		]);
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(document.querySelectorAll('.transcoder-page-worker-card')).toHaveLength(2));
		const claimed = document.querySelectorAll('.transcoder-page-worker-claimed');
		expect(claimed).toHaveLength(1);
		expect(claimed[0].textContent).toContain('gpu-7');
		const titles = [...document.querySelectorAll('.transcoder-page-worker-task')];
		expect(titles[0].getAttribute('title')).toBe('/media/transcode/movie1.mkv');
		expect(titles[1].getAttribute('title')).toBe('track-9');
	});

	it('shows the bare progress when a worker has no heartbeat', async () => {
		const h = await setup();
		h.fetchWorkers.mockResolvedValue([makeWorker({ claim_heartbeat_at: null })]);
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(document.querySelector('.transcoder-page-worker-heartbeat-idle')).not.toBeNull());
		expect(document.querySelector('.transcoder-page-worker-heartbeat')).toBeNull();
	});

	it('uses a multi-column grid only when more than one worker may run', async () => {
		const h = await setup();
		h.fetchWorkers.mockResolvedValue([makeWorker()]);
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(document.querySelector('.transcoder-page-worker-card')).not.toBeNull());
		const grid = document.querySelector('.transcoder-page-worker-card')!.parentElement!;
		expect(grid.className).toContain('sm:grid-cols-2');
		h.cleanup();

		const single = await setup();
		single.fetchStats.mockResolvedValue(makeStats({ max_parallel: 1 }));
		single.fetchWorkers.mockResolvedValue([makeWorker()]);
		single.renderComponent(single.Page);
		await single.waitFor(() => expect(document.querySelector('.transcoder-page-worker-card')).not.toBeNull());
		const singleGrid = document.querySelector('.transcoder-page-worker-card')!.parentElement!;
		expect(singleGrid.className).not.toContain('sm:grid-cols-2');
	});
});

describe('stats states', () => {
	it('shows the stats skeleton before the first poll answers', async () => {
		const h = await setup();
		h.fetchStats.mockReturnValue(new Promise(() => {}));
		h.renderComponent(h.Page);
		expect(document.querySelector('.transcoder-page-skeleton-title')).not.toBeNull();
		expect(h.screen.queryByText('Transcoder Offline')).not.toBeInTheDocument();
		expect(h.screen.queryByText(/Workers \d/)).not.toBeInTheDocument();
	});

	it('shows the error alert and the offline banner when the stats poll fails', async () => {
		const h = await setup();
		h.fetchStats.mockRejectedValue(new Error('connection refused'));
		h.renderComponent(h.Page);
		await h.waitFor(() =>
			expect(h.screen.getByText('Failed to reach transcoder: connection refused')).toBeInTheDocument()
		);
		expect(h.screen.getByText('Transcoder Offline')).toBeInTheDocument();
		expect(document.querySelector('.transcoder-page-skeleton-title')).toBeNull();
	});
});

describe('stats recovering and failing again', () => {
	it('swaps the stats block for the error banners when a poll fails, and back when it recovers', async () => {
		const h = await setup();
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.screen.getByText(/Workers 0\/2 active/)).toBeInTheDocument());

		h.fetchStats.mockRejectedValue(new Error('timed out'));
		await h.refreshStats();
		await h.waitFor(() => expect(h.screen.getByText('Failed to reach transcoder: timed out')).toBeInTheDocument());
		expect(h.screen.getByText('Transcoder Offline')).toBeInTheDocument();

		h.fetchStats.mockResolvedValue(makeStats());
		await h.refreshStats();
		// jsdom never finishes the fade-out, so the old banners stay in the
		// DOM; the stats block coming back is what shows the recovery.
		await h.waitFor(() => expect(h.screen.getAllByText(/Workers 0\/2 active/).length).toBeGreaterThan(0));
	});
});

describe('GPU rows', () => {
	it('shows no GPU rows when loading them fails', async () => {
		const h = await setup();
		h.fetchGpus.mockRejectedValue(new Error('gpus down'));
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.screen.getByText(/Workers 0\/2 active/)).toBeInTheDocument());
		await h.waitFor(() => expect(h.fetchGpus).toHaveBeenCalled());
		expect(h.screen.queryByTestId('gpu-rows')).not.toBeInTheDocument();
	});

	it('coalesces transcode events within 300 ms into one reload', async () => {
		vi.useFakeTimers();
		const h = await setup();
		h.renderComponent(h.Page);
		await vi.advanceTimersByTimeAsync(200);
		const before = h.fetchGpus.mock.calls.length;
		const handler = transcodeEventHandler(h);
		handler();
		await vi.advanceTimersByTimeAsync(200);
		handler();
		await vi.advanceTimersByTimeAsync(299);
		expect(h.fetchGpus.mock.calls.length - before).toBe(0);
		await vi.advanceTimersByTimeAsync(2);
		expect(h.fetchGpus.mock.calls.length - before).toBe(1);
	});

	it('drops a pending reload when the page unmounts', async () => {
		vi.useFakeTimers();
		const h = await setup();
		const { unmount } = h.renderComponent(h.Page);
		await vi.advanceTimersByTimeAsync(200);
		const before = h.fetchGpus.mock.calls.length;
		transcodeEventHandler(h)();
		unmount();
		await vi.advanceTimersByTimeAsync(1000);
		expect(h.fetchGpus.mock.calls.length - before).toBe(0);
	});
});

describe('ripper-only deployment', () => {
	it('shows no held banner when the held count cannot be fetched', async () => {
		const h = await setup();
		h.setTranscoderEnabled(false);
		h.fetchStats.mockRejectedValue(new Error('no transcoder'));
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.fetchStats).toHaveBeenCalledTimes(1));
		await new Promise((r) => setTimeout(r, 0));
		expect(h.screen.getByTestId('transcoder-unavailable')).toBeInTheDocument();
		expect(h.screen.queryByTestId('transcoder-held-encode-tasks')).not.toBeInTheDocument();
	});

	it('uses the singular wording when one encode task is held', async () => {
		const h = await setup();
		h.setTranscoderEnabled(false);
		h.fetchStats.mockResolvedValue(makeStats({ queued_encode_tasks: 1 }));
		h.renderComponent(h.Page);
		await h.waitFor(() =>
			expect(h.screen.getByTestId('transcoder-held-encode-tasks')).toHaveTextContent(
				'1 encode task is held. Re-run setup without --ripper-only to resume them.'
			)
		);
	});
});

describe('jobs list', () => {
	it('says so when there are no tasks', async () => {
		const h = await setup();
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.screen.getByText('No transcode tasks found.')).toBeInTheDocument());
	});

	it('shows the error message when loading jobs fails with an Error', async () => {
		const h = await setup();
		h.fetchJobs.mockRejectedValue(new Error('jobs exploded'));
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.screen.getByText('Failed to load: jobs exploded')).toBeInTheDocument());
	});

	it('shows a generic message when loading jobs fails with a non-Error', async () => {
		const h = await setup();
		h.fetchJobs.mockRejectedValue('nope');
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.screen.getByText('Failed to load: Failed to load jobs')).toBeInTheDocument());
	});

	it('titles a card without an output path "Task #<id>" and falls back to the source track id', async () => {
		const h = await setup();
		h.fetchJobs.mockResolvedValue([makeTask({ id: 't-9', output_path: null, source_track_id: 'track-9' })]);
		h.renderComponent(h.Page);
		const title = await h.screen.findByText('Task #t-9');
		expect(title.getAttribute('title')).toBe('track-9');
	});

	it('omits Queued and Updated when a card has no timestamps', async () => {
		const h = await setup();
		h.fetchJobs.mockResolvedValue([makeTask({ created_at: null, updated_at: null } as Partial<TranscodeTaskView>)]);
		h.renderComponent(h.Page);
		await h.screen.findByText('movie1.mkv');
		expect(jobMeta()).not.toContain('Queued');
		expect(jobMeta()).not.toContain('Updated');
	});

	it('dismisses a failed-action banner, naming the verb when the failure is not an Error', async () => {
		const h = await setup();
		h.fetchJobs.mockResolvedValue([makeTask({ status: 'failed' })]);
		h.retryJob.mockRejectedValueOnce('boom');
		h.renderComponent(h.Page);
		await h.fireEvent.click(await h.screen.findByText('Retry'));
		await h.waitFor(() => expect(h.screen.getByText(/Retry failed/)).toBeInTheDocument());
		await h.fireEvent.click(h.screen.getByText('Dismiss'));
		expect(h.screen.queryByText(/Retry failed/)).not.toBeInTheDocument();
	});
});

describe('jobs polling', () => {
	it('refetches the jobs every 5 s without the skeleton while tasks are queued, and stops once none are', async () => {
		vi.useFakeTimers();
		const h = await setup();
		h.fetchStats.mockResolvedValue(makeStats({ tasks_by_status: { queued: 1 }, total_tasks: 1 }));
		h.fetchJobs.mockResolvedValue([makeTask()]);
		h.renderComponent(h.Page);
		await vi.advanceTimersByTimeAsync(200);
		expect(isSkeletonShown()).toBe(false);
		const first = h.fetchJobs.mock.calls.length;

		const pending = deferred<TranscodeTaskView[]>();
		h.fetchJobs.mockReturnValueOnce(pending.promise);
		await vi.advanceTimersByTimeAsync(5000);
		expect(h.fetchJobs.mock.calls.length).toBeGreaterThan(first);
		expect(isSkeletonShown()).toBe(false);
		pending.resolve([makeTask()]);

		// The next stats poll reports nothing queued, which stops the timer.
		h.fetchStats.mockResolvedValue(makeStats({ tasks_by_status: { done: 1 }, total_tasks: 1 }));
		await vi.advanceTimersByTimeAsync(5000);
		const settled = h.fetchJobs.mock.calls.length;
		await vi.advanceTimersByTimeAsync(20000);
		expect(h.fetchJobs.mock.calls).toHaveLength(settled);
	});
});

describe('switching tabs', () => {
	it('shows the skeleton on the first visit of a tab and not on a revisit', async () => {
		const h = await setup();
		h.fetchJobs.mockResolvedValue([makeTask()]);
		h.renderComponent(h.Page);
		await h.screen.findByText('movie1.mkv');
		expect(isSkeletonShown()).toBe(false);

		const first = deferred<TranscodeTaskView[]>();
		h.fetchJobs.mockReturnValueOnce(first.promise);
		await h.fireEvent.click(h.screen.getByRole('button', { name: 'Queued' }));
		expect(h.fetchJobs).toHaveBeenLastCalledWith({ status: 'queued' });
		expect(isSkeletonShown()).toBe(true);
		first.resolve([makeTask({ id: 't-q', output_path: '/media/q.mkv' })]);
		await h.screen.findByText('q.mkv');
		expect(isSkeletonShown()).toBe(false);

		const second = deferred<TranscodeTaskView[]>();
		h.fetchJobs.mockReturnValueOnce(second.promise);
		await h.fireEvent.click(h.screen.getByRole('button', { name: 'Queued' }));
		expect(h.fetchJobs).toHaveBeenLastCalledWith({ status: 'queued' });
		expect(isSkeletonShown()).toBe(false);
		expect(h.screen.getByText('q.mkv')).toBeInTheDocument();
		second.resolve([makeTask({ id: 't-q', output_path: '/media/q.mkv' })]);
	});

	// #537: the jobs request is not tied to the tab that issued it, so a slow
	// response for the first tab lands under whichever tab is active when it
	// arrives. Pinned as today's behaviour, not as the intended one.
	it('stores a late response from the previous tab under the new tab and shows it there (#537)', async () => {
		const h = await setup();
		const allRequest = deferred<TranscodeTaskView[]>();
		h.fetchJobs.mockReturnValueOnce(allRequest.promise);
		h.renderComponent(h.Page);
		await h.waitFor(() => expect(h.fetchJobs).toHaveBeenCalledTimes(1));

		h.fetchJobs.mockResolvedValueOnce([makeTask({ id: 't-q', output_path: '/media/queued-task.mkv' })]);
		await h.fireEvent.click(h.screen.getByRole('button', { name: 'Queued' }));
		await h.screen.findByText('queued-task.mkv');

		allRequest.resolve([makeTask({ id: 't-a', output_path: '/media/all-task.mkv' })]);
		await h.screen.findByText('all-task.mkv');
		expect(h.screen.getByRole('button', { name: 'Queued' })).toHaveAttribute('data-selected', 'true');

		// The cache now holds that response under the Queued tab: revisiting
		// Queued paints it with no skeleton.
		const revisit = deferred<TranscodeTaskView[]>();
		h.fetchJobs.mockReturnValueOnce(revisit.promise);
		await h.fireEvent.click(h.screen.getByRole('button', { name: 'Queued' }));
		expect(isSkeletonShown()).toBe(false);
		expect(h.screen.getByText('all-task.mkv')).toBeInTheDocument();
		revisit.resolve([]);
	});
});
