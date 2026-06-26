import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TrackTitleSearch from './TrackTitleSearch.svelte';
import { createTrack } from './__fixtures__/job';
import type { MetadataCandidate } from '$lib/types/api.gen';

vi.mock('$lib/api/jobs', () => ({
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	updateTrackTitle: vi.fn(() => Promise.resolve()),
	clearTrackTitle: vi.fn(() => Promise.resolve()),
	updateTrack: vi.fn(() => Promise.resolve())
}));

import { searchMetadata, fetchMediaDetail, updateTrackTitle, clearTrackTitle, updateTrack } from '$lib/api/jobs';
const mockSearchMetadata = vi.mocked(searchMetadata);
const mockFetchDetail = vi.mocked(fetchMediaDetail);
const mockUpdateTrackTitle = vi.mocked(updateTrackTitle);
const mockClearTrackTitle = vi.mocked(clearTrackTitle);
const mockUpdateTrack = vi.mocked(updateTrack);

function createCandidate(overrides: Partial<MetadataCandidate> = {}): MetadataCandidate {
	return {
		title: 'Result',
		year: 2024,
		kind: 'movie',
		poster_url: null,
		provider_id: 'tt1111',
		...overrides
	};
}

describe('TrackTitleSearch', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('rendering', () => {
		it('renders search form with pre-filled track title', () => {
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack({ title: 'Track Title' }) }
			});
			expect(screen.getByDisplayValue('Track Title')).toBeInTheDocument();
		});

		it('renders search button', () => {
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack() }
			});
			expect(screen.getByText('Search')).toBeInTheDocument();
		});

		it('falls back to source_ref basename when no title', () => {
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack({ title: null, source_ref: 'title_02.mkv' }) }
			});
			expect(screen.getByDisplayValue('title_02')).toBeInTheDocument();
		});
	});

	describe('interactions', () => {
		it('calls searchMetadata on search', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [createCandidate({ title: 'Found Title', provider_id: 'tt2222' })] });
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack() }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(mockSearchMetadata).toHaveBeenCalledWith('t00');
				expect(screen.getByText('Found Title')).toBeInTheDocument();
			});
		});

		it('shows no results message', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [] });
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack() }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(screen.getByText(/No results found/)).toBeInTheDocument();
			});
		});

		it('shows error on search failure', async () => {
			mockSearchMetadata.mockRejectedValue(new Error('Search failed'));
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack() }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(screen.getByText('Search failed')).toBeInTheDocument();
			});
		});

		it('shows detail editor when result is selected', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [createCandidate({ title: 'Picked', provider_id: 'tt3333' })] });
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack() }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => expect(screen.getByText('Picked')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Picked'));
			await waitFor(() => {
				expect(screen.getByDisplayValue('Picked')).toBeInTheDocument();
				expect(screen.getByText('Apply')).toBeInTheDocument();
			});
		});

		it('renders close button when onclose provided', () => {
			const onclose = vi.fn();
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack(), onclose }
			});
			const closeBtn = screen.getByTitle('Close');
			expect(closeBtn).toBeInTheDocument();
		});

		it('renders Clear Override button when track has title', () => {
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack({ title: 'Override Title' }) }
			});
			expect(screen.getByText('Clear Override')).toBeInTheDocument();
		});

		it('calls clearTrackTitle on Clear Override click', async () => {
			const onclear = vi.fn();
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_7', track: createTrack({ id: 'trk_9', title: 'Override' }), onclear }
			});
			await fireEvent.click(screen.getByText('Clear Override'));
			await waitFor(() => {
				expect(mockClearTrackTitle).toHaveBeenCalledWith('job_7', 'trk_9');
				expect(onclear).toHaveBeenCalled();
			});
		});

		it('renders year input with pre-filled value', () => {
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_1', track: createTrack({ year: 2023 }) }
			});
			expect(screen.getByDisplayValue('2023')).toBeInTheDocument();
		});

		it('applies a track title edit via bulk-PATCH wrap', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [createCandidate({ title: 'Picked', year: 2021 })] });
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_3', track: createTrack({ id: 'trk_5' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => expect(screen.getByText('Picked')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Picked'));
			await fireEvent.click(screen.getByText('Apply'));
			await waitFor(() => {
				expect(mockUpdateTrackTitle).toHaveBeenCalledWith('job_3', 'trk_5', expect.objectContaining({ title: 'Picked', year: 2021 }));
			});
		});

		it('shows the no-results message without a "Set manually" button', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [] } as any);
			renderComponent(TrackTitleSearch, { props: { jobId: 'job_1', track: createTrack({ title: '' }) } });
			await fireEvent.input(screen.getByPlaceholderText('Title...'), { target: { value: 'Nope' } });
			await fireEvent.click(screen.getByRole('button', { name: /search/i }));
			await waitFor(() => expect(screen.getByText(/No results/i)).toBeInTheDocument());
			expect(screen.queryByText('Set manually')).not.toBeInTheDocument();
		});
	});

	describe('track options (custom filename + episode)', () => {
		it('saves a custom_filename via updateTrack', async () => {
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_9', track: createTrack({ id: 'trk_7' }) }
			});
			const input = screen.getByPlaceholderText('Custom filename (optional)');
			await fireEvent.input(input, { target: { value: 'My Feature.mkv' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Save options' }));
			await waitFor(() =>
				expect(mockUpdateTrack).toHaveBeenCalledWith('job_9', 'trk_7', {
					custom_filename: 'My Feature.mkv'
				})
			);
		});

		it('hides episode inputs for non-series tracks', () => {
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_9', track: createTrack({ video_type: 'movie' }) }
			});
			expect(screen.queryByPlaceholderText('Episode #')).toBeNull();
		});

		it('shows episode inputs for series tracks and sends them', async () => {
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_9', track: createTrack({ id: 'trk_8', video_type: 'series' }) }
			});
			await fireEvent.input(screen.getByPlaceholderText('Episode #'), { target: { value: '3' } });
			await fireEvent.input(screen.getByPlaceholderText('Episode name'), {
				target: { value: 'The One' }
			});
			await fireEvent.click(screen.getByRole('button', { name: 'Save options' }));
			await waitFor(() =>
				expect(mockUpdateTrack).toHaveBeenCalledWith('job_9', 'trk_8', {
					custom_filename: null,
					episode_number: 3,
					episode_name: 'The One'
				})
			);
		});

		it('coerces a non-numeric episode # to null', async () => {
			renderComponent(TrackTitleSearch, {
				props: { jobId: 'job_9', track: createTrack({ id: 'trk_9', video_type: 'series' }) }
			});
			await fireEvent.input(screen.getByPlaceholderText('Episode #'), { target: { value: 'abc' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Save options' }));
			await waitFor(() =>
				expect(mockUpdateTrack).toHaveBeenCalledWith('job_9', 'trk_9', {
					custom_filename: null,
					episode_number: null,
					episode_name: null
				})
			);
		});
	});
});
