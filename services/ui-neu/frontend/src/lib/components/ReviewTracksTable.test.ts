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

function scanTitle(overrides: Record<string, unknown> = {}) {
	return {
		index: 0,
		duration_seconds: 4568,
		chapter_count: 6,
		size_bytes: 1993701376,
		source_file: 'B1_t00.mkv',
		...overrides
	} as any;
}

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

	it('falls back to scanned titles when there are no materialized tracks', () => {
		renderComponent(ReviewTracksTable, {
			props: {
				job,
				tracks: [],
				scanTitles: [scanTitle({ index: 0 }), scanTitle({ index: 1, source_file: 'B1_t01.mkv' })],
				isVideo: true,
				isMusic: false,
				onrefresh: vi.fn()
			}
		});
		expect(screen.getByText('Scanned titles (2)')).toBeInTheDocument();
		// length rendered from the scan (4568s -> 1h 16m 8s)
		expect(screen.getAllByText(/1h 16m/).length).toBeGreaterThan(0);
		// read-only: no episode input rendered for scanned rows
		expect(screen.queryByPlaceholderText('--')).not.toBeInTheDocument();
	});

	it('materialized tracks win over scanned titles when both are present', () => {
		renderComponent(ReviewTracksTable, {
			props: {
				job,
				tracks: [track()],
				scanTitles: [scanTitle(), scanTitle({ index: 1 }), scanTitle({ index: 2 })],
				isVideo: true,
				isMusic: false,
				onrefresh: vi.fn()
			}
		});
		expect(screen.getByText('Tracks (1)')).toBeInTheDocument();
		expect(screen.queryByText(/Scanned titles/)).not.toBeInTheDocument();
	});

	it('shows "No tracks yet." when there are neither tracks nor scanned titles', () => {
		renderComponent(ReviewTracksTable, {
			props: { job, tracks: [], scanTitles: [], isVideo: true, isMusic: false, onrefresh: vi.fn() }
		});
		expect(screen.getByText('No tracks yet.')).toBeInTheDocument();
	});

	it('a scanned title row is read-only (clicking it does not open TrackTitleSearch)', async () => {
		renderComponent(ReviewTracksTable, {
			props: { job, tracks: [], scanTitles: [scanTitle()], isVideo: true, isMusic: false, onrefresh: vi.fn() }
		});
		// the title cell shows an em-dash and is not clickable → no search field appears
		// (isVideo: true also renders a second em-dash in the episode column, so use getAllByText)
		await fireEvent.click(screen.getAllByText('—')[0]);
		expect(screen.queryByPlaceholderText('Title...')).not.toBeInTheDocument();
	});
});
