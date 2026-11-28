// Open arms the coverage tool reports that are Svelte's, not the component's:
// each text or attribute `{...}` below compiles to `(...) ?? ''`, and each sits
// inside an #if on the same value. The track's year, the job's year, the
// track's IMDb link, the attempt count (inside `attempts > 1`) and the failed
// track's last error.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent, within } from '$lib/testing/render';
import JobTrackRowHarness from './JobTrackRowHarness.svelte';
import { createJob, createTrack } from '$lib/__fixtures__/job';
import type { JobView, NamingPreviewItem, TrackView } from '$lib/types/api.gen';
import { searchMetadata, updateTrack } from '$lib/api/jobs';
import type { TitleClassLabel } from '$lib/jobs/title-class';
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
const onstageretried = vi.fn();
const ontoggleedit = vi.fn();
const oncloseedit = vi.fn();

interface Overrides {
	job?: Partial<JobView>;
	tracksAreSeries?: boolean;
	preview?: NamingPreviewItem;
	editing?: boolean;
	excludeError?: string | null;
	classLabel?: TitleClassLabel | null;
	nameable?: boolean;
}

function renderRow(track: TrackView, overrides: Overrides = {}) {
	return renderComponent(JobTrackRowHarness, {
		job: createJob(overrides.job ?? {}),
		track,
		classLabel: overrides.classLabel ?? null,
		nameable: overrides.nameable ?? false,
		preview: overrides.preview,
		tracksAreSeries: overrides.tracksAreSeries ?? false,
		editing: overrides.editing ?? false,
		ontoggleedit,
		oncloseedit,
		onexcludedchange,
		excludeError: overrides.excludeError,
		ontitleapplied,
		onstageretried
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

describe('JobTrackRow title class', () => {
	it('shows the class label in the meta pills, and none for a plain title', () => {
		renderRow(pilot(), { classLabel: { text: 'Copy of #0', tone: 'muted' } });
		expect(screen.getByTestId('track-class-label')).toHaveTextContent('Copy of #0');
		cleanup();
		renderRow(pilot());
		expect(screen.queryByTestId('track-class-label')).toBeNull();
	});
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

		it('lets an admin name a version of the film, and hides the edit from a title that is not one', async () => {
			renderRow({ ...pilot(), edition: null }, { nameable: true });
			expect(within(cell('Title')).getByRole('button', { name: 'Edit Edition name' })).toBeInTheDocument();
			cleanup();
			renderRow({ ...pilot(), edition: null });
			expect(within(cell('Title')).queryByRole('button', { name: 'Edit Edition name' })).toBeNull();
		});

		it('shows an edition name read-only to a non-admin', () => {
			setRole('guest');
			renderRow(pilot(), { nameable: true });
			expect(within(cell('Title')).getByText('Extended')).toBeInTheDocument();
			expect(within(cell('Title')).queryByRole('button', { name: 'Edit Edition name' })).toBeNull();
			setRole('admin');
		});

		it('swaps a broken track poster for the poster fallback', async () => {
			renderRow(pilot());
			const img = cell('Title').querySelector('img[data-poster]') as HTMLImageElement;
			await fireEvent.error(img);
			expect(cell('Title').querySelector('img[data-poster]')).toBeNull();
			expect(cell('Title').querySelector('.poster-image-fallback.job-detail-track-poster')).not.toBeNull();
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

		it('gives an admin a title button that calls ontoggleedit and reports the edit state', async () => {
			renderRow(pilot());
			const button = within(cell('Title')).getByRole('button', { name: 'Pilot (2008)' });
			expect(button).toHaveAttribute('aria-expanded', 'false');
			await fireEvent.click(button);
			expect(ontoggleedit).toHaveBeenCalledTimes(1);
			cleanup();
			renderRow(pilot(), { editing: true });
			expect(within(cell('Title')).getByRole('button', { name: 'Pilot (2008)' })).toHaveAttribute(
				'aria-expanded',
				'true'
			);
		});

		it('opens the edit from the job title of an untitled track too', async () => {
			renderRow(bare(), { job: { title: 'Show', year: 2001 } });
			await fireEvent.click(within(cell('Title')).getByRole('button', { name: /^Show/ }));
			expect(ontoggleedit).toHaveBeenCalledTimes(1);
		});

		it('gives a guest no title button, and a click on the cell calls nothing', async () => {
			setRole('guest');
			renderRow(pilot());
			expect(within(cell('Title')).queryByRole('button')).not.toBeInTheDocument();
			await fireEvent.click(cell('Title'));
			expect(ontoggleedit).not.toHaveBeenCalled();
			cleanup();
			renderRow(bare());
			expect(within(cell('Title')).queryByRole('button')).not.toBeInTheDocument();
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

	it('says "Waiting for files" for a queued encode whose staged copy is not ready', () => {
		const stage = { status: 'pending', bytes_durable: 0, attempts: 0 } as TrackView['stage'];
		renderRow(createTrack({ id: 'trk_1', status: 'done', transcode_status: 'queued', stage }));
		expect(text(cell('Transcode'))).toBe('Waiting for files');
		cleanup();
		renderRow(createTrack({ id: 'trk_1', status: 'done', transcode_status: 'queued', stage: null }));
		expect(text(cell('Transcode'))).not.toContain('Waiting for files');
	});

	it('adds a staging line under a track whose copy has not finished, and none once staged', () => {
		const stage = (status: string) =>
			({ status, bytes_durable: 0, attempts: 1, last_error: 'boom' }) as TrackView['stage'];
		renderRow(createTrack({ id: 'trk_1', status: 'done', stage: stage('failed') }));
		expect(screen.getByTestId('track-stage-row')).toBeInTheDocument();
		cleanup();
		renderRow(createTrack({ id: 'trk_1', status: 'done', stage: stage('staged') }));
		expect(screen.queryByTestId('track-stage-row')).toBeNull();
		cleanup();
		renderRow(createTrack({ id: 'trk_1', status: 'done', stage: null }));
		expect(screen.queryByTestId('track-stage-row')).toBeNull();
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

		it('words the box by what a tick does', () => {
			renderRow(pilot(), { job: { status: 'awaiting_review', rip_invocation: 'per_title' } });
			expect(screen.getByRole('checkbox')).toHaveAttribute('title', 'Rip and transcode this title');
			cleanup();
			renderRow(pilot(), { job: { status: 'ripped', rip_invocation: 'per_title' } });
			expect(screen.getByRole('checkbox')).toHaveAttribute('title', 'Include this title in the transcode');
		});

		it('disables the box of a title that was not ripped', () => {
			renderRow(createTrack({ id: 'trk_3', index: 3, status: 'skipped', excluded: true }), {
				job: { status: 'ripped', rip_invocation: 'per_title' }
			});
			const box = screen.getByRole('checkbox');
			expect(box).toBeDisabled();
			expect(box).toHaveAttribute('title', 'Not ripped: it was unticked when the rip started');
		});

		it('shows why the last toggle failed under the checkbox', () => {
			renderRow(pilot(), { excludeError: 'denied' });
			expect(screen.getByRole('alert')).toHaveTextContent('denied');
			expect(screen.getByRole('checkbox')).toBeInTheDocument();
		});

		it('shows no toggle error by default', () => {
			renderRow(pilot());
			expect(screen.queryByRole('alert')).not.toBeInTheDocument();
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

		it('offers Set by hand while editing', () => {
			renderRow(pilot(), { editing: true });
			expect(screen.getByRole('button', { name: 'Set by hand' })).toBeInTheDocument();
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
