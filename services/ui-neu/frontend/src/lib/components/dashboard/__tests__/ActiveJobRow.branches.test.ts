import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/testing/render';
import ActiveJobRow from '../ActiveJobRow.svelte';
import { createJob } from '../../../__fixtures__/job';

// Branch pins for ActiveJobRow, beside ActiveJobRow.test.ts and the other
// tests that render it. The branches below cannot be reached from the
// rendered row, so nothing here forces them:
// - The `job ? ... : ...` arms of `active`: the derived is only read inside
//   the `{:else}` of `{#if !job}`, so `job` is always set when it runs.

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

const ripProgress = (done: number, total: number) => ({
	tracks_total: total,
	tracks_done: done,
	tracks_failed: 0,
	current_track_id: null,
	current_track_index: null
});

async function expand(title = 'Test Movie') {
	await fireEvent.click(screen.getByText(title));
	await waitFor(() => expect(screen.getByText('Job ID')).toBeInTheDocument());
}

function detailValue(label: string): HTMLElement {
	// Scoped to the label cells: a type pill can also read "Disc".
	const labelCell = screen.getByText(label, { selector: 'td.job-active-row-detail-label' });
	return labelCell.nextElementSibling as HTMLElement;
}

describe('ActiveJobRow branches', () => {
	beforeEach(() => {
		live.value = { rip: null, transcode: null };
	});
	afterEach(() => cleanup());

	describe('handleCancelIso', () => {
		it('does nothing when the ISO job has no drive_id', async () => {
			const { cancelIsoRip } = await import('$lib/api/iso');
			vi.mocked(cancelIsoRip).mockClear();
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ drive_id: null }), isoSource: 'a.iso' }
			});
			await fireEvent.click(screen.getByText('Cancel'));
			expect(cancelIsoRip).not.toHaveBeenCalled();
			expect(screen.getByText('Cancel')).not.toBeDisabled();
		});

		it('toasts "Unknown error" when the cancel rejects with a non-Error', async () => {
			const { cancelIsoRip } = await import('$lib/api/iso');
			const { addToast } = await import('$lib/stores/toast.svelte');
			vi.mocked(addToast).mockClear();
			vi.mocked(cancelIsoRip).mockRejectedValueOnce('nope');
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ drive_id: 'drv_iso_1' }), isoSource: 'a.iso' }
			});
			await fireEvent.click(screen.getByText('Cancel'));
			await waitFor(() =>
				expect(addToast).toHaveBeenCalledWith({ tone: 'error', title: 'Cancel failed', body: 'Unknown error' })
			);
		});

		it('shows Cancelling... while the cancel is in flight', async () => {
			const { cancelIsoRip } = await import('$lib/api/iso');
			let release: () => void = () => {};
			vi.mocked(cancelIsoRip).mockReturnValueOnce(new Promise<void>((r) => (release = r)) as never);
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ drive_id: 'drv_iso_1' }), isoSource: 'a.iso' }
			});
			await fireEvent.click(screen.getByText('Cancel'));
			await waitFor(() => expect(screen.getByText('Cancelling...')).toBeDisabled());
			release();
			await waitFor(() => expect(screen.getByText('Cancel')).not.toBeDisabled());
		});
	});

	describe('stage text in the expanded Progress cell', () => {
		it.each([
			['scratch-to-media', 'Copying to shared storage'],
			['work-to-completed', 'Moving to completed'],
			['some-other-stage', 'some-other-stage']
		])('shows %s as "%s"', async (stage, text) => {
			live.value = { rip: { phase: stage }, transcode: null };
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			await expand();
			expect(detailValue('Progress')).toHaveTextContent(text);
		});

		it('shows a dash when there is no stage', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			await expand();
			expect(detailValue('Progress')).toHaveTextContent('-');
		});

		it('shows a dash for a stage while the job is not in progress', async () => {
			live.value = { rip: { phase: 'scratch-to-media' }, transcode: null };
			renderComponent(ActiveJobRow, { props: { job: createJob({ status: 'failed' }) } });
			await expand();
			expect(detailValue('Progress')).toHaveTextContent('-');
			expect(screen.queryByText('Copying to shared storage')).not.toBeInTheDocument();
		});
	});

	describe('track counts', () => {
		it('counts from rip_progress in the row and the details', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob({ rip_progress: ripProgress(2, 5) }) } });
			expect(screen.getByText('2/5')).toBeInTheDocument();
			await expand();
			expect(screen.getByText('2 / 5 ripped')).toBeInTheDocument();
		});

		it('falls back to 0 with no rip_progress', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob({ rip_progress: null }) } });
			expect(screen.queryByText('0/0')).not.toBeInTheDocument();
			await expand();
			expect(detailValue('Tracks')).toHaveTextContent('-');
			expect(screen.queryByText(/ripped$/)).not.toBeInTheDocument();
		});

		it('shows a zero total as a dash even when tracks are ripped', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob({ rip_progress: ripProgress(2, 0) }) } });
			expect(screen.queryByText('2/0')).not.toBeInTheDocument();
			await expand();
			expect(detailValue('Tracks')).toHaveTextContent('-');
		});

		it('hides the collapsed count when the job is not in progress', () => {
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ status: 'failed', rip_progress: ripProgress(2, 5) }) }
			});
			expect(screen.queryByText('2/5')).not.toBeInTheDocument();
		});
	});

	describe('collapsed row', () => {
		it('shows the ISO source chip for an ISO rip', () => {
			renderComponent(ActiveJobRow, {
				props: { job: createJob(), isoSource: 'disc.iso', isoKind: 'folder' }
			});
			expect(screen.getByText('Folder')).toBeInTheDocument();
		});

		it('shows no Done badge for a partially complete transcode', () => {
			renderComponent(ActiveJobRow, {
				props: {
					job: createJob({
						status: 'ripped',
						transcode_progress: {
							state: 'done_partial',
							tasks_total: 4,
							tasks_done: 3,
							tasks_failed: 1,
							percent: 100
						} as never
					})
				}
			});
			expect(screen.queryByText(/^Done /)).not.toBeInTheDocument();
		});

		it('shows the disc pill for a disc type', () => {
			renderComponent(ActiveJobRow, { props: { job: createJob({ disc_type: 'dvd' }) } });
			expect(screen.getByText('DVD')).toBeInTheDocument();
		});

		it('shows no disc pill without a disc type', () => {
			const { container } = renderComponent(ActiveJobRow, { props: { job: createJob({ disc_type: undefined }) } });
			expect(container.querySelector('.job-active-row-disc-pill')).toBeNull();
		});

		it('gives a CD the square poster class and other discs not', () => {
			const cd = renderComponent(ActiveJobRow, { props: { job: createJob({ disc_type: 'cd' }) } });
			expect(cd.container.querySelector('.job-active-row-poster-square')).not.toBeNull();
			cd.unmount();
			const dvd = renderComponent(ActiveJobRow, { props: { job: createJob({ disc_type: 'dvd' }) } });
			expect(dvd.container.querySelector('.job-active-row-poster-square')).toBeNull();
		});

		it('hides the year when the job has none', () => {
			const { container } = renderComponent(ActiveJobRow, { props: { job: createJob({ year: null }) } });
			expect(container.querySelector('.job-active-row-collapsed .job-active-row-meta')).toBeNull();
		});
	});

	describe('expanded table', () => {
		it('shows dashes for no disc type, no year, no tracks and no stage', async () => {
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ disc_type: undefined, year: null, title: null }) }
			});
			await fireEvent.click(screen.getByText('Untitled'));
			await waitFor(() => expect(screen.getByText('Job ID')).toBeInTheDocument());
			expect(detailValue('Disc')).toHaveTextContent('-');
			expect(detailValue('Year')).toHaveTextContent('-');
			expect(detailValue('Tracks')).toHaveTextContent('-');
			expect(detailValue('Progress')).toHaveTextContent('-');
		});

		it('shows the disc label, year and counts when set', async () => {
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ disc_type: 'dvd', rip_progress: ripProgress(1, 2) }) }
			});
			await expand();
			expect(within(detailValue('Disc')).getByText('DVD')).toBeInTheDocument();
			expect(detailValue('Year')).toHaveTextContent('2024');
			expect(detailValue('Tracks')).toHaveTextContent('1 / 2 ripped');
		});

		it('gives a CD the square large poster class and other discs not', async () => {
			const cd = renderComponent(ActiveJobRow, { props: { job: createJob({ disc_type: 'cd' }) } });
			await expand();
			expect(cd.container.querySelector('.job-active-row-poster-lg-square')).not.toBeNull();
			cd.unmount();
			const dvd = renderComponent(ActiveJobRow, { props: { job: createJob({ disc_type: 'dvd' }) } });
			await expand();
			expect(dvd.container.querySelector('.job-active-row-poster-lg-square')).toBeNull();
			expect(dvd.container.querySelector('.job-active-row-poster-lg')).not.toBeNull();
		});

		it('falls back to the "Poster" alt text for an untitled job', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob({ title: null, poster_url: 'http://x/p.jpg' }) } });
			await fireEvent.click(screen.getByText('Untitled'));
			await waitFor(() => expect(screen.getByAltText('Poster')).toBeInTheDocument());
		});
	});

	describe('toggle', () => {
		it('does not expand when the Details link is clicked', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			await fireEvent.click(screen.getByText('Details'));
			expect(screen.queryByText('Job ID')).not.toBeInTheDocument();
		});

		it('does not expand when the Cancel button is clicked', async () => {
			renderComponent(ActiveJobRow, {
				props: { job: createJob({ drive_id: null }), isoSource: 'a.iso' }
			});
			await fireEvent.click(screen.getByText('Cancel'));
			expect(screen.queryByText('Job ID')).not.toBeInTheDocument();
		});

		it('expands and collapses from the chevron button', async () => {
			renderComponent(ActiveJobRow, { props: { job: createJob() } });
			const chevron = screen.getByTitle('Expand');
			expect(chevron).toHaveAttribute('aria-expanded', 'false');
			await fireEvent.click(chevron);
			await waitFor(() => expect(screen.getByText('Job ID')).toBeInTheDocument());
			expect(chevron).toHaveAttribute('aria-expanded', 'true');
			expect(chevron).toHaveAttribute('title', 'Collapse');
			await fireEvent.click(chevron);
			expect(chevron).toHaveAttribute('aria-expanded', 'false');
		});
	});

	describe('progress row', () => {
		it('shows no progress row for a job that is not in progress', () => {
			live.value = { rip: { pct: 40 }, transcode: null };
			const { container } = renderComponent(ActiveJobRow, { props: { job: createJob({ status: 'failed' }) } });
			expect(container.querySelector('.job-active-row-progress')).toBeNull();
		});

		it('shows the progress row for a job in progress', () => {
			const { container } = renderComponent(ActiveJobRow, { props: { job: createJob() } });
			expect(container.querySelector('.job-active-row-progress')).not.toBeNull();
		});
	});
});
