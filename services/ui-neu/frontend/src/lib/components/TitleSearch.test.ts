import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import TitleSearch from './TitleSearch.svelte';
import { createJob } from './__fixtures__/job';
import type { MetadataCandidate } from '$lib/types/api.gen';

vi.mock('$lib/api/jobs', () => ({
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	updateJobTitle: vi.fn(() => Promise.resolve()),
	resolveJob: vi.fn(() => Promise.resolve({ job: {}, fan_out: [] }))
}));

import { searchMetadata, fetchMediaDetail, updateJobTitle, resolveJob } from '$lib/api/jobs';
const mockSearchMetadata = vi.mocked(searchMetadata);
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
				expect(mockSearchMetadata).toHaveBeenCalledWith('Test');
				expect(screen.getByText('Result 1')).toBeInTheDocument();
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
				expect(screen.getByDisplayValue('Direct Movie')).toBeInTheDocument();
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
				expect(screen.getByText('Movie A')).toBeInTheDocument();
				expect(screen.getByText('Movie B')).toBeInTheDocument();
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
			await waitFor(() => expect(screen.getByText('Movie A')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Movie A'));
			await fireEvent.click(screen.getByText('Apply Poster'));
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
			await waitFor(() => expect(screen.getByText('The Matrix')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('The Matrix'));
			await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
			await waitFor(() => {
				expect(mockResolve).toHaveBeenCalledWith('job_7', {
					title: 'The Matrix',
					year: 1999,
					metadata: { video_type: 'movie' }
				});
				expect(mockUpdateTitle).toHaveBeenCalledWith('job_7', { poster_url_manual: 'https://img/m.jpg' });
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
			await waitFor(() => expect(screen.getByText('The Matrix')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('The Matrix'));
			await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
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
					job: createJob({ id: 'job_7', status: 'identified', title: 'matrix', poster_url_manual: 'https://same/p.jpg' })
				}
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => expect(screen.getByText('The Matrix')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('The Matrix'));
			await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
			await waitFor(() => expect(mockResolve).toHaveBeenCalled());
			expect(mockUpdateTitle).not.toHaveBeenCalled();
		});

		it('non-resolvable job: Apply is poster-only (button reads "Apply Poster", no resolve)', async () => {
			mockSearchMetadata.mockResolvedValue({
				candidates: [createCandidate({ title: 'The Matrix', year: 1999, poster_url: 'https://img/m.jpg' })]
			});
			// createJob default status is 'ripping' (non-resolvable)
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_7', title: 'matrix' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => expect(screen.getByText('The Matrix')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('The Matrix'));
			await fireEvent.click(screen.getByRole('button', { name: 'Apply Poster' }));
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
			await waitFor(() => expect(screen.getByText('X')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('X'));
			const titleInput = screen.getByDisplayValue('X');
			await fireEvent.input(titleInput, { target: { value: '   ' } });
			await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
			await waitFor(() => expect(screen.getByText('Title is required')).toBeInTheDocument());
			expect(mockResolve).not.toHaveBeenCalled();
		});

		it('manual entry: "Set manually" synthesizes a candidate and applies via resolve', async () => {
			mockSearchMetadata.mockResolvedValue({ candidates: [] });
			// year: null so the synthesized candidate has no year (the prefilled year
			// input mirrors job.year, which createJob defaults to 2024 unless overridden).
			renderComponent(TitleSearch, {
				props: { job: createJob({ id: 'job_7', status: 'awaiting_user_id', title: 'Obscure Film', year: null }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => expect(screen.getByText('Set manually')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Set manually'));
			await waitFor(() => expect(screen.getByDisplayValue('Obscure Film')).toBeInTheDocument());
			await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
			await waitFor(() => {
				expect(mockResolve).toHaveBeenCalledWith('job_7', {
					title: 'Obscure Film',
					year: null,
					metadata: { video_type: 'movie' }
				});
			});
		});
	});
});
