import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import DiscReviewWidget from './DiscReviewWidget.svelte';
import type { JobView, TrackView } from '$lib/types/api.gen';
import { createJob, createJobDetail, createTrack } from './__fixtures__/job';

/** Build a JobDetailView from explicit job overrides + tracks. */
function detail(jobOverrides: Partial<JobView> = {}, tracks: TrackView[] = []) {
	return { ...createJobDetail({ tracks }), job: createJob(jobOverrides) };
}

vi.mock('$lib/api/jobs', () => ({
	fetchJob: vi.fn(() => Promise.resolve(createJobDetail())),
	abandonJob: vi.fn(() => Promise.resolve()),
	startWaitingJob: vi.fn(() => Promise.resolve(createJob())),
	pauseWaitingJob: vi.fn(() => Promise.resolve(createJob())),
	resolveJob: vi.fn(() => Promise.resolve(createJob())),
	updateTrack: vi.fn(() => Promise.resolve(createJob())),
	patchJob: vi.fn(() => Promise.resolve(createJob())),
	applySession: vi.fn(() => Promise.resolve({ created_task_ids: [], collisions: [] })),
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	searchMusicMetadata: vi.fn(),
	fetchMusicDetail: vi.fn(),
	updateJobTitle: vi.fn(() => Promise.resolve(createJob())),
	updateJobConfig: vi.fn(() => Promise.resolve(createJob())),
	updateJobNaming: vi.fn(() => Promise.reject(new Error('not available'))),
	updateJobTranscodeConfig: vi.fn(() => Promise.reject(new Error('not available'))),
	updateTrackTitle: vi.fn(() => Promise.resolve(createJob())),
	clearTrackTitle: vi.fn(() => Promise.resolve(createJob())),
	fetchNamingVariables: vi.fn(() => Promise.resolve({ variables: {} })),
	namingPreview: vi.fn(() => Promise.resolve({ rendered: '' })),
	validatePattern: vi.fn(() => Promise.resolve({ valid: true }))
}));

vi.mock('$lib/api/settings', () => ({
	fetchTranscoderScheme: vi.fn(() => Promise.resolve(null)),
	fetchTranscoderPresets: vi.fn(() => Promise.resolve(null))
}));

// ApplySessionDialog (opened by the "Apply session" button) fetches these.
vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(() => Promise.resolve([]))
}));
vi.mock('$lib/api/ripPresets', () => ({
	fetchRipPresets: vi.fn(() => Promise.resolve([]))
}));
vi.mock('$lib/api/transcodePresets', () => ({
	fetchTranscodePresets: vi.fn(() => Promise.resolve([]))
}));

import { fetchJob, abandonJob, updateTrack, startWaitingJob, pauseWaitingJob } from '$lib/api/jobs';
const mockFetchJob = vi.mocked(fetchJob);
const mockCancel = vi.mocked(abandonJob);
const mockUpdateTrack = vi.mocked(updateTrack);
const mockStart = vi.mocked(startWaitingJob);
const mockPause = vi.mocked(pauseWaitingJob);

/** Render the widget with a JobView. */
function renderWidget(jobOverrides: Partial<Parameters<typeof createJob>[0]> = {}, extraProps: Record<string, unknown> = {}) {
	return renderComponent(DiscReviewWidget, {
		props: { job: createJob({ status: 'identified', ...jobOverrides }), ...extraProps }
	});
}

describe('DiscReviewWidget', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
		mockFetchJob.mockResolvedValue(detail({ title: 'Test Movie', disc_type: 'bluray' }));
	});

	describe('rendering', () => {
		it('renders job title', async () => {
			renderWidget({ title: 'Test Movie' });
			await waitFor(() => {
				expect(screen.getByText('Test Movie')).toBeInTheDocument();
			});
		});

		it('renders the Start rip button for awaiting_review + Cancel always', async () => {
			renderWidget({ status: 'awaiting_review' });
			await waitFor(() => {
				expect(screen.getByText('Start rip')).toBeInTheDocument();
				expect(screen.getByText('Cancel')).toBeInTheDocument();
			});
		});

		it('shows Start rip on an awaiting_user_id job (review-card start)', async () => {
			renderWidget({ status: 'awaiting_user_id' });
			await waitFor(() => expect(screen.getByText('Cancel')).toBeInTheDocument());
			expect(screen.getByText('Start rip')).toBeInTheDocument();
		});

		it('keeps Start rip after the job is identified (saving must not flip it to Done)', async () => {
			renderWidget({ status: 'identified' });
			await waitFor(() => expect(screen.getByText('Cancel')).toBeInTheDocument());
			expect(screen.getByText('Start rip')).toBeInTheDocument();
			// The old "Done" button is gone — Start rip / Cancel are the actions.
			expect(screen.queryByText('Done')).not.toBeInTheDocument();
		});

		it('renders a View details link to the job page', async () => {
			renderWidget({ id: 'job_vd', status: 'awaiting_user_id' });
			const link = await screen.findByText('View details');
			expect(link.closest('a')?.getAttribute('href')).toBe('/jobs/job_vd');
		});

		it('renders disc type info', async () => {
			renderWidget({ disc_type: 'bluray' });
			await waitFor(() => {
				expect(screen.getByText('Blu-ray')).toBeInTheDocument();
			});
		});

		it('renders drive name from driveNames prop', async () => {
			renderWidget({ drive_id: 'drv_1' }, { driveNames: { drv_1: 'Main Drive' } });
			await waitFor(() => {
				expect(screen.getByText('Main Drive')).toBeInTheDocument();
			});
		});
	});

	describe('search button visibility', () => {
		it('shows Search button for video discs', async () => {
			renderWidget({ disc_type: 'bluray' });
			await waitFor(() => {
				expect(screen.getByText('Search')).toBeInTheDocument();
			});
		});

		it('does NOT show the removed Transcode/Settings buttons', async () => {
			renderWidget({ disc_type: 'bluray' });
			await waitFor(() => expect(screen.getByText('Search')).toBeInTheDocument());
			expect(screen.queryByText('Transcode')).not.toBeInTheDocument();
			expect(screen.queryByText('Settings')).not.toBeInTheDocument();
		});

		it('Info is the first action button and toggles the Info form', async () => {
			renderWidget({ status: 'awaiting_user_id', disc_type: 'dvd' });
			expect(screen.getByRole('button', { name: 'Info' })).toBeInTheDocument();
			await fireEvent.click(screen.getByRole('button', { name: 'Info' }));
			await waitFor(() => expect(screen.getByLabelText('Title')).toBeInTheDocument());
		});

		it('no longer renders a standalone "Disc info" button', () => {
			renderWidget({ status: 'awaiting_user_id', disc_type: 'dvd' });
			expect(screen.queryByRole('button', { name: 'Disc info' })).not.toBeInTheDocument();
		});

		it('opens the Apply session dialog', async () => {
			renderWidget({ disc_type: 'bluray' });
			await waitFor(() => expect(screen.getByText('Apply session')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Apply session'));
			await waitFor(() => expect(screen.getByRole('dialog', { name: /apply session/i })).toBeInTheDocument());
		});
	});

	describe('interactions', () => {
		it('Start rip calls startWaitingJob for an awaiting_review job', async () => {
			renderWidget({ id: 'job_9', status: 'awaiting_review' });
			const btn = await screen.findByText('Start rip');
			await fireEvent.click(btn);
			await waitFor(() => expect(mockStart).toHaveBeenCalledWith('job_9'));
		});

		it('Start rip saves (resolveJob) before starting an awaiting_user_id job', async () => {
			const { resolveJob } = await import('$lib/api/jobs');
			const mockResolve = vi.mocked(resolveJob);
			renderWidget({ id: 'job_u', status: 'awaiting_user_id' });
			const btn = await screen.findByText('Start rip');
			await fireEvent.click(btn);
			// resolve (the save) fires; for awaiting_user_id no rip-start-review is needed
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockStart).not.toHaveBeenCalled();
		});

		it('the countdown pause control toggles per-job pause', async () => {
			// awaiting_review + a wait_start_time renders the CountdownTimer with a
			// pause toggle; clicking it calls pauseWaitingJob(id, true).
			renderWidget({
				id: 'job_9',
				status: 'awaiting_review',
				wait_start_time: new Date().toISOString()
			});
			const pauseBtn = await screen.findByTitle('Pause timer');
			await fireEvent.click(pauseBtn);
			await waitFor(() => expect(mockPause).toHaveBeenCalledWith('job_9', true));
		});

		it('calls abandonJob with the job id when Cancel is clicked', async () => {
			renderWidget({ id: 'job_9' });
			await waitFor(() => expect(screen.getByText('Cancel')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Cancel'));
			await waitFor(() => {
				expect(mockCancel).toHaveBeenCalledWith('job_9');
			});
		});

		it('calls ondismiss after cancel', async () => {
			const ondismiss = vi.fn();
			renderWidget({}, { ondismiss });
			await waitFor(() => expect(screen.getByText('Cancel')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Cancel'));
			await waitFor(() => {
				expect(ondismiss).toHaveBeenCalled();
			});
		});

		it('calls onrefresh after cancel', async () => {
			const onrefresh = vi.fn();
			renderWidget({}, { onrefresh });
			await waitFor(() => expect(screen.getByText('Cancel')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Cancel'));
			await waitFor(() => {
				expect(onrefresh).toHaveBeenCalled();
			});
		});
	});

	describe('tracks table', () => {
		it('renders v3 track rows (index / title / source)', async () => {
			mockFetchJob.mockResolvedValue(
				detail({ title: 'Kolchak', disc_type: 'bluray' }, [
					createTrack({ id: 'trk_1', index: 0, source_ref: 'Kolchak_t00.mkv', title: 'Demon in Lace', duration_seconds: 3012, episode_number: 16 })
				])
			);
			renderWidget({ disc_type: 'bluray' });
			await waitFor(() => {
				expect(screen.getByText('Demon in Lace')).toBeInTheDocument();
				expect(screen.getByText('Kolchak_t00.mkv')).toBeInTheDocument();
			});
		});

		it('persists an episode-number edit via updateTrack bulk-PATCH', async () => {
			mockFetchJob.mockResolvedValue(
				detail({ disc_type: 'bluray' }, [createTrack({ id: 'trk_1', index: 0, source_ref: 't00.mkv', title: 'Ep' })])
			);
			renderWidget({ id: 'job_3', disc_type: 'bluray' });
			await waitFor(() => expect(screen.getByText('Ep')).toBeInTheDocument());
			const epInput = screen.getByPlaceholderText('--');
			await fireEvent.change(epInput, { target: { value: '7' } });
			await waitFor(() => {
				expect(mockUpdateTrack).toHaveBeenCalledWith('job_3', 'trk_1', { episode_number: 7 });
			});
		});
	});

	it('renders skeleton when job prop is omitted', () => {
		const { container } = renderComponent(DiscReviewWidget, { props: {} });
		expect(container.querySelector('[aria-busy="true"]')).not.toBeNull();
	});

	it('renders scanned titles when the job has no materialized tracks yet', async () => {
		const { fetchJob } = await import('$lib/api/jobs');
		vi.mocked(fetchJob).mockResolvedValueOnce(
			detail(
				{
					status: 'awaiting_user_id',
					metadata_json: {
						scan_result: {
							disc_type: 'dvd',
							titles: [
								{ index: 0, duration_seconds: 3600, source_file: 'B1_t00.mkv' },
								{ index: 1, duration_seconds: 1800, source_file: 'B1_t01.mkv' }
							]
						}
					}
				},
				[]
			)
		);
		renderWidget({ status: 'awaiting_user_id' });
		await waitFor(() => expect(screen.getByText('Scanned titles (2)')).toBeInTheDocument());
	});
});
