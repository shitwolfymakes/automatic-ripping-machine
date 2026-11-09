import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent, within } from '$lib/test-utils';
import JobTracksTable from '../JobTracksTable.svelte';
import { createJob, createTrack } from '$lib/components/__fixtures__/job';
import type { JobView, NamingPreviewItem, TrackView } from '$lib/types/api.gen';
import { searchMetadata, updateTrackTitle } from '$lib/api/jobs';
import * as authStore from '$lib/stores/auth';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper - not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/api/jobs', () => ({
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	updateTrackTitle: vi.fn(),
	clearTrackTitle: vi.fn(),
	updateTrack: vi.fn()
}));

const setRole = (authStore as unknown as { __setRole: (r: string | null) => void }).__setRole;

const onexcludedchange = vi.fn();
const ontitleapplied = vi.fn();

interface Overrides {
	job?: Partial<JobView>;
	tracksAreSeries?: boolean;
	previews?: NamingPreviewItem[];
}

function renderTable(tracks: TrackView[], overrides: Overrides = {}) {
	return renderComponent(JobTracksTable, {
		job: createJob(overrides.job ?? {}),
		tracks,
		tracksAreSeries: overrides.tracksAreSeries ?? false,
		previewByTrack: new Map((overrides.previews ?? []).map((p) => [p.track_id, p])),
		onexcludedchange,
		ontitleapplied
	});
}

function previewItem(trackId: string, outputName: string): NamingPreviewItem {
	return {
		track_id: trackId,
		track_number: 1,
		output_path: `Dir/${outputName}`,
		output_dir: 'Dir',
		output_name: outputName
	};
}

const text = (el: HTMLElement) => (el.textContent ?? '').replace(/\s+/g, ' ').trim();
const trackRows = () => Array.from(document.querySelectorAll<HTMLElement>('tr.table-row'));
const cellOf = (row: HTMLElement, label: string) => row.querySelector<HTMLElement>(`td[data-label="${label}"]`)!;

const series = () => [
	createTrack({
		id: 'trk_1',
		index: 1,
		kind: 'video_title',
		title: 'Pilot',
		year: 2008,
		imdb_id: 'tt0959621',
		edition: 'Extended',
		role: 'episode',
		poster_url: 'https://example.test/p.jpg',
		episode_number: 1,
		episode_name: 'First',
		duration_seconds: 2750,
		size_bytes: 1_000_000_000,
		status: 'done',
		attempts: 2,
		custom_filename: 'my-pilot',
		transcode_status: 'in_progress',
		transcode_fps: 12.5,
		transcode_avg_fps: 10
	}),
	createTrack({
		id: 'trk_2',
		index: 2,
		title: null,
		episode_number: 2,
		episode_name: null,
		duration_seconds: null,
		expected_duration_seconds: 600,
		excluded: true,
		status: 'failed',
		last_error: 'MakeMKV exited 1',
		attempts: 1
	}),
	createTrack({
		id: 'trk_3',
		index: 3,
		title: null,
		episode_number: null,
		duration_seconds: null,
		expected_duration_seconds: null,
		role: 'episode',
		status: 'done'
	})
];

beforeEach(() => {
	setRole('admin');
	vi.clearAllMocks();
});

afterEach(() => {
	cleanup();
});

describe('JobTracksTable', () => {
	it('titles the table with the track count', () => {
		renderTable(series());
		expect(screen.getByText('Tracks (3)')).toBeInTheDocument();
	});

	it('has the Episode column only for a series', () => {
		renderTable(series(), { tracksAreSeries: true });
		const headers = screen.getAllByRole('columnheader').map((h) => h.textContent?.trim());
		expect(headers.slice(0, 5)).toEqual(['#', 'Kind', 'Title', 'Episode', 'Filename']);
		cleanup();
		renderTable([createTrack({ id: 'trk_1', status: 'done' })]);
		expect(screen.queryByRole('columnheader', { name: 'Episode' })).not.toBeInTheDocument();
	});

	describe('the Title column', () => {
		it('shows a titled track with its poster, year, IMDb link, edition and role', () => {
			renderTable(series());
			const cell = cellOf(trackRows()[0], 'Title');
			expect(text(cell)).toContain('Pilot (2008)');
			expect(cell.querySelector('img[data-poster]')).not.toBeNull();
			expect(within(cell).getByRole('link', { name: 'IMDb' })).toHaveAttribute(
				'href',
				'https://www.imdb.com/title/tt0959621'
			);
			expect(within(cell).getByText('Extended')).toBeInTheDocument();
			expect(within(cell).getByText('episode')).toBeInTheDocument();
		});

		it('swaps a broken track poster for the placeholder', async () => {
			renderTable(series());
			const img = cellOf(trackRows()[0], 'Title').querySelector('img[data-poster]') as HTMLImageElement;
			await fireEvent.error(img);
			expect(img.src).toContain('poster-placeholder.svg');
		});

		it('shows an untitled track under the job title and year', () => {
			renderTable(series());
			const cell = cellOf(trackRows()[1], 'Title');
			// The year follows the title with no space: pinned as rendered today.
			expect(text(cell)).toBe('Test Movie(2024)');
			expect(cell.querySelector('img')).toBeNull();
		});

		it('shows an untitled track under Untitled when the job has no title or year', () => {
			renderTable([createTrack({ id: 'trk_1', status: 'done' })], { job: { title: null, year: null } });
			expect(text(cellOf(trackRows()[0], 'Title'))).toBe('Untitled');
		});

		it('shows a titled track without extras as just its title', () => {
			renderTable([createTrack({ id: 'trk_1', status: 'done', title: 'Bare' })]);
			const cell = cellOf(trackRows()[0], 'Title');
			expect(text(cell)).toBe('Bare');
			expect(cell.querySelector('img')).toBeNull();
			expect(cell.querySelector('a')).toBeNull();
		});

		it('does not open the title search when the IMDb link is clicked', async () => {
			renderTable(series());
			const link = within(cellOf(trackRows()[0], 'Title')).getByRole('link', { name: 'IMDb' });
			link.addEventListener('click', (e) => e.preventDefault());
			await fireEvent.click(link);
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});
	});

	it('names the episode from the preview, else by number and name, else a dash', () => {
		const tracks = [...series(), createTrack({ id: 'trk_4', index: 4, episode_number: 4, episode_name: 'Fourth' })];
		renderTable(tracks, { tracksAreSeries: true, previews: [previewItem('trk_1', 'Show - S01E01.mkv')] });
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Episode'))).toBe('Show - S01E01.mkv');
		expect(text(cellOf(rows[1], 'Episode'))).toBe('2');
		expect(text(cellOf(rows[3], 'Episode'))).toBe('4 Fourth');
		expect(text(cellOf(rows[2], 'Episode'))).toBe('-');
	});

	it('shows the preview name with a custom badge, else excluded, else a dash, in Filename', () => {
		renderTable(series(), {
			previews: [previewItem('trk_1', 'Show - S01E01.mkv'), previewItem('trk_3', 'Show - S01E03.mkv')]
		});
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Filename'))).toBe('Show - S01E01.mkv custom');
		expect(text(cellOf(rows[2], 'Filename'))).toBe('Show - S01E03.mkv');
		expect(within(cellOf(rows[2], 'Filename')).queryByText('custom')).not.toBeInTheDocument();
		expect(text(cellOf(rows[1], 'Filename'))).toBe('excluded');
		cleanup();
		renderTable(series());
		expect(text(cellOf(trackRows()[2], 'Filename'))).toBe('-');
	});

	it('shows the duration, else the expected duration with a tilde, else a dash', () => {
		renderTable(series());
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Length'))).toBe('45:50');
		expect(text(cellOf(rows[1], 'Length'))).toBe('~10:00');
		expect(text(cellOf(rows[2], 'Length'))).toBe('-');
	});

	it('shows rip status, with the attempt count only after a retry', () => {
		renderTable(series());
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Rip'))).toContain('x2');
		expect(text(cellOf(rows[1], 'Rip'))).not.toContain('x1');
		expect(text(cellOf(rows[1], 'Rip'))).toContain('Failed');
	});

	it('shows transcode status with fps only while in progress, else a dash', () => {
		renderTable(series());
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Transcode'))).toContain('12.5 fps (avg 10.0)');
		expect(text(cellOf(rows[1], 'Transcode'))).toBe('-');
	});

	it('shows transcode status without fps when the encoder has not reported a rate', () => {
		renderTable([
			createTrack({ id: 'trk_1', status: 'done', transcode_status: 'in_progress', transcode_fps: null }),
			createTrack({ id: 'trk_2', index: 1, status: 'done', transcode_status: 'done', transcode_fps: 30 })
		]);
		const rows = trackRows();
		expect(text(cellOf(rows[0], 'Transcode'))).not.toContain('fps');
		expect(text(cellOf(rows[1], 'Transcode'))).not.toContain('fps');
	});

	it("shows a failed track's last error under its row, and nothing for other cases", () => {
		renderTable([
			...series(),
			createTrack({ id: 'trk_4', index: 4, status: 'failed', last_error: null }),
			createTrack({ id: 'trk_5', index: 5, status: 'done', last_error: 'stale error' })
		]);
		expect(screen.getByText('MakeMKV exited 1')).toBeInTheDocument();
		expect(screen.getAllByText('Error:')).toHaveLength(1);
		expect(screen.queryByText('stale error')).not.toBeInTheDocument();
	});

	describe('the Include column', () => {
		it('calls onexcludedchange with the track id and the new value', async () => {
			renderTable(series());
			const boxes = screen.getAllByRole('checkbox') as HTMLInputElement[];
			expect(boxes.map((b) => b.checked)).toEqual([true, false, true]);
			await fireEvent.click(boxes[0]);
			expect(onexcludedchange).toHaveBeenLastCalledWith('trk_1', true);
			await fireEvent.click(boxes[1]);
			expect(onexcludedchange).toHaveBeenLastCalledWith('trk_2', false);
		});

		it('shows a non-admin Included or Excluded as text', () => {
			setRole('guest');
			renderTable(series());
			expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
			const rows = trackRows();
			expect(text(cellOf(rows[0], 'Include'))).toBe('Included');
			expect(text(cellOf(rows[1], 'Include'))).toBe('Excluded');
		});
	});

	describe('per-track title search', () => {
		const picked = { title: 'Picked', year: 2001, kind: 'movie', poster_url: null, provider_id: 'tt3333' };
		const two = () => [createTrack({ id: 'trk_1', status: 'done' }), createTrack({ id: 'trk_2', index: 1 })];

		it('opens under the row when an admin clicks the title cell and closes on the next click', async () => {
			renderTable([createTrack({ id: 'trk_1', status: 'done' })]);
			const cell = cellOf(trackRows()[0], 'Title');
			await fireEvent.click(cell);
			expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
			await fireEvent.click(cell);
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});

		it('moves from one track to another when a second title cell is clicked', async () => {
			renderTable(two());
			const rows = trackRows();
			await fireEvent.click(cellOf(rows[0], 'Title'));
			await fireEvent.click(cellOf(rows[1], 'Title'));
			expect(screen.getAllByRole('button', { name: 'Search' })).toHaveLength(1);
		});

		it('closes from its close button', async () => {
			renderTable(two());
			await fireEvent.click(cellOf(trackRows()[0], 'Title'));
			await fireEvent.click(screen.getByTitle('Close'));
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});

		it('closes on applying a match and calls ontitleapplied', async () => {
			vi.mocked(searchMetadata).mockResolvedValue({ candidates: [picked] });
			vi.mocked(updateTrackTitle).mockResolvedValue(undefined as never);
			renderTable(two());
			await fireEvent.click(cellOf(trackRows()[0], 'Title'));
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByText('Picked'));
			await fireEvent.click(await screen.findByRole('button', { name: 'Apply' }));
			await waitFor(() => expect(ontitleapplied).toHaveBeenCalledTimes(1));
			await waitFor(() => expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument());
		});

		it('opens nothing when a guest clicks a title cell', async () => {
			setRole('guest');
			renderTable(two());
			await fireEvent.click(cellOf(trackRows()[0], 'Title'));
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
		});
	});
});
