import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import { EMPTY_LIVE } from '$lib/stores/job-live.svelte';

vi.mock('$lib/stores/job-live.svelte', async (importOriginal) => ({
	...(await importOriginal<typeof import('$lib/stores/job-live.svelte')>()),
	jobLive: { watch: () => () => {}, get: () => EMPTY_LIVE }
}));
vi.mock('$lib/stores/dashboard', async () => {
	const { writable } = await import('svelte/store');
	return { dashboard: writable<unknown>({ review_wait_seconds: 60, ripping_enabled: true }) };
});

import JobCard from '../JobCard.svelte';
import { createJob } from '../../../__fixtures__/job';

describe('JobCard', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	describe('rendering', () => {
		it('renders job title', () => {
			renderComponent(JobCard, { props: { job: createJob() } });
			expect(screen.getByText('Test Movie')).toBeInTheDocument();
		});

		it('renders Untitled when no title', () => {
			renderComponent(JobCard, {
				props: { job: createJob({ title: null }) }
			});
			expect(screen.getByText('Untitled')).toBeInTheDocument();
		});

		it('renders year when present', () => {
			renderComponent(JobCard, { props: { job: createJob() } });
			expect(screen.getByText('2024')).toBeInTheDocument();
		});

		it('renders status badge', () => {
			const { container } = renderComponent(JobCard, { props: { job: createJob({ status: 'ripped' }) } });
			// the rail's readout repeats the stage name, so scope to the badge
			expect(container.querySelector('.status-badge')).toHaveTextContent('Ripped');
		});
	});

	describe('optional fields', () => {
		it('omits the year and disc pill when absent', () => {
			const { container } = renderComponent(JobCard, {
				props: { job: createJob({ year: null, disc_type: undefined }) }
			});
			expect(screen.queryByText('2024')).not.toBeInTheDocument();
			expect(container.querySelector('.job-card-disc-pill')).toBeNull();
		});

		it('shows the disc pill and a square poster for a cd', () => {
			const { container } = renderComponent(JobCard, {
				props: { job: createJob({ disc_type: 'cd', title: null }) }
			});
			expect(container.querySelector('.job-card-disc-pill')).toBeInTheDocument();
			expect(container.querySelector('.job-card-poster-square')).toBeInTheDocument();
		});
	});

	describe('stage rail', () => {
		it.each(['identifying', 'awaiting_review', 'ripping', 'ripped', 'transcoding', 'success', 'failure'])(
			'renders the stage rail for every job status (%s)',
			(status) => {
				const { container } = renderComponent(JobCard, {
					props: { job: createJob({ status: status as never }) }
				});
				expect(container.querySelector('.job-card-rail ol[aria-label="Job stages"]')).toBeInTheDocument();
			}
		);

		it('shows no Done X/Y badge for a partial transcode', () => {
			const { container } = renderComponent(JobCard, {
				props: {
					job: createJob({
						status: 'ripped',
						transcode_progress: { state: 'done_partial', tasks_total: 3, tasks_done: 2, tasks_failed: 1, percent: 100 }
					})
				}
			});
			expect(screen.queryByText(/Done \d+\/\d+/)).not.toBeInTheDocument();
			expect(container.querySelector('.badge-warning')).toBeNull();
		});
	});

	describe('skeleton', () => {
		it('renders a SkeletonCard when job prop is omitted', () => {
			const { container } = renderComponent(JobCard, { props: {} });
			expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
		});

		it('renders no stage rail while the job is loading', () => {
			const { container } = renderComponent(JobCard, { props: {} });
			expect(container.querySelector('ol[aria-label="Job stages"]')).toBeNull();
		});
	});
});
