import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/test-utils';
import ReviewTracksTable from './ReviewTracksTable.svelte';
import type { TrackView } from '$lib/types/api.gen';
import { createJob } from './__fixtures__/job';

vi.mock('$lib/api/jobs', () => ({
	updateTrack: vi.fn(),
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
					track({ id: 'trk_0', index: 0, source_ref: '0', role: 'episode', episode_number: 1, duration_seconds: 3093 }),
					track({ id: 'trk_5', index: 5, source_ref: '5', role: 'extra', duration_seconds: 542 }),
					track({ id: 'trk_6', index: 6, source_ref: '6', duration_seconds: 2990 })
				],
				isVideo: true,
				isMusic: false
			}
		});
		expect(screen.getByTestId('track-role')).toHaveTextContent('Extra');
		// The episode and the unplaced title keep their number box.
		expect(screen.getAllByPlaceholderText('--')).toHaveLength(2);
	});
});
