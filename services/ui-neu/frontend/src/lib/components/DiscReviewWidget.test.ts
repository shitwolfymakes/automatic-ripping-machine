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

import { fetchJob, abandonJob, updateTrack } from '$lib/api/jobs';
const mockFetchJob = vi.mocked(fetchJob);
const mockCancel = vi.mocked(abandonJob);
const mockUpdateTrack = vi.mocked(updateTrack);

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

		it('renders Start and Cancel buttons', async () => {
			renderWidget();
			await waitFor(() => {
				expect(screen.getByText('Start')).toBeInTheDocument();
				expect(screen.getByText('Cancel')).toBeInTheDocument();
			});
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

		it('shows the Disc info button', async () => {
			renderWidget({ disc_type: 'bluray' });
			await waitFor(() => expect(screen.getByText('Disc info')).toBeInTheDocument());
		});

		it('opens the Apply session dialog', async () => {
			renderWidget({ disc_type: 'bluray' });
			await waitFor(() => expect(screen.getByText('Apply session')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Apply session'));
			await waitFor(() => expect(screen.getByRole('dialog', { name: /apply session/i })).toBeInTheDocument());
		});
	});

	describe('disc info', () => {
		it('saves disc_number / disc_total via patchJob', async () => {
			const { patchJob } = await import('$lib/api/jobs');
			const mockPatch = vi.mocked(patchJob);
			mockFetchJob.mockResolvedValue(detail({ id: 'job_d', disc_type: 'bluray' }));
			renderWidget({ id: 'job_d', disc_type: 'bluray' });
			await waitFor(() => expect(screen.getByText('Disc info')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Disc info'));

			const numberInput = await screen.findByLabelText(/disc number/i);
			const totalInput = screen.getByLabelText(/disc total/i);
			await fireEvent.input(numberInput, { target: { value: '2' } });
			await fireEvent.input(totalInput, { target: { value: '4' } });
			await fireEvent.click(screen.getByRole('button', { name: /^save$/i }));

			await waitFor(() => {
				expect(mockPatch).toHaveBeenCalledWith('job_d', { disc_number: 2, disc_total: 4 });
			});
		});
	});

	describe('interactions', () => {
		it('renders Start as a disabled coming-soon control', async () => {
			renderWidget({ id: 'job_9' });
			await waitFor(() => expect(screen.getByText('Start')).toBeInTheDocument());
			expect(screen.getByText('Start')).toBeDisabled();
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
});
