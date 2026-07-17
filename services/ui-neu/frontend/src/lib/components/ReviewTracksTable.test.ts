import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, waitFor, cleanup } from '$lib/test-utils';

vi.mock('$lib/api/jobs', () => ({
	updateTrack: vi.fn()
}));
import { updateTrack } from '$lib/api/jobs';
import ReviewTracksTable from './ReviewTracksTable.svelte';

const mockUpdateTrack = vi.mocked(updateTrack);

function track(overrides: Record<string, unknown> = {}) {
	return {
		id: 'trk_1', index: 1, title: null, year: null,
		episode_number: null, excluded: false,
		duration_seconds: 3600, output_path: null, source_ref: 't00',
		...overrides
	} as any;
}
const job = { id: 'job_1', title: 'X', year: 2000 } as any;

beforeEach(() => {
	mockUpdateTrack.mockReset();
	mockUpdateTrack.mockResolvedValue({} as any);
});

afterEach(() => {
	cleanup();
});

describe('ReviewTracksTable', () => {
	it('renders a row per track', () => {
		renderComponent(ReviewTracksTable, {
			props: { job, tracks: [track(), track({ id: 'trk_2', index: 2 })], isVideo: true, isMusic: false, onrefresh: vi.fn() }
		});
		expect(screen.getByText('Tracks (2)')).toBeInTheDocument();
	});

	it('editing an episode number calls updateTrack', async () => {
		renderComponent(ReviewTracksTable, {
			props: { job, tracks: [track()], isVideo: true, isMusic: false, onrefresh: vi.fn() }
		});
		const ep = screen.getByPlaceholderText('--');
		await fireEvent.change(ep, { target: { value: '4' } });
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledWith('job_1', 'trk_1', { episode_number: 4 }));
	});

	it('clicking the title cell toggles the per-track search row open', async () => {
		renderComponent(ReviewTracksTable, {
			props: { job, tracks: [track()], isVideo: true, isMusic: false, onrefresh: vi.fn() }
		});
		// no search row initially
		expect(screen.queryByPlaceholderText('Title...')).not.toBeInTheDocument();
		// clicking the title cell (the untitled fallback text "X (2000)") opens TrackTitleSearch
		await fireEvent.click(screen.getByText(/^X/));
		// TrackTitleSearch renders a search input with placeholder "Title..."
		await waitFor(() => expect(screen.getByPlaceholderText('Title...')).toBeInTheDocument());
	});
});
