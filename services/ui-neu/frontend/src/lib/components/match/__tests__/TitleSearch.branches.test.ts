import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/testing/render';
import type { MetadataCandidate, ResolveResponse } from '$lib/types/api.gen';
import TitleSearch from '../TitleSearch.svelte';
import { createJob } from '../../../__fixtures__/job';

// Branch pins for TitleSearch, beside TitleSearch.test.ts, ahead of splitting
// it into helpers, stores and a source picker. Every branch of the component
// is reachable from the rendered component, so nothing is left unpinned.

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

vi.mock('$lib/stores/config', async () => {
	const { writable } = await import('svelte/store');
	const keyed = writable({ tmdb: true, omdb: true, tvdb: true });
	return {
		searchProviders: writable({ movie: 'omdb', tv: 'tmdb' }),
		keyedSources: { subscribe: keyed.subscribe }
	};
});

vi.mock('$lib/api/jobs', () => ({
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	fetchMatchDetails: vi.fn(),
	updateJobTitle: vi.fn(),
	resolveJob: vi.fn()
}));

import { searchMetadata, fetchMatchDetails, fetchMediaDetail, updateJobTitle, resolveJob } from '$lib/api/jobs';
import * as configStore from '$lib/stores/config';

const mockSearch = vi.mocked(searchMetadata);
const mockMatchDetails = vi.mocked(fetchMatchDetails);
const mockFetchDetail = vi.mocked(fetchMediaDetail);
const mockUpdateTitle = vi.mocked(updateJobTitle);
const mockResolve = vi.mocked(resolveJob);

const providers = configStore.searchProviders as unknown as {
	set: (v: { movie: string; tv: string }) => void;
};

const RESOLVED = { job: {}, fan_out: [] } as unknown as ResolveResponse;

function cand(overrides: Partial<MetadataCandidate> = {}): MetadataCandidate {
	return { title: 'Result', year: 2024, kind: 'movie', poster_url: null, provider_id: 'tt1111', ...overrides };
}

// A resolvable job with no year, so the year box starts blank.
const resolvable = (o: Parameters<typeof createJob>[0] = {}) =>
	createJob({ id: 'job_1', status: 'awaiting_user_id', title: 'Q', year: null, ...o });

type Props = Partial<{
	onapply: () => void;
	onresolved: (r: ResolveResponse) => void;
	onseries: () => void;
	initialType: 'movie' | 'tv';
}>;

const searchButton = () => screen.getByRole('button', { name: /^Search/ });
const titleBox = () => screen.getByRole('textbox', { name: 'Title' });
const yearBox = () => screen.getByPlaceholderText('Year');
const imdbBox = () => screen.getByPlaceholderText('IMDb ID (tt...)');
const sourceSelect = () => screen.getByRole('combobox', { name: 'Search with' }) as HTMLSelectElement;
const typeInto = (el: HTMLElement, value: string) => fireEvent.input(el, { target: { value } });
// The search box is also labelled Title; the edit field has no aria-label.
const editTitleInput = () =>
	screen.getAllByLabelText('Title').find((el) => !el.hasAttribute('aria-label')) as HTMLElement;
const useButton = () => screen.getByRole('button', { name: /^(Use this match|Use poster|Applying\.\.\.)$/ });
const flush = () => new Promise((r) => setTimeout(r, 0));

async function search() {
	await fireEvent.click(searchButton());
}

/** Render, search for `candidates`, and wait for the picker. */
async function openResults(candidates: MetadataCandidate[], job = resolvable(), props: Props = {}) {
	mockSearch.mockResolvedValue({ candidates });
	const view = renderComponent(TitleSearch, { props: { job, ...props } });
	await search();
	await screen.findByRole('heading', { name: candidates[0].title });
	return view;
}

async function openEdit() {
	await fireEvent.click(screen.getByRole('button', { name: 'Edit before using' }));
}

async function clickUse() {
	await fireEvent.click(useButton());
}

describe('TitleSearch branches', () => {
	beforeEach(() => {
		mockSearch.mockReset();
		mockFetchDetail.mockReset();
		mockMatchDetails.mockReset().mockResolvedValue({ candidates: [] });
		mockUpdateTitle.mockReset().mockResolvedValue(undefined as never);
		mockResolve.mockReset().mockResolvedValue(RESOLVED);
		providers.set({ movie: 'omdb', tv: 'tmdb' });
	});

	afterEach(() => {
		cleanup();
	});

	describe('search type and source', () => {
		it.each([
			['initialType tv beats a movie job', { media_type: 'movie' as const }, 'tv', 'tv'],
			['initialType movie beats a tv job', { media_type: 'tv' as const }, 'movie', 'movie'],
			['a tv job searches tv', { media_type: 'tv' as const }, undefined, 'tv'],
			['an episodic job with no type searches tv', { looks_episodic: true }, undefined, 'tv'],
			[
				'a movie job that looks episodic searches movie',
				{ media_type: 'movie' as const, looks_episodic: true },
				undefined,
				'movie'
			],
			['a job with no type that is not episodic searches movie', { looks_episodic: false }, undefined, 'movie']
		])('%s', async (_name, jobOverrides, initialType, expected) => {
			mockSearch.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: resolvable(jobOverrides), initialType } });
			await search();
			const source = expected === 'tv' ? 'tmdb' : 'omdb';
			expect(mockSearch).toHaveBeenCalledWith('Q', expected, source, null);
		});

		it('sends the picked source', async () => {
			mockSearch.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: resolvable({ media_type: 'movie' }) } });
			await fireEvent.change(sourceSelect(), { target: { value: 'tmdb' } });
			await search();
			expect(mockSearch).toHaveBeenCalledWith('Q', 'movie', 'tmdb', null);
		});

		it('a type change drops the pick, the results and the error line', async () => {
			mockSearch.mockResolvedValueOnce({ candidates: [] });
			const { rerender } = renderComponent(TitleSearch, { props: { job: resolvable({ media_type: 'movie' }) } });
			await fireEvent.change(sourceSelect(), { target: { value: 'tmdb' } });
			await search();
			expect(await screen.findByText('No results found. Try a different search term.')).toBeInTheDocument();
			await rerender({ job: resolvable({ media_type: 'tv' }) });
			expect(screen.queryByText('No results found. Try a different search term.')).toBeNull();
			expect(sourceSelect().value).toBe('tmdb');
			cleanup();

			mockSearch.mockResolvedValueOnce({ candidates: [cand({ title: 'Found' })] });
			const second = renderComponent(TitleSearch, { props: { job: resolvable({ media_type: 'movie' }) } });
			await search();
			await screen.findByRole('heading', { name: 'Found' });
			await second.rerender({ job: resolvable({ media_type: 'tv' }) });
			expect(screen.queryByRole('heading', { name: 'Found' })).toBeNull();
			expect(screen.queryByText('1 RESULT')).toBeNull();
		});

		it('sends undefined when the Settings default is not among the type sources', async () => {
			providers.set({ movie: 'tvdb', tv: 'tmdb' });
			mockSearch.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: resolvable({ media_type: 'movie' }) } });
			await search();
			expect(mockSearch).toHaveBeenCalledWith('Q', 'movie', undefined, null);
		});

		it('a TV pick is dropped on a change to movie: the movie search sends the movie default', async () => {
			mockSearch.mockResolvedValue({ candidates: [] });
			const { rerender } = renderComponent(TitleSearch, { props: { job: resolvable({ media_type: 'tv' }) } });
			await fireEvent.change(sourceSelect(), { target: { value: 'tvdb' } });
			await search();
			expect(mockSearch).toHaveBeenLastCalledWith('Q', 'tv', 'tvdb', null);
			await rerender({ job: resolvable({ media_type: 'movie' }) });
			await search();
			expect(mockSearch).toHaveBeenLastCalledWith('Q', 'movie', 'omdb', null);
		});
	});

	describe('IMDb lookup', () => {
		it('sends the trimmed id, wins over a filled query and shows only the first candidate', async () => {
			mockFetchDetail.mockResolvedValue({
				candidates: [cand({ title: 'First' }), cand({ title: 'Second' })]
			});
			renderComponent(TitleSearch, { props: { job: resolvable({ title: 'Filled query' }) } });
			await typeInto(imdbBox(), '  tt0133093 ');
			await search();
			expect(await screen.findByRole('heading', { name: 'First' })).toBeInTheDocument();
			expect(mockFetchDetail).toHaveBeenCalledWith('tt0133093');
			expect(mockSearch).not.toHaveBeenCalled();
			expect(screen.getByText('1 RESULT')).toBeInTheDocument();
			expect(screen.queryByText('Second')).toBeNull();
		});

		it('says so when there is no match', async () => {
			mockFetchDetail.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await typeInto(imdbBox(), 'tt1');
			await search();
			expect(await screen.findByText('No match found for that IMDb ID.')).toBeInTheDocument();
		});

		it('shows the message of an Error', async () => {
			mockFetchDetail.mockRejectedValue(new Error('IMDb is down'));
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await typeInto(imdbBox(), 'tt1');
			await search();
			expect(await screen.findByText('IMDb is down')).toBeInTheDocument();
		});

		it('shows "IMDb lookup failed" for a non-Error rejection', async () => {
			mockFetchDetail.mockRejectedValue('nope');
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await typeInto(imdbBox(), 'tt1');
			await search();
			expect(await screen.findByText('IMDb lookup failed')).toBeInTheDocument();
		});
	});

	describe('text search', () => {
		it('sends the trimmed query, the type, the source and the year', async () => {
			mockSearch.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: resolvable({ media_type: 'tv' }) } });
			await typeInto(titleBox(), '  Kolchak  ');
			await typeInto(yearBox(), '1974');
			await search();
			expect(mockSearch).toHaveBeenCalledWith('Kolchak', 'tv', 'tmdb', 1974);
		});

		it.each([
			[' 1999 ', 1999],
			['99', null],
			['19999', null],
			['abc', null],
			['', null]
		])('year input %j is sent as %j', async (input, sent) => {
			mockSearch.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await typeInto(yearBox(), input);
			await search();
			expect(mockSearch).toHaveBeenCalledWith('Q', 'movie', 'omdb', sent);
		});

		it('shows the no-results line', async () => {
			mockSearch.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await search();
			expect(await screen.findByText('No results found. Try a different search term.')).toBeInTheDocument();
		});

		it('shows the message of an Error', async () => {
			mockSearch.mockRejectedValue(new Error('Backend said no'));
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await search();
			expect(await screen.findByText('Backend said no')).toBeInTheDocument();
		});

		it('shows "Search failed" for a non-Error rejection', async () => {
			mockSearch.mockRejectedValue('nope');
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await search();
			expect(await screen.findByText('Search failed')).toBeInTheDocument();
		});

		it('an api key error shows the warning with the message and a Settings link', async () => {
			mockSearch.mockRejectedValue(new Error('TMDB API Key missing'));
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await search();
			const message = await screen.findByText('TMDB API Key missing');
			expect(message.closest('.alert-warning')).not.toBeNull();
			expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/settings');
		});

		it('any other error shows the plain help line with no Settings link', async () => {
			mockSearch.mockRejectedValue(new Error('Timed out'));
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await search();
			const message = await screen.findByText('Timed out');
			expect(message).toHaveClass('field-help');
			expect(message.closest('.alert-warning')).toBeNull();
			expect(screen.queryByRole('link', { name: 'Settings' })).toBeNull();
		});

		it('a new search closes the open results before the answer lands', async () => {
			mockSearch.mockResolvedValueOnce({ candidates: [cand({ title: 'Old' })] });
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await search();
			await screen.findByRole('heading', { name: 'Old' });
			mockSearch.mockReturnValueOnce(new Promise(() => {}));
			await search();
			expect(screen.queryByRole('heading', { name: 'Old' })).toBeNull();
			expect(screen.queryByText('1 RESULT')).toBeNull();
		});

		it('a new search clears the previous error line before the answer lands', async () => {
			mockSearch.mockRejectedValueOnce(new Error('Old failure'));
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await search();
			await screen.findByText('Old failure');
			mockSearch.mockReturnValueOnce(new Promise(() => {}));
			await search();
			expect(screen.queryByText('Old failure')).toBeNull();
		});

		it('a new IMDb lookup closes the results and clears the error before the answer lands', async () => {
			mockSearch.mockResolvedValueOnce({ candidates: [cand({ title: 'Old' })] });
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await search();
			await screen.findByRole('heading', { name: 'Old' });
			await typeInto(imdbBox(), 'tt9');
			mockFetchDetail.mockReturnValueOnce(new Promise(() => {}));
			await search();
			expect(screen.queryByRole('heading', { name: 'Old' })).toBeNull();
		});

		it('a text search that fails after a later one answered keeps the later results', async () => {
			let failFirst!: (e: Error) => void;
			mockSearch.mockReturnValueOnce(new Promise((_, reject) => (failFirst = reject)));
			mockSearch.mockResolvedValueOnce({ candidates: [cand({ title: 'Later' })] });
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await fireEvent.keyDown(titleBox(), { key: 'Enter' });
			await fireEvent.keyDown(titleBox(), { key: 'Enter' });
			await screen.findByRole('heading', { name: 'Later' });
			failFirst(new Error('First failed'));
			expect(await screen.findByText('First failed')).toBeInTheDocument();
			await new Promise((r) => setTimeout(r, 20));
			expect(screen.getByRole('heading', { name: 'Later' })).toBeInTheDocument();
		});

		it('an IMDb lookup that fails after a later one answered keeps the later results', async () => {
			let failFirst!: (e: Error) => void;
			mockFetchDetail.mockReturnValueOnce(new Promise((_, reject) => (failFirst = reject)));
			mockFetchDetail.mockResolvedValueOnce({ candidates: [cand({ title: 'Later' })] });
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await typeInto(imdbBox(), 'tt1');
			await fireEvent.keyDown(imdbBox(), { key: 'Enter' });
			await fireEvent.keyDown(imdbBox(), { key: 'Enter' });
			await screen.findByRole('heading', { name: 'Later' });
			failFirst(new Error('First failed'));
			expect(await screen.findByText('First failed')).toBeInTheDocument();
			await new Promise((r) => setTimeout(r, 20));
			expect(screen.getByRole('heading', { name: 'Later' })).toBeInTheDocument();
		});
	});

	describe('search controls', () => {
		it.each([
			['title', titleBox],
			['year', yearBox]
		])('Enter in the %s input searches', async (_n, box) => {
			mockSearch.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await fireEvent.keyDown(box(), { key: 'Enter' });
			expect(mockSearch).toHaveBeenCalledTimes(1);
		});

		it('Enter in the IMDb input looks the id up', async () => {
			mockFetchDetail.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await typeInto(imdbBox(), 'tt5');
			await fireEvent.keyDown(imdbBox(), { key: 'Enter' });
			expect(mockFetchDetail).toHaveBeenCalledWith('tt5');
		});

		it('another key does not search', async () => {
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await fireEvent.keyDown(titleBox(), { key: 'a' });
			await fireEvent.keyDown(yearBox(), { key: 'Tab' });
			await fireEvent.keyDown(imdbBox(), { key: ' ' });
			expect(mockSearch).not.toHaveBeenCalled();
			expect(mockFetchDetail).not.toHaveBeenCalled();
		});

		it('Enter with a blank query and a blank IMDb id sends nothing', async () => {
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await typeInto(titleBox(), '   ');
			await typeInto(imdbBox(), '  ');
			await fireEvent.keyDown(titleBox(), { key: 'Enter' });
			expect(mockSearch).not.toHaveBeenCalled();
			expect(mockFetchDetail).not.toHaveBeenCalled();
			expect(screen.queryByText('Searching...')).toBeNull();
		});

		it('Search is disabled while both are blank or whitespace', async () => {
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			expect(searchButton()).toBeEnabled();
			await typeInto(titleBox(), '   ');
			expect(searchButton()).toBeDisabled();
			await typeInto(imdbBox(), '  ');
			expect(searchButton()).toBeDisabled();
			await typeInto(imdbBox(), 'tt1');
			expect(searchButton()).toBeEnabled();
		});

		it('shows "Searching..." and is disabled while a search is pending', async () => {
			mockSearch.mockReturnValue(new Promise(() => {}));
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			await search();
			const pending = screen.getByRole('button', { name: 'Searching...' });
			expect(pending).toBeDisabled();
		});

		it('focusing the title input selects its text', async () => {
			renderComponent(TitleSearch, { props: { job: resolvable() } });
			const select = vi.spyOn(titleBox() as HTMLInputElement, 'select');
			await fireEvent.focus(titleBox());
			expect(select).toHaveBeenCalledTimes(1);
		});
	});

	describe('edit before using', () => {
		it('opening fills the fields from the current row, and a second click closes it', async () => {
			await openResults([cand({ title: 'Show', year: 1999, kind: 'tv', poster_url: 'https://p/1.jpg' })]);
			const toggle = screen.getByRole('button', { name: 'Edit before using' });
			expect(toggle).toHaveAttribute('aria-expanded', 'false');
			await fireEvent.click(toggle);
			expect(toggle).toHaveAttribute('aria-expanded', 'true');
			expect(editTitleInput()).toHaveValue('Show');
			expect(screen.getByLabelText('Year')).toHaveValue('1999');
			expect(screen.getByLabelText('Type')).toHaveValue('series');
			expect(screen.getByLabelText('Poster URL')).toHaveValue('https://p/1.jpg');
			await fireEvent.click(toggle);
			expect(toggle).toHaveAttribute('aria-expanded', 'false');
			expect(screen.queryByLabelText('Poster URL')).toBeNull();
		});

		it('fills a blank year, Series for kind series, and a blank poster from a bare row', async () => {
			await openResults([cand({ title: 'Bare', year: null, kind: 'series', poster_url: null })]);
			await openEdit();
			expect(screen.getByLabelText('Year')).toHaveValue('');
			expect(screen.getByLabelText('Type')).toHaveValue('series');
			expect(screen.getByLabelText('Poster URL')).toHaveValue('');
		});

		it('fills Movie for a movie kind', async () => {
			await openResults([cand({ title: 'Film', kind: 'movie' })]);
			await openEdit();
			expect(screen.getByLabelText('Type')).toHaveValue('movie');
		});

		it('reopening refills from the row, dropping earlier edits', async () => {
			await openResults([cand({ title: 'Film', year: 2001 })]);
			await openEdit();
			await typeInto(editTitleInput(), 'Changed');
			await typeInto(screen.getByLabelText('Year'), '1850');
			await openEdit();
			await openEdit();
			expect(editTitleInput()).toHaveValue('Film');
			expect(screen.getByLabelText('Year')).toHaveValue('2001');
		});

		it('re-picking the same row keeps it open', async () => {
			await openResults([cand({ title: 'One' }), cand({ title: 'Two', provider_id: 'tt2' })]);
			await openEdit();
			await typeInto(editTitleInput(), 'Typed');
			await fireEvent.click(screen.getByRole('button', { name: /^One/ }));
			await flush();
			expect(editTitleInput()).toHaveValue('Typed');
		});

		it('picking another row closes it', async () => {
			await openResults([cand({ title: 'One' }), cand({ title: 'Two', provider_id: 'tt2' })]);
			await openEdit();
			await fireEvent.click(screen.getByRole('button', { name: /^Two/ }));
			await flush();
			expect(screen.queryByLabelText('Poster URL')).toBeNull();
		});

		it('is hidden for a guest', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
			auth.__setRole('guest');
			try {
				await openResults([cand({ title: 'One' })]);
				expect(screen.queryByRole('button', { name: 'Edit before using' })).toBeNull();
			} finally {
				auth.__setRole('admin');
			}
		});
	});

	describe('apply', () => {
		it('uses the row title, year and kind when not editing', async () => {
			await openResults([cand({ title: 'Row Show', year: 2001, kind: 'series', poster_url: 'https://p/r.jpg' })]);
			await clickUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve).toHaveBeenCalledWith('job_1', { title: 'Row Show', year: 2001, media_type: 'tv' });
			expect(mockUpdateTitle).toHaveBeenCalledWith('job_1', { poster_url_manual: 'https://p/r.jpg' });
		});

		it('uses a row with no year as a null year and no poster as no poster save', async () => {
			await openResults([cand({ title: 'Plain', year: null, kind: 'movie', poster_url: null })]);
			await clickUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve).toHaveBeenCalledWith('job_1', { title: 'Plain', year: null, media_type: 'movie' });
			expect(mockUpdateTitle).not.toHaveBeenCalled();
		});

		it('uses the trimmed edit fields when editing', async () => {
			await openResults([cand({ title: 'Row', year: 2001, poster_url: 'https://p/r.jpg' })]);
			await openEdit();
			await typeInto(editTitleInput(), '  Edited  ');
			await typeInto(screen.getByLabelText('Year'), ' 1999 ');
			await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'series' } });
			await typeInto(screen.getByLabelText('Poster URL'), '  https://p/typed.jpg  ');
			await clickUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve).toHaveBeenCalledWith('job_1', { title: 'Edited', year: 1999, media_type: 'tv' });
			expect(mockUpdateTitle).toHaveBeenCalledWith('job_1', { poster_url_manual: 'https://p/typed.jpg' });
		});

		it.each([
			['', null],
			['   ', null],
			['abc', null],
			['1999', 1999]
		])('an edited year %j is sent as %j', async (input, sent) => {
			await openResults([cand({ title: 'Row', year: 2001 })]);
			await openEdit();
			await typeInto(screen.getByLabelText('Year'), input);
			await clickUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve).toHaveBeenCalledWith('job_1', { title: 'Row', year: sent, media_type: 'movie' });
		});

		it('a whitespace title shows "Title is required" and sends no request', async () => {
			await openResults([cand({ title: 'Row' })]);
			await openEdit();
			await typeInto(editTitleInput(), '   ');
			await clickUse();
			expect(await screen.findByText('Title is required')).toBeInTheDocument();
			expect(mockResolve).not.toHaveBeenCalled();
			expect(mockUpdateTitle).not.toHaveBeenCalled();
		});

		it('the match path sends every external id, the row poster and its facts', async () => {
			const facts = { genres: ['Drama'], cast: [], creators: [] };
			await openResults([
				cand({
					title: 'Show',
					year: 1974,
					kind: 'tv',
					provider: 'tmdb',
					poster_url: 'https://p/s.jpg',
					external_ids: { imdb: 'tt1', tmdb: '2', tmdb_kind: 'tv', tvdb: '3', tvmaze: '4' },
					facts
				})
			]);
			await clickUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve).toHaveBeenCalledWith('job_1', {
				title: 'Show',
				year: 1974,
				media_type: 'tv',
				external_ids: { imdb: 'tt1', tmdb: '2', tmdb_kind: 'tv', tvdb: '3', tvmaze: '4' },
				match: {
					provider: 'tmdb',
					poster_url: 'https://p/s.jpg',
					poster_is_manual: false,
					poster_url_manual: null,
					facts
				}
			});
			expect(mockUpdateTitle).not.toHaveBeenCalled();
		});

		it('the match path sends null for missing ids, facts and poster when external_ids is absent', async () => {
			await openResults([cand({ title: 'Film', year: 2001, kind: 'movie', provider: 'omdb', poster_url: null })]);
			await clickUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve).toHaveBeenCalledWith('job_1', {
				title: 'Film',
				year: 2001,
				media_type: 'movie',
				external_ids: { imdb: null, tmdb: null, tmdb_kind: null, tvdb: null, tvmaze: null },
				match: { provider: 'omdb', poster_url: null, poster_is_manual: false, poster_url_manual: null, facts: null }
			});
		});

		it('the match path marks a typed poster manual, keeping the row poster as the automatic one', async () => {
			await openResults([cand({ title: 'Film', provider: 'omdb', poster_url: 'https://p/auto.jpg' })]);
			await openEdit();
			await typeInto(screen.getByLabelText('Poster URL'), ' https://p/mine.jpg ');
			await clickUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1].match).toEqual({
				provider: 'omdb',
				poster_url: 'https://p/auto.jpg',
				poster_is_manual: true,
				poster_url_manual: 'https://p/mine.jpg',
				facts: null
			});
		});

		it('the match path sends a manual flag only once the poster was typed', async () => {
			await openResults([cand({ title: 'Film', provider: 'omdb', poster_url: 'https://p/auto.jpg' })]);
			await openEdit();
			await typeInto(editTitleInput(), 'Film 2');
			await clickUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1].match).toMatchObject({
				poster_is_manual: false,
				poster_url_manual: null
			});
			expect(mockResolve.mock.calls[0][1].title).toBe('Film 2');
		});

		it('a changed type takes the plain resolve path and saves the poster', async () => {
			await openResults([cand({ title: 'Show', kind: 'tv', provider: 'tmdb', poster_url: 'https://p/s.jpg' })]);
			await openEdit();
			await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'movie' } });
			await clickUse();
			await waitFor(() => expect(mockUpdateTitle).toHaveBeenCalled());
			expect(mockResolve).toHaveBeenCalledWith('job_1', { title: 'Show', year: 2024, media_type: 'movie' });
			expect(mockUpdateTitle).toHaveBeenCalledWith('job_1', { poster_url_manual: 'https://p/s.jpg' });
		});

		it('the plain path saves the poster only when it differs from the manual one', async () => {
			const job = resolvable({ poster_url_manual: 'https://p/same.jpg' });
			await openResults([cand({ title: 'Film', poster_url: 'https://p/same.jpg' })], job);
			await clickUse();
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockUpdateTitle).not.toHaveBeenCalled();
		});

		it('the plain path counts a missing manual poster as null and clears a different one', async () => {
			const job = resolvable({ poster_url_manual: 'https://p/old.jpg' });
			await openResults([cand({ title: 'Film', poster_url: null })], job);
			await clickUse();
			await waitFor(() => expect(mockUpdateTitle).toHaveBeenCalled());
			expect(mockUpdateTitle).toHaveBeenCalledWith('job_1', { poster_url_manual: null });
		});

		it('a failed poster save reports "Identified; poster not saved"', async () => {
			mockUpdateTitle.mockRejectedValue(new Error('nope'));
			await openResults([cand({ title: 'Film', poster_url: 'https://p/f.jpg' })]);
			await clickUse();
			expect(await screen.findByText('Identified; poster not saved')).toBeInTheDocument();
		});

		it('a job that cannot resolve saves the poster only and reports "Poster updated"', async () => {
			const job = createJob({ id: 'job_1', status: 'ripping', title: 'Q', year: null });
			await openResults([cand({ title: 'Film', poster_url: 'https://p/f.jpg' })], job);
			await fireEvent.click(screen.getByRole('button', { name: 'Use poster' }));
			expect(await screen.findByText('Poster updated')).toBeInTheDocument();
			expect(mockUpdateTitle).toHaveBeenCalledWith('job_1', { poster_url_manual: 'https://p/f.jpg' });
			expect(mockResolve).not.toHaveBeenCalled();
		});

		it('a movie on a resolvable job calls onresolved and onapply, not onseries', async () => {
			const props = { onapply: vi.fn(), onresolved: vi.fn(), onseries: vi.fn() };
			await openResults([cand({ title: 'Film', provider: 'omdb' })], resolvable(), props);
			await clickUse();
			await waitFor(() => expect(props.onapply).toHaveBeenCalledTimes(1));
			expect(props.onresolved).toHaveBeenCalledWith(RESOLVED);
			expect(props.onseries).not.toHaveBeenCalled();
		});

		it('a series on a resolvable job calls onresolved and onseries, not onapply', async () => {
			const props = { onapply: vi.fn(), onresolved: vi.fn(), onseries: vi.fn() };
			await openResults([cand({ title: 'Show', kind: 'tv', provider: 'tmdb' })], resolvable(), props);
			await clickUse();
			await waitFor(() => expect(props.onseries).toHaveBeenCalledTimes(1));
			expect(props.onresolved).toHaveBeenCalledWith(RESOLVED);
			expect(props.onapply).not.toHaveBeenCalled();
		});

		it('a series on a job that cannot resolve calls onapply only', async () => {
			const props = { onapply: vi.fn(), onresolved: vi.fn(), onseries: vi.fn() };
			const job = createJob({ id: 'job_1', status: 'ripping', title: 'Q', year: null });
			await openResults([cand({ title: 'Show', kind: 'tv' })], job, props);
			await fireEvent.click(screen.getByRole('button', { name: 'Use poster' }));
			await waitFor(() => expect(props.onapply).toHaveBeenCalledTimes(1));
			expect(props.onresolved).not.toHaveBeenCalled();
			expect(props.onseries).not.toHaveBeenCalled();
		});

		it('succeeds with no callbacks passed', async () => {
			await openResults([cand({ title: 'Show', kind: 'tv', provider: 'tmdb' })]);
			await clickUse();
			expect(await screen.findByText('Identified')).toBeInTheDocument();
			cleanup();
			await openResults([cand({ title: 'Film' })]);
			await clickUse();
			expect(await screen.findByText('Identified')).toBeInTheDocument();
		});

		it('a failure shows the message of an Error and calls no callback', async () => {
			const props = { onapply: vi.fn(), onresolved: vi.fn(), onseries: vi.fn() };
			mockResolve.mockRejectedValue(new Error('Conflict'));
			await openResults([cand({ title: 'Film', provider: 'omdb' })], resolvable(), props);
			await clickUse();
			expect(await screen.findByText('Conflict')).toBeInTheDocument();
			expect(props.onapply).not.toHaveBeenCalled();
			expect(props.onresolved).not.toHaveBeenCalled();
			expect(props.onseries).not.toHaveBeenCalled();
		});

		it('a failure shows "Apply failed" for a non-Error', async () => {
			mockResolve.mockRejectedValue('nope');
			await openResults([cand({ title: 'Film' })]);
			await clickUse();
			expect(await screen.findByText('Apply failed')).toBeInTheDocument();
		});

		it('the picker shows Applying... and disables Use while the apply is pending', async () => {
			let finish!: (v: ResolveResponse) => void;
			mockResolve.mockReturnValue(new Promise((r) => (finish = r)));
			await openResults([cand({ title: 'Film' })]);
			await clickUse();
			expect(screen.getByRole('button', { name: 'Applying...' })).toBeDisabled();
			finish(RESOLVED);
			expect(await screen.findByRole('button', { name: 'Use this match' })).toBeEnabled();
		});

		it('the feedback line is hidden by a new search', async () => {
			await openResults([cand({ title: 'Film' })]);
			await clickUse();
			expect(await screen.findByText('Identified')).toBeInTheDocument();
			await search();
			await screen.findByRole('heading', { name: 'Film' });
			expect(screen.queryByText('Identified')).toBeNull();
		});
	});
});
