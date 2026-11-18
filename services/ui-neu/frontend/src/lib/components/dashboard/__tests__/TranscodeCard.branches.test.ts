import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import TranscodeCard from '../TranscodeCard.svelte';
import type { TranscodeTaskView } from '$lib/types/api.gen';
import type { TaskLive } from '$lib/stores/job-live.svelte';

const h = vi.hoisted(() => ({
	unfollow: vi.fn(),
	followTask: vi.fn(),
	task: vi.fn()
}));
vi.mock('$lib/stores/job-live.svelte', () => ({
	jobLive: { followTask: h.followTask, task: h.task }
}));

function taskLive(over: Partial<TaskLive> = {}): TaskLive {
	return {
		taskId: 't-1',
		pct: null,
		etaSeconds: null,
		fps: null,
		avgFps: null,
		pass: null,
		bytesDone: null,
		bytesTotal: null,
		rateBps: null,
		phase: null,
		trackId: null,
		...over
	};
}

function resetLive(): void {
	h.unfollow = vi.fn();
	h.followTask.mockReset().mockImplementation(() => h.unfollow);
	h.task.mockReset().mockImplementation(() => taskLive());
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

describe('TranscodeCard branches', () => {
	beforeEach(() => {
		resetLive();
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	describe('following the task', () => {
		it('follows while the task is active and unfollows when it stops being active', async () => {
			const { rerender } = renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(h.followTask).toHaveBeenCalledTimes(1);
			await rerender({ job: createTranscodeTask({ status: 'done' }) });
			await waitFor(() => expect(h.unfollow).toHaveBeenCalledTimes(1));
		});

		it('does not re-follow when only other row fields change', async () => {
			const { rerender } = renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			await rerender({ job: createTranscodeTask({ progress_pct: 60, updated_at: '2025-06-15T11:30:00Z' }) });
			expect(h.followTask).toHaveBeenCalledTimes(1);
			expect(h.unfollow).not.toHaveBeenCalled();
		});

		it('follows the new task when the card shows a different one', async () => {
			const { rerender } = renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			await rerender({ job: createTranscodeTask({ id: 't-2' }) });
			await waitFor(() => expect(h.followTask).toHaveBeenLastCalledWith('t-2'));
			expect(h.unfollow).toHaveBeenCalledTimes(1);
		});

		it('unfollows when it unmounts', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			cleanup();
			expect(h.unfollow).toHaveBeenCalledTimes(1);
		});

		it('follows nothing without a task', () => {
			renderComponent(TranscodeCard, { props: {} });
			expect(h.followTask).not.toHaveBeenCalled();
			expect(h.task).not.toHaveBeenCalled();
		});
	});

	describe('ETA of an active task', () => {
		it('formats the store ETA', () => {
			h.task.mockReturnValue(taskLive({ etaSeconds: 900 }));
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(etaEl()).toHaveTextContent('~15m');
		});

		it('shows an ETA of zero seconds as "< 1m" without the "~", rather than falling back', () => {
			h.task.mockReturnValue(taskLive({ etaSeconds: 0 }));
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(etaEl().textContent?.trim()).toBe('< 1m');
		});

		it('shows an ETA under a minute as "< 1m" without the "~"', () => {
			h.task.mockReturnValue(taskLive({ etaSeconds: 45 }));
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(etaEl().textContent?.trim()).toBe('< 1m');
		});

		it('falls back to the dash when the store has no record at all', () => {
			h.task.mockReturnValue(null);
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ started_at: null }) } });
			expect(etaEl().textContent?.trim()).toBe('-');
			expect(fpsEl()).not.toBeInTheDocument();
		});

		it('shows a dash with no ETA and no started_at', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ started_at: null }) } });
			expect(etaEl().textContent?.trim()).toBe('-');
		});

		it('shows the elapsed time from started_at when the store has no estimate', () => {
			renderComponent(TranscodeCard, {
				props: { job: createTranscodeTask({ progress_pct: 0, started_at: '2025-06-15T11:59:00Z' }) }
			});
			expect(etaEl().textContent?.trim()).toBe('1m 0s');
		});
	});

	describe('frame rate of an active task', () => {
		it('shows the store fps and average', () => {
			h.task.mockReturnValue(taskLive({ fps: 60, avgFps: 55 }));
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(fpsEl()).toHaveTextContent('60.0 fps (avg 55.0)');
		});

		it('renders no frame rate element without one', () => {
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
