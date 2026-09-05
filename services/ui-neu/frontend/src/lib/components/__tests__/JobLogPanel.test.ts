import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';
import type { WSEnvelope } from '$lib/api/ws';

const fetchJobLogMock = vi.fn();
vi.mock('$lib/api/logs', async (orig) => {
	const actual = (await orig()) as Record<string, unknown>;
	return {
		...actual,
		fetchJobLog: (...a: unknown[]) => fetchJobLogMock(...a),
		jobLogDownloadUrl: (id: string) => `/api/logs/${id}.zip`
	};
});

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

import JobLogPanel from '$lib/components/JobLogPanel.svelte';

function raw(overrides: Partial<Record<string, unknown>> = {}) {
	return {
		ts: '2026-09-05T10:00:00Z',
		level: 'info',
		service: 'arm-backend',
		job_id: 'job_a',
		msg: 'line',
		extra: {},
		...overrides
	};
}

const ENTRIES = [
	{ timestamp: '2026-09-05T10:00:00Z', level: 'info', logger: 'arm', event: 'backend line', job_id: 'job_a', label: null, service: 'arm-backend' },
	{ timestamp: '2026-09-05T10:00:01Z', level: 'warning', logger: 'ripper', event: 'ripper line', job_id: 'job_a', label: null, service: 'arm-ripper-XYZ' },
	{ timestamp: '2026-09-05T10:00:02Z', level: 'error', logger: 'transcode', event: 'transcode line', job_id: 'job_a', label: null, service: 'arm-transcode-t1' }
];

beforeEach(() => {
	fetchJobLogMock.mockReset();
	subscribeMock.mockReset();
	subscribeMock.mockImplementation(() => vi.fn());
	wsHandler = null;
});

afterEach(() => cleanup());

describe('JobLogPanel', () => {
	it('renders lines from load()', async () => {
		fetchJobLogMock.mockResolvedValue(ENTRIES);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripped', defaultOpen: true } });
		await waitFor(() => {
			expect(screen.getByText('backend line')).toBeInTheDocument();
			expect(screen.getByText('ripper line')).toBeInTheDocument();
			expect(screen.getByText('transcode line')).toBeInTheDocument();
		});
	});

	it('shows the empty state when there are no lines', async () => {
		fetchJobLogMock.mockResolvedValue([]);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripped', defaultOpen: true } });
		await waitFor(() => {
			expect(screen.getByText(/no log lines for this job yet/i)).toBeInTheDocument();
		});
	});

	it('shows the error state in red on a failed load', async () => {
		fetchJobLogMock.mockRejectedValue(new Error('boom'));
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripped', defaultOpen: true } });
		await waitFor(() => {
			expect(screen.getByText(/boom/)).toBeInTheDocument();
		});
	});

	it('filters hide other services without dropping them from state', async () => {
		fetchJobLogMock.mockResolvedValue(ENTRIES);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripped', defaultOpen: true } });
		await waitFor(() => expect(screen.getByText('backend line')).toBeInTheDocument());

		const ripperBtn = screen.getByTestId('job-log-filter-ripper');
		await fireEvent.click(ripperBtn);

		await waitFor(() => {
			expect(screen.getByText('ripper line')).toBeInTheDocument();
			expect(screen.queryByText('backend line')).not.toBeInTheDocument();
			expect(screen.queryByText('transcode line')).not.toBeInTheDocument();
		});
		expect(ripperBtn).toHaveAttribute('aria-checked', 'true');
	});

	it('appends a live line delivered via the mocked wsClient.subscribe handler', async () => {
		fetchJobLogMock.mockResolvedValue([]);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripping', defaultOpen: true } });
		await waitFor(() => expect(screen.getByText(/no log lines/i)).toBeInTheDocument());

		expect(wsHandler).not.toBeNull();
		wsHandler?.({
			op: 'event',
			event_id: 'evt_1',
			event_type: 'log.line',
			emitted_at: 'now',
			topic: 'logs.job_a',
			job_id: 'job_a',
			track_id: null,
			payload: raw({ msg: 'live line' })
		});

		await waitFor(() => {
			expect(screen.getByText('live line')).toBeInTheDocument();
		});
	});

	it('header links point at the job log page and the download zip', async () => {
		fetchJobLogMock.mockResolvedValue([]);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripped', defaultOpen: true } });
		await waitFor(() => {
			expect(screen.getByTestId('job-log-open')).toHaveAttribute('href', '/logs/job_a');
			expect(screen.getByTestId('job-log-download')).toHaveAttribute('href', '/api/logs/job_a.zip');
		});
	});

	it('header links are rendered even when collapsed', async () => {
		fetchJobLogMock.mockResolvedValue([]);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripped', defaultOpen: false } });
		await waitFor(() => {
			expect(screen.getByTestId('job-log-open')).toBeInTheDocument();
			expect(screen.getByTestId('job-log-download')).toBeInTheDocument();
		});
	});

	it('is collapsed by default for a terminal job', async () => {
		fetchJobLogMock.mockResolvedValue(ENTRIES);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripped' } });
		await waitFor(() => expect(fetchJobLogMock).toHaveBeenCalled());
		expect(screen.queryByTestId('job-log-view')).not.toBeInTheDocument();
	});

	it('is open by default for an active job', async () => {
		fetchJobLogMock.mockResolvedValue(ENTRIES);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripping' } });
		await waitFor(() => {
			expect(screen.getByTestId('job-log-view')).toBeInTheDocument();
		});
	});

	it('subscribes to the WS feed only for an active job', async () => {
		fetchJobLogMock.mockResolvedValue([]);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripping', defaultOpen: true } });
		await waitFor(() => expect(subscribeMock).toHaveBeenCalledWith('logs.job_a', expect.any(Function)));
	});

	it('does not subscribe to the WS feed for a terminal job', async () => {
		fetchJobLogMock.mockResolvedValue(ENTRIES);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripped', defaultOpen: true } });
		await waitFor(() => expect(fetchJobLogMock).toHaveBeenCalled());
		expect(subscribeMock).not.toHaveBeenCalled();
	});

	it('calls stop() (unsubscribes) when status transitions to terminal', async () => {
		const unsub = vi.fn();
		subscribeMock.mockReturnValue(unsub);
		fetchJobLogMock.mockResolvedValue([]);
		const { rerender } = renderComponent(JobLogPanel, {
			props: { jobId: 'job_a', status: 'ripping', defaultOpen: true }
		});
		await waitFor(() => expect(subscribeMock).toHaveBeenCalled());

		await rerender({ jobId: 'job_a', status: 'ripped', defaultOpen: true });

		await waitFor(() => expect(unsub).toHaveBeenCalled());
	});

	it('shows a live indicator while subscribed', async () => {
		fetchJobLogMock.mockResolvedValue([]);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripping', defaultOpen: true } });
		await waitFor(() => {
			expect(screen.getByText(/live/i)).toBeInTheDocument();
		});
	});

	it('shows the line count in the header', async () => {
		fetchJobLogMock.mockResolvedValue(ENTRIES);
		renderComponent(JobLogPanel, { props: { jobId: 'job_a', status: 'ripped', defaultOpen: true } });
		await waitFor(() => {
			expect(screen.getByText(/3 lines/)).toBeInTheDocument();
		});
	});
});
