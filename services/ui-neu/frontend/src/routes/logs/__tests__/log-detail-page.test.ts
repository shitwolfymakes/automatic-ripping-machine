import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { WSEnvelope } from '$lib/api/ws';
import LogDetailPage from '../[job_id]/+page.svelte';

const ENTRIES = [
	{ level: 'info', logger: 'arm', event: 'started ripping', service: 'arm-backend' },
	{ level: 'error', logger: 'ripper', event: 'makemkv failed', service: 'arm-ripper-XYZ' }
];

const fetchJobLog = vi.fn();
vi.mock('$lib/api/logs', () => ({
	fetchJobLog: (...a: unknown[]) => fetchJobLog(...a),
	jobLogDownloadUrl: (id: string) => `/api/logs/${id}.zip`,
	toLogEntry: (raw: Record<string, unknown>) => ({
		timestamp: raw.ts ?? null,
		level: raw.level,
		logger: raw.service,
		event: raw.msg,
		job_id: raw.job_id ?? null,
		label: null,
		service: raw.service
	})
}));

const subscribeMock = vi.fn();
let wsHandler: ((env: WSEnvelope) => void) | null = null;
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		subscribe: (topic: string, handler: (env: WSEnvelope) => void) => {
			wsHandler = handler;
			return subscribeMock(topic, handler);
		}
	}
}));

// SvelteKit page store: provide the route param (matches the repo's existing
// $app/stores mock pattern — async + await import, NOT require).
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ params: { job_id: 'job_a' } }) };
});

beforeEach(() => {
	fetchJobLog.mockReset();
	subscribeMock.mockReset();
	subscribeMock.mockImplementation(() => vi.fn());
	wsHandler = null;
});

describe('Logs single-job viewer', () => {
	afterEach(() => cleanup());

	it('renders entries from fetchJobLog', async () => {
		fetchJobLog.mockResolvedValue(ENTRIES);
		renderComponent(LogDetailPage);
		await waitFor(() => {
			expect(screen.getByText('started ripping')).toBeInTheDocument();
			expect(screen.getByText('makemkv failed')).toBeInTheDocument();
		});
	});

	it('filters by level', async () => {
		fetchJobLog.mockResolvedValue(ENTRIES);
		renderComponent(LogDetailPage);
		await waitFor(() => expect(screen.getByText('started ripping')).toBeInTheDocument());
		const sel = screen.getByLabelText(/level/i);
		await fireEvent.change(sel, { target: { value: 'error' } });
		await waitFor(() => {
			expect(screen.queryByText('started ripping')).not.toBeInTheDocument();
			expect(screen.getByText('makemkv failed')).toBeInTheDocument();
		});
	});

	it('filters by free text', async () => {
		fetchJobLog.mockResolvedValue(ENTRIES);
		renderComponent(LogDetailPage);
		await waitFor(() => expect(screen.getByText('started ripping')).toBeInTheDocument());
		const search = screen.getByPlaceholderText(/filter/i);
		await fireEvent.input(search, { target: { value: 'makemkv' } });
		await waitFor(() => {
			expect(screen.queryByText('started ripping')).not.toBeInTheDocument();
			expect(screen.getByText('makemkv failed')).toBeInTheDocument();
		});
	});

	it('shows the empty state when a job has no log lines', async () => {
		fetchJobLog.mockResolvedValue([]);
		renderComponent(LogDetailPage);
		await waitFor(() => expect(screen.getByText(/no log entries/i)).toBeInTheDocument());
	});

	it('shows a download link to the per-job zip', async () => {
		fetchJobLog.mockResolvedValue(ENTRIES);
		renderComponent(LogDetailPage);
		await waitFor(() => {
			expect(screen.getByText(/download/i).closest('a')).toHaveAttribute('href', '/api/logs/job_a.zip');
		});
	});

	it('re-fetches when Refresh is clicked', async () => {
		fetchJobLog.mockResolvedValue(ENTRIES);
		renderComponent(LogDetailPage);
		await waitFor(() => expect(screen.getByText('started ripping')).toBeInTheDocument());
		const callsBefore = fetchJobLog.mock.calls.length;
		const refresh = screen.getByText(/refresh/i);
		await fireEvent.click(refresh);
		await waitFor(() => expect(fetchJobLog.mock.calls.length).toBeGreaterThan(callsBefore));
	});

	it('shows an error message when the fetch fails', async () => {
		fetchJobLog.mockRejectedValueOnce(new Error('boom'));
		renderComponent(LogDetailPage);
		await waitFor(() => expect(screen.getByText(/could not load log/i)).toBeInTheDocument());
	});

	it('subscribes to the live feed for this job on mount', async () => {
		fetchJobLog.mockResolvedValue(ENTRIES);
		renderComponent(LogDetailPage);
		await waitFor(() => expect(subscribeMock).toHaveBeenCalledWith('logs.job_a', expect.any(Function)));
	});

	it('appends a live line delivered via the WS subscription', async () => {
		fetchJobLog.mockResolvedValue(ENTRIES);
		renderComponent(LogDetailPage);
		await waitFor(() => expect(screen.getByText('started ripping')).toBeInTheDocument());

		wsHandler?.({
			op: 'event',
			event_id: 'evt_1',
			event_type: 'log.line',
			emitted_at: 'now',
			topic: 'logs.job_a',
			job_id: 'job_a',
			track_id: null,
			payload: { ts: 't', level: 'info', service: 'arm-transcode-t1', job_id: 'job_a', msg: 'live line', extra: {} }
		});

		await waitFor(() => {
			expect(screen.getByText('live line')).toBeInTheDocument();
		});
	});

	it('unsubscribes on destroy', async () => {
		const unsub = vi.fn();
		subscribeMock.mockReturnValue(unsub);
		fetchJobLog.mockResolvedValue(ENTRIES);
		renderComponent(LogDetailPage);
		await waitFor(() => expect(subscribeMock).toHaveBeenCalled());
		cleanup();
		expect(unsub).toHaveBeenCalled();
	});
});
