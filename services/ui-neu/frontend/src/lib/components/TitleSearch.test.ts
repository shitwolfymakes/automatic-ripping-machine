import { describe, it, expect, vi, afterEach } from 'vitest';
import { tick } from 'svelte';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TitleSearch from './TitleSearch.svelte';
import { createJob } from './__fixtures__/job';
import type { MetadataCandidate, ResolveResponse } from '$lib/types/api.gen';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

vi.mock('$lib/stores/config', async () => {
	const { writable } = await import('svelte/store');
	const keyed = writable({ tmdb: true, omdb: true, tvdb: true });
	return {
		searchProviders: writable({ movie: 'omdb', tv: 'tmdb' }),
		keyedSources: { subscribe: keyed.subscribe },
		// Test-only helper - not part of the real module's public API.
		__setKeyed: (v: { tmdb: boolean; omdb: boolean; tvdb: boolean }) => keyed.set(v)
	};
});

vi.mock('$lib/api/jobs', () => ({
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	fetchMatchDetails: vi.fn(() => Promise.resolve({ candidates: [] })),
	updateJobTitle: vi.fn(() => Promise.resolve()),
	resolveJob: vi.fn(() => Promise.resolve({ job: {}, fan_out: [] }))
}));

import { searchMetadata, fetchMatchDetails, fetchMediaDetail, updateJobTitle, resolveJob } from '$lib/api/jobs';
import * as configStore from '$lib/stores/config';
const setKeyed = (configStore as unknown as { __setKeyed: (v: Record<string, boolean>) => void }).__setKeyed;
const mockSearchMetadata = vi.mocked(searchMetadata);
const mockMatchDetails = vi.mocked(fetchMatchDetails);
const mockFetchDetail = vi.mocked(fetchMediaDetail);
const mockUpdateTitle = vi.mocked(updateJobTitle);
const mockResolve = vi.mocked(resolveJob);

function createCandidate(overrides: Partial<MetadataCandidate> = {}): MetadataCandidate {
	return {
		title: 'Result',
		year: 2024,
		kind: 'movie',
		poster_url: null,
		provider_id: 'tt1111',
		...overrides
	};
}

describe('TitleSearch', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('source picker', () => {
		afterEach(() => setKeyed({ tmdb: true, omdb: true, tvdb: true }));

		const sourceSelect = () => screen.getByRole('combobox', { name: 'Search with' }) as HTMLSelectElement;
		const option = (id: string) => sourceSelect().querySelector(`option[value="${id}"]`) as HTMLOptionElement;
		const sourceNames = () => Array.from(sourceSelect().options).map((o) => o.textContent?.trim());
		const checkedSource = () => sourceSelect().selectedOptions[0]?.textContent?.trim();
		const pick = (id: string) => fireEvent.change(sourceSelect(), { target: { value: id } });

		it('lists TMDb and OMDb for movies, and all four for TV, in order', () => {
			renderComponent(TitleSearch, { props: { job: createJob({ media_type: 'movie' }) } });
			expect(sourceNames()).toEqual(['TMDb', 'OMDb']);
			cleanup();
			renderComponent(TitleSearch, { props: { job: createJob({ media_type: 'tv' }) } });
			expect(sourceNames()).toEqual(['TMDb', 'OMDb', 'TVmaze', 'TVDB']);
		});

		it('has no Movie/TV toggle: the type comes from the job', () => {
			renderComponent(TitleSearch, { props: { job: createJob({ media_type: 'movie' }) } });
			expect(screen.queryByRole('radiogroup', { name: 'Search type' })).toBeNull();
			expect(screen.queryByRole('radio', { name: 'TV' })).toBeNull();
		});

		it('defaults to the Settings choice per type, and a job type change resets it', async () => {
			const { rerender } = renderComponent(TitleSearch, { props: { job: createJob({ media_type: 'movie' }) } });
			expect(checkedSource()).toBe('OMDb');
			await pick('tmdb');
			expect(checkedSource()).toBe('TMDb');
			await rerender({ job: createJob({ media_type: 'tv' }) });
			expect(checkedSource()).toBe('TMDb');
			await pick('tvmaze');
			await rerender({ job: createJob({ media_type: 'movie' }) });
			expect(checkedSource()).toBe('OMDb');
		});

		it('disables a source whose key is not saved, and never TVmaze', () => {
			setKeyed({ tmdb: false, omdb: true, tvdb: false });
			renderComponent(TitleSearch, { props: { job: createJob({ media_type: 'tv' }) } });
			expect(option('tmdb')).toBeDisabled();
			expect(option('tmdb').textContent).toBe('TMDb (needs API key)');
			expect(option('tvdb')).toBeDisabled();
			expect(option('tvdb').textContent).toBe('TVDB (needs API key)');
			expect(option('tvmaze')).not.toBeDisabled();
			expect(option('omdb')).not.toBeDisabled();
		});

		it('searches the chosen source: TVmaze with no TMDb key never sends tmdb', async () => {
			setKeyed({ tmdb: false, omdb: false, tvdb: false });
			mockSearchMetadata.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: createJob({ title: 'Kolchak', media_type: 'tv' }) } });
			await pick('tvmaze');
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await waitFor(() => expect(mockSearchMetadata).toHaveBeenCalledWith('Kolchak', 'tv', 'tvmaze', 2024));
			expect(mockSearchMetadata.mock.calls.every((c) => c[2] !== 'tmdb')).toBe(true);
		});

		it('starts on the first usable source when the TV default has no key', async () => {
			setKeyed({ tmdb: false, omdb: false, tvdb: true });
			mockSearchMetadata.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, { props: { job: createJob({ title: 'Kolchak', media_type: 'tv' }) } });
			expect(checkedSource()).toBe('TVmaze');
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await waitFor(() => expect(mockSearchMetadata).toHaveBeenCalledWith('Kolchak', 'tv', 'tvmaze', 2024));
		});

		it('starts on TMDb when the movie default OMDb has no key', () => {
			setKeyed({ tmdb: true, omdb: false, tvdb: false });
			renderComponent(TitleSearch, { props: { job: createJob({ media_type: 'movie' }) } });
			expect(checkedSource()).toBe('TMDb');
		});

		it('keeps the unkeyed default when no movie source is usable', () => {
			setKeyed({ tmdb: false, omdb: false, tvdb: false });
			renderComponent(TitleSearch, { props: { job: createJob({ media_type: 'movie' }) } });
			expect(sourceSelect().value).toBe('omdb');
		});

		it('replaces the provider badge', () => {
			renderComponent(TitleSearch, { props: { job: createJob({ media_type: 'movie' }) } });
			expect(screen.queryByTitle(/search provider configured/i)).toBeNull();
		});
	});

	describe('rendering', () => {
		it('renders search form with pre-filled title', () => {
			renderComponent(TitleSearch, {
				props: { job: createJob({ title: 'My Movie' }) }
			});
			expect(screen.getByDisplayValue('My Movie')).toBeInTheDocument();
		});

		it('renders search button', () => {
			renderComponent(TitleSearch, {
				props: { job: createJob() }
			});
			expect(screen.getByText('Search')).toBeInTheDocument();
		});

		it('renders year input pre-filled', () => {
			renderComponent(TitleSearch, {
				props: { job: createJob({ year: 2024 }) }
			});
			expect(screen.getByDisplayValue('2024')).toBeInTheDocument();
		});
	});

	describe('interactions', () => {
		it('calls searchMetadata on search', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [createCandidate({ title: 'Result 1' })] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ title: 'Test', year: 2024 }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(mockSearchMetadata).toHaveBeenCalledWith('Test', 'movie', 'omdb', 2024);
				expect(screen.getByRole('heading', { name: 'Result 1' })).toBeInTheDocument();
			});
		});

		it('shows no results message', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ title: 'Nonexistent' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(screen.getByText('No results found. Try a different search term.')).toBeInTheDocument();
			});
		});

		it('shows error on search failure', async () => {
			mockSearchMetadata.mockRejectedValue(new Error('API error'));
			renderComponent(TitleSearch, {
				props: { job: createJob({ title: 'Test' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(screen.getByText('API error')).toBeInTheDocument();
			});
		});

		it('renders IMDb ID input field', () => {
			renderComponent(TitleSearch, {
				props: { job: createJob() }
			});
			expect(screen.getByPlaceholderText('IMDb ID (tt...)')).toBeInTheDocument();
		});

		it('does direct IMDb lookup when IMDb ID is entered', async () => {
			mockFetchDetail.mockResolvedValue({
				candidates: [createCandidate({ title: 'Direct Movie', provider_id: 'tt9999' })]
			});
			renderComponent(TitleSearch, {
				props: { job: createJob({ title: 'Test' }) }
			});
			const imdbInput = screen.getByPlaceholderText('IMDb ID (tt...)');
			await fireEvent.input(imdbInput, { target: { value: 'tt9999' } });
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(mockFetchDetail).toHaveBeenCalledWith('tt9999');
				expect(screen.getByRole('heading', { name: 'Direct Movie' })).toBeInTheDocument();
			});
		});

		it('renders multiple search results', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [
					createCandidate({ title: 'Movie A' }),
					createCandidate({ title: 'Movie B', year: 2023, provider_id: 'tt2222', kind: 'series' })
				]
			});
			renderComponent(TitleSearch, {
				props: { job: createJob({ title: 'Movie', year: 2024 }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(screen.getByRole('button', { name: /^Movie A/ })).toBeInTheDocument();
				expect(screen.getByRole('button', { name: /^Movie B/ })).toBeInTheDocument();
			});
		});

		it('applies poster via updateJobTitle on selection', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'Movie A', poster_url: 'https://img/p.jpg' })]
			});
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_42', title: 'Movie', year: 2024 }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'Movie A' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use poster' }));
			await waitFor(() => {
				expect(mockUpdateTitle).toHaveBeenCalledWith('job_42', { poster_url_manual: 'https://img/p.jpg' });
			});
		});
	});

	describe('apply identifies the movie', () => {
		it('resolvable job: Apply resolves title/year + applies the poster', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'The Matrix', year: 1999, poster_url: 'https://img/m.jpg' })]
			});
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_7', status: 'awaiting_user_id', title: 'matrix' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'The Matrix' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => {
				expect(mockResolve).toHaveBeenCalledWith('job_7', {
					title: 'The Matrix',
					year: 1999,
					media_type: 'movie'
				});
				expect(mockUpdateTitle).toHaveBeenCalledWith('job_7', { poster_url_manual: 'https://img/m.jpg' });
			});
		});

		it('held review disc: Apply resolves title/year (not poster-only)', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'The Matrix', year: 1999, poster_url: 'https://img/m.jpg' })]
			});
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_9', status: 'awaiting_review', title: 'matrix' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'The Matrix' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => {
				expect(mockResolve).toHaveBeenCalledWith('job_9', { title: 'The Matrix', year: 1999, media_type: 'movie' });
			});
		});

		it('resolvable job: a poster failure still reports identify success', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'The Matrix', year: 1999, poster_url: 'https://img/m.jpg' })]
			});
			mockUpdateTitle.mockRejectedValueOnce(new Error('poster blip'));
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_7', status: 'identified', title: 'matrix' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'The Matrix' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => {
				expect(mockResolve).toHaveBeenCalled();
				expect(screen.getByText('Identified; poster not saved')).toBeInTheDocument();
			});
		});

		it('resolvable job: unchanged poster is not PATCHed', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'The Matrix', year: 1999, poster_url: 'https://same/p.jpg' })]
			});
			renderComponent(TitleSearch, {
				props: {
					job: createJob({
						id: 'job_7',
						status: 'identified',
						title: 'matrix',
						poster_url_manual: 'https://same/p.jpg'
					})
				}
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'The Matrix' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockUpdateTitle).not.toHaveBeenCalled();
		});

		it('non-resolvable job: Apply is poster-only (button reads "Use poster", no resolve)', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'The Matrix', year: 1999, poster_url: 'https://img/m.jpg' })]
			});
			// createJob default status is 'ripping' (non-resolvable)
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_7', title: 'matrix' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'The Matrix' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use poster' }));
			await waitFor(() => {
				expect(mockUpdateTitle).toHaveBeenCalledWith('job_7', { poster_url_manual: 'https://img/m.jpg' });
			});
			expect(mockResolve).not.toHaveBeenCalled();
		});

		it('empty title blocks resolve', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [createCandidate({ title: 'X' })] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_7', status: 'identified', title: 'x' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'X' });
			await fireEvent.click(screen.getByRole('button', { name: 'Edit before using' }));
			const titleInput = screen.getByDisplayValue('X');
			await fireEvent.input(titleInput, { target: { value: '   ' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(screen.getByText('Title is required')).toBeInTheDocument());
			expect(mockResolve).not.toHaveBeenCalled();
		});

		it('shows the no-results message without a "Set manually" button', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [] } as any);
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_1', status: 'awaiting_user_id', title: '', year: null }) }
			});
			await fireEvent.input(screen.getByPlaceholderText('Title...'), { target: { value: 'Nope' } });
			await fireEvent.click(screen.getByRole('button', { name: /search/i }));
			await waitFor(() => expect(screen.getByText(/No results found/i)).toBeInTheDocument());
			expect(screen.queryByText('Set manually')).not.toBeInTheDocument();
		});
	});

	describe('guest write-control gating', () => {
		afterEach(async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('admin');
		});

		it('hides the Apply button for guests', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('guest');
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'The Matrix', year: 1999 })]
			});
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_7', status: 'awaiting_user_id', title: 'matrix' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'The Matrix' });
			expect(screen.queryByRole('button', { name: 'Use this match' })).not.toBeInTheDocument();
			expect(screen.queryByRole('button', { name: 'Use poster' })).not.toBeInTheDocument();
			expect(screen.queryByRole('button', { name: 'Edit before using' })).not.toBeInTheDocument();
		});

		it('shows the Apply button for admins', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'The Matrix', year: 1999 })]
			});
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_7', status: 'awaiting_user_id', title: 'matrix' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'The Matrix' });
			expect(screen.getByRole('button', { name: 'Use this match' })).toBeInTheDocument();
		});
	});

	describe('search type follows the job', () => {
		it('searches TV for an episodic disc with no type yet', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ title: 'kolchak', media_type: null, looks_episodic: true }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			expect(mockSearchMetadata).toHaveBeenCalledWith('kolchak', 'tv', 'tmdb', 2024);
		});

		it("changing the job's type clears results and searches the new type", async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [createCandidate({ title: 'Result 1' })] });
			const { rerender } = renderComponent(TitleSearch, {
				props: { job: createJob({ title: 'x', media_type: 'movie' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'Result 1' });
			await rerender({ job: createJob({ title: 'x', media_type: 'tv' }) });
			expect(screen.queryByText('Result 1')).not.toBeInTheDocument();
			await fireEvent.click(screen.getByText('Search'));
			expect(mockSearchMetadata).toHaveBeenLastCalledWith('x', 'tv', 'tmdb', 2024);
		});

		it('applying a series sends its ids and opens episode matching', async () => {
			const ids = { tmdb: '5084', imdb: 'tt0071003', tvdb: '77170', tmdb_kind: 'tv' as const };
			mockSearchMetadata.mockResolvedValue({
				candidates: [
					createCandidate({
						title: 'Kolchak: The Night Stalker',
						year: 1974,
						kind: 'tv',
						provider: 'tmdb',
						external_ids: ids
					})
				]
			});
			const onseries = vi.fn();
			const onapply = vi.fn();
			renderComponent(TitleSearch, {
				props: {
					job: createJob({ id: 'job_9', status: 'ripped', title: 'kolchak', media_type: 'tv' }),
					onseries,
					onapply
				}
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'Kolchak: The Night Stalker' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() =>
				expect(mockResolve).toHaveBeenCalledWith('job_9', {
					title: 'Kolchak: The Night Stalker',
					year: 1974,
					media_type: 'tv',
					external_ids: { ...ids, tvmaze: null },
					match: {
						provider: 'tmdb',
						poster_url: null,
						poster_is_manual: false,
						poster_url_manual: null,
						facts: null
					}
				})
			);
			expect(onseries).toHaveBeenCalled();
			expect(onapply).not.toHaveBeenCalled();
		});

		it('sends every show id with nulls included when a match is picked (null means clear)', async () => {
			const ids = { tmdb: '5084', imdb: null, tvdb: null, tmdb_kind: 'tv' as const };
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'Kolchak', year: 1974, kind: 'tv', provider: 'tmdb', external_ids: ids })]
			});
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_9', status: 'ripped', title: 'kolchak', media_type: 'tv' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'Kolchak' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1].external_ids).toEqual({
				imdb: null,
				tmdb: '5084',
				tmdb_kind: 'tv',
				tvdb: null,
				tvmaze: null
			});
		});

		it('a candidate without a provider sends no ids even when its ids are all null', async () => {
			const ids = { tmdb: null, imdb: null, tvdb: null, tmdb_kind: null };
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'Kolchak', year: 1974, kind: 'tv', external_ids: ids })]
			});
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_9', status: 'ripped', title: 'kolchak', media_type: 'tv' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'Kolchak' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1].external_ids).toBeUndefined();
		});

		it('does not send a TV candidate ids when the form type is switched to Movie', async () => {
			const ids = { tmdb: '5084', tmdb_kind: 'tv' as const };
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'Kolchak', year: 1974, kind: 'tv', provider: 'tmdb', external_ids: ids })]
			});
			const onseries = vi.fn();
			const onapply = vi.fn();
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_9', status: 'ripped', title: 'kolchak' }), onseries, onapply }
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'Kolchak' });
			await fireEvent.click(screen.getByRole('button', { name: 'Edit before using' }));
			await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'movie' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1].external_ids).toBeUndefined();
			expect(mockResolve.mock.calls[0][1].match).toBeUndefined();
			expect(mockResolve.mock.calls[0][1].media_type).toBe('movie');
			expect(onapply).toHaveBeenCalled();
			expect(onseries).not.toHaveBeenCalled();
		});

		it('a poster-only apply on a TV job does not start episode matching', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'Kolchak', year: 1974, kind: 'tv' })]
			});
			const onseries = vi.fn();
			const onapply = vi.fn();
			renderComponent(TitleSearch, {
				props: {
					job: createJob({ id: 'job_9', status: 'ripping', title: 'kolchak', media_type: 'tv' }),
					onseries,
					onapply
				}
			});
			await fireEvent.click(screen.getByText('Search'));
			await screen.findByRole('heading', { name: 'Kolchak' });
			await fireEvent.click(screen.getByRole('button', { name: 'Use poster' }));
			await waitFor(() => expect(onapply).toHaveBeenCalled());
			expect(mockResolve).not.toHaveBeenCalled();
			expect(onseries).not.toHaveBeenCalled();
		});
	});
	describe('match picker', () => {
		const tvmazeRow = createCandidate({
			title: 'Kolchak: The Night Stalker',
			year: 1974,
			kind: 'tv',
			provider: 'tvmaze',
			poster_url: 'https://static.tvmaze.com/k.jpg',
			external_ids: { imdb: 'tt0071003', tvdb: '77170', tvmaze: '1' },
			facts: { genres: ['Horror'], cast: [], creators: [] }
		});

		it('sends the year and shows results in the picker with the first selected', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ status: 'awaiting_user_id', title: 'Kolchak', year: 1974, media_type: 'tv' }) }
			});
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			expect(mockSearchMetadata).toHaveBeenCalledWith('Kolchak', 'tv', 'tmdb', 1974);
			expect(await screen.findByText('1 RESULT')).toBeInTheDocument();
			expect(screen.getByRole('heading', { name: 'Kolchak: The Night Stalker' })).toBeInTheDocument();
		});

		it('Use this match resolves with every show id and the match block', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ status: 'awaiting_user_id', title: 'Kolchak', media_type: 'tv' }) }
			});
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1]).toEqual({
				title: 'Kolchak: The Night Stalker',
				year: 1974,
				media_type: 'tv',
				external_ids: { imdb: 'tt0071003', tmdb: null, tmdb_kind: null, tvdb: '77170', tvmaze: '1' },
				match: {
					provider: 'tvmaze',
					poster_url: 'https://static.tvmaze.com/k.jpg',
					poster_is_manual: false,
					poster_url_manual: null,
					facts: { genres: ['Horror'], cast: [], creators: [] }
				}
			});
			expect(mockUpdateTitle).not.toHaveBeenCalled();
		});

		it('an edited poster is sent as manual', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ status: 'awaiting_user_id', title: 'Kolchak', media_type: 'tv' }) }
			});
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Edit before using' }));
			await fireEvent.input(screen.getByLabelText('Poster URL'), { target: { value: 'https://x.example/p.jpg' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			// The candidate's poster stays the automatic one; the edit is the override.
			expect(mockResolve.mock.calls[0][1].match).toMatchObject({
				poster_url: 'https://static.tvmaze.com/k.jpg',
				poster_is_manual: true,
				poster_url_manual: 'https://x.example/p.jpg'
			});
		});

		it('a cleared poster is sent as a cleared override', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ status: 'awaiting_user_id', title: 'Kolchak', media_type: 'tv' }) }
			});
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Edit before using' }));
			await fireEvent.input(screen.getByLabelText('Poster URL'), { target: { value: '' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1].match).toMatchObject({
				poster_url: 'https://static.tvmaze.com/k.jpg',
				poster_is_manual: true,
				poster_url_manual: null
			});
		});

		it('editing the type to the other kind sends no ids and no match', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ status: 'awaiting_user_id', title: 'Kolchak', media_type: 'tv' }) }
			});
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Edit before using' }));
			await fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'movie' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			const body = mockResolve.mock.calls[0][1];
			expect(body.media_type).toBe('movie');
			expect(body.match).toBeUndefined();
			expect(body.external_ids).toBeUndefined();
		});

		it('Close clears the results', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [tvmazeRow] });
			renderComponent(TitleSearch, {
				props: { job: createJob({ status: 'awaiting_user_id', title: 'Kolchak', media_type: 'tv' }) }
			});
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Close' }));
			expect(screen.queryByText('1 RESULT')).toBeNull();
		});
	});

	describe('details arriving after Edit is opened', () => {
		const row = createCandidate({
			title: 'Kolchak',
			year: 1974,
			kind: 'tv',
			provider: 'tvmaze',
			provider_id: '1',
			poster_url: 'https://row/p.jpg',
			external_ids: { tvmaze: '1' }
		});
		const job = () => createJob({ id: 'job_9', status: 'awaiting_user_id', title: 'Kolchak', media_type: 'tv' });
		// The search box is also labelled Title; the edit field is the one without an aria-label.
		const editTitleInput = () =>
			screen.getAllByLabelText('Title').find((el) => !el.hasAttribute('aria-label')) as HTMLElement;
		const flush = async () => {
			await tick();
			await new Promise((r) => setTimeout(r, 0));
		};

		async function openEditBeforeDetails() {
			let resolveDetails!: (v: { candidates: MetadataCandidate[] }) => void;
			mockMatchDetails.mockReturnValue(new Promise((r) => (resolveDetails = r)));
			mockSearchMetadata.mockResolvedValue({ candidates: [row] });
			renderComponent(TitleSearch, { props: { job: job() } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Edit before using' }));
			return async () => {
				resolveDetails({ candidates: [{ ...row, poster_url: 'https://detail/p.jpg' }] });
				await flush();
			};
		}

		it('an untouched poster follows the details and is not manual', async () => {
			const land = await openEditBeforeDetails();
			await fireEvent.input(editTitleInput(), { target: { value: 'Kolchak edited' } });
			await land();
			expect(editTitleInput()).toHaveValue('Kolchak edited');
			expect(screen.getByLabelText('Poster URL')).toHaveValue('https://row/p.jpg');
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			const body = mockResolve.mock.calls[0][1];
			expect(body.title).toBe('Kolchak edited');
			expect(body.match).toMatchObject({ poster_url: 'https://detail/p.jpg', poster_is_manual: false });
		});

		it('a typed poster is manual and keeps the typed value', async () => {
			const land = await openEditBeforeDetails();
			await fireEvent.input(screen.getByLabelText('Poster URL'), { target: { value: 'https://typed/p.jpg' } });
			await land();
			await fireEvent.click(screen.getByRole('button', { name: 'Use this match' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockResolve.mock.calls[0][1].match).toMatchObject({
				poster_url: 'https://detail/p.jpg',
				poster_is_manual: true,
				poster_url_manual: 'https://typed/p.jpg'
			});
		});

		it('picking another row closes Edit and reopening shows that row', async () => {
			const row2 = createCandidate({
				title: 'Second Show',
				year: 1980,
				kind: 'tv',
				provider: 'tvmaze',
				provider_id: '2'
			});
			mockMatchDetails.mockResolvedValue({ candidates: [] });
			mockSearchMetadata.mockResolvedValue({ candidates: [row, row2] });
			renderComponent(TitleSearch, { props: { job: job() } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Edit before using' }));
			expect(editTitleInput()).toHaveValue('Kolchak');
			await fireEvent.click(screen.getByRole('button', { name: /^Second Show/ }));
			await flush();
			expect(screen.getAllByLabelText('Title')).toHaveLength(1);
			await fireEvent.click(screen.getByRole('button', { name: 'Edit before using' }));
			expect(editTitleInput()).toHaveValue('Second Show');
			expect(screen.getByLabelText('Year')).toHaveValue('1980');
		});

		it('a Use that lands after picking another row reports under its own row only', async () => {
			const row2 = createCandidate({
				title: 'Second Show',
				year: 1980,
				kind: 'tv',
				provider: 'tvmaze',
				provider_id: '2'
			});
			let finish!: (v: ResolveResponse) => void;
			mockResolve.mockReturnValue(new Promise((r) => (finish = r)));
			mockMatchDetails.mockResolvedValue({ candidates: [] });
			mockSearchMetadata.mockResolvedValue({ candidates: [row, row2] });
			renderComponent(TitleSearch, { props: { job: job() } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await fireEvent.click(await screen.findByRole('button', { name: 'Use this match' }));
			await fireEvent.click(screen.getByRole('button', { name: /^Second Show/ }));
			finish({ job: job() } as unknown as ResolveResponse);
			await flush();
			expect(screen.queryByText('Identified')).not.toBeInTheDocument();
			await fireEvent.click(screen.getByRole('button', { name: /^Kolchak/ }));
			await flush();
			expect(screen.getByText('Identified')).toBeInTheDocument();
		});
	});
});
