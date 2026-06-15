import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import MusicSearch from './MusicSearch.svelte';
import { createJob } from './__fixtures__/job';
import type { MetadataCandidate } from '$lib/types/api.gen';

vi.mock('$lib/api/jobs', () => ({
	searchMusicMetadata: vi.fn(),
	fetchMusicDetail: vi.fn(),
	updateJobTitle: vi.fn(() => Promise.resolve())
}));

import { searchMusicMetadata, fetchMusicDetail, updateJobTitle } from '$lib/api/jobs';
const mockSearchMusicMetadata = vi.mocked(searchMusicMetadata);
const mockFetchMusicDetail = vi.mocked(fetchMusicDetail);
const mockUpdateJobTitle = vi.mocked(updateJobTitle);

function createMusicCandidate(overrides: Partial<MetadataCandidate> = {}): MetadataCandidate {
	return {
		title: 'Album',
		year: 2024,
		kind: 'release',
		poster_url: null,
		provider_id: 'r1',
		...overrides
	};
}

describe('MusicSearch', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('rendering', () => {
		it('renders search form with pre-filled title', () => {
			renderComponent(MusicSearch, {
				props: { job: createJob({ title: 'My Album' }) }
			});
			expect(screen.getByDisplayValue('My Album')).toBeInTheDocument();
		});

		it('renders search button', () => {
			renderComponent(MusicSearch, {
				props: { job: createJob() }
			});
			expect(screen.getByText('Search')).toBeInTheDocument();
		});
	});

	describe('interactions', () => {
		it('calls searchMusicMetadata with query only', async () => {
			mockSearchMusicMetadata.mockResolvedValue({
				candidates: [createMusicCandidate({ title: 'Found Album' })]
			});
			renderComponent(MusicSearch, {
				props: { job: createJob({ title: 'Search Term' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(mockSearchMusicMetadata).toHaveBeenCalledWith('Search Term');
				expect(screen.getByText('Found Album')).toBeInTheDocument();
			});
		});

		it('shows no results message', async () => {
			mockSearchMusicMetadata.mockResolvedValue({ candidates: [] });
			renderComponent(MusicSearch, {
				props: { job: createJob({ title: 'Nothing' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(screen.getByText(/No results found/)).toBeInTheDocument();
			});
		});

		it('shows error on search failure', async () => {
			mockSearchMusicMetadata.mockRejectedValue(new Error('MusicBrainz error'));
			renderComponent(MusicSearch, {
				props: { job: createJob({ title: 'Test' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(screen.getByText('MusicBrainz error')).toBeInTheDocument();
			});
		});

		it('renders result cards with year', async () => {
			mockSearchMusicMetadata.mockResolvedValue({
				candidates: [
					createMusicCandidate({ provider_id: 'r1', title: 'Album One' }),
					createMusicCandidate({ provider_id: 'r2', title: 'Album Two', year: 2023 })
				]
			});
			renderComponent(MusicSearch, {
				props: { job: createJob({ title: 'Test' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => {
				expect(screen.getByText('Album One')).toBeInTheDocument();
				expect(screen.getByText('Album Two')).toBeInTheDocument();
			});
		});

		it('loads release detail and applies cover art via updateJobTitle', async () => {
			mockSearchMusicMetadata.mockResolvedValue({
				candidates: [createMusicCandidate({ provider_id: 'r9', title: 'Album One', poster_url: 'https://img/a.jpg' })]
			});
			mockFetchMusicDetail.mockResolvedValue({
				release_id: 'r9',
				title: 'Album One',
				artist: 'Band A',
				year: 2024,
				poster_url: 'https://img/a.jpg',
				tracks: [{ position: 1, title: 'Song 1' }]
			});
			renderComponent(MusicSearch, {
				props: { job: createJob({ id: 'job_77', title: 'Test' }) }
			});
			await fireEvent.click(screen.getByText('Search'));
			await waitFor(() => expect(screen.getByText('Album One')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Album One'));
			await waitFor(() => {
				expect(mockFetchMusicDetail).toHaveBeenCalledWith('r9');
				expect(screen.getByText('Song 1')).toBeInTheDocument();
			});
			await fireEvent.click(screen.getByText('Apply Cover Art'));
			await waitFor(() => {
				expect(mockUpdateJobTitle).toHaveBeenCalledWith('job_77', { poster_url_manual: 'https://img/a.jpg' });
			});
		});
	});
});
