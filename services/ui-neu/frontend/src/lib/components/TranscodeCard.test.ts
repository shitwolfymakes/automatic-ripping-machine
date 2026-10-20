import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TranscodeCard from './TranscodeCard.svelte';
import type { TranscodeTaskView } from '$lib/types/api.gen';
import type { WSEnvelope } from '$lib/api/ws';

const wsHandlers = new Map<string, (env: WSEnvelope) => void>();
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		subscribe: vi.fn((topic: string, handler: (env: WSEnvelope) => void) => {
			wsHandlers.set(topic, handler);
			return () => wsHandlers.delete(topic);
		})
	}
}));

function progressEvent(taskId: string, payload: Record<string, unknown>): WSEnvelope {
	return {
		op: 'event',
		event_id: 'evt_1',
		event_type: 'transcode.progress',
		emitted_at: '2025-06-15T12:00:00Z',
		topic: `transcode.progress.${taskId}`,
		job_id: null,
		track_id: null,
		payload: { task_id: taskId, ...payload }
	};
}

function createTranscodeTask(overrides: Partial<TranscodeTaskView> = {}): TranscodeTaskView {
	return {
		id: 't-1',
		session_application_id: 'job-1',
		job_id: 'job-1',
		source_track_id: 'track-1',
		status: 'in_progress',
		output_path: '/media/transcode/my_movie.mkv',
		progress_pct: 45,
		attempts: 1,
		claimed_by: null,
		claim_heartbeat_at: null,
		last_error: null,
		created_at: '2025-06-15T10:05:00Z',
		updated_at: '2025-06-15T11:00:00Z',
		...overrides
	};
}

describe('TranscodeCard', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	it('renders a skeleton card when the data prop is omitted', () => {
		const { container } = renderComponent(TranscodeCard, { props: {} });
		expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
	});

	describe('collapsed state', () => {
		it('renders the output basename as the title', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(screen.getByText('my_movie.mkv')).toBeInTheDocument();
		});

		it('falls back to Transcode # when no output path', () => {
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ output_path: null }) }
			});
			expect(screen.getByText('Transcode #t-1')).toBeInTheDocument();
		});

		it('renders status badge with a humanized label', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			// in_progress now renders as the parsed label "In Progress".
			const matches = screen.getAllByText('In Progress');
			expect(matches.length).toBeGreaterThanOrEqual(1);
		});

		it('shows error indicator when the task has a last_error', () => {
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ last_error: 'Encode failed' }) }
			});
			expect(screen.getByTitle('Encode failed')).toBeInTheDocument();
		});

		it('does not show expanded detail by default', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(screen.queryByText('Open job')).not.toBeInTheDocument();
			expect(screen.queryByText('Open transcoder')).not.toBeInTheDocument();
		});
	});

	describe('expanded state', () => {
		beforeEach(() => {
			vi.useRealTimers(); // slide transition needs real timers
		});

		it('shows Open job + Open transcoder buttons when expanded', async () => {
			// session_application_id == the owning job id, so Open job points at it.
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			await fireEvent.click(screen.getByText('my_movie.mkv'));
			await waitFor(() => {
				const openJob = screen.getByText('Open job');
				expect(openJob).toBeInTheDocument();
				expect(openJob.getAttribute('href')).toBe('/jobs/job-1');
				expect(screen.getByText('Open transcoder')).toBeInTheDocument();
			});
		});

		it('shows progress percentage in the expanded table', async () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ progress_pct: 45 }) } });
			await fireEvent.click(screen.getByText('my_movie.mkv'));
			await waitFor(() => {
				const matches = screen.getAllByText('45%');
				expect(matches.length).toBeGreaterThanOrEqual(1);
			});
		});

		it('shows error text when expanded', async () => {
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ last_error: 'Encode failed' }) }
			});
			await fireEvent.click(screen.getByText('my_movie.mkv'));
			await waitFor(() => {
				expect(screen.getByText('Encode failed')).toBeInTheDocument();
			});
		});

		it('renders Task ID as a link to the owning job page', async () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			await fireEvent.click(screen.getByText('my_movie.mkv'));
			await waitFor(() => {
				const idLink = screen.getByText('#t-1');
				expect(idLink).toBeInTheDocument();
				expect(idLink.getAttribute('href')).toBe('/jobs/job-1');
			});
		});

		it('links to /jobs/{job_id}, not session_application_id', async () => {
			const job = {
				id: 'txt_1',
				job_id: 'job_42',
				session_application_id: 'sap_9',
				status: 'in_progress',
				source_track_id: 'trk',
				progress_pct: 0,
				attempts: 1
			} as any;
			const { getByText } = renderComponent(TranscodeCard, { props: { job } });
			await fireEvent.click(getByText('Transcode #txt_1'));
			await waitFor(() => {
				const link = getByText('Open job').closest('a');
				expect(link?.getAttribute('href')).toBe('/jobs/job_42');
			});
		});
	});
	// D-130: the ETA must not count the time a task sat queued.
	describe('ETA', () => {
		it('extrapolates from started_at, not created_at', () => {
			// Queued at 10:05, claimed at 11:59, 50% at 12:00: one more minute,
			// not the 1h55m that measuring from created_at would give.
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ progress_pct: 50, started_at: '2025-06-15T11:59:00Z' }) }
			});
			expect(screen.getByTitle('Estimated time remaining')).toHaveTextContent('~1m 0s');
		});

		it('prefers the transcoder-reported eta_seconds from the live progress event', async () => {
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ progress_pct: 50, started_at: '2025-06-15T11:59:00Z' }) }
			});
			const handler = wsHandlers.get('transcode.progress.t-1');
			expect(handler).toBeDefined();
			handler?.(progressEvent('t-1', { progress_pct: 51, eta_seconds: 1800 }));
			await waitFor(() => expect(screen.getByTitle('Estimated time remaining')).toHaveTextContent('~30m 0s'));
			// A tick without an ETA falls back to the local estimate.
			handler?.(progressEvent('t-1', { progress_pct: 52, eta_seconds: null }));
			await waitFor(() => expect(screen.getByTitle('Estimated time remaining')).toHaveTextContent('~1m 0s'));
		});

		it('shows no ETA or elapsed time from created_at when the claim time is unknown', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ started_at: null }) } });
			expect(screen.getByTitle('Estimated time remaining').textContent?.trim()).toBe('-');
		});

		it('does not subscribe for a task that is not running', () => {
			wsHandlers.clear();
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ status: 'queued' }) } });
			expect(wsHandlers.size).toBe(0);
		});

		it('drops the subscription when the card unmounts', () => {
			wsHandlers.clear();
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(wsHandlers.has('transcode.progress.t-1')).toBe(true);
			cleanup();
			expect(wsHandlers.size).toBe(0);
		});
	});
});
