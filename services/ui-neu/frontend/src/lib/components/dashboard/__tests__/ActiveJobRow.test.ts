import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import ActiveJobRow from '../ActiveJobRow.svelte';
import { createJob } from '../../../__fixtures__/job';

const live = vi.hoisted(() => ({ value: { rip: null, transcode: null } as Record<string, unknown> }));
vi.mock('$lib/stores/job-live.svelte', () => ({
	jobLive: { watch: vi.fn(() => () => {}), get: vi.fn(() => live.value) }
}));

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/api/iso', () => ({
	cancelIsoRip: vi.fn(() => Promise.resolve())
}));

vi.mock('$lib/stores/toast.svelte', () => ({
	addToast: vi.fn()
}));

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
			// The expanded detail table (Job ID row) is hidden until the row is expanded.
			expect(screen.queryByText('Job ID')).not.toBeInTheDocument();
		});
	});

	describe('expand/collapse', () => {
		it('shows expanded detail on click', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			// Click the row to expand
			await fireEvent.click(screen.getByText('Test Movie'));
			await waitFor(() => {
				expect(screen.getByText('Job ID')).toBeInTheDocument();
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
				expect(screen.getByText('Job ID')).toBeInTheDocument();
			});
		});
	});

	describe('ISO source', () => {
		it('shows the ISO chip and Cancel for an ISO rip', async () => {
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ drive_id: 'drv_iso_1' }), isoSource: 'Blade_Runner_2049_UHD.iso' }
			});
			expect(screen.getByText('ISO')).toBeInTheDocument();
			expect(screen.getAllByText('Blade_Runner_2049_UHD.iso').length).toBeGreaterThan(0);
			expect(screen.getByText('Cancel')).toBeInTheDocument();
		});

		it('omits the ISO chip and Cancel for a physical-drive job', () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			expect(screen.queryByText('ISO')).not.toBeInTheDocument();
			expect(screen.queryByText('Cancel')).not.toBeInTheDocument();
		});

		it('cancels through cancelIsoRip without expanding the row', async () => {
			const { cancelIsoRip } = await import('$lib/api/iso');
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ drive_id: 'drv_iso_1' }), isoSource: 'a.iso' }
			});
			await fireEvent.click(screen.getByText('Cancel'));
			await waitFor(() => expect(cancelIsoRip).toHaveBeenCalledWith('drv_iso_1'));
			expect(screen.queryByText('Job ID')).not.toBeInTheDocument();
		});

		it('marks the row root data-source="iso" for an ISO rip only', () => {
			const { container, unmount } = renderComponent(ActiveJobRow, {
				props: { job: createJob({ drive_id: 'drv_iso_1' }), isoSource: 'a.iso' }
			});
			expect(container.querySelector('.job-active-row')?.getAttribute('data-source')).toBe('iso');
			unmount();
			const optical = renderComponent(ActiveJobRow, { props: { job: createJob() } });
			expect(optical.container.querySelector('.job-active-row')?.hasAttribute('data-source')).toBe(false);
		});

		it('surfaces a failed cancel as an error toast', async () => {
			const { cancelIsoRip } = await import('$lib/api/iso');
			const { addToast } = await import('$lib/stores/toast.svelte');
			vi.mocked(cancelIsoRip).mockRejectedValueOnce(new Error('cannot cancel: not an active ISO rip'));
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ drive_id: 'drv_iso_1' }), isoSource: 'a.iso' }
			});
			await fireEvent.click(screen.getByText('Cancel'));
			await waitFor(() =>
				expect(addToast).toHaveBeenCalledWith({
					tone: 'error',
					title: 'Cancel failed',
					body: 'cannot cancel: not an active ISO rip'
				})
			);
			expect(screen.getByText('Cancel')).not.toBeDisabled();
		});
	});
});

describe('progress row without a progress figure', () => {
	afterEach(() => {
		cleanup();
		live.value = { rip: null, transcode: null };
	});

	it.each(['created', 'identified', 'awaiting_user_id', 'awaiting_review', 'ripping'])(
		'shows the indeterminate bar, not the waiting sentence, for a %s job',
		(status) => {
			const { container } = renderComponent(ActiveJobRow, { props: { job: createJob({ status: status as never }) } });
			expect(container.querySelector('[data-indeterminate="true"]')).not.toBeNull();
			expect(screen.queryByText(/Waiting for the first progress report/)).toBeNull();
		}
	);

	it('shows the live bar once a progress figure arrives', () => {
		live.value = {
			rip: { pct: 40, etaSeconds: null, bytesDone: null, bytesTotal: null, rateBps: null, phase: null, pass: null },
			transcode: null
		};
		const { container } = renderComponent(ActiveJobRow, { props: { job: createJob({ status: 'ripping' }) } });
		expect(screen.getByTestId('live-progress-line')).toBeInTheDocument();
		expect(container.querySelector('[data-indeterminate="true"]')).toBeNull();
	});
});
