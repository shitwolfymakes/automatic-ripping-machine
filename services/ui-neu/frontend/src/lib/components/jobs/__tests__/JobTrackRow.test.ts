import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent, within } from '$lib/testing/render';
import JobTrackRowHarness from './JobTrackRowHarness.svelte';
import { createJob, createTrack } from '$lib/__fixtures__/job';
import type { JobView, NamingPreviewItem, TrackView } from '$lib/types/api.gen';
import { searchMetadata, updateTrack } from '$lib/api/jobs';
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
	clearTrackTitle: vi.fn(),
	updateTrack: vi.fn()
}));

const setRole = (authStore as unknown as { __setRole: (r: string | null) => void }).__setRole;

const onexcludedchange = vi.fn();
const ontitleapplied = vi.fn();
const ontoggleedit = vi.fn();
const oncloseedit = vi.fn();

interface Overrides {
	job?: Partial<JobView>;
	tracksAreSeries?: boolean;
	preview?: NamingPreviewItem;
	editing?: boolean;
}

function renderRow(track: TrackView, overrides: Overrides = {}) {
	return renderComponent(JobTrackRowHarness, {
		job: createJob(overrides.job ?? {}),
		track,
		preview: overrides.preview,
		tracksAreSeries: overrides.tracksAreSeries ?? false,
		editing: overrides.editing ?? false,
		ontoggleedit,
		oncloseedit,
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
const row = () => document.querySelector<HTMLElement>('tr.table-row')!;
const cell = (label: string) => row().querySelector<HTMLElement>(`td[data-label="${label}"]`)!;

const pilot = () =>
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
	});

const failed = () =>
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
	});

const bare = () =>
	createTrack({
		id: 'trk_3',
		index: 3,
		title: null,
		episode_number: null,
		duration_seconds: null,
		expected_duration_seconds: null,
		role: 'episode',
		status: 'done'
	});

beforeEach(() => {
	setRole('admin');
	vi.clearAllMocks();
});

afterEach(() => {
	cleanup();
});

describe('JobTrackRow', () => {
	it('marks an excluded track disabled and shows its index', () => {
		renderRow(failed());
		expect(row()).toHaveAttribute('data-disabled', 'true');
		expect(text(cell('#'))).toBe('2');
	});

	describe('the Title column', () => {
		it('shows a titled track with its poster, year, IMDb link, edition and role', () => {
			renderRow(pilot());
			const title = cell('Title');
			expect(text(title)).toContain('Pilot (2008)');
			expect(title.querySelector('img[data-poster]')).not.toBeNull();
			expect(within(title).getByRole('link', { name: 'IMDb' })).toHaveAttribute(
				'href',
				'https://www.imdb.com/title/tt0959621'
			);
			expect(within(title).getByText('Extended')).toBeInTheDocument();
			expect(within(title).getByText('episode')).toBeInTheDocument();
		});

		it('swaps a broken track poster for the placeholder', async () => {
			renderRow(pilot());
			const img = cell('Title').querySelector('img[data-poster]') as HTMLImageElement;
			await fireEvent.error(img);
			expect(img.src).toContain('poster-placeholder.svg');
		});

		it('shows an untitled track under the job title and year', () => {
			renderRow(failed());
			// The year follows the title with no space: pinned as rendered today.
			expect(text(cell('Title'))).toBe('Test Movie(2024)');
			expect(cell('Title').querySelector('img')).toBeNull();
		});

		it('shows an untitled track under Untitled when the job has no title or year', () => {
			renderRow(createTrack({ id: 'trk_1', status: 'done' }), { job: { title: null, year: null } });
			expect(text(cell('Title'))).toBe('Untitled');
		});

		it('shows a titled track without extras as just its title', () => {
			renderRow(createTrack({ id: 'trk_1', status: 'done', title: 'Bare' }));
			expect(text(cell('Title'))).toBe('Bare');
			expect(cell('Title').querySelector('img')).toBeNull();
			expect(cell('Title').querySelector('a')).toBeNull();
		});

		it('does not toggle the edit when the IMDb link is clicked', async () => {
			renderRow(pilot());
			const link = within(cell('Title')).getByRole('link', { name: 'IMDb' });
			link.addEventListener('click', (e) => e.preventDefault());
			await fireEvent.click(link);
			expect(ontoggleedit).not.toHaveBeenCalled();
		});

		it('calls ontoggleedit when an admin clicks the title cell', async () => {
			renderRow(pilot());
			await fireEvent.click(cell('Title'));
			expect(ontoggleedit).toHaveBeenCalledTimes(1);
		});

		it('calls nothing when a guest clicks the title cell', async () => {
			setRole('guest');
			renderRow(pilot());
			await fireEvent.click(cell('Title'));
			expect(ontoggleedit).not.toHaveBeenCalled();
		});
	});

	describe('the Episode column', () => {
		it('is absent unless the tracks are a series', () => {
			renderRow(pilot());
			expect(row().querySelector('td[data-label="Episode"]')).toBeNull();
		});

		it('names the episode from the preview', () => {
			renderRow(pilot(), { tracksAreSeries: true, preview: previewItem('trk_1', 'Show - S01E01.mkv') });
			expect(text(cell('Episode'))).toBe('Show - S01E01.mkv');
		});

		it('names the episode by number and name, or by number alone', () => {
			renderRow(pilot(), { tracksAreSeries: true });
			expect(text(cell('Episode'))).toBe('1 First');
			cleanup();
			renderRow(failed(), { tracksAreSeries: true });
			expect(text(cell('Episode'))).toBe('2');
		});

		it('shows a dash when the track has no episode', () => {
			renderRow(bare(), { tracksAreSeries: true });
			expect(text(cell('Episode'))).toBe('-');
		});
	});

	it('shows the preview name with a custom badge, else excluded, else a dash, in Filename', () => {
		renderRow(pilot(), { preview: previewItem('trk_1', 'Show - S01E01.mkv') });
		expect(text(cell('Filename'))).toBe('Show - S01E01.mkv custom');
		expect(cell('Filename')).toHaveAttribute('title', 'Show - S01E01.mkv');
		cleanup();
		renderRow(bare(), { preview: previewItem('trk_3', 'Show - S01E03.mkv') });
		expect(text(cell('Filename'))).toBe('Show - S01E03.mkv');
		expect(within(cell('Filename')).queryByText('custom')).not.toBeInTheDocument();
		cleanup();
		renderRow(failed());
		expect(text(cell('Filename'))).toBe('excluded');
		cleanup();
		renderRow(bare());
		expect(text(cell('Filename'))).toBe('-');
		expect(cell('Filename')).toHaveAttribute('title', '');
	});

	it('shows the duration, else the expected duration with a tilde, else a dash', () => {
		renderRow(pilot());
		expect(text(cell('Length'))).toBe('45:50');
		cleanup();
		renderRow(failed());
		expect(text(cell('Length'))).toBe('~10:00');
		cleanup();
		renderRow(bare());
		expect(text(cell('Length'))).toBe('-');
	});

	it('shows the kind and size labels', () => {
		renderRow(pilot());
		expect(text(cell('Kind'))).not.toBe('');
		expect(text(cell('Size'))).not.toBe('');
	});

	it('shows rip status, with the attempt count only after a retry', () => {
		renderRow(pilot());
		expect(text(cell('Rip'))).toContain('x2');
		cleanup();
		renderRow(failed());
		expect(text(cell('Rip'))).not.toContain('x1');
		expect(text(cell('Rip'))).toContain('Failed');
	});

	it('shows transcode status with fps only while in progress, else a dash', () => {
		renderRow(pilot());
		expect(text(cell('Transcode'))).toContain('12.5 fps (avg 10.0)');
		cleanup();
		renderRow(failed());
		expect(text(cell('Transcode'))).toBe('-');
	});

	it('shows transcode status without fps when the encoder has not reported a rate', () => {
		renderRow(createTrack({ id: 'trk_1', status: 'done', transcode_status: 'in_progress', transcode_fps: null }));
		expect(text(cell('Transcode'))).not.toContain('fps');
		cleanup();
		renderRow(createTrack({ id: 'trk_2', status: 'done', transcode_status: 'done', transcode_fps: 30 }));
		expect(text(cell('Transcode'))).not.toContain('fps');
	});

	it("shows a failed track's last error under its row, and nothing for other cases", () => {
		renderRow(failed());
		expect(screen.getByText('MakeMKV exited 1')).toBeInTheDocument();
		expect(screen.getAllByText('Error:')).toHaveLength(1);
		cleanup();
		renderRow(createTrack({ id: 'trk_4', index: 4, status: 'failed', last_error: null }));
		expect(screen.queryByText('Error:')).not.toBeInTheDocument();
		cleanup();
		renderRow(createTrack({ id: 'trk_5', index: 5, status: 'done', last_error: 'stale error' }));
		expect(screen.queryByText('stale error')).not.toBeInTheDocument();
	});

	describe('the Include column', () => {
		it('calls onexcludedchange with the track id and the new value', async () => {
			renderRow(pilot());
			const box = screen.getByRole('checkbox') as HTMLInputElement;
			expect(box.checked).toBe(true);
			await fireEvent.click(box);
			expect(onexcludedchange).toHaveBeenLastCalledWith('trk_1', true);
			cleanup();
			renderRow(failed());
			const other = screen.getByRole('checkbox') as HTMLInputElement;
			expect(other.checked).toBe(false);
			await fireEvent.click(other);
			expect(onexcludedchange).toHaveBeenLastCalledWith('trk_2', false);
		});

		it('shows a non-admin Included or Excluded as text', () => {
			setRole('guest');
			renderRow(pilot());
			expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
			expect(text(cell('Include'))).toBe('Included');
			cleanup();
			renderRow(failed());
			expect(text(cell('Include'))).toBe('Excluded');
		});
	});

	describe('the title search row', () => {
		const picked = { title: 'Picked', year: 2001, kind: 'movie', poster_url: null, provider_id: 'tt3333' };

		it('renders only while editing', () => {
			renderRow(pilot());
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
			cleanup();
			renderRow(pilot(), { editing: true });
			expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
		});

		it('calls oncloseedit from its close button', async () => {
			renderRow(pilot(), { editing: true });
			await fireEvent.click(screen.getByTitle('Close'));
			expect(oncloseedit).toHaveBeenCalledTimes(1);
		});

		it('calls ontitleapplied on applying a match', async () => {
			vi.mocked(searchMetadata).mockResolvedValue({ candidates: [picked] });
			vi.mocked(updateTrack).mockResolvedValue(undefined as never);
			renderRow(pilot(), { editing: true });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByText('Picked'));
			await fireEvent.click(await screen.findByRole('button', { name: 'Apply' }));
			await waitFor(() => expect(ontitleapplied).toHaveBeenCalledTimes(1));
		});
	});
});
