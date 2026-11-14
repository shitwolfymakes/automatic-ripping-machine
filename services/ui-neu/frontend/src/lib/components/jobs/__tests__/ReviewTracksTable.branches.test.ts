import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import type { MetadataCandidate, ScanTitle, TrackView } from '$lib/types/api.gen';
import ReviewTracksTable from '../ReviewTracksTable.svelte';
import { createJob } from '../../../__fixtures__/job';

// Branch pins for ReviewTracksTable, beside ReviewTracksTable.test.ts. Every
// branch is reachable from the rendered component.

const { adminStore } = await vi.hoisted(async () => {
	const { writable } = await import('svelte/store');
	return { adminStore: writable(true) };
});

vi.mock('$lib/stores/auth', () => ({
	isAdmin: { subscribe: adminStore.subscribe }
}));

vi.mock('$lib/api/jobs', () => ({
	updateTrack: vi.fn(() => Promise.resolve({})),
	clearTrackTitle: vi.fn(() => Promise.resolve()),
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn()
}));
import { updateTrack, clearTrackTitle, searchMetadata } from '$lib/api/jobs';
const mockUpdate = vi.mocked(updateTrack);
const mockClear = vi.mocked(clearTrackTitle);
const mockSearch = vi.mocked(searchMetadata);

const track = (o: Partial<TrackView>): TrackView =>
	({ id: 'trk_0', index: 0, source_ref: '0', kind: 'video_title', duration_seconds: null, ...o }) as TrackView;

const scan = (o: Partial<ScanTitle>): ScanTitle => ({ index: 0, duration_seconds: 100, ...o });

const candidate: MetadataCandidate = {
	title: 'Picked',
	year: 2021,
	kind: 'movie',
	poster_url: null,
	provider_id: 'tt1'
};

function renderTable(props: Record<string, unknown> = {}) {
	return renderComponent(ReviewTracksTable, {
		props: { job: createJob({ media_type: 'tv' }), tracks: [], isVideo: true, isMusic: false, ...props }
	});
}

beforeEach(() => {
	adminStore.set(true);
});

afterEach(() => {
	cleanup();
	vi.clearAllMocks();
});

describe('ReviewTracksTable header', () => {
	it('titles a track list "Tracks (N)" with Title, Episode and search columns for video', () => {
		renderTable({ tracks: [track({ id: 'a' }), track({ id: 'b', index: 1 })] });
		expect(screen.getByRole('heading', { name: 'Tracks (2)' })).toBeInTheDocument();
		expect(screen.getByRole('columnheader', { name: 'Title' })).toBeInTheDocument();
		expect(screen.getByRole('columnheader', { name: 'Episode' })).toBeInTheDocument();
		expect(screen.getAllByRole('columnheader')).toHaveLength(7);
	});

	it('titles a scan list "Scanned titles (N)"', () => {
		renderTable({ tracks: [], scanTitles: [scan({ index: 1 })] });
		expect(screen.getByRole('heading', { name: 'Scanned titles (1)' })).toBeInTheDocument();
	});

	it('calls the first column Name for music and drops the video columns', () => {
		renderTable({ tracks: [track({ id: 'a' })], isVideo: false, isMusic: true });
		expect(screen.getByRole('columnheader', { name: 'Name' })).toBeInTheDocument();
		expect(screen.queryByRole('columnheader', { name: 'Title' })).toBeNull();
		expect(screen.queryByRole('columnheader', { name: 'Episode' })).toBeNull();
		expect(screen.getAllByRole('columnheader')).toHaveLength(5);
		expect(screen.queryByTitle('Search title')).toBeNull();
	});

	it('says "No tracks yet." with neither tracks nor scanned titles', () => {
		renderTable();
		expect(screen.getByText('No tracks yet.')).toBeInTheDocument();
		expect(screen.queryByRole('table')).toBeNull();
	});
});

describe('ReviewTracksTable title cell', () => {
	it('shows the row title with its year', () => {
		renderTable({ tracks: [track({ title: 'Alpha', year: 1999 })] });
		expect(screen.getByText('Alpha')).toBeInTheDocument();
		expect(screen.getByText('(1999)')).toBeInTheDocument();
	});

	it('shows the row title alone without a year', () => {
		renderTable({ tracks: [track({ title: 'Alpha' })] });
		expect(screen.getByText('Alpha')).toBeInTheDocument();
		expect(screen.getByText('Alpha').parentElement).toHaveTextContent(/^Alpha$/);
	});

	it('falls back to the job title and year for an untitled track', () => {
		renderTable({ job: createJob({ title: 'Test Movie', year: 2024 }), tracks: [track({})] });
		expect(screen.getByText(/Test Movie/)).toHaveTextContent(/^Test Movie\s*\(2024\)$/);
	});

	it('falls back to the job title without a year when the job has none', () => {
		renderTable({ job: createJob({ title: 'Test Movie', year: null }), tracks: [track({})] });
		expect(screen.getByText(/Test Movie/)).toHaveTextContent(/^Test Movie$/);
	});

	it('falls back to "Untitled" for an untitled track on an untitled job', () => {
		renderTable({ job: createJob({ title: '', year: null }), tracks: [track({})] });
		expect(screen.getByText('Untitled')).toBeInTheDocument();
	});

	it('shows "Untitled" with the job year when only the year is known', () => {
		renderTable({ job: createJob({ title: '', year: 2001 }), tracks: [track({})] });
		expect(screen.getByText(/Untitled/)).toHaveTextContent(/^Untitled\s*\(2001\)$/);
	});

	it('shows "-" for a scanned title, in the title, episode and include cells', () => {
		renderTable({ scanTitles: [scan({ index: 3 })] });
		expect(screen.getAllByText('-')).toHaveLength(3);
		expect(screen.queryByTitle('Search title')).toBeNull();
		expect(screen.queryByRole('checkbox')).toBeNull();
	});
});

describe('ReviewTracksTable episode cell', () => {
	it('shows the generated name from fileNames', () => {
		renderTable({
			tracks: [track({ id: 'a', role: 'episode', episode_number: 1 })],
			fileNames: new Map([['a', 'Show - S01E01.mkv']])
		});
		expect(screen.getByTestId('track-generated-name')).toHaveTextContent('Show - S01E01.mkv');
		expect(screen.queryByPlaceholderText('--')).toBeNull();
	});

	it.each([
		['extra', 'Extra'],
		['trailer', 'Trailer'],
		['other', 'Other']
	] as const)('shows a "%s" without an episode number as the %s chip', (role, label) => {
		renderTable({ tracks: [track({ role })] });
		expect(screen.getByTestId('track-role')).toHaveTextContent(label);
		expect(screen.queryByPlaceholderText('--')).toBeNull();
	});

	it.each([['main'], ['episode'], [undefined]] as const)('shows the number input for role %s', (role) => {
		renderTable({ tracks: [track({ role })] });
		expect(screen.getByPlaceholderText('--')).toBeInTheDocument();
		expect(screen.queryByTestId('track-role')).toBeNull();
	});

	it('shows the number input for an extra that has an episode number', () => {
		renderTable({ tracks: [track({ role: 'extra', episode_number: 7 })] });
		expect(screen.getByPlaceholderText('--')).toHaveValue('7');
		expect(screen.queryByTestId('track-role')).toBeNull();
	});

	it('leaves the number input empty without an episode number', () => {
		renderTable({ tracks: [track({ role: 'episode' })] });
		expect(screen.getByPlaceholderText('--')).toHaveValue('');
	});

	it('shows the episode name beside the input when there is a number and a name', () => {
		renderTable({ tracks: [track({ role: 'episode', episode_number: 2, episode_name: 'Pilot' })] });
		expect(screen.getByTestId('track-episode-name')).toHaveTextContent('Pilot');
	});

	it('hides the episode name when there is a number but no name', () => {
		renderTable({ tracks: [track({ role: 'episode', episode_number: 2 })] });
		expect(screen.queryByTestId('track-episode-name')).toBeNull();
	});

	it('hides the episode name when there is a name but no number', () => {
		renderTable({ tracks: [track({ role: 'episode', episode_name: 'Pilot' })] });
		expect(screen.queryByTestId('track-episode-name')).toBeNull();
	});

	it('disables the input and marks the row on an excluded track', () => {
		renderTable({ tracks: [track({ role: 'episode', excluded: true })] });
		const input = screen.getByPlaceholderText('--');
		expect(input).toBeDisabled();
		expect(input.closest('tr')).toHaveAttribute('data-disabled', 'true');
	});

	it('leaves the input enabled and the row unmarked on an included track', () => {
		renderTable({ tracks: [track({ role: 'episode' })] });
		const input = screen.getByPlaceholderText('--');
		expect(input).toBeEnabled();
		expect(input.closest('tr')).toHaveAttribute('data-disabled', 'false');
	});
});

describe('ReviewTracksTable length', () => {
	it.each([
		['null', null, '--'],
		['undefined', undefined, '--'],
		['0', 0, '--'],
		['59s', 59, '0m 59s'],
		['123s', 123, '2m 3s'],
		['3600s', 3600, '1h 0m 0s'],
		['3723s', 3723, '1h 2m 3s']
	])('shows %s as "%s"', (_name, secs, text) => {
		renderTable({ tracks: [track({ duration_seconds: secs as number | null })] });
		expect(screen.getByText(text)).toBeInTheDocument();
	});
});

describe('ReviewTracksTable include cell', () => {
	it('shows the checkbox to an admin', () => {
		renderTable({ tracks: [track({ id: 'a', index: 4 })] });
		expect(screen.getByRole('checkbox', { name: 'Include track 4' })).toBeChecked();
	});

	it('shows "Included" as text to a guest', () => {
		adminStore.set(false);
		renderTable({ tracks: [track({})] });
		expect(screen.getByText('Included')).toBeInTheDocument();
		expect(screen.queryByRole('checkbox')).toBeNull();
	});

	it('shows "Excluded" as text to a guest for an excluded track', () => {
		adminStore.set(false);
		renderTable({ tracks: [track({ excluded: true })] });
		expect(screen.getByText('Excluded')).toBeInTheDocument();
		expect(screen.queryByRole('checkbox')).toBeNull();
	});
});

describe('ReviewTracksTable updates', () => {
	it.each([
		['3', 3],
		[' 4 ', 4],
		['1e2', 100],
		['', null],
		['   ', null],
		['abc', null],
		['Infinity', null]
	])('sends episode_number for the input value %j as %j', async (raw, expected) => {
		const onrefresh = vi.fn();
		renderTable({ job: createJob({ id: 'job_9' }), tracks: [track({ id: 'a', role: 'episode' })], onrefresh });
		await fireEvent.change(screen.getByPlaceholderText('--'), { target: { value: raw } });
		expect(mockUpdate).toHaveBeenCalledTimes(1);
		expect(mockUpdate).toHaveBeenCalledWith('job_9', 'a', { episode_number: expected });
		await waitFor(() => expect(onrefresh).toHaveBeenCalledTimes(1));
	});

	it('sends excluded true when the Include box is unchecked', async () => {
		renderTable({ job: createJob({ id: 'job_9' }), tracks: [track({ id: 'a' })] });
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Include track 0' }));
		expect(mockUpdate).toHaveBeenCalledWith('job_9', 'a', { excluded: true });
	});

	it('sends excluded false when the Include box is checked', async () => {
		renderTable({ job: createJob({ id: 'job_9' }), tracks: [track({ id: 'a', excluded: true })] });
		const box = screen.getByRole('checkbox', { name: 'Include track 0' });
		expect(box).not.toBeChecked();
		await fireEvent.click(box);
		expect(mockUpdate).toHaveBeenCalledWith('job_9', 'a', { excluded: false });
	});

	it('succeeds quietly when onrefresh is not passed', async () => {
		renderTable({ tracks: [track({ id: 'a' })] });
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Include track 0' }));
		await waitFor(() => expect(mockUpdate).toHaveBeenCalledTimes(1));
		expect(screen.queryByText(/Failed to update track/)).toBeNull();
	});

	it('shows the message of a failed update and does not refresh', async () => {
		const onrefresh = vi.fn();
		mockUpdate.mockRejectedValueOnce(new Error('boom'));
		renderTable({ tracks: [track({ id: 'a' })], onrefresh });
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Include track 0' }));
		expect(await screen.findByText('Failed to update track: boom')).toBeInTheDocument();
		expect(onrefresh).not.toHaveBeenCalled();
	});

	it('shows "Unknown error" when a failed update throws a non-Error', async () => {
		const onrefresh = vi.fn();
		mockUpdate.mockRejectedValueOnce('nope');
		renderTable({ tracks: [track({ id: 'a' })], onrefresh });
		await fireEvent.click(screen.getByRole('checkbox', { name: 'Include track 0' }));
		expect(await screen.findByText('Failed to update track: Unknown error')).toBeInTheDocument();
		expect(onrefresh).not.toHaveBeenCalled();
	});

	it('clears the error line when the next update starts, before it settles', async () => {
		mockUpdate.mockRejectedValueOnce(new Error('boom'));
		let settle!: () => void;
		mockUpdate.mockReturnValueOnce(new Promise((resolve) => (settle = () => resolve({}) as unknown as void)) as never);
		const onrefresh = vi.fn();
		renderTable({ tracks: [track({ id: 'a' })], onrefresh });
		const box = screen.getByRole('checkbox', { name: 'Include track 0' });
		await fireEvent.click(box);
		await screen.findByText('Failed to update track: boom');

		await fireEvent.click(box);
		await waitFor(() => expect(screen.queryByText(/Failed to update track/)).toBeNull());
		expect(onrefresh).not.toHaveBeenCalled();

		settle();
		await waitFor(() => expect(onrefresh).toHaveBeenCalledTimes(1));
	});
});

describe('ReviewTracksTable title search', () => {
	const two = () => [track({ id: 'a', index: 1, title: 'Alpha' }), track({ id: 'b', index: 2, title: 'Beta' })];
	const panel = (n: number) => screen.queryByText(new RegExp(`Track ${n} Title Override`));

	it('opens a video track search from its title cell and closes it on a second click', async () => {
		renderTable({ tracks: two() });
		const cell = screen.getByText('Alpha').closest('td')!;
		expect(panel(1)).toBeNull();
		await fireEvent.click(cell);
		expect(panel(1)).toBeInTheDocument();
		expect(panel(2)).toBeNull();
		await fireEvent.click(cell);
		expect(panel(1)).toBeNull();
	});

	it('does nothing when the title cell of a scanned title is clicked', async () => {
		renderTable({ scanTitles: [scan({ index: 1 })] });
		const cell = screen.getAllByText('-')[0].closest('td')!;
		await fireEvent.click(cell);
		expect(screen.queryByText(/Title Override/)).toBeNull();
	});

	it('does nothing when the title cell is clicked and the job is not video', async () => {
		renderTable({ tracks: two(), isVideo: false });
		await fireEvent.click(screen.getByText('Alpha').closest('td')!);
		expect(screen.queryByText(/Title Override/)).toBeNull();
	});

	it('keeps the search button state and title in step with the open state', async () => {
		renderTable({ tracks: two() });
		const [button] = screen.getAllByTitle('Search title');
		expect(button).toHaveAttribute('aria-pressed', 'false');
		await fireEvent.click(button);
		expect(panel(1)).toBeInTheDocument();
		const pressed = screen.getByTitle('Close search');
		expect(pressed).toBe(button);
		expect(pressed).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getAllByTitle('Search title')).toHaveLength(1);
		await fireEvent.click(pressed);
		expect(panel(1)).toBeNull();
		expect(button).toHaveAttribute('aria-pressed', 'false');
		expect(button).toHaveAttribute('title', 'Search title');
	});

	it('applies in one open search, closing only that one, and refreshes', async () => {
		const onrefresh = vi.fn();
		mockSearch.mockResolvedValue({ candidates: [candidate] } as never);
		renderTable({ job: createJob({ id: 'job_9' }), tracks: two(), onrefresh });
		await fireEvent.click(screen.getByText('Alpha').closest('td')!);
		await fireEvent.click(screen.getByText('Beta').closest('td')!);
		expect(panel(1)).toBeInTheDocument();
		expect(panel(2)).toBeInTheDocument();

		await fireEvent.click(screen.getAllByText('Search')[0]);
		await fireEvent.click(await screen.findByText('Picked'));
		await fireEvent.click(screen.getByText('Apply'));

		await waitFor(() => expect(panel(1)).toBeNull());
		expect(panel(2)).toBeInTheDocument();
		expect(mockUpdate).toHaveBeenCalledWith('job_9', 'a', expect.objectContaining({ title: 'Picked', year: 2021 }));
		expect(onrefresh).toHaveBeenCalledTimes(1);
	});

	it('refreshes when Clear Override is used and leaves the search open', async () => {
		const onrefresh = vi.fn();
		renderTable({ job: createJob({ id: 'job_9' }), tracks: two(), onrefresh });
		await fireEvent.click(screen.getByText('Alpha').closest('td')!);
		await fireEvent.click(screen.getByText('Clear Override'));
		await waitFor(() => expect(onrefresh).toHaveBeenCalledTimes(1));
		expect(mockClear).toHaveBeenCalledWith('job_9', 'a');
		expect(panel(1)).toBeInTheDocument();
	});

	it('closes only its own search when Close is pressed', async () => {
		renderTable({ tracks: two() });
		await fireEvent.click(screen.getByText('Alpha').closest('td')!);
		await fireEvent.click(screen.getByText('Beta').closest('td')!);
		await fireEvent.click(screen.getAllByTitle('Close')[1]);
		expect(panel(2)).toBeNull();
		expect(panel(1)).toBeInTheDocument();
	});
});
