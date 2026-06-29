import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import JobRow from './JobRow.svelte';
import { createJob } from './__fixtures__/job';

// JobRow renders a <tr>, which needs a <table> parent for valid DOM
function renderInTable(props: Record<string, unknown>) {
	const { container, ...rest } = renderComponent(JobRow, { props });
	// Wrap in a table if the browser didn't auto-correct
	return { container, ...rest };
}

describe('JobRow', () => {
	beforeEach(() => {
		vi.useFakeTimers();
		vi.setSystemTime(new Date('2025-06-15T12:00:00Z'));
	});

	afterEach(() => {
		cleanup();
		vi.useRealTimers();
	});

	describe('rendering', () => {
		it('renders job title as a link', () => {
			renderInTable({ job: createJob() });
			const link = screen.getByText('Test Movie');
			expect(link).toBeInTheDocument();
			expect(link.closest('a')).toHaveAttribute('href', '/jobs/job_1');
		});

		it('renders Untitled when no title', () => {
			renderInTable({ job: createJob({ title: null }) });
			expect(screen.getByText('Untitled')).toBeInTheDocument();
		});

		it('renders status badge', () => {
			renderInTable({ job: createJob({ status: 'ripped' }) });
			expect(screen.getByText('Ripped')).toBeInTheDocument();
		});

		it('renders year when present', () => {
			renderInTable({ job: createJob() });
			expect(screen.getByText('2024')).toBeInTheDocument();
		});
	});

	describe('props', () => {
		it('renders disc type label', () => {
			renderInTable({ job: createJob({ disc_type: 'bluray' }) });
			expect(screen.getByText('Blu-ray')).toBeInTheDocument();
		});

		it('invokes onselect with the job id when checkbox toggled', async () => {
			let captured: [string, boolean] | null = null;
			const { container } = renderComponent(JobRow, {
				props: {
					job: createJob(),
					onselect: (id: string, sel: boolean) => {
						captured = [id, sel];
					}
				}
			});
			const checkbox = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
			checkbox.click();
			expect(captured).toEqual(['job_1', true]);
		});
	});

	describe('skeleton', () => {
		it('renders skeleton cells when job prop is omitted', () => {
			const { container } = renderComponent(JobRow, { props: {} });
			const skeletonCells = container.querySelectorAll('[data-variant="line"]');
			expect(skeletonCells.length).toBeGreaterThan(0);
		});
	});

	describe('Rip + Transcode columns', () => {
		it('renders separate Rip and Transcode columns; partial transcode is not green', async () => {
			const job = {
				id: 'job_x', status: 'ripped', title: 'M', disc_type: 'dvd', drive_id: 'd',
				metadata_json: {}, transcode_progress: { state: 'done_partial', tasks_total: 4, tasks_done: 2, tasks_failed: 2, percent: 50 }
			} as any;
			const { getByText, getAllByText } = renderInTable({ job });
			expect(getByText('Ripped')).toBeInTheDocument();                      // Rip column
			// Only the StatusBadge renders "Transcode failed"; the redundant caption is suppressed.
			expect(getAllByText('Transcode failed').length).toBe(1);             // Transcode column (red, not green)
		});

		it('shows an em-dash in Transcode when no session', async () => {
			const job = { id: 'job_y', status: 'ripped', title: 'M', disc_type: 'dvd', drive_id: 'd', metadata_json: {}, transcode_progress: null } as any;
			const { getByText } = renderInTable({ job });
			expect(getByText('—')).toBeInTheDocument();
		});
	});
});
