import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import LogDetailPage from '../[job_id]/+page.svelte';

const ENTRIES = [
	{ level: 'info', logger: 'arm', event: 'started ripping' },
	{ level: 'error', logger: 'ripper', event: 'makemkv failed' }
];

const fetchJobLog = vi.fn();
vi.mock('$lib/api/logs', () => ({
	fetchJobLog: (...a: unknown[]) => fetchJobLog(...a),
	jobLogDownloadUrl: (id: string) => `/api/logs/${id}.zip`
}));

// SvelteKit page store: provide the route param (matches the repo's existing
// $app/stores mock pattern — async + await import, NOT require).
vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ params: { job_id: 'job_a' } }) };
});

beforeEach(() => fetchJobLog.mockReset());

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
});
