import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import RipSettings from './RipSettings.svelte';
import { createJob } from './__fixtures__/job';

vi.mock('$lib/api/jobs', () => ({
	updateJobConfig: vi.fn(() => Promise.resolve({})),
	updateJobNaming: vi.fn(() => Promise.reject(new Error('Per-job naming overrides is not yet available in v3'))),
	fetchNamingVariables: vi.fn(() =>
		Promise.resolve({
			variables: {
				common: [
					{ token: 'title', description: 'Title' },
					{ token: 'year', description: 'Year' }
				],
				tv: [
					{ token: 'season', description: 'Season' },
					{ token: 'episode', description: 'Episode' }
				]
			}
		})
	),
	namingPreview: vi.fn(() => Promise.resolve({ rendered: 'Preview' })),
	validatePattern: vi.fn(() => Promise.resolve({ valid: true }))
}));

const defaultConfig: Record<string, string | null> = {
	RIPMETHOD: 'mkv',
	DISCTYPE: 'bluray',
	MAINFEATURE: '0',
	MINLENGTH: '120',
	MAXLENGTH: '99999',
	AUDIO_FORMAT: 'flac',
	MOVIE_TITLE_PATTERN: '{title} ({year})',
	MOVIE_FOLDER_PATTERN: '{title} ({year})',
	TV_TITLE_PATTERN: '{title} S{season}E{episode}',
	TV_FOLDER_PATTERN: '{title}/Season {season}',
	MUSIC_TITLE_PATTERN: '{artist} - {album}',
	MUSIC_FOLDER_PATTERN: '{artist}/{album} ({year})'
};

describe('RipSettings', () => {
	afterEach(() => cleanup());

	describe('rendering', () => {
		it('renders rip method selector for non-music', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig }
			});
			expect(screen.getByText('Rip Method')).toBeInTheDocument();
		});

		it('hides rip method selector for music', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, isMusic: true }
			});
			expect(screen.queryByText('Rip Method')).not.toBeInTheDocument();
		});

		it('renders disc type selector', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig }
			});
			expect(screen.getByText('Disc Type')).toBeInTheDocument();
		});

		it('shows main feature checkbox for non-music, non-multi-title', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig }
			});
			expect(screen.getByText('Main Feature Only')).toBeInTheDocument();
		});

		it('hides main feature checkbox for multi-title', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, multiTitle: true }
			});
			expect(screen.queryByText('Main Feature Only')).not.toBeInTheDocument();
		});

		it('shows min/max length for non-music', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig }
			});
			expect(screen.getByText('Min Length (s)')).toBeInTheDocument();
			expect(screen.getByText('Max Length (s)')).toBeInTheDocument();
		});

		it('hides min/max length for music', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, isMusic: true }
			});
			expect(screen.queryByText('Min Length (s)')).not.toBeInTheDocument();
		});

		it('shows audio format selector for music', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, isMusic: true }
			});
			expect(screen.getByText('Audio Format')).toBeInTheDocument();
		});

		it('shows save button', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig }
			});
			expect(screen.getByText('Save Settings')).toBeInTheDocument();
		});
	});

	describe('naming patterns', () => {
		it('shows movie naming for movie media type', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, mediaType: 'movie' }
			});
			expect(screen.getByText('Movie Naming')).toBeInTheDocument();
			const matches = screen.getAllByText('{title} ({year})');
			expect(matches.length).toBeGreaterThanOrEqual(1);
		});

		it('shows TV naming for tv media type', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, mediaType: 'tv' }
			});
			expect(screen.getByText('TV Naming')).toBeInTheDocument();
		});

		it('shows music naming when isMusic is true', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, isMusic: true }
			});
			expect(screen.getByText('Music Naming')).toBeInTheDocument();
		});
	});

	describe('interactions', () => {
		it('calls onsaved after successful save', async () => {
			const onsaved = vi.fn();
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, onsaved }
			});
			await fireEvent.click(screen.getByText('Save Settings'));
			await waitFor(() => {
				expect(onsaved).toHaveBeenCalledOnce();
			});
		});
	});

	describe('naming overrides', () => {
		it('shows Override toggle button', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, mediaType: 'tv' }
			});
			expect(screen.getByText('Override')).toBeInTheDocument();
		});

		it('shows editable inputs and Save Pattern when override is enabled', async () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, mediaType: 'tv' }
			});
			await fireEvent.click(screen.getByText('Override'));
			await waitFor(() => {
				expect(screen.getByText('Save Pattern')).toBeInTheDocument();
			});
		});

		it('shows flattened variable badges when override is enabled', async () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, mediaType: 'tv' }
			});
			await fireEvent.click(screen.getByText('Override'));
			await waitFor(() => {
				expect(screen.getByText('{title}')).toBeInTheDocument();
				expect(screen.getByText('{episode}')).toBeInTheDocument();
				expect(screen.getByText('{season}')).toBeInTheDocument();
			});
		});

		it('shows read-only pattern when override is disabled', () => {
			renderComponent(RipSettings, {
				props: { job: createJob(), config: defaultConfig, mediaType: 'tv' }
			});
			expect(screen.getByText('{title} S{season}E{episode}')).toBeInTheDocument();
		});
	});
});
