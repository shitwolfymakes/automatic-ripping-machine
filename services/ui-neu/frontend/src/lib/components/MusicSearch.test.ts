import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import MusicSearch from './MusicSearch.svelte';
import { createJob, createTrack } from './__fixtures__/job';

vi.mock('$lib/api/jobs', () => ({
	searchMusicMetadata: vi.fn(),
	fetchMusicDetail: vi.fn(),
	resolveJob: vi.fn(() => Promise.resolve({ job: {}, fan_out: [] }))
}));
import { searchMusicMetadata, fetchMusicDetail, resolveJob } from '$lib/api/jobs';
const mockSearch = vi.mocked(searchMusicMetadata);
const mockDetail = vi.mocked(fetchMusicDetail);
const mockResolve = vi.mocked(resolveJob);

afterEach(() => { cleanup(); vi.clearAllMocks(); });

it('searches with track_count when "match track count" is on and discTracks present', async () => {
	mockSearch.mockResolvedValue({ candidates: [] });
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_1', disc_type: 'cd', title: 'Abbey Road' }),
			discTracks: [createTrack(), createTrack({ id: 'trk_2', index: 1 })]
		}
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() =>
		expect(mockSearch).toHaveBeenCalledWith('Abbey Road', expect.objectContaining({ track_count: 2 }))
	);
});

it('multi-disc apply writes only the held disc\'s tracks', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'The Wall', year: 1979, kind: 'music', poster_url: null, provider_id: 'rel-2' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-2', title: 'The Wall', artist: 'Pink Floyd', year: 1979,
		poster_url: null, disc_count: 2, track_count: 4,
		tracks: [
			{ position: 1, title: 'In the Flesh?', length_ms: 213000, disc_number: 1 },
			{ position: 2, title: 'The Thin Ice', length_ms: 151000, disc_number: 1 },
			{ position: 1, title: 'Hey You', length_ms: 280000, disc_number: 2 },
			{ position: 2, title: 'Is There Anybody Out There?', length_ms: 152000, disc_number: 2 }
		]
	});
	const onapply = vi.fn();
	renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_wall', disc_type: 'cd', title: 'The Wall', disc_number: 2 }),
			discTracks: [
				createTrack({ id: 'trk_d2_1', index: 0 }),
				createTrack({ id: 'trk_d2_2', index: 1 })
			],
			onapply
		}
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('The Wall'));
	await fireEvent.click(screen.getByText('The Wall'));
	await waitFor(() => screen.getByText('Hey You'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	await waitFor(() => {
		const [, payload] = mockResolve.mock.calls[0] as unknown as [string, { metadata: { tracks: Array<{ title: string; disc_number: number | null }> } }];
		const titles = payload.metadata.tracks.map((t) => t.title);
		expect(titles).toEqual(['Hey You', 'Is There Anybody Out There?']);
		expect(titles).not.toContain('In the Flesh?');
		expect(onapply).toHaveBeenCalled();
	});
});

it('loads detail and applies the chosen release via resolveJob', async () => {
	mockSearch.mockResolvedValue({
		candidates: [{ title: 'Abbey Road', year: 1969, kind: 'music', poster_url: null, provider_id: 'rel-1' }]
	});
	mockDetail.mockResolvedValue({
		release_id: 'rel-1', title: 'Abbey Road', artist: 'The Beatles', year: 1969,
		poster_url: null, disc_count: 1, track_count: 1,
		tracks: [{ position: 1, title: 'Come Together', length_ms: 259000, disc_number: 1 }]
	});
	const onapply = vi.fn();
	renderComponent(MusicSearch, {
		props: { job: createJob({ id: 'job_9', disc_type: 'cd', title: 'Abbey Road' }), discTracks: [], onapply }
	});
	await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
	await waitFor(() => screen.getByText('Abbey Road'));
	await fireEvent.click(screen.getByText('Abbey Road'));
	await waitFor(() => screen.getByText('Come Together'));
	await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
	await waitFor(() => {
		expect(mockResolve).toHaveBeenCalledWith('job_9', expect.objectContaining({
			title: 'Abbey Road',
			metadata: expect.objectContaining({ artist: 'The Beatles', album: 'Abbey Road' })
		}));
		expect(onapply).toHaveBeenCalled();
	});
});
