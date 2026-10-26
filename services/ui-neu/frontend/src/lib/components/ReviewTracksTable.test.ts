import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, fireEvent } from '$lib/test-utils';
import { updateTrack } from '$lib/api/jobs';
import ReviewTracksTable from './ReviewTracksTable.svelte';
import type { TrackView } from '$lib/types/api.gen';
import { createJob } from './__fixtures__/job';

vi.mock('$lib/stores/auth', async () => {
	const { readable } = await import('svelte/store');
	return { isAdmin: readable(true), isAuthenticated: readable(true), authStore: readable({ role: 'admin' }) };
});

vi.mock('$lib/api/jobs', () => ({
	updateTrack: vi.fn(() => Promise.resolve({})),
	updateTrackTitle: vi.fn(),
	clearTrackTitle: vi.fn(),
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn()
}));

const track = (o: Partial<TrackView>): TrackView =>
	({ id: 'trk_0', index: 0, source_ref: '0', kind: 'video_title', duration_seconds: null, ...o }) as TrackView;

afterEach(cleanup);

describe('ReviewTracksTable', () => {
	it('shows the scan estimate as the length before the rip', () => {
		renderComponent(ReviewTracksTable, {
			props: {
				job: createJob({ media_type: 'tv' }),
				tracks: [track({ expected_duration_seconds: 3093 })],
				isVideo: true,
				isMusic: false
			}
		});
		expect(screen.getByText('51m 33s')).toBeInTheDocument();
		expect(screen.queryByText('--')).toBeNull();
	});

	it('labels an extra instead of showing it as unplaced', () => {
		renderComponent(ReviewTracksTable, {
			props: {
				job: createJob({ media_type: 'tv' }),
				tracks: [
					track({
						id: 'trk_0',
						index: 0,
						source_ref: '0',
						role: 'episode',
						episode_number: 1,
						episode_name: 'The Ripper',
						duration_seconds: 3093
					}),
					track({ id: 'trk_5', index: 5, source_ref: '5', role: 'extra', duration_seconds: 542 }),
					track({ id: 'trk_6', index: 6, source_ref: '6', duration_seconds: 2990 })
				],
				isVideo: true,
				isMusic: false
			}
		});
		expect(screen.getByTestId('track-role')).toHaveTextContent('Extra');
		// Every track has an Include box, like the job page.
		expect(screen.getAllByRole('checkbox', { name: /Include track/ })).toHaveLength(3);
		// The placed episode shows its name beside the number, as on the job page.
		expect(screen.getByTestId('track-episode-name')).toHaveTextContent('The Ripper');
		// The episode and the unplaced title keep their number box.
		expect(screen.getAllByPlaceholderText('--')).toHaveLength(2);
	});

	it('shows the generated name as the episode once a session names the track', () => {
		renderComponent(ReviewTracksTable, {
			props: {
				job: createJob({ media_type: 'tv' }),
				tracks: [track({ id: 'trk_0', role: 'episode', episode_number: 1, episode_name: 'The Ripper' })],
				fileNames: new Map([['trk_0', 'Kolchak - S01E01 - The Ripper.mkv']]),
				isVideo: true,
				isMusic: false
			}
		});
		expect(screen.getByTestId('track-generated-name')).toHaveTextContent('Kolchak - S01E01 - The Ripper.mkv');
		expect(screen.queryByPlaceholderText('--')).toBeNull();
	});

	it('the Include box leaves a track out of the output', async () => {
		renderComponent(ReviewTracksTable, {
			props: { job: createJob({ media_type: 'tv' }), tracks: [track({ id: 'trk_0' })], isVideo: true, isMusic: false }
		});
		const box = screen.getByRole('checkbox', { name: 'Include track 0' });
		expect(box).toBeChecked();
		await fireEvent.click(box);
		expect(updateTrack).toHaveBeenCalledWith(expect.anything(), 'trk_0', { excluded: true });
	});
});
