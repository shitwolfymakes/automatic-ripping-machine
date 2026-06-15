import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import JobCard from './JobCard.svelte';
import { createJob } from './__fixtures__/job';

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
			renderComponent(JobCard, { props: { job: createJob({ status: 'ripped' }) } });
			expect(screen.getByText('ripped')).toBeInTheDocument();
		});
	});

	describe('props', () => {
		it('shows track counts for active jobs with rip progress', () => {
			renderComponent(JobCard, {
				props: {
					job: createJob({
						status: 'ripping',
						rip_progress: {
							tracks_total: 5,
							tracks_done: 1,
							tracks_failed: 0,
							current_track_id: null,
							current_track_index: null
						}
					})
				}
			});
			expect(screen.getByText(/1 \/ 5 titles/)).toBeInTheDocument();
		});

		it('shows progress bar when progress is provided', () => {
			const { container } = renderComponent(JobCard, {
				props: { job: createJob(), progress: 50 }
			});
			expect(container.querySelector('[data-progress-track]')).toBeInTheDocument();
		});

		it('shows indeterminate bar when active with no progress', () => {
			const { container } = renderComponent(JobCard, {
				props: { job: createJob({ status: 'ripping' }) }
			});
			expect(container.querySelector('.animate-indeterminate')).toBeInTheDocument();
		});
	});

	describe('skeleton', () => {
		it('renders a SkeletonCard when job prop is omitted', () => {
			const { container } = renderComponent(JobCard, { props: {} });
			const skeletonShell = container.querySelector('[aria-busy="true"]');
			expect(skeletonShell).not.toBeNull();
		});
	});
});
