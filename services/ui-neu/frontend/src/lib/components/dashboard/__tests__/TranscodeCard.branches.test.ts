import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import TranscodeCard from '../TranscodeCard.svelte';
import type { TranscodeTaskView } from '$lib/types/api.gen';
import type { WSEnvelope } from '$lib/api/ws';

// Branch pins for TranscodeCard, beside TranscodeCard.test.ts. Every branch is
// reachable from the rendered component.

const wsHandlers = new Map<string, (env: WSEnvelope) => void>();
const unsubscribed: string[] = [];
vi.mock('$lib/api/ws', () => ({
	wsClient: {
		subscribe: vi.fn((topic: string, handler: (env: WSEnvelope) => void) => {
			wsHandlers.set(topic, handler);
			return () => {
				unsubscribed.push(topic);
				wsHandlers.delete(topic);
			};
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

const etaEl = () => screen.getByTitle('Estimated time remaining');
const fpsEl = () => screen.queryByTitle('Encoder frame rate');

function send(taskId: string, payload: Record<string, unknown>) {
	wsHandlers.get(`transcode.progress.${taskId}`)?.(progressEvent(taskId, payload));
}

describe('TranscodeCard branches', () => {
	beforeEach(() => {
		wsHandlers.clear();
		unsubscribed.length = 0;
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	describe('live progress subscription', () => {
		it('subscribes while the task is active and unsubscribes when it stops being active', async () => {
			const { rerender } = renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(wsHandlers.has('transcode.progress.t-1')).toBe(true);
			await rerender({ job: createTranscodeTask({ status: 'done' }) });
			await waitFor(() => expect(unsubscribed).toContain('transcode.progress.t-1'));
			expect(wsHandlers.size).toBe(0);
		});

		it('unsubscribes when it unmounts', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			cleanup();
			expect(unsubscribed).toEqual(['transcode.progress.t-1']);
		});
	});

	describe('live sample fields', () => {
		it('uses eta_seconds, fps and avg_fps when all three are numbers', async () => {
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ eta_seconds: 900, fps: 10, avg_fps: 5 }) }
			});
			send('t-1', { eta_seconds: 1800, fps: 60, avg_fps: 55.55 });
			await waitFor(() => expect(etaEl()).toHaveTextContent('~30m 0s'));
			expect(fpsEl()).toHaveTextContent('60.0 fps (avg 55.5)');
		});

		it('falls back to the task row when none of them is present', async () => {
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ eta_seconds: 900, fps: 10, avg_fps: 5 }) }
			});
			send('t-1', { eta_seconds: 1800, fps: 60, avg_fps: 55 });
			await waitFor(() => expect(etaEl()).toHaveTextContent('~30m 0s'));
			send('t-1', {});
			await waitFor(() => expect(etaEl()).toHaveTextContent('~15m 0s'));
			expect(fpsEl()).toHaveTextContent('10.0 fps (avg 5.0)');
		});

		it('ignores eta_seconds, fps and avg_fps that arrive as strings', async () => {
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ eta_seconds: 900, fps: 10, avg_fps: 5 }) }
			});
			send('t-1', { eta_seconds: '1800', fps: '60', avg_fps: '55' });
			await waitFor(() => expect(etaEl()).toHaveTextContent('~15m 0s'));
			expect(fpsEl()).toHaveTextContent('10.0 fps (avg 5.0)');
		});

		it('shows a numeric fps without a string avg_fps', async () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			send('t-1', { fps: 60, avg_fps: '55' });
			await waitFor(() => expect(fpsEl()).toHaveTextContent('60.0 fps'));
			expect(fpsEl()?.textContent).not.toContain('avg');
		});

		it('ignores a sample for another task once the card shows a different task', async () => {
			const { rerender } = renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ eta_seconds: 900, fps: 10, avg_fps: 5 }) }
			});
			send('t-1', { eta_seconds: 1800, fps: 60, avg_fps: 55 });
			await waitFor(() => expect(etaEl()).toHaveTextContent('~30m 0s'));
			await rerender({ job: createTranscodeTask({ id: 't-2', eta_seconds: 300, fps: 20, avg_fps: 15 }) });
			await waitFor(() => expect(etaEl()).toHaveTextContent('~5m 0s'));
			expect(fpsEl()).toHaveTextContent('20.0 fps (avg 15.0)');
		});
	});

	describe('ETA of an active task', () => {
		it('prefers the live ETA over the row ETA, and the row ETA over the started_at estimate', async () => {
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ progress_pct: 50, started_at: '2025-06-15T11:59:00Z', eta_seconds: 900 }) }
			});
			expect(etaEl()).toHaveTextContent('~15m 0s');
			send('t-1', { eta_seconds: 1800 });
			await waitFor(() => expect(etaEl()).toHaveTextContent('~30m 0s'));
		});

		it('shows a dash with no ETA and no started_at', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ started_at: null }) } });
			expect(etaEl().textContent?.trim()).toBe('-');
		});

		it('shows the elapsed time from started_at when no estimate can be made', () => {
			// progress_pct 0 makes etaTime return null.
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ progress_pct: 0, started_at: '2025-06-15T11:59:00Z' }) }
			});
			expect(etaEl().textContent?.trim()).toBe('1m 0s');
		});
	});

	describe('frame rate of an active task', () => {
		it('prefers the live fps over the row values', async () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ fps: 10, avg_fps: 5 }) } });
			send('t-1', { fps: 60, avg_fps: 55 });
			await waitFor(() => expect(fpsEl()).toHaveTextContent('60.0 fps (avg 55.0)'));
		});

		it('shows the row values with no live fps', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ fps: 10, avg_fps: 5 }) } });
			expect(fpsEl()).toHaveTextContent('10.0 fps (avg 5.0)');
		});

		it('renders no frame rate element with neither', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(fpsEl()).not.toBeInTheDocument();
		});
	});

	describe('a task that is not active', () => {
		it('shows the elapsed time from created_at', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ status: 'queued' }) } });
			expect(screen.getByText('1h 55m')).toBeInTheDocument();
			expect(screen.queryByTitle('Estimated time remaining')).not.toBeInTheDocument();
		});

		it('shows nothing there without created_at', () => {
			const { container } = renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ status: 'queued', created_at: null }) }
			});
			expect(container.querySelector('.transcode-card-meta')).toBeNull();
		});
	});

	describe('clicks', () => {
		beforeEach(() => {
			vi.useRealTimers(); // slide transition needs real timers
		});

		const chevron = () => screen.getByTitle(/^(Expand|Collapse)$/);

		it('toggles the detail when the card is clicked', async () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			const title = screen.getByRole('heading', { name: 'my_movie.mkv' });
			await fireEvent.click(title);
			expect(chevron()).toHaveAttribute('aria-expanded', 'true');
			await fireEvent.click(title);
			expect(chevron()).toHaveAttribute('aria-expanded', 'false');
		});

		it('toggles the detail when the chevron is clicked', async () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			await fireEvent.click(chevron());
			expect(chevron()).toHaveAttribute('aria-expanded', 'true');
			await fireEvent.click(chevron());
			expect(chevron()).toHaveAttribute('aria-expanded', 'false');
		});

		it('does not toggle when a link inside the card is clicked', async () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			await fireEvent.click(chevron());
			const link = await screen.findByText('Open job');
			link.addEventListener('click', (e) => e.preventDefault());
			await fireEvent.click(link);
			expect(chevron()).toHaveAttribute('aria-expanded', 'true');
		});

		it('does not toggle when a button other than the chevron is clicked', async () => {
			const { container } = renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			const button = document.createElement('button');
			container.querySelector('.transcode-card')?.appendChild(button);
			await fireEvent.click(button);
			expect(chevron()).toHaveAttribute('aria-expanded', 'false');
		});
	});
});
