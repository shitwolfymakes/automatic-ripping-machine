import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import type { JobView, MetadataCandidate, MetadataReleaseDetail, TrackView } from '$lib/types/api.gen';
import MusicSearch from '../MusicSearch.svelte';
import { GLYPH_PATHS } from '../../ui/glyph-names';
import { createJob, createTrack } from '../../__fixtures__/job';

// Branch pins for MusicSearch, beside MusicSearch.test.ts. One branch cannot
// be reached from the rendered component, so nothing here forces it:
// - The `!detail` half of applyRelease's guard: every caller sits inside the
//   open-release block (Apply, "Apply anyway" and "Apply titles"), which
//   renders only while `detail` is set, and applyRelease runs synchronously
//   up to that guard. The coverage tool counts the operand as evaluated, so it
//   reports no gap, but its true outcome is unreachable; only the blank-album
//   half is exercised ("Apply anyway" after the album was cleared).

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper, not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/api/jobs', () => ({
	searchMusicMetadata: vi.fn(),
	fetchMusicDetail: vi.fn(),
	resolveJob: vi.fn(),
	patchJob: vi.fn()
}));
import { searchMusicMetadata, fetchMusicDetail, resolveJob, patchJob } from '$lib/api/jobs';
const mockSearch = vi.mocked(searchMusicMetadata);
const mockDetail = vi.mocked(fetchMusicDetail);
const mockResolve = vi.mocked(resolveJob);
const mockPatchJob = vi.mocked(patchJob);

beforeEach(() => {
	mockSearch.mockReset();
	mockDetail.mockReset();
	mockResolve.mockReset();
	mockResolve.mockResolvedValue({ job: {}, fan_out: [] } as never);
	mockPatchJob.mockReset();
	mockPatchJob.mockResolvedValue({} as never);
});

afterEach(() => {
	cleanup();
});

// ---- fixtures and helpers ---------------------------------------------

function cand(o: Partial<MetadataCandidate> = {}): MetadataCandidate {
	return { title: 'Abbey Road', year: 1969, kind: 'music', poster_url: null, provider_id: 'rel-1', ...o };
}

function trk(position: number | null, title: string, length_ms: number | null | undefined, disc_number = 1) {
	return { position, title, length_ms, disc_number };
}

function rel(o: Partial<MetadataReleaseDetail> = {}): MetadataReleaseDetail {
	return {
		release_id: 'rel-1',
		title: 'Abbey Road',
		artist: 'The Beatles',
		year: 1969,
		poster_url: null,
		disc_count: 1,
		track_count: 2,
		tracks: [trk(1, 'Come Together', 259000), trk(2, 'Something', 182000)],
		...o
	};
}

function disc(index: number, secs: number | null, o: Partial<TrackView> = {}): TrackView {
	return createTrack({ id: `trk_${index}`, index, expected_duration_seconds: secs, ...o });
}

function deferred<T>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

interface MountOpts {
	job?: Partial<JobView>;
	discTracks?: TrackView[];
	onapply?: () => void;
}

function mount(opts: MountOpts = {}) {
	return renderComponent(MusicSearch, {
		props: {
			job: createJob({ id: 'job_1', disc_type: 'cd', title: 'Abbey Road', ...opts.job }),
			discTracks: opts.discTracks ?? [],
			onapply: opts.onapply
		}
	});
}

const queryInput = () => screen.getByPlaceholderText('Album or title...') as HTMLInputElement;
const artistInput = () => screen.getByPlaceholderText('Artist (optional)') as HTMLInputElement;
const countryInput = () => screen.getByLabelText('Country') as HTMLInputElement;
const searchBtn = () => screen.getByRole('button', { name: /^Search/ });
const clearBtn = () => screen.queryByRole('button', { name: 'Clear' });
const cards = () => Array.from(document.querySelectorAll<HTMLElement>('.music-search-poster-card'));
const isFlipped = (i = 0) => cards()[i].dataset.flipped === 'true';
const flipBtn = (i = 0) => cards()[i].querySelector<HTMLElement>('[title="Flip to see tracklist"]')!;
const backBtn = (i = 0) => cards()[i].querySelector<HTMLElement>('[title="Flip back"]')!;
const backRows = (i = 0) =>
	Array.from(cards()[i].querySelectorAll('.music-search-back-row')).map((tr) =>
		Array.from(tr.querySelectorAll('td')).map((td) => td.textContent?.trim() ?? '')
	);
const detailRows = () =>
	Array.from(document.querySelectorAll('.music-search-detail-table tbody tr')).map((tr) =>
		Array.from(tr.querySelectorAll('td')).map((td) => td.textContent?.trim() ?? '')
	);
const albumInput = () => screen.getByLabelText('Album') as HTMLInputElement;
const editArtist = () => screen.getAllByLabelText('Artist')[1] as HTMLInputElement;
const yearInput = () => screen.getByLabelText('Year') as HTMLInputElement;
const discNumberInput = () => screen.getByLabelText('Disc #') as HTMLInputElement;
const discTotalInput = () => screen.getByLabelText('Disc total') as HTMLInputElement;
const applyBtn = () => screen.getByRole('button', { name: /^Appl(y|ying)/ });

async function typeInto(el: HTMLElement, value: string) {
	await fireEvent.input(el, { target: { value } });
}

async function searchFor(cands: MetadataCandidate[]) {
	mockSearch.mockResolvedValue({ candidates: cands });
	await fireEvent.click(searchBtn());
	await screen.findByText(cands[0].title);
}

async function openCard(title: string) {
	await fireEvent.click(screen.getByText(title));
	await screen.findByRole('button', { name: /Back to results/ });
}

async function openRelease(d: MetadataReleaseDetail, opts: MountOpts = {}) {
	mount(opts);
	await searchFor([cand({ title: d.title, provider_id: d.release_id })]);
	mockDetail.mockResolvedValue(d);
	await openCard(d.title);
}

async function backToResults() {
	await fireEvent.click(screen.getByRole('button', { name: /Back to results/ }));
}

// The back face is always in the DOM, so a flip is observed through the card's
// data-flipped attribute and the rows it holds.
async function flipFirstCard(d: MetadataReleaseDetail, opts: MountOpts = {}) {
	mount(opts);
	await searchFor([cand({ track_count: 2 })]);
	mockDetail.mockResolvedValue(d);
	await fireEvent.click(flipBtn());
	await waitFor(() => expect(isFlipped()).toBe(true));
}

function expectGlyph(cell: Element | null | undefined, glyph: 'check' | 'x' | '~' | '-') {
	expect(cell).toBeTruthy();
	if (glyph === 'check' || glyph === 'x') {
		expect(cell!.querySelector('path')!.getAttribute('d')).toBe(GLYPH_PATHS[glyph]);
	} else {
		expect(cell!.textContent!.trim()).toBe(glyph);
	}
}

// ---- search form --------------------------------------------------------

describe('search form seeding', () => {
	it('seeds the query from job.title', () => {
		mount({ job: { title: 'Dark Side', metadata_json: { music: { album: 'Other', artist: 'Pink Floyd' } } } });
		expect(queryInput()).toHaveValue('Dark Side');
		expect(artistInput()).toHaveValue('Pink Floyd');
	});

	it('falls back to the music album, then to empty', () => {
		mount({ job: { title: '', metadata_json: { music: { album: 'The Wall' } } } });
		expect(queryInput()).toHaveValue('The Wall');
		expect(artistInput()).toHaveValue('');
		cleanup();
		mount({ job: { title: '', metadata_json: {} } });
		expect(queryInput()).toHaveValue('');
	});

	it('selects the query text when the field is focused', async () => {
		mount();
		const select = vi.spyOn(queryInput(), 'select');
		await fireEvent.focus(queryInput());
		expect(select).toHaveBeenCalledTimes(1);
	});
});

describe('search opts', () => {
	it.each([
		['Type', 'change', 'album', { release_type: 'album' }],
		['Format', 'change', 'CD', { format: 'CD' }],
		['Country', 'input', 'GB', { country: 'GB' }],
		['Status', 'change', 'official', { status: 'official' }]
	])('sends %s alone', async (label, evt, value, opts) => {
		mockSearch.mockResolvedValue({ candidates: [] });
		mount();
		const el = screen.getByLabelText(label);
		if (evt === 'input') await typeInto(el, value);
		else await fireEvent.change(el, { target: { value } });
		await fireEvent.click(searchBtn());
		await waitFor(() => expect(mockSearch).toHaveBeenCalledWith('Abbey Road', opts));
	});

	it('trims the query, artist and country', async () => {
		mockSearch.mockResolvedValue({ candidates: [] });
		mount();
		await typeInto(queryInput(), '  Dark Side  ');
		await typeInto(artistInput(), '  Pink Floyd ');
		await typeInto(countryInput(), ' GB ');
		await fireEvent.click(searchBtn());
		await waitFor(() => expect(mockSearch).toHaveBeenCalledWith('Dark Side', { artist: 'Pink Floyd', country: 'GB' }));
	});

	it('leaves out a blank or whitespace artist and country', async () => {
		mockSearch.mockResolvedValue({ candidates: [] });
		mount();
		await typeInto(artistInput(), '   ');
		await typeInto(countryInput(), '  ');
		await fireEvent.click(searchBtn());
		await waitFor(() => expect(mockSearch).toHaveBeenCalledWith('Abbey Road', {}));
	});

	it('sends track_count only with the match box on and disc tracks', async () => {
		mockSearch.mockResolvedValue({ candidates: [] });
		mount({ discTracks: [disc(0, 100), disc(1, 100)] });
		await fireEvent.click(searchBtn());
		await waitFor(() => expect(mockSearch).toHaveBeenLastCalledWith('Abbey Road', { track_count: 2 }));
		await fireEvent.click(screen.getByRole('checkbox'));
		await fireEvent.click(searchBtn());
		await waitFor(() => expect(mockSearch).toHaveBeenLastCalledWith('Abbey Road', {}));
		expect(mockSearch).toHaveBeenCalledTimes(2);
	});
});

describe('match checkbox', () => {
	it('is absent without disc tracks', () => {
		mount();
		expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
		expect(screen.queryByText(/ tracks$/)).not.toBeInTheDocument();
	});

	it('starts checked with the track count when there are disc tracks', () => {
		mount({ discTracks: [disc(0, 100), disc(1, 100), disc(2, 100)] });
		expect(screen.getByRole('checkbox')).toBeChecked();
		expect(screen.getByText('3 tracks')).toBeInTheDocument();
	});
});

describe('search triggers', () => {
	it.each([
		['query', () => queryInput()],
		['artist', () => artistInput()],
		['country', () => countryInput()]
	])('Enter in the %s input searches, another key does not', async (_name, field) => {
		mockSearch.mockResolvedValue({ candidates: [] });
		mount();
		await fireEvent.keyDown(field(), { key: 'a' });
		expect(mockSearch).not.toHaveBeenCalled();
		await fireEvent.keyDown(field(), { key: 'Enter' });
		await waitFor(() => expect(mockSearch).toHaveBeenCalledTimes(1));
	});

	it.each(['', '   '])('Enter with the query %j sends nothing', async (value) => {
		mount();
		await typeInto(queryInput(), value);
		await fireEvent.keyDown(queryInput(), { key: 'Enter' });
		expect(mockSearch).not.toHaveBeenCalled();
		expect(screen.queryByText('No results found.')).not.toBeInTheDocument();
	});

	it('disables Search while the query is blank', async () => {
		mount();
		expect(searchBtn()).toBeEnabled();
		await typeInto(queryInput(), '  ');
		expect(searchBtn()).toBeDisabled();
	});

	it('shows "Searching..." and disables the button while a search is pending', async () => {
		const d = deferred<{ candidates: MetadataCandidate[] }>();
		mockSearch.mockReturnValue(d.promise);
		mount();
		await fireEvent.click(searchBtn());
		expect(screen.getByRole('button', { name: 'Searching...' })).toBeDisabled();
		d.resolve({ candidates: [] });
		await screen.findByRole('button', { name: 'Search' });
		expect(searchBtn()).toBeEnabled();
	});
});

describe('Clear button', () => {
	it('is hidden with no active filter', () => {
		mount();
		expect(clearBtn()).not.toBeInTheDocument();
	});

	it.each([
		['Type', 'album'],
		['Format', 'CD'],
		['Status', 'official']
	])('is shown by the %s filter alone', async (label, value) => {
		mount();
		await fireEvent.change(screen.getByLabelText(label), { target: { value } });
		expect(clearBtn()).toBeInTheDocument();
	});

	it('is shown by the Country filter alone, but not by whitespace', async () => {
		mount();
		await typeInto(countryInput(), '   ');
		expect(clearBtn()).not.toBeInTheDocument();
		await typeInto(countryInput(), 'GB');
		expect(clearBtn()).toBeInTheDocument();
	});

	it('is shown by the checked match box and hidden once it is unchecked', async () => {
		mount({ discTracks: [disc(0, 100)] });
		expect(clearBtn()).toBeInTheDocument();
		await fireEvent.click(screen.getByRole('checkbox'));
		expect(clearBtn()).not.toBeInTheDocument();
	});

	it('empties every filter, unchecks the box and hides', async () => {
		mount({ discTracks: [disc(0, 100)] });
		await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'album' } });
		await fireEvent.change(screen.getByLabelText('Format'), { target: { value: 'CD' } });
		await typeInto(countryInput(), 'GB');
		await fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'official' } });
		await fireEvent.click(clearBtn()!);
		expect(screen.getByLabelText('Type')).toHaveValue('');
		expect(screen.getByLabelText('Format')).toHaveValue('');
		expect(countryInput()).toHaveValue('');
		expect(screen.getByLabelText('Status')).toHaveValue('');
		expect(screen.getByRole('checkbox')).not.toBeChecked();
		expect(clearBtn()).not.toBeInTheDocument();
	});
});

// ---- search results -----------------------------------------------------

describe('search results', () => {
	it('shows the response detail as the message and still draws the candidates', async () => {
		mount();
		mockSearch.mockResolvedValue({ candidates: [cand()], detail: 'Provider is rate limited' });
		await fireEvent.click(searchBtn());
		expect(await screen.findByText('Provider is rate limited')).toBeInTheDocument();
		expect(screen.getByText('Abbey Road')).toBeInTheDocument();
	});

	it('shows "No results found." for no candidates', async () => {
		mount();
		mockSearch.mockResolvedValue({ candidates: [] });
		await fireEvent.click(searchBtn());
		expect(await screen.findByText('No results found.')).toBeInTheDocument();
	});

	it('shows an Error rejection message', async () => {
		mount();
		mockSearch.mockRejectedValue(new Error('Gateway down'));
		await fireEvent.click(searchBtn());
		expect(await screen.findByText('Gateway down')).toBeInTheDocument();
	});

	it('shows "Search failed" for a non-Error rejection', async () => {
		mount();
		mockSearch.mockRejectedValue('nope');
		await fireEvent.click(searchBtn());
		expect(await screen.findByText('Search failed')).toBeInTheDocument();
	});

	it('clears the previous results, message and flipped cards on a new search', async () => {
		mount();
		mockSearch.mockResolvedValue({ candidates: [cand({ track_count: 2 })], detail: 'Old note' });
		await fireEvent.click(searchBtn());
		await screen.findByText('Old note');
		mockDetail.mockResolvedValue(rel());
		await fireEvent.click(flipBtn());
		await waitFor(() => expect(isFlipped()).toBe(true));

		const d = deferred<{ candidates: MetadataCandidate[] }>();
		mockSearch.mockReturnValue(d.promise);
		await fireEvent.click(searchBtn());
		expect(cards()).toHaveLength(0);
		expect(screen.queryByText('Old note')).not.toBeInTheDocument();

		d.resolve({ candidates: [cand({ track_count: 2 })] });
		await waitFor(() => expect(cards()).toHaveLength(1));
		expect(isFlipped()).toBe(false);
	});

	it('closes the open release on a new search', async () => {
		await openRelease(rel());
		const d = deferred<{ candidates: MetadataCandidate[] }>();
		mockSearch.mockReturnValue(d.promise);
		await fireEvent.click(searchBtn());
		expect(screen.queryByRole('button', { name: /Back to results/ })).not.toBeInTheDocument();
		d.resolve({ candidates: [cand()] });
		await waitFor(() => expect(cards()).toHaveLength(1));
	});
});

// ---- result cards -------------------------------------------------------

describe('result cards', () => {
	it('shows each optional pill when present', async () => {
		mount();
		await searchFor([cand({ release_type: 'Album', format: 'CD', country: 'GB', track_count: 12, year: 1969 })]);
		const card = cards()[0];
		expect(card.querySelector('.music-search-result-year')).toHaveTextContent('1969');
		expect(card.querySelector('[data-kind="type"]')).toHaveTextContent('Album');
		expect(card.querySelector('[data-kind="format"]')).toHaveTextContent('CD');
		expect(card.querySelector('[data-kind="country"]')).toHaveTextContent('GB');
		expect(card.querySelector('[data-kind="tracks"]')).toHaveTextContent('12 tracks');
	});

	it('shows no pill when the optional fields are absent', async () => {
		mount();
		await searchFor([cand({ year: null })]);
		const card = cards()[0];
		expect(card.querySelector('.music-search-result-year')).toBeNull();
		expect(card.querySelector('[data-kind]')).toBeNull();
		expect(screen.queryByTitle('Flip to see tracklist')).not.toBeInTheDocument();
	});

	it('fetches nothing when a card with no provider_id is clicked', async () => {
		mount();
		await searchFor([cand({ provider_id: null })]);
		await fireEvent.click(screen.getByText('Abbey Road'));
		expect(mockDetail).not.toHaveBeenCalled();
		expect(screen.queryByRole('button', { name: /Back to results/ })).not.toBeInTheDocument();
	});

	it('neither fetches nor flips from a flip button on a card with no provider_id', async () => {
		mount();
		await searchFor([cand({ provider_id: null, track_count: 3 })]);
		await fireEvent.click(flipBtn());
		expect(mockDetail).not.toHaveBeenCalled();
		expect(isFlipped()).toBe(false);
	});
});

describe('card flip', () => {
	it('shows the Loading face while the fetch is pending', async () => {
		mount();
		await searchFor([cand({ track_count: 2 })]);
		const d = deferred<MetadataReleaseDetail>();
		mockDetail.mockReturnValue(d.promise);
		await fireEvent.click(flipBtn());
		expect(isFlipped()).toBe(true);
		expect(cards()[0]).toHaveTextContent('Loading...');
		d.resolve(rel());
		await waitFor(() => expect(cards()[0]).not.toHaveTextContent('Loading...'));
	});

	it('shows the back face header and rows', async () => {
		await flipFirstCard(rel({ tracks: [trk(1, 'Come Together', 259000), trk(2, 'Something', null)] }));
		await waitFor(() => expect(backRows()).toHaveLength(2));
		const card = cards()[0];
		expect(mockDetail).toHaveBeenCalledWith('rel-1');
		expect(card.querySelector('.music-search-back-title')).toHaveTextContent('Abbey Road');
		expect(card.querySelector('.music-search-back-artist')).toHaveTextContent('The Beatles');
		expect(backRows()).toEqual([
			['1', 'Come Together', '4:19'],
			['2', 'Something', '-']
		]);
	});

	it('shows an empty artist when the release has none', async () => {
		await flipFirstCard(rel({ artist: null }));
		await waitFor(() => expect(backRows()).toHaveLength(2));
		expect(cards()[0].querySelector('.music-search-back-artist')!.textContent).toBe('');
	});

	it('has no match column without disc tracks', async () => {
		await flipFirstCard(rel());
		await waitFor(() => expect(backRows()).toHaveLength(2));
		expect(cards()[0].querySelector('.music-search-back-row [data-tone]')).toBeNull();
	});

	it.each([
		['match', 259, 'success', 'check'],
		['close', 265, 'warning', '~'],
		['mismatch', 400, 'danger', 'x'],
		['unknown', null, 'muted', '-']
	] as const)('shows the %s match kind in the back face', async (kind, secs, tone, glyph) => {
		await flipFirstCard(rel({ tracks: [trk(1, 'Come Together', 259000)] }), { discTracks: [disc(0, secs)] });
		await waitFor(() => expect(backRows()).toHaveLength(1));
		const cell = cards()[0].querySelector('.music-search-back-row [data-tone]');
		expect(cell).toHaveAttribute('data-tone', tone);
		expect(cell).toHaveAttribute('title', kind);
		expectGlyph(cell, glyph);
	});

	it('gives a release track past the last disc track the unknown kind', async () => {
		await flipFirstCard(rel(), { discTracks: [disc(0, 259)] });
		await waitFor(() => expect(backRows()).toHaveLength(2));
		const cells = cards()[0].querySelectorAll('.music-search-back-row [data-tone]');
		expect(cells[0]).toHaveAttribute('data-tone', 'success');
		expect(cells[1]).toHaveAttribute('data-tone', 'muted');
		expect(cells[1]).toHaveAttribute('title', 'unknown');
	});

	it.each([
		['no tracks', rel({ tracks: [] })],
		['a missing tracks list', rel({ tracks: undefined })]
	])('shows "No track data" for a release with %s', async (_name, d) => {
		await flipFirstCard(d);
		expect(cards()[0].querySelector('.music-search-back-empty')).toHaveTextContent('No track data');
		expect(backRows()).toHaveLength(0);
	});

	it('shows the fallback face when the fetch fails', async () => {
		mount();
		await searchFor([cand({ track_count: 2, year: null })]);
		mockDetail.mockRejectedValue(new Error('boom'));
		await fireEvent.click(flipBtn());
		await waitFor(() => expect(mockDetail).toHaveBeenCalledTimes(1));
		await waitFor(() => expect(cards()[0]).not.toHaveTextContent('Loading...'));
		expect(isFlipped()).toBe(true);
		expect(cards()[0].querySelector('.music-search-back-empty')).toHaveTextContent('No track data');
		expect(backRows()).toHaveLength(0);
	});

	it('hides the back face on flip back and refetches on the next flip', async () => {
		await flipFirstCard(rel());
		await waitFor(() => expect(backRows()).toHaveLength(2));
		await fireEvent.click(backBtn());
		expect(isFlipped()).toBe(false);
		expect(backRows()).toHaveLength(0);
		await fireEvent.click(flipBtn());
		await waitFor(() => expect(backRows()).toHaveLength(2));
		expect(mockDetail).toHaveBeenCalledTimes(2);
	});

	it('flips again when the fetch resolves after a flip back (today)', async () => {
		mount();
		await searchFor([cand({ track_count: 2 })]);
		const d = deferred<MetadataReleaseDetail>();
		mockDetail.mockReturnValue(d.promise);
		await fireEvent.click(flipBtn());
		await fireEvent.click(backBtn());
		expect(isFlipped()).toBe(false);
		d.resolve(rel());
		await waitFor(() => expect(isFlipped()).toBe(true));
		await waitFor(() => expect(backRows()).toHaveLength(2));
	});
});

// ---- opening a release --------------------------------------------------

describe('opening a release', () => {
	it('shows "Loading..." while the detail fetch is pending', async () => {
		mount();
		await searchFor([cand()]);
		const d = deferred<MetadataReleaseDetail>();
		mockDetail.mockReturnValue(d.promise);
		await fireEvent.click(screen.getByText('Abbey Road'));
		expect(screen.getByText('Loading...')).toBeInTheDocument();
		d.resolve(rel());
		await screen.findByRole('button', { name: /Back to results/ });
		expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
	});

	it.each([
		['an Error', new Error('Detail exploded'), 'Detail exploded'],
		['a non-Error', 'nope', 'Load failed']
	])('keeps the results and shows no message when the fetch rejects with %s (today)', async (_n, err, text) => {
		mount();
		await searchFor([cand()]);
		mockDetail.mockRejectedValue(err);
		await fireEvent.click(screen.getByText('Abbey Road'));
		await waitFor(() => expect(mockDetail).toHaveBeenCalledTimes(1));
		await waitFor(() => expect(screen.queryByText('Loading...')).not.toBeInTheDocument());
		expect(cards()).toHaveLength(1);
		expect(screen.queryByText(text)).not.toBeInTheDocument();
		expect(screen.queryByRole('button', { name: /Back to results/ })).not.toBeInTheDocument();
	});

	it('shows the full header', async () => {
		await openRelease(
			rel({
				title: 'The Wall',
				artist: 'Pink Floyd',
				country: 'GB',
				format: 'CD',
				status: 'Official',
				disc_count: 2,
				catalog_number: 'SHVL 800',
				barcode: '0094635'
			})
		);
		const meta = document.querySelector('.music-search-detail-meta')!;
		expect(meta.querySelector('.music-search-detail-title')).toHaveTextContent('The Wall');
		const text = meta.textContent!;
		for (const part of ['Pink Floyd', 'GB', 'CD', 'Official', '2 discs', 'Cat# SHVL 800', '| 0094635']) {
			expect(text).toContain(part);
		}
	});

	it('omits the optional header parts and shows an empty artist', async () => {
		await openRelease(rel({ artist: null }));
		const meta = document.querySelector('.music-search-detail-meta')!;
		expect(meta.querySelector('.music-search-detail-title')).toHaveTextContent('Abbey Road');
		expect(meta.querySelectorAll('p')[1].textContent).toBe('');
		expect(meta.querySelectorAll('p')[2].textContent!.trim()).toBe('');
		expect(meta.querySelector('.music-search-catalog')!.textContent!.trim()).toBe('');
		expect(screen.queryByText(/discs$/)).not.toBeInTheDocument();
	});

	it('Back to results shows the same cards again without a new search', async () => {
		mount();
		await searchFor([cand({ title: 'Abbey Road' }), cand({ title: 'Let It Be', provider_id: 'rel-2' })]);
		mockDetail.mockResolvedValue(rel());
		await openCard('Abbey Road');
		expect(cards()).toHaveLength(0);
		await backToResults();
		expect(cards()).toHaveLength(2);
		expect(screen.getByText('Let It Be')).toBeInTheDocument();
		expect(mockSearch).toHaveBeenCalledTimes(1);
	});
});

// ---- tracklist ----------------------------------------------------------

describe('tracklist', () => {
	it('shows the disc columns, the Match column and the Total row with disc tracks', async () => {
		await openRelease(
			rel({
				tracks: [trk(1, 'One', 259000), trk(2, 'Two', 265000), trk(3, 'Three', 400000), trk(4, 'Four', 100000)]
			}),
			{ discTracks: [disc(0, 259), disc(1, 259), disc(2, 259)] }
		);
		const headers = Array.from(document.querySelectorAll('thead th')).map((th) => th.textContent);
		expect(headers).toEqual(['#', 'Title', 'Disc Length', 'Match Length', 'Match']);
		const rows = detailRows();
		expect(rows.map((r) => r.slice(0, 4))).toEqual([
			['1', 'One', '4:19', '4:19'],
			['2', 'Two', '4:19', '4:25'],
			['3', 'Three', '4:19', '6:40'],
			['4', 'Four', '-', '1:40']
		]);
		const cells = Array.from(document.querySelectorAll('tbody tr')).map((tr) => tr.querySelector('[data-tone]'));
		const expected = [
			['success', 'check'],
			['warning', '~'],
			['danger', 'x'],
			['muted', '-']
		] as const;
		expected.forEach(([tone, glyph], i) => {
			expect(cells[i]).toHaveAttribute('data-tone', tone);
			expectGlyph(cells[i], glyph);
		});
		// Totals: disc 3 * 259s = 12:57, release 1024s = 17:04, a mismatch.
		const total = Array.from(document.querySelectorAll('.music-search-tfoot td'));
		expect(total.map((td) => td.textContent!.trim()).slice(0, 4)).toEqual(['Total', '', '12:57', '17:04']);
		expect(total[4]).toHaveAttribute('data-tone', 'danger');
	});

	it('shows a matching Total tone', async () => {
		await openRelease(rel(), { discTracks: [disc(0, 259), disc(1, 182)] });
		const total = document.querySelectorAll('.music-search-tfoot td');
		expect(total[2]).toHaveTextContent('7:21');
		expect(total[3]).toHaveTextContent('7:21');
		expect(total[4]).toHaveAttribute('data-tone', 'success');
	});

	it('shows Duration and no disc columns without disc tracks', async () => {
		await openRelease(rel());
		const headers = Array.from(document.querySelectorAll('thead th')).map((th) => th.textContent);
		expect(headers).toEqual(['#', 'Title', 'Duration']);
		expect(detailRows()).toEqual([
			['1', 'Come Together', '4:19'],
			['2', 'Something', '3:02']
		]);
		expect(screen.queryByText('Total')).not.toBeInTheDocument();
		expect(document.querySelector('.music-search-tfoot')).toBeNull();
	});

	it('falls back to the row number when the position is null', async () => {
		await openRelease(rel({ tracks: [trk(null, 'First', 1000), trk(null, 'Second', 2000)] }));
		expect(detailRows().map((r) => r[0])).toEqual(['1', '2']);
	});

	it("shows only the held disc's tracks on a multi-disc release", async () => {
		await openRelease(
			rel({
				disc_count: 2,
				tracks: [trk(1, 'D1 One', 1000, 1), trk(1, 'D2 One', 1000, 2), trk(2, 'D2 Two', 1000, 2)]
			}),
			{ job: { disc_number: 2 } }
		);
		expect(detailRows().map((r) => r[1])).toEqual(['D2 One', 'D2 Two']);
	});

	it.each([
		['without job.disc_number', 2, {}],
		['with disc_count 1', 1, { disc_number: 2 }],
		['with disc_count null', null, { disc_number: 2 }]
	])('shows every track %s', async (_name, disc_count, job) => {
		await openRelease(rel({ disc_count, tracks: [trk(1, 'D1 One', 1000, 1), trk(1, 'D2 One', 1000, 2)] }), { job });
		expect(detailRows().map((r) => r[1])).toEqual(['D1 One', 'D2 One']);
	});

	it('shows no rows for a release with no tracks list, held disc or not', async () => {
		await openRelease(rel({ tracks: undefined }));
		expect(detailRows()).toEqual([]);
		cleanup();
		await openRelease(rel({ tracks: undefined, disc_count: 2 }), { job: { disc_number: 1 } });
		expect(detailRows()).toEqual([]);
	});

	it('shows "-" for the disc total when no disc track has an expected duration', async () => {
		await openRelease(rel(), { discTracks: [disc(0, null), disc(1, null)] });
		const total = document.querySelectorAll('.music-search-tfoot td');
		expect(total[2]).toHaveTextContent('-');
		expect(total[3]).toHaveTextContent('7:21');
		expect(detailRows().map((r) => r[2])).toEqual(['-', '-']);
	});
});

// ---- edit fields --------------------------------------------------------

describe('edit fields', () => {
	it('seeds album, artist and year from the release', async () => {
		await openRelease(rel({ title: 'Revolver', artist: 'The Beatles', year: 1966 }));
		expect(albumInput()).toHaveValue('Revolver');
		expect(editArtist()).toHaveValue('The Beatles');
		expect(yearInput()).toHaveValue('1966');
	});

	it('seeds a blank artist and year when the release has none', async () => {
		await openRelease(rel({ artist: null, year: null }));
		expect(editArtist()).toHaveValue('');
		expect(yearInput()).toHaveValue('');
	});

	it('seeds Disc # and Disc total from the job', async () => {
		await openRelease(rel(), { job: { disc_number: 2, disc_total: 3 } });
		expect(discNumberInput()).toHaveValue('2');
		expect(discTotalInput()).toHaveValue('3');
	});

	it('leaves Disc # and Disc total blank when the job has none', async () => {
		await openRelease(rel());
		expect(discNumberInput()).toHaveValue('');
		expect(discTotalInput()).toHaveValue('');
	});

	it('fills a blank Disc total from a multi-disc release and leaves a set one alone', async () => {
		await openRelease(rel({ disc_count: 3 }));
		expect(discTotalInput()).toHaveValue('3');
		cleanup();
		await openRelease(rel({ disc_count: 3 }), { job: { disc_total: 5 } });
		expect(discTotalInput()).toHaveValue('5');
	});

	it('keeps Disc # and Disc total after Back and opening another release', async () => {
		mount();
		await searchFor([cand({ title: 'Abbey Road' }), cand({ title: 'Let It Be', provider_id: 'rel-2' })]);
		mockDetail.mockResolvedValue(rel({ disc_count: 2 }));
		await openCard('Abbey Road');
		await typeInto(discNumberInput(), '9');
		await typeInto(discTotalInput(), '7');
		await backToResults();
		mockDetail.mockResolvedValue(rel({ release_id: 'rel-2', title: 'Let It Be', disc_count: 2 }));
		await openCard('Let It Be');
		expect(albumInput()).toHaveValue('Let It Be');
		expect(discNumberInput()).toHaveValue('9');
		expect(discTotalInput()).toHaveValue('7');
	});

	it('resets Album, Artist and Year when Disc total is typed on a multi-disc release (today)', async () => {
		await openRelease(rel({ disc_count: 2 }));
		await typeInto(albumInput(), 'Edited');
		await typeInto(editArtist(), 'Someone');
		await typeInto(yearInput(), '2001');
		await typeInto(discTotalInput(), '4');
		expect(albumInput()).toHaveValue('Abbey Road');
		expect(editArtist()).toHaveValue('The Beatles');
		expect(yearInput()).toHaveValue('1969');
		expect(discTotalInput()).toHaveValue('4');
	});

	it('refills Disc total with the disc count when it is cleared (today)', async () => {
		await openRelease(rel({ disc_count: 2 }), { job: { disc_total: 5 } });
		await typeInto(discTotalInput(), '');
		expect(discTotalInput()).toHaveValue('2');
	});

	it('keeps edits when Disc total is typed on a single-disc release', async () => {
		await openRelease(rel());
		await typeInto(albumInput(), 'Edited');
		await typeInto(discTotalInput(), '4');
		expect(albumInput()).toHaveValue('Edited');
	});
});

// ---- apply --------------------------------------------------------------

describe('Apply button', () => {
	it.each(['', '   '])('is disabled while the album is %j', async (value) => {
		await openRelease(rel());
		expect(applyBtn()).toBeEnabled();
		await typeInto(albumInput(), value);
		expect(applyBtn()).toBeDisabled();
	});

	it('shows "Applying..." and is disabled while pending', async () => {
		await openRelease(rel());
		const d = deferred<never>();
		mockResolve.mockReturnValue(d.promise);
		await fireEvent.click(applyBtn());
		expect(screen.getByRole('button', { name: 'Applying...' })).toBeDisabled();
		d.resolve({ job: {}, fan_out: [] } as never);
		await screen.findByRole('button', { name: 'Apply' });
		expect(applyBtn()).toBeEnabled();
	});
});

// Two disc tracks of 100s against a 25:00 release: a total mismatch.
const MISMATCH_TRACKS = [trk(1, 'Track A', 400000), trk(2, 'Track B', 400000)];
const DISC_100 = () => [disc(0, 100), disc(1, 100)];
const ALERT = 'Total length differs, likely the wrong release';
const anyway = () => screen.getByRole('button', { name: 'Apply anyway' });
const applyTitles = () => screen.getByRole('button', { name: 'Apply titles' });
const cancel = () => screen.getByRole('button', { name: 'Cancel' });

describe('total-mismatch alert', () => {
	it('shows only with disc tracks and a mismatched total', async () => {
		await openRelease(rel({ tracks: MISMATCH_TRACKS }), { discTracks: DISC_100() });
		await fireEvent.click(applyBtn());
		expect(screen.getByText(ALERT)).toBeInTheDocument();
		expect(mockResolve).not.toHaveBeenCalled();
	});

	it('does not show without disc tracks', async () => {
		await openRelease(rel({ tracks: MISMATCH_TRACKS }));
		await fireEvent.click(applyBtn());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(screen.queryByText(ALERT)).not.toBeInTheDocument();
	});

	it('does not show when the totals match', async () => {
		await openRelease(rel(), { discTracks: [disc(0, 259), disc(1, 182)] });
		await fireEvent.click(applyBtn());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(screen.queryByText(ALERT)).not.toBeInTheDocument();
	});

	it('closes on Cancel with no request', async () => {
		await openRelease(rel({ tracks: MISMATCH_TRACKS }), { discTracks: DISC_100() });
		await fireEvent.click(applyBtn());
		await fireEvent.click(cancel());
		expect(screen.queryByText(ALERT)).not.toBeInTheDocument();
		expect(mockResolve).not.toHaveBeenCalled();
	});

	it('applies on "Apply anyway"', async () => {
		await openRelease(rel({ tracks: MISMATCH_TRACKS }), { discTracks: DISC_100() });
		await fireEvent.click(applyBtn());
		await fireEvent.click(anyway());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(screen.queryByText(ALERT)).not.toBeInTheDocument();
	});

	it('skips the alert on a second Apply once confirmed', async () => {
		await openRelease(rel({ tracks: MISMATCH_TRACKS }), { discTracks: DISC_100() });
		await fireEvent.click(applyBtn());
		await fireEvent.click(anyway());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		await fireEvent.click(applyBtn());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(2));
		expect(screen.queryByText(ALERT)).not.toBeInTheDocument();
	});

	it('sends nothing on "Apply anyway" after the album was cleared', async () => {
		await openRelease(rel({ tracks: MISMATCH_TRACKS }), { discTracks: DISC_100() });
		await fireEvent.click(applyBtn());
		await typeInto(albumInput(), '');
		await fireEvent.click(anyway());
		expect(mockResolve).not.toHaveBeenCalled();
		expect(screen.queryByText(ALERT)).not.toBeInTheDocument();
	});
});

// Audio disc tracks whose total matches the release (7:21), so only the
// mapping preview gates the apply.
const AUDIO_TRACKS = () => [disc(0, 259, { kind: 'audio_track' }), disc(1, 182, { kind: 'audio_track' })];

describe('mapping preview', () => {
	it('shows the rows for audio disc tracks and release tracks', async () => {
		await openRelease(rel({ tracks: [trk(1, 'Come Together', 259000), trk(2, 'Something', 190000)] }), {
			discTracks: [disc(0, 259, { kind: 'audio_track' }), disc(1, 182, { kind: 'audio_track' })]
		});
		await fireEvent.click(applyBtn());
		expect(screen.getByText('Confirm track title mapping')).toBeInTheDocument();
		expect(mockResolve).not.toHaveBeenCalled();
		const rows = Array.from(document.querySelectorAll('.music-search-mapping-preview tbody tr'));
		expect(rows.map((r) => Array.from(r.querySelectorAll('td')).map((td) => td.textContent!.trim()))).toEqual([
			['Disc #0 (4:19)', '', 'Come Together', '4:19', ''],
			['Disc #1 (3:02)', '', 'Something', '3:10', '~']
		]);
		const tones = rows.map((r) => r.querySelector('[data-tone]'));
		expect(tones[0]).toHaveAttribute('data-tone', 'success');
		expect(tones[1]).toHaveAttribute('data-tone', 'warning');
	});

	it('leaves out disc tracks of another kind', async () => {
		await openRelease(rel(), {
			discTracks: [
				disc(0, 259, { kind: 'audio_track' }),
				disc(1, null, { kind: 'video_title' }),
				disc(2, 182, { kind: 'audio_track' })
			]
		});
		await fireEvent.click(applyBtn());
		const rows = Array.from(document.querySelectorAll('.music-search-mapping-preview tbody tr'));
		expect(rows.map((r) => r.querySelector('td')!.textContent!.trim())).toEqual(['Disc #0 (4:19)', 'Disc #2 (3:02)']);
	});

	it('stops the pairs at the shorter list', async () => {
		await openRelease(rel({ tracks: [trk(1, 'Come Together', 259000), trk(2, 'Something', null)] }), {
			discTracks: [disc(0, 259, { kind: 'audio_track' })]
		});
		await fireEvent.click(applyBtn());
		expect(document.querySelectorAll('.music-search-mapping-preview tbody tr')).toHaveLength(1);
	});

	it('stops the pairs at the shorter list when the release is shorter', async () => {
		await openRelease(rel({ tracks: [trk(1, 'Come Together', 259000)] }), {
			discTracks: [disc(0, 259, { kind: 'audio_track' }), disc(1, null, { kind: 'audio_track' })]
		});
		await fireEvent.click(applyBtn());
		expect(document.querySelectorAll('.music-search-mapping-preview tbody tr')).toHaveLength(1);
	});

	it('does not show without audio disc tracks', async () => {
		await openRelease(rel(), { discTracks: [disc(0, 259), disc(1, 182)] });
		await fireEvent.click(applyBtn());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(screen.queryByText('Confirm track title mapping')).not.toBeInTheDocument();
	});

	it('does not show for a release with no tracks', async () => {
		await openRelease(rel({ tracks: [] }), { discTracks: [disc(0, null, { kind: 'audio_track' })] });
		await fireEvent.click(applyBtn());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(screen.queryByText('Confirm track title mapping')).not.toBeInTheDocument();
	});

	it('closes on Cancel with no request', async () => {
		await openRelease(rel(), { discTracks: AUDIO_TRACKS() });
		await fireEvent.click(applyBtn());
		await fireEvent.click(cancel());
		expect(screen.queryByText('Confirm track title mapping')).not.toBeInTheDocument();
		expect(mockResolve).not.toHaveBeenCalled();
	});

	it('applies on "Apply titles"', async () => {
		await openRelease(rel(), { discTracks: AUDIO_TRACKS() });
		await fireEvent.click(applyBtn());
		await fireEvent.click(applyTitles());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(screen.queryByText('Confirm track title mapping')).not.toBeInTheDocument();
	});

	it('skips the preview on a second Apply once confirmed', async () => {
		await openRelease(rel(), { discTracks: AUDIO_TRACKS() });
		await fireEvent.click(applyBtn());
		await fireEvent.click(applyTitles());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		await fireEvent.click(applyBtn());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(2));
		expect(screen.queryByText('Confirm track title mapping')).not.toBeInTheDocument();
	});
});

describe('both gates', () => {
	const audioMismatch = () => [disc(0, 100, { kind: 'audio_track' }), disc(1, 100, { kind: 'audio_track' })];

	it('opens the mapping preview after "Apply anyway", and "Apply titles" sends', async () => {
		await openRelease(rel({ tracks: MISMATCH_TRACKS }), { discTracks: audioMismatch() });
		await fireEvent.click(applyBtn());
		await fireEvent.click(anyway());
		expect(screen.queryByText(ALERT)).not.toBeInTheDocument();
		expect(screen.getByText('Confirm track title mapping')).toBeInTheDocument();
		expect(mockResolve).not.toHaveBeenCalled();
		await fireEvent.click(applyTitles());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
	});

	it('opening another release resets both confirmations', async () => {
		mount({ discTracks: audioMismatch() });
		await searchFor([cand({ title: 'Abbey Road' }), cand({ title: 'Let It Be', provider_id: 'rel-2' })]);
		mockDetail.mockResolvedValue(rel({ tracks: MISMATCH_TRACKS }));
		await openCard('Abbey Road');
		await fireEvent.click(applyBtn());
		await fireEvent.click(anyway());
		await fireEvent.click(applyTitles());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		await backToResults();
		mockDetail.mockResolvedValue(rel({ release_id: 'rel-2', title: 'Let It Be', tracks: MISMATCH_TRACKS }));
		await openCard('Let It Be');
		await fireEvent.click(applyBtn());
		expect(screen.getByText(ALERT)).toBeInTheDocument();
		await fireEvent.click(anyway());
		expect(screen.getByText('Confirm track title mapping')).toBeInTheDocument();
		expect(mockResolve).toHaveBeenCalledTimes(1);
	});
});

describe('resolve request', () => {
	it('sends the trimmed fields, numbers and the release tracks', async () => {
		await openRelease(
			rel({
				tracks: [
					trk(1, 'Come Together', 259000, 1),
					{ position: 2, title: 'Something' },
					{ position: null, title: 'Untitled', length_ms: 5000, disc_number: 2 }
				]
			})
		);
		await typeInto(albumInput(), '  New Album ');
		await typeInto(editArtist(), ' New Artist  ');
		await typeInto(yearInput(), ' 1999 ');
		await typeInto(discNumberInput(), ' 2 ');
		await typeInto(discTotalInput(), '3');
		await fireEvent.click(applyBtn());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(mockResolve).toHaveBeenCalledWith('job_1', {
			title: 'New Album',
			year: 1999,
			disc_number: 2,
			disc_total: 3,
			music: {
				artist: 'New Artist',
				album: 'New Album',
				tracks: [
					{ position: 1, title: 'Come Together', length_ms: 259000, disc_number: 1 },
					{ position: 2, title: 'Something', length_ms: null, disc_number: null },
					{ position: null, title: 'Untitled', length_ms: 5000, disc_number: 2 }
				]
			}
		});
	});

	it.each([
		['blank', ''],
		['not a number', 'abc']
	])('sends null for a year, disc number and disc total that are %s', async (_name, value) => {
		await openRelease(rel());
		await typeInto(yearInput(), value);
		await typeInto(discNumberInput(), value);
		await typeInto(discTotalInput(), value);
		await fireEvent.click(applyBtn());
		await waitFor(() => expect(mockResolve).toHaveBeenCalledTimes(1));
		expect(mockResolve).toHaveBeenCalledWith(
			'job_1',
			expect.objectContaining({ year: null, disc_number: null, disc_total: null })
		);
	});
});

describe('PATCH after resolve', () => {
	it('sends the cover only', async () => {
		await openRelease(rel({ poster_url: 'https://img.example/cover.jpg' }));
		await fireEvent.click(applyBtn());
		await waitFor(() => expect(mockPatchJob).toHaveBeenCalledTimes(1));
		expect(mockPatchJob).toHaveBeenCalledWith('job_1', { poster_url_manual: 'https://img.example/cover.jpg' });
	});

	it('sends the track titles only', async () => {
		await openRelease(rel(), { discTracks: AUDIO_TRACKS() });
		await fireEvent.click(applyBtn());
		await fireEvent.click(applyTitles());
		await waitFor(() => expect(mockPatchJob).toHaveBeenCalledTimes(1));
		expect(mockPatchJob).toHaveBeenCalledWith('job_1', {
			tracks: [
				{ track_id: 'trk_0', title: 'Come Together' },
				{ track_id: 'trk_1', title: 'Something' }
			]
		});
	});

	it('sends both', async () => {
		await openRelease(rel({ poster_url: 'https://img.example/cover.jpg' }), { discTracks: AUDIO_TRACKS() });
		await fireEvent.click(applyBtn());
		await fireEvent.click(applyTitles());
		await waitFor(() => expect(mockPatchJob).toHaveBeenCalledTimes(1));
		expect(mockPatchJob).toHaveBeenCalledWith('job_1', {
			poster_url_manual: 'https://img.example/cover.jpg',
			tracks: [
				{ track_id: 'trk_0', title: 'Come Together' },
				{ track_id: 'trk_1', title: 'Something' }
			]
		});
	});

	it('sends no PATCH with neither', async () => {
		await openRelease(rel());
		await fireEvent.click(applyBtn());
		await screen.findByText('Release applied');
		expect(mockPatchJob).not.toHaveBeenCalled();
	});
});

describe('apply outcome', () => {
	it('shows "Release applied" and calls onapply', async () => {
		const onapply = vi.fn();
		await openRelease(rel(), { onapply });
		await fireEvent.click(applyBtn());
		expect(await screen.findByText('Release applied')).toBeInTheDocument();
		expect(onapply).toHaveBeenCalledTimes(1);
	});

	it('shows "Release applied" and no error when onapply is not passed', async () => {
		await openRelease(rel());
		await fireEvent.click(applyBtn());
		expect(await screen.findByText('Release applied')).toBeInTheDocument();
		expect(screen.queryByText('Apply failed')).not.toBeInTheDocument();
	});

	it('reports a failed PATCH but still calls onapply', async () => {
		const onapply = vi.fn();
		mockPatchJob.mockRejectedValue(new Error('patch down'));
		await openRelease(rel({ poster_url: 'https://img.example/cover.jpg' }), { onapply });
		await fireEvent.click(applyBtn());
		expect(await screen.findByText('Identified; cover/track titles not saved')).toBeInTheDocument();
		expect(onapply).toHaveBeenCalledTimes(1);
	});

	it.each([
		['an Error message', new Error('Resolve exploded'), 'Resolve exploded'],
		['"Apply failed" for a non-Error', 'nope', 'Apply failed']
	])('shows %s on a failed resolve, with no PATCH and no onapply', async (_n, err, text) => {
		const onapply = vi.fn();
		mockResolve.mockRejectedValue(err);
		await openRelease(rel({ poster_url: 'https://img.example/cover.jpg' }), { onapply });
		await fireEvent.click(applyBtn());
		const msg = await screen.findByText(text);
		expect(msg).toHaveAttribute('data-tone', 'error');
		expect(mockPatchJob).not.toHaveBeenCalled();
		expect(onapply).not.toHaveBeenCalled();
	});
});
