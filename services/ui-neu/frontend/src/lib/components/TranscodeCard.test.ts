import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TranscodeCard from './TranscodeCard.svelte';
import type { TranscodeTaskView } from '$lib/types/api.gen';

function createTranscodeTask(overrides: Partial<TranscodeTaskView> = {}): TranscodeTaskView {
	return {
		id: 't-1',
		session_application_id: 'job-1',
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
	});
});
