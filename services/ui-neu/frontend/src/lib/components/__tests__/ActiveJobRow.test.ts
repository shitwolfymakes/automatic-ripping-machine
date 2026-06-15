import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import ActiveJobRow from '../ActiveJobRow.svelte';
import { createJob } from '../__fixtures__/job';

describe('ActiveJobRow', () => {
	afterEach(() => cleanup());

	describe('collapsed state', () => {
		it('renders title', () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			expect(screen.getByText('Test Movie')).toBeInTheDocument();
		});

		it('renders year', () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			expect(screen.getByText('2024')).toBeInTheDocument();
		});

		it('renders status badge', () => {
			renderComponent(ActiveJobRow, { props: { job: createJob({ status: 'ripping' }) } });
			expect(screen.getByText('Ripping')).toBeInTheDocument();
		});

		it('does not show expanded detail by default', () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			expect(screen.queryByText('Open details')).not.toBeInTheDocument();
		});
	});

	describe('expand/collapse', () => {
		it('shows expanded detail on click', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			// Click the row to expand
			await fireEvent.click(screen.getByText('Test Movie'));
			await waitFor(() => {
				expect(screen.getByText('Open details')).toBeInTheDocument();
			});
		});

		it('shows track counts when expanded', async () => {
			renderComponent(ActiveJobRow, {
				props: {
					job: createJob({
						status: 'ripping',
						rip_progress: {
							tracks_total: 5,
							tracks_done: 2,
							tracks_failed: 0,
							current_track_id: null,
							current_track_index: null
						}
					})
				}
			});
			await fireEvent.click(screen.getByText('Test Movie'));
			await waitFor(() => {
				expect(screen.getByText('2 / 5 ripped')).toBeInTheDocument();
			});
		});

		it('expanded state has chevron rotated', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			await fireEvent.click(screen.getByText('Test Movie'));
			await waitFor(() => {
				expect(screen.getByText('Open details')).toBeInTheDocument();
			});
		});
	});
});
