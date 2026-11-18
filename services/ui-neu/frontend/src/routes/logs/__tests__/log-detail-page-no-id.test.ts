import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor } from '$lib/testing/render';
import LogDetailPage from '../[job_id]/+page.svelte';

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
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		subscribe: (topic: string, handler: unknown) => subscribeMock(topic, handler)
	}
}));

// The route carries no job_id param at all.
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ params: {} }) };
});

beforeEach(() => {
	fetchJobLog.mockReset();
	fetchJobLog.mockResolvedValue([]);
	subscribeMock.mockReset();
	subscribeMock.mockImplementation(() => vi.fn());
});

describe('Logs single-job viewer without a job id', () => {
	afterEach(() => cleanup());

	it('shows an empty id line', () => {
		renderComponent(LogDetailPage);
		expect(document.querySelector('.log-detail-page-id')).toHaveTextContent(/^$/);
	});

	it('fetches the log with an empty job id', async () => {
		renderComponent(LogDetailPage);
		await waitFor(() => expect(fetchJobLog).toHaveBeenCalledWith('', 1000));
	});

	it('subscribes to the bare logs. topic', async () => {
		renderComponent(LogDetailPage);
		await waitFor(() => expect(subscribeMock).toHaveBeenCalledWith('logs.', expect.any(Function)));
	});

	it('points the download link at the empty id', () => {
		renderComponent(LogDetailPage);
		expect(screen.getByText(/download/i).closest('a')).toHaveAttribute('href', '/api/logs/.zip');
	});
});
