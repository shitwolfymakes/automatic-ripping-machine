import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { MediaType, MetadataCandidate, TrackView } from '$lib/types/api.gen';
import TrackTitleSearch from '../TrackTitleSearch.svelte';
import { createTrack } from '../../../__fixtures__/job';

// Branch pins for TrackTitleSearch, beside TrackTitleSearch.test.ts. Every
// branch of the component is reachable from the rendered component, so
// nothing is left unpinned.

vi.mock('$lib/api/jobs', () => ({
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	clearTrackTitle: vi.fn(),
	updateTrack: vi.fn()
}));

import { searchMetadata, fetchMediaDetail, clearTrackTitle, updateTrack } from '$lib/api/jobs';
const mockSearch = vi.mocked(searchMetadata);
const mockImdb = vi.mocked(fetchMediaDetail);
const mockClear = vi.mocked(clearTrackTitle);
const mockUpdateTrack = vi.mocked(updateTrack);

beforeEach(() => {
	mockSearch.mockReset();
	mockImdb.mockReset();
	mockClear.mockReset();
	mockClear.mockResolvedValue(undefined as never);
	mockUpdateTrack.mockReset();
	mockUpdateTrack.mockResolvedValue(undefined as never);
});

afterEach(() => {
	cleanup();
});

// ---- fixtures and helpers ---------------------------------------------

function cand(o: Partial<MetadataCandidate> = {}): MetadataCandidate {
	return { title: 'Result', year: 2024, kind: 'movie', poster_url: null, provider_id: 'tt1111', ...o };
}

interface RenderProps {
	track?: Partial<TrackView>;
	mediaType?: MediaType | null;
	onapply?: () => void;
	onclear?: () => void;
	onclose?: () => void;
}

function show({ track = {}, ...rest }: RenderProps = {}) {
	return renderComponent(TrackTitleSearch, {
		props: { jobId: 'job_1', track: createTrack({ id: 'trk_1', ...track }), ...rest }
	});
}

// The API type says source_ref is a string, but the component also guards a
// runtime null, so the seeding tests pass one through a cast.
const nullRef = null as unknown as string;

function deferred<T = void>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

const searchButton = () => screen.getByRole('button', { name: /^(Search|\.\.\.)$/ });
const titleInput = () => screen.getByPlaceholderText('Title...') as HTMLInputElement;
const yearInput = () => screen.getByPlaceholderText('Year') as HTMLInputElement;
const imdbInputEl = () => screen.getByPlaceholderText('tt...') as HTMLInputElement;
const field = (label: string) => screen.getByLabelText(label) as HTMLInputElement;

async function type(el: HTMLElement, value: string) {
	await fireEvent.input(el, { target: { value } });
}

async function runTextSearch(candidates: MetadataCandidate[], query?: string) {
	mockSearch.mockResolvedValue({ candidates } as never);
	if (query !== undefined) await type(titleInput(), query);
	await fireEvent.click(searchButton());
	if (candidates.length > 0) await screen.findByText(candidates[0].title);
}

async function openCard(c: MetadataCandidate, candidates: MetadataCandidate[] = [c]) {
	await runTextSearch(candidates, 'q');
	await fireEvent.click(screen.getByTitle(cardTitle(c)));
	await screen.findByRole('button', { name: 'Apply' });
}

function cardTitle(c: MetadataCandidate) {
	return `${c.title}${c.year ? ` (${c.year})` : ''}`;
}

async function lookUpImdb(id: string, candidates: MetadataCandidate[]) {
	mockImdb.mockResolvedValue({ candidates } as never);
	await type(imdbInputEl(), id);
	await fireEvent.click(searchButton());
}

async function openEditorViaImdb(c: MetadataCandidate = cand({ title: 'Imdb Pick' })) {
	await lookUpImdb('tt0000001', [c]);
	await screen.findByRole('button', { name: 'Apply' });
}

const applyButton = () => screen.getByRole('button', { name: /^(Apply|Applying\.\.\.)$/ }) as HTMLButtonElement;
const saveButton = () => screen.getByRole('button', { name: /^(Save options|Saving\.\.\.)$/ }) as HTMLButtonElement;
const clearButton = () =>
	screen.getByRole('button', { name: /^(Clear Override|Clearing\.\.\.)$/ }) as HTMLButtonElement;

// ---- seeding ----------------------------------------------------------

describe('TrackTitleSearch seeding', () => {
	it('seeds the query from the track title', () => {
		show({ track: { title: 'My Title', source_ref: 'x.mkv' } });
		expect(titleInput().value).toBe('My Title');
	});

	it('seeds the query from source_ref without its extension when there is no title', () => {
		show({ track: { title: null, source_ref: 'title_02.mkv' } });
		expect(titleInput().value).toBe('title_02');
	});

	it('seeds an empty query when there is neither a title nor a source_ref', () => {
		show({ track: { title: null, source_ref: nullRef } });
		expect(titleInput().value).toBe('');
	});

	it('seeds the year, custom filename, episode number and episode name', () => {
		show({
			track: { year: 1999, custom_filename: 'Cut.mkv', episode_number: 4, episode_name: 'Pilot', role: 'episode' }
		});
		expect(yearInput().value).toBe('1999');
		expect(field('Custom filename').value).toBe('Cut.mkv');
		expect(field('Episode').value).toBe('4');
		expect(field('Episode name').value).toBe('Pilot');
	});

	it('seeds empty strings when year, filename, episode number and episode name are null', () => {
		show({
			track: { year: null, custom_filename: null, episode_number: null, episode_name: null, role: 'episode' }
		});
		expect(yearInput().value).toBe('');
		expect(field('Custom filename').value).toBe('');
		expect(field('Episode').value).toBe('');
		expect(field('Episode name').value).toBe('');
	});

	it.each([
		['shows', { role: 'episode' as const }, 'movie' as MediaType | null, true],
		['shows', { role: null }, 'tv' as MediaType | null, true],
		['hides', { role: 'main' as const }, 'tv' as MediaType | null, false],
		['hides', { role: null }, null, false]
	])('%s the episode inputs for role %j on media type %s', (_w, track, mediaType, visible) => {
		show({ track, mediaType });
		expect(screen.queryByLabelText('Episode') !== null).toBe(visible);
		expect(screen.queryByLabelText('Episode name') !== null).toBe(visible);
	});
});

// ---- header -----------------------------------------------------------

describe('TrackTitleSearch header', () => {
	it('shows the Track <index> Title Override heading', () => {
		show({ track: { index: 3 } });
		expect(screen.getByRole('heading', { name: 'Track 3 Title Override' })).toBeInTheDocument();
	});

	it('shows Clear Override only when the track has a title', () => {
		show({ track: { title: 'Has One' } });
		expect(screen.getByText('Clear Override')).toBeInTheDocument();
		cleanup();
		show({ track: { title: null } });
		expect(screen.queryByText('Clear Override')).toBeNull();
	});

	it('shows Close only when onclose is passed and calls it', async () => {
		show();
		expect(screen.queryByTitle('Close')).toBeNull();
		cleanup();
		const onclose = vi.fn();
		show({ onclose });
		await fireEvent.click(screen.getByTitle('Close'));
		expect(onclose).toHaveBeenCalledTimes(1);
	});
});

// ---- search: IMDb path ------------------------------------------------

describe('TrackTitleSearch IMDb search', () => {
	it('sends the trimmed id to fetchMediaDetail and wins over a filled query', async () => {
		show({ track: { title: 'Filled' } });
		await lookUpImdb('  tt9999999  ', [cand({ title: 'By Id' })]);
		await waitFor(() => expect(mockImdb).toHaveBeenCalledWith('tt9999999'));
		expect(mockSearch).not.toHaveBeenCalled();
	});

	it('opens the editor on the first candidate with no result cards and no Back button', async () => {
		show();
		await lookUpImdb('tt1', [cand({ title: 'First', year: 2001 }), cand({ title: 'Second' })]);
		await screen.findByRole('button', { name: 'Apply' });
		expect(field('Title').value).toBe('First');
		expect(screen.queryByTitle('Second')).toBeNull();
		expect(screen.queryByTitle('First (2001)')).toBeNull();
		expect(screen.queryByRole('button', { name: 'Back' })).toBeNull();
	});

	it('shows "No match found for that IMDb ID." for no candidates', async () => {
		show();
		await lookUpImdb('tt1', []);
		expect(await screen.findByText('No match found for that IMDb ID.')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Apply' })).toBeNull();
	});

	it('shows the Error message when the lookup rejects', async () => {
		show();
		mockImdb.mockRejectedValue(new Error('imdb down'));
		await type(imdbInputEl(), 'tt1');
		await fireEvent.click(searchButton());
		expect(await screen.findByText('imdb down')).toBeInTheDocument();
	});

	it('shows "IMDb lookup failed" when the lookup rejects with a non-Error', async () => {
		show();
		mockImdb.mockRejectedValue('boom');
		await type(imdbInputEl(), 'tt1');
		await fireEvent.click(searchButton());
		expect(await screen.findByText('IMDb lookup failed')).toBeInTheDocument();
	});

	it('clears earlier result cards', async () => {
		show();
		await runTextSearch([cand({ title: 'Old Card' })], 'q');
		await lookUpImdb('tt1', []);
		await screen.findByText('No match found for that IMDb ID.');
		expect(screen.queryByText('Old Card')).toBeNull();
	});

	it('shows "..." and disables Search while the lookup is pending', async () => {
		show();
		const d = deferred<{ candidates: MetadataCandidate[] }>();
		mockImdb.mockReturnValue(d.promise as never);
		await type(imdbInputEl(), 'tt1');
		await fireEvent.click(searchButton());
		await waitFor(() => expect(searchButton()).toHaveTextContent('...'));
		expect(searchButton()).toBeDisabled();
		d.resolve({ candidates: [] });
		await waitFor(() => expect(searchButton()).toHaveTextContent('Search'));
	});
});

// ---- search: text path ------------------------------------------------

describe('TrackTitleSearch text search', () => {
	it('sends only the trimmed query to searchMetadata, not the year', async () => {
		show();
		await type(yearInput(), '2020');
		await runTextSearch([cand()], '  Some Film  ');
		expect(mockSearch).toHaveBeenCalledTimes(1);
		expect(mockSearch.mock.calls[0]).toEqual(['Some Film']);
	});

	it('shows "No results found." for no candidates', async () => {
		show();
		await runTextSearch([], 'q');
		expect(await screen.findByText('No results found.')).toBeInTheDocument();
	});

	it('shows the Error message when the search rejects', async () => {
		show();
		mockSearch.mockRejectedValue(new Error('search broke'));
		await type(titleInput(), 'q');
		await fireEvent.click(searchButton());
		expect(await screen.findByText('search broke')).toBeInTheDocument();
	});

	it('shows "Search failed" when the search rejects with a non-Error', async () => {
		show();
		mockSearch.mockRejectedValue('boom');
		await type(titleInput(), 'q');
		await fireEvent.click(searchButton());
		expect(await screen.findByText('Search failed')).toBeInTheDocument();
	});

	it('closes an open editor when a new text search runs', async () => {
		show();
		await openEditorViaImdb();
		const d = deferred<{ candidates: MetadataCandidate[] }>();
		mockSearch.mockReturnValue(d.promise as never);
		await type(imdbInputEl(), '');
		await type(titleInput(), 'again');
		await fireEvent.click(searchButton());
		await waitFor(() => expect(screen.queryByRole('button', { name: 'Apply' })).toBeNull());
		d.resolve({ candidates: [] });
		await screen.findByText('No results found.');
	});

	it('keeps the previous result cards on screen while a new text search is pending', async () => {
		show();
		await runTextSearch([cand({ title: 'Earlier' })], 'q');
		const d = deferred<{ candidates: MetadataCandidate[] }>();
		mockSearch.mockReturnValue(d.promise as never);
		await fireEvent.click(searchButton());
		await waitFor(() => expect(searchButton()).toHaveTextContent('...'));
		expect(searchButton()).toBeDisabled();
		expect(screen.getByText('Earlier')).toBeInTheDocument();
		d.resolve({ candidates: [cand({ title: 'Later' })] });
		await screen.findByText('Later');
		expect(screen.queryByText('Earlier')).toBeNull();
	});
});

// ---- search: triggers -------------------------------------------------

describe('TrackTitleSearch search triggers', () => {
	it.each([
		['title', titleInput],
		['year', yearInput],
		['IMDb', imdbInputEl]
	])('Enter in the %s input searches', async (_n, get) => {
		mockSearch.mockResolvedValue({ candidates: [] } as never);
		show({ track: { title: 'Seeded' } });
		await fireEvent.keyDown(get(), { key: 'Enter' });
		await waitFor(() => expect(mockSearch).toHaveBeenCalledWith('Seeded'));
	});

	it('another key does not search', async () => {
		show({ track: { title: 'Seeded' } });
		await fireEvent.keyDown(titleInput(), { key: 'a' });
		expect(mockSearch).not.toHaveBeenCalled();
		expect(mockImdb).not.toHaveBeenCalled();
	});

	it('Enter with a blank query and a blank IMDb id sends nothing', async () => {
		show({ track: { title: null, source_ref: nullRef } });
		await type(imdbInputEl(), '   ');
		await fireEvent.keyDown(titleInput(), { key: 'Enter' });
		expect(mockSearch).not.toHaveBeenCalled();
		expect(mockImdb).not.toHaveBeenCalled();
	});

	it('disables Search while both inputs are blank or whitespace', async () => {
		show({ track: { title: null, source_ref: nullRef } });
		expect(searchButton()).toBeDisabled();
		await type(titleInput(), '   ');
		await type(imdbInputEl(), '  ');
		expect(searchButton()).toBeDisabled();
		await type(imdbInputEl(), 'tt1');
		expect(searchButton()).toBeEnabled();
		await type(imdbInputEl(), '');
		await type(titleInput(), 'x');
		expect(searchButton()).toBeEnabled();
	});

	it('shows "..." and disables Search while a text search is pending', async () => {
		show();
		const d = deferred<{ candidates: MetadataCandidate[] }>();
		mockSearch.mockReturnValue(d.promise as never);
		await fireEvent.click(searchButton());
		await waitFor(() => expect(searchButton()).toHaveTextContent('...'));
		expect(searchButton()).toBeDisabled();
		d.resolve({ candidates: [] });
		await waitFor(() => expect(searchButton()).toHaveTextContent('Search'));
	});

	it.each(['No API key configured', 'Missing Api Key'])(
		'shows the warning alert with a Settings link for "%s"',
		async (message) => {
			show();
			mockSearch.mockRejectedValue(new Error(message));
			await fireEvent.click(searchButton());
			const text = await screen.findByText(message);
			expect(text.closest('.alert-warning')).not.toBeNull();
			expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings');
		}
	);

	it('shows the plain help line for any other error', async () => {
		show();
		mockSearch.mockRejectedValue(new Error('network down'));
		await fireEvent.click(searchButton());
		const text = await screen.findByText('network down');
		expect(text).toHaveClass('field-help');
		expect(screen.queryByRole('link', { name: 'Settings' })).toBeNull();
		expect(document.querySelector('.alert-warning')).toBeNull();
	});
});

// ---- result cards -----------------------------------------------------

describe('TrackTitleSearch result cards', () => {
	it('shows at most 8 cards', async () => {
		show();
		const many = Array.from({ length: 10 }, (_, i) => cand({ title: `R${i}`, year: null }));
		await runTextSearch(many, 'q');
		expect(screen.getByText('R7')).toBeInTheDocument();
		expect(screen.queryByText('R8')).toBeNull();
		expect(screen.queryByText('R9')).toBeNull();
	});

	it('titles each card with the year when it has one and without it otherwise', async () => {
		show();
		await runTextSearch([cand({ title: 'With', year: 2020 }), cand({ title: 'Without', year: null })], 'q');
		expect(screen.getByTitle('With (2020)')).toBeInTheDocument();
		expect(screen.getByTitle('Without')).toBeInTheDocument();
	});

	it('shows the poster only when the candidate has one, and the year line', async () => {
		show();
		await runTextSearch(
			[
				cand({ title: 'Pic', year: 2020, poster_url: 'https://img.test/p.jpg' }),
				cand({ title: 'NoPic', year: null, poster_url: null })
			],
			'q'
		);
		const pic = screen.getByTitle('Pic (2020)');
		const noPic = screen.getByTitle('NoPic');
		expect(pic.querySelector('img')).not.toBeNull();
		expect(noPic.querySelector('[data-poster]')).toBeNull();
		expect(pic.querySelector('.track-title-search-result-year')).toHaveTextContent('2020');
		expect(noPic.querySelector('.track-title-search-result-year')).toHaveTextContent('');
		expect(noPic.querySelector('.track-title-search-result-year')?.textContent).toBe('');
	});

	it.each([
		['tv', 'Series'],
		['series', 'Series'],
		['movie', 'Movie'],
		['other', 'Movie']
	])('opens the editor seeded from a %s card as %s', async (kind, type) => {
		show();
		const c = cand({ title: 'Seed', year: 2010, kind, poster_url: 'https://img.test/s.jpg' });
		await openCard(c);
		expect(field('Title').value).toBe('Seed');
		expect(field('Year').value).toBe('2010');
		expect((screen.getByLabelText('Type') as HTMLSelectElement).value).toBe(type.toLowerCase());
		expect(field('Poster URL').value).toBe('https://img.test/s.jpg');
	});

	it('seeds an empty year and poster for a card with neither', async () => {
		show();
		await openCard(cand({ title: 'Bare', year: null, poster_url: null }));
		expect(field('Year').value).toBe('');
		expect(field('Poster URL').value).toBe('');
	});

	it('Back closes the editor and shows the cards again, and the next card reseeds the fields', async () => {
		show();
		const a = cand({ title: 'Alpha', year: 2001, kind: 'movie' });
		const b = cand({ title: 'Beta', year: 2002, kind: 'tv' });
		await openCard(a, [a, b]);
		await type(field('Title'), 'Edited');
		await fireEvent.click(screen.getByRole('button', { name: 'Back' }));
		expect(screen.queryByRole('button', { name: 'Apply' })).toBeNull();
		await fireEvent.click(screen.getByTitle('Beta (2002)'));
		await screen.findByRole('button', { name: 'Apply' });
		expect(field('Title').value).toBe('Beta');
		expect(field('Year').value).toBe('2002');
		expect((screen.getByLabelText('Type') as HTMLSelectElement).value).toBe('series');
	});
});

// ---- apply ------------------------------------------------------------

describe('TrackTitleSearch apply', () => {
	it('is disabled while the title is blank or whitespace', async () => {
		show();
		await openEditorViaImdb();
		expect(applyButton()).toBeEnabled();
		await type(field('Title'), '   ');
		expect(applyButton()).toBeDisabled();
		await type(field('Title'), '');
		expect(applyButton()).toBeDisabled();
	});

	it('sends the trimmed title, numeric year, role main for Movie and no poster when blank', async () => {
		show({ track: { id: 'trk_4' } });
		await openEditorViaImdb(cand({ title: 'x', year: 2000, kind: 'movie', poster_url: null }));
		await type(field('Title'), '  Trimmed  ');
		await type(field('Year'), ' 1999 ');
		await type(field('Poster URL'), '   ');
		await fireEvent.click(applyButton());
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack.mock.calls[0]).toStrictEqual([
			'job_1',
			'trk_4',
			{ title: 'Trimmed', year: 1999, role: 'main', poster_url: undefined }
		]);
	});

	it('sends role episode for Series, the trimmed poster and no year when the year is blank', async () => {
		show({ track: { id: 'trk_4' } });
		await openEditorViaImdb(cand({ title: 'Show', year: 2000, kind: 'tv', poster_url: null }));
		await type(field('Year'), '');
		await type(field('Poster URL'), '  https://img.test/p.jpg  ');
		await fireEvent.click(applyButton());
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack.mock.calls[0]).toStrictEqual([
			'job_1',
			'trk_4',
			{ title: 'Show', year: undefined, role: 'episode', poster_url: 'https://img.test/p.jpg' }
		]);
	});

	it.each([
		['movie', 'series', 'episode'],
		['series', 'movie', 'main']
	])('sends the role for a %s card whose Type is changed to %s', async (kind, next, role) => {
		show();
		await openEditorViaImdb(cand({ title: 'Switch', kind }));
		await fireEvent.change(screen.getByLabelText('Type'), { target: { value: next } });
		await fireEvent.click(applyButton());
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack.mock.calls[0][2].role).toBe(role);
	});

	it('sends no year when the year is not a number', async () => {
		show();
		await openEditorViaImdb();
		await type(field('Year'), 'abc');
		await fireEvent.click(applyButton());
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack.mock.calls[0][2].year).toBeUndefined();
	});

	it('shows "Applying..." and disables Apply while pending', async () => {
		show();
		await openEditorViaImdb();
		const d = deferred();
		mockUpdateTrack.mockReturnValue(d.promise as never);
		await fireEvent.click(applyButton());
		await waitFor(() => expect(applyButton()).toHaveTextContent('Applying...'));
		expect(applyButton()).toBeDisabled();
		d.resolve();
		await waitFor(() => expect(applyButton()).toHaveTextContent('Apply'));
	});

	it('shows "Track title updated" and calls onapply', async () => {
		const onapply = vi.fn();
		show({ onapply });
		await openEditorViaImdb();
		await fireEvent.click(applyButton());
		expect(await screen.findByText('Track title updated')).toBeInTheDocument();
		expect(onapply).toHaveBeenCalledTimes(1);
	});

	it('succeeds without error when onapply is not passed', async () => {
		show();
		await openEditorViaImdb();
		await fireEvent.click(applyButton());
		expect(await screen.findByText('Track title updated')).toBeInTheDocument();
	});

	it.each([
		['the Error message', new Error('nope'), 'nope'],
		['"Update failed" for a non-Error', 'boom', 'Update failed']
	])('shows %s on failure and does not call onapply', async (_n, err, shown) => {
		const onapply = vi.fn();
		show({ onapply });
		await openEditorViaImdb();
		mockUpdateTrack.mockRejectedValue(err);
		await fireEvent.click(applyButton());
		expect(await screen.findByText(shown)).toBeInTheDocument();
		expect(onapply).not.toHaveBeenCalled();
		expect(applyButton()).toHaveTextContent('Apply');
	});
});

// ---- save options -----------------------------------------------------

describe('TrackTitleSearch save options', () => {
	it('sends the trimmed custom filename, or null when blank, and no episode keys on a non-series track', async () => {
		show({ track: { id: 'trk_2', role: 'main' } });
		await type(field('Custom filename'), '  Cut.mkv  ');
		await fireEvent.click(saveButton());
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack.mock.calls[0]).toStrictEqual(['job_1', 'trk_2', { custom_filename: 'Cut.mkv' }]);
		await type(field('Custom filename'), '   ');
		await fireEvent.click(saveButton());
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledTimes(2));
		expect(mockUpdateTrack.mock.calls[1]).toStrictEqual(['job_1', 'trk_2', { custom_filename: null }]);
	});

	it('sends the episode number and trimmed episode name on a series track', async () => {
		show({ track: { id: 'trk_2', role: 'episode' } });
		await type(field('Custom filename'), 'F');
		await type(field('Episode'), ' 4 ');
		await type(field('Episode name'), '  The One  ');
		await fireEvent.click(saveButton());
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack.mock.calls[0]).toStrictEqual([
			'job_1',
			'trk_2',
			{ custom_filename: 'F', episode_number: 4, episode_name: 'The One' }
		]);
	});

	it.each([
		['blank', ''],
		['not a number', 'abc']
	])('sends a null episode number and episode name when they are %s', async (_n, value) => {
		show({ track: { id: 'trk_2', role: 'episode' } });
		await type(field('Episode'), value);
		await type(field('Episode name'), '   ');
		await fireEvent.click(saveButton());
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledTimes(1));
		expect(mockUpdateTrack.mock.calls[0]).toStrictEqual([
			'job_1',
			'trk_2',
			{ custom_filename: null, episode_number: null, episode_name: null }
		]);
	});

	it('shows "Saving..." and disables the button while pending', async () => {
		show();
		const d = deferred();
		mockUpdateTrack.mockReturnValue(d.promise as never);
		await fireEvent.click(saveButton());
		await waitFor(() => expect(saveButton()).toHaveTextContent('Saving...'));
		expect(saveButton()).toBeDisabled();
		d.resolve();
		await waitFor(() => expect(saveButton()).toHaveTextContent('Save options'));
	});

	it('calls onapply and shows "Track options saved" when the editor is open', async () => {
		const onapply = vi.fn();
		show({ onapply });
		await openEditorViaImdb();
		await fireEvent.click(saveButton());
		expect(await screen.findByText('Track options saved')).toBeInTheDocument();
		expect(onapply).toHaveBeenCalledTimes(1);
	});

	it('succeeds without error when onapply is not passed', async () => {
		show();
		await openEditorViaImdb();
		await fireEvent.click(saveButton());
		expect(await screen.findByText('Track options saved')).toBeInTheDocument();
	});

	it("shows no outcome line when no editor is open (today's behaviour)", async () => {
		const onapply = vi.fn();
		show({ onapply });
		await fireEvent.click(saveButton());
		await waitFor(() => expect(onapply).toHaveBeenCalledTimes(1));
		expect(screen.queryByText('Track options saved')).toBeNull();
		mockUpdateTrack.mockRejectedValue(new Error('hidden failure'));
		await fireEvent.click(saveButton());
		await waitFor(() => expect(saveButton()).toHaveTextContent('Save options'));
		await waitFor(() => expect(mockUpdateTrack).toHaveBeenCalledTimes(2));
		expect(screen.queryByText('hidden failure')).toBeNull();
	});

	it.each([
		['the Error message', new Error('save broke'), 'save broke'],
		['"Save failed" for a non-Error', 'boom', 'Save failed']
	])('shows %s on failure and does not call onapply', async (_n, err, shown) => {
		const onapply = vi.fn();
		show({ onapply });
		await openEditorViaImdb();
		mockUpdateTrack.mockRejectedValue(err);
		await fireEvent.click(saveButton());
		expect(await screen.findByText(shown)).toBeInTheDocument();
		expect(onapply).not.toHaveBeenCalled();
	});
});

// ---- clear override ---------------------------------------------------

describe('TrackTitleSearch clear override', () => {
	it('calls clearTrackTitle with the job and track ids', async () => {
		show({ track: { id: 'trk_9', title: 'Old' } });
		await fireEvent.click(clearButton());
		await waitFor(() => expect(mockClear).toHaveBeenCalledWith('job_1', 'trk_9'));
	});

	it('shows "Clearing..." and disables the button while pending', async () => {
		show({ track: { title: 'Old' } });
		const d = deferred();
		mockClear.mockReturnValue(d.promise as never);
		await fireEvent.click(clearButton());
		await waitFor(() => expect(clearButton()).toHaveTextContent('Clearing...'));
		expect(clearButton()).toBeDisabled();
		d.resolve();
		await waitFor(() => expect(clearButton()).toHaveTextContent('Clear Override'));
	});

	it('closes the editor and the result cards and calls onclear on success', async () => {
		const onclear = vi.fn();
		show({ track: { title: 'Old' }, onclear });
		await openCard(cand({ title: 'Card' }), [cand({ title: 'Card' }), cand({ title: 'Other' })]);
		await fireEvent.click(clearButton());
		await waitFor(() => expect(onclear).toHaveBeenCalledTimes(1));
		expect(screen.queryByRole('button', { name: 'Apply' })).toBeNull();
		expect(screen.queryByText('Card')).toBeNull();
		expect(screen.queryByText('Other')).toBeNull();
	});

	it('succeeds without error when onclear is not passed', async () => {
		show({ track: { title: 'Old' } });
		await runTextSearch([cand({ title: 'Card' })]);
		await fireEvent.click(clearButton());
		await waitFor(() => expect(screen.queryByText('Card')).toBeNull());
	});

	it.each([
		['the Error message', new Error('clear broke'), 'clear broke'],
		['"Clear failed" for a non-Error', 'boom', 'Clear failed']
	])('shows %s on failure while the editor is open', async (_n, err, shown) => {
		const onclear = vi.fn();
		show({ track: { title: 'Old' }, onclear });
		await openEditorViaImdb();
		mockClear.mockRejectedValue(err);
		await fireEvent.click(clearButton());
		expect(await screen.findByText(shown)).toBeInTheDocument();
		expect(onclear).not.toHaveBeenCalled();
	});

	it("shows nothing on failure when no editor is open (today's behaviour)", async () => {
		show({ track: { title: 'Old' } });
		mockClear.mockRejectedValue(new Error('hidden clear failure'));
		await fireEvent.click(clearButton());
		await waitFor(() => expect(clearButton()).toHaveTextContent('Clear Override'));
		await waitFor(() => expect(mockClear).toHaveBeenCalledTimes(1));
		expect(screen.queryByText('hidden clear failure')).toBeNull();
		expect(screen.queryByText('Clear failed')).toBeNull();
	});
});
