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

describe('TranscodeCard', () => {
	beforeEach(() => {
		resetLive();
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
			// in_progress renders as the parsed label "In Progress".
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
	// The ETA must not count the time a task sat queued. The store owns
	// the estimate from started_at; the card shows what task() returns.
	describe('ETA', () => {
		it('shows the ETA the store reports, in the coarse form', () => {
			h.task.mockReturnValue(taskLive({ etaSeconds: 60 }));
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(screen.getByTitle('Estimated time remaining')).toHaveTextContent('~1m 0s');
		});

		it('reads the store for this task, merged over its row', () => {
			const job = createTranscodeTask({ eta_seconds: 900 });
			renderComponent(TranscodeCard, { props: { job } });
			expect(h.task).toHaveBeenCalledWith('t-1', job);
		});

		it('rounds a long ETA to whole minutes', () => {
			h.task.mockReturnValue(taskLive({ etaSeconds: 1800 }));
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(screen.getByTitle('Estimated time remaining')).toHaveTextContent('~30m');
		});

		it('shows no ETA or elapsed time from created_at when the claim time is unknown', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ started_at: null }) } });
			expect(screen.getByTitle('Estimated time remaining').textContent?.trim()).toBe('-');
		});

		it('does not follow a task that is not running', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ status: 'queued' }) } });
			expect(h.followTask).not.toHaveBeenCalled();
		});

		it('follows the running task and unfollows when the card unmounts', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(h.followTask).toHaveBeenCalledWith('t-1');
			expect(h.unfollow).not.toHaveBeenCalled();
			cleanup();
			expect(h.unfollow).toHaveBeenCalledTimes(1);
		});
	});

	// The encoder frame rate beside the ETA.
	describe('frame rate', () => {
		it('shows the rate and average the store reports', () => {
			h.task.mockReturnValue(taskLive({ fps: 45.67, avgFps: 23.46 }));
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(screen.getByTitle('Encoder frame rate')).toHaveTextContent('45.7 fps (avg 23.5)');
		});

		it('omits a missing average', () => {
			h.task.mockReturnValue(taskLive({ fps: 60 }));
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(screen.getByTitle('Encoder frame rate').textContent).not.toContain('avg');
		});

		it('renders nothing when no rate has been reported', () => {
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask() } });
			expect(screen.queryByTitle('Encoder frame rate')).not.toBeInTheDocument();
		});

		it('hides the rate once the task is no longer running', () => {
			h.task.mockReturnValue(taskLive({ fps: 45.67 }));
			renderComponent(TranscodeCard, { props: { job: createTranscodeTask({ status: 'done' }) } });
			expect(screen.queryByTitle('Encoder frame rate')).not.toBeInTheDocument();
		});
	});
});
