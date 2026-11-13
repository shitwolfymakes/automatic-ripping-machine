// The review card's facts list, rendered with plain props.
//
// Branch not forced here: the Disc row's `{#if discLine}` never turns false,
// since the disc type label is never empty ("Unknown" stands in for a missing
// type), so the row always shows.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, within } from '$lib/test-utils';
import type { JobView } from '$lib/types/api.gen';
import { readJobMetadata } from '$lib/jobs/metadata';
import type { EpisodeStatus } from '$lib/episodes/status';
import type { SourceRow } from '$lib/jobs/review-card';
import { createJob } from '../../../__fixtures__/job';
import DiscReviewFacts from '../DiscReviewFacts.svelte';

const SOURCE: SourceRow = { label: 'Drive', value: 'Drive A' };

interface FactsOptions {
	isVideo?: boolean;
	isTv?: boolean;
	isMusic?: boolean;
	isPostRip?: boolean;
	episodeRow?: EpisodeStatus | null;
	sourceRow?: SourceRow;
	appliedSession?: string | null;
	onopenseason?: () => void;
	onopenepisodes?: () => void;
}

function renderFacts(job: JobView, options: FactsOptions = {}) {
	const props = {
		job,
		jobMeta: readJobMetadata(job.metadata_json, job),
		isVideo: true,
		isTv: false,
		isMusic: false,
		isPostRip: false,
		episodeRow: null,
		sourceRow: SOURCE,
		appliedSession: null,
		onopenseason: () => {},
		onopenepisodes: () => {},
		...options
	};
	renderComponent(DiscReviewFacts, { props });
}

function tvJob(overrides: Partial<JobView> = {}): JobView {
	return createJob({ media_type: 'tv', ...overrides });
}

function imdb(): JobView['metadata_json'] {
	return { identity: { external_ids: { imdb: 'tt0133093' } } } as JobView['metadata_json'];
}

function row(label: string): HTMLElement {
	const dt = screen.getAllByText(label, { selector: 'dt' })[0];
	return dt.parentElement as HTMLElement;
}

function episodes(state: EpisodeStatus['state'], rest: Partial<EpisodeStatus> = {}): EpisodeStatus {
	return { state, source: null, total: null, unmatched: null, ...rest };
}

const MISS_JOB: Partial<JobView> = {
	status: 'awaiting_user_id',
	metadata_json: { identify_attempts: [{ outcome: 'no_sources' }] } as JobView['metadata_json']
};

describe('DiscReviewFacts', () => {
	afterEach(cleanup);

	it('is a single dl whose rows are its direct children', () => {
		renderFacts(createJob());
		const list = document.querySelector('dl.disc-review-widget-rows') as HTMLElement;
		expect(list.parentElement).toBe(document.body.firstElementChild);
		expect(list.children.length).toBeGreaterThan(0);
		for (const child of Array.from(list.children)) {
			expect(child).toHaveClass('disc-review-widget-row');
		}
	});

	describe('Match / Show row', () => {
		it('is hidden off video discs', () => {
			renderFacts(createJob(), { isVideo: false });
			expect(screen.queryByTestId('match-row')).toBeNull();
		});

		it('labels a movie Match and a TV disc Show', () => {
			renderFacts(createJob());
			expect(within(screen.getByTestId('match-row')).getByText('Match')).toBeInTheDocument();
			cleanup();
			renderFacts(tvJob(), { isTv: true });
			expect(within(screen.getByTestId('match-row')).getByText('Show')).toBeInTheDocument();
		});

		it('links the IMDb id twice and adds the match detail', () => {
			renderFacts(createJob({ metadata_json: imdb(), year: 1999 }));
			const links = within(screen.getByTestId('match-row')).getAllByRole('link');
			expect(links.map((a) => a.getAttribute('href'))).toEqual([
				'https://www.imdb.com/title/tt0133093',
				'https://www.imdb.com/title/tt0133093'
			]);
			expect(links[0]).toHaveTextContent('IMDb');
			expect(links[1]).toHaveTextContent('tt0133093');
			expect(screen.getByTestId('match-row')).toHaveTextContent(', 1999');
		});

		it('shows an IMDb match without a detail when the job has no year or type', () => {
			renderFacts(createJob({ metadata_json: imdb(), year: null }));
			const match = screen.getByTestId('match-row');
			expect(match).toHaveTextContent('Match IMDb tt0133093');
			expect(match.querySelector('.disc-review-widget-muted')).toBeNull();
		});

		it('names the provider of a movie matched without an IMDb id', () => {
			renderFacts(createJob({ year: 1999, metadata_json: { identity: { provider: 'tmdb' } } }));
			expect(screen.getByTestId('match-row')).toHaveTextContent('Matched on TMDb , 1999');
		});

		it('says "Set by hand" for a title no provider matched, without a detail', () => {
			renderFacts(createJob({ year: null }));
			const match = screen.getByTestId('match-row');
			expect(match).toHaveTextContent('Set by hand');
			expect(match.querySelector('.disc-review-widget-muted')).toBeNull();
		});

		it('adds the detail to a hand-set match', () => {
			renderFacts(createJob({ year: 1999, media_type: 'movie' }));
			expect(screen.getByTestId('match-row')).toHaveTextContent('Set by hand , Movie, 1999');
		});

		it('keys a TV match on has_series', () => {
			renderFacts(tvJob({ has_series: true, year: 1974, metadata_json: { identity: { provider: 'tvdb' } } }), {
				isTv: true
			});
			expect(screen.getByTestId('match-row')).toHaveTextContent('Show Matched on TVDB , TV Series, 1974');
		});

		it('treats an identify miss as no match even with a title', () => {
			renderFacts(createJob({ title: 'Disc Title', status: 'awaiting_user_id' }));
			expect(screen.getByTestId('match-row')).toHaveTextContent('No match');
		});

		it('treats a blank title as no match', () => {
			renderFacts(createJob({ title: '  ' }));
			expect(screen.getByTestId('match-row')).toHaveTextContent('No match, pick a title with Search');
		});

		it('hints at the Search for an unmatched TV disc', () => {
			renderFacts(tvJob({ has_series: false }), { isTv: true });
			const match = screen.getByTestId('match-row');
			expect(match).toHaveTextContent('Needs show, pick a show with Search');
			expect(within(match).queryByTestId('identify-miss-reason')).toBeNull();
		});

		it('gives the miss reason, with its test id, for an unmatched disc', () => {
			renderFacts(createJob(MISS_JOB));
			const match = screen.getByTestId('match-row');
			expect(match).toHaveTextContent('No match');
			expect(within(match).getByTestId('identify-miss-reason')).toHaveTextContent(
				', No online source is switched on for this kind of disc.'
			);
		});
	});

	describe('Season row', () => {
		it('shows "Season N" when a season is set', () => {
			renderFacts(tvJob({ season: 3 }), { isTv: true, isPostRip: true });
			expect(screen.getByTestId('season-row')).toHaveTextContent('Season 3');
			expect(within(screen.getByTestId('season-row')).queryByRole('button')).toBeNull();
		});

		it('offers "Season not set" before the rip and calls onopenseason', async () => {
			const onopenseason = vi.fn();
			renderFacts(tvJob(), { isTv: true, onopenseason });
			await fireEvent.click(within(screen.getByTestId('season-row')).getByRole('button', { name: 'Season not set' }));
			expect(onopenseason).toHaveBeenCalledOnce();
		});

		it('is hidden post-rip on TV with no season', () => {
			renderFacts(tvJob(), { isTv: true, isPostRip: true });
			expect(screen.queryByTestId('season-row')).toBeNull();
		});

		it('is hidden off TV', () => {
			renderFacts(createJob({ season: 3 }));
			expect(screen.queryByTestId('season-row')).toBeNull();
		});
	});

	describe('Episodes row', () => {
		it('is hidden when there is no episode state', () => {
			renderFacts(tvJob(), { isTv: true, episodeRow: null });
			expect(screen.queryByTestId('episode-status')).toBeNull();
		});

		it('lets a matched row name its source and calls onopenepisodes', async () => {
			const onopenepisodes = vi.fn();
			renderFacts(tvJob(), { isTv: true, episodeRow: episodes('matched', { source: 'TheDiscDB' }), onopenepisodes });
			const status = screen.getByTestId('episode-status');
			expect(status).toHaveAttribute('data-state', 'matched');
			await fireEvent.click(within(status).getByRole('button', { name: 'Episodes matched from TheDiscDB' }));
			expect(onopenepisodes).toHaveBeenCalledOnce();
		});

		it('lets a matched row without a source say so plainly', () => {
			renderFacts(tvJob(), { isTv: true, episodeRow: episodes('matched') });
			expect(screen.getByRole('button', { name: 'Episodes matched' })).toBeInTheDocument();
		});

		it('flags a guess and links Review', async () => {
			const onopenepisodes = vi.fn();
			renderFacts(tvJob(), { isTv: true, episodeRow: episodes('guess'), onopenepisodes });
			const status = screen.getByTestId('episode-status');
			expect(status).toHaveAttribute('data-state', 'guess');
			expect(status).toHaveTextContent('Episodes placed, a guess,');
			await fireEvent.click(within(status).getByRole('button', { name: 'Review' }));
			expect(onopenepisodes).toHaveBeenCalledOnce();
		});

		it('counts the unmatched titles of an attention row and links Review', async () => {
			const onopenepisodes = vi.fn();
			renderFacts(tvJob(), {
				isTv: true,
				episodeRow: episodes('attention', { total: 8, unmatched: 3 }),
				onopenepisodes
			});
			const status = screen.getByTestId('episode-status');
			expect(status).toHaveAttribute('data-state', 'attention');
			expect(status).toHaveTextContent('Episodes need attention, 3 of 8 titles unmatched,');
			await fireEvent.click(within(status).getByRole('button', { name: 'Review' }));
			expect(onopenepisodes).toHaveBeenCalledOnce();
		});

		it.each([
			['no total', { total: null, unmatched: 3 }],
			['no unmatched count', { total: 8, unmatched: 0 }]
		])('leaves the count out of an attention row with %s', (_name, counts) => {
			renderFacts(tvJob(), { isTv: true, episodeRow: episodes('attention', counts) });
			expect(screen.getByTestId('episode-status')).not.toHaveTextContent('unmatched');
		});

		it('shows the matching detail while episodes match', () => {
			renderFacts(tvJob(), {
				isTv: true,
				episodeRow: episodes('matching', { source: 'TheDiscDB', total: 8, unmatched: 3 })
			});
			const status = screen.getByTestId('episode-status');
			expect(status).toHaveAttribute('data-state', 'matching');
			expect(status).toHaveTextContent('Matching episodes... TheDiscDB, 5 of 8 titles');
		});

		it('shows no detail while matching without one', () => {
			renderFacts(tvJob(), { isTv: true, episodeRow: episodes('matching') });
			const status = screen.getByTestId('episode-status');
			expect(status).toHaveTextContent('Matching episodes...');
			expect(status.querySelector('.disc-review-widget-muted')).toBeNull();
		});

		it('waits for a show', () => {
			renderFacts(tvJob(), { isTv: true, episodeRow: episodes('waiting') });
			const status = screen.getByTestId('episode-status');
			expect(status).toHaveAttribute('data-state', 'waiting');
			expect(status).toHaveTextContent('Waiting for show');
		});
	});

	describe('music Match row', () => {
		const cd: Partial<JobView> = { ...MISS_JOB, disc_type: 'cd' };

		it('shows the miss reason on a music disc', () => {
			renderFacts(createJob(cd), { isVideo: false, isMusic: true });
			const matchRow = row('Match');
			expect(matchRow).toHaveTextContent('No match');
			expect(within(matchRow).getByTestId('identify-miss-reason')).toHaveTextContent(
				'No online source is switched on for this kind of disc.'
			);
		});

		it('is hidden on a music disc with no miss reason', () => {
			renderFacts(createJob({ disc_type: 'cd' }), { isVideo: false, isMusic: true });
			expect(screen.queryByText('Match', { selector: 'dt' })).toBeNull();
		});

		it('is hidden when the disc is not music', () => {
			renderFacts(createJob(cd), { isVideo: false, isMusic: false });
			expect(screen.queryByText('Match', { selector: 'dt' })).toBeNull();
		});
	});

	describe('Artist and Album rows', () => {
		it('show the values with a title attribute', () => {
			renderFacts(createJob({ metadata_json: { music: { artist: 'Daft Punk', album: 'Discovery' } } }), {
				isVideo: false
			});
			expect(within(row('Artist')).getByText('Daft Punk')).toHaveAttribute('title', 'Daft Punk');
			expect(within(row('Album')).getByText('Discovery')).toHaveAttribute('title', 'Discovery');
		});

		it('are hidden when unset', () => {
			renderFacts(createJob(), { isVideo: false });
			expect(screen.queryByText('Artist', { selector: 'dt' })).toBeNull();
			expect(screen.queryByText('Album', { selector: 'dt' })).toBeNull();
		});
	});

	describe('Disc row', () => {
		it('shows the disc type, number and title count with a title attribute', () => {
			renderFacts(
				createJob({
					disc_type: 'bluray',
					disc_number: 1,
					disc_total: 4,
					metadata_json: {
						scan_result: { disc_type: 'bluray', titles: [1, 2, 3].map((index) => ({ index, duration_seconds: 60 })) }
					}
				})
			);
			expect(within(row('Disc')).getByText('Blu-ray, Disc 1/4, 3 titles')).toHaveAttribute(
				'title',
				'Blu-ray, Disc 1/4, 3 titles'
			);
		});
	});

	describe('Source row', () => {
		it('shows its label, value and title', () => {
			renderFacts(createJob(), { sourceRow: { label: 'ISO', value: 'movie.iso' } });
			const source = row('ISO');
			expect(within(source).getByText('movie.iso')).toHaveAttribute('title', 'movie.iso');
			expect(within(source).getByText('movie.iso')).toHaveClass('disc-review-widget-source');
		});
	});

	describe('Session row', () => {
		it('shows the applied session with a title attribute', () => {
			renderFacts(createJob(), { appliedSession: 'Film night' });
			expect(within(row('Session')).getByText('Film night')).toHaveAttribute('title', 'Film night');
		});

		it('is hidden when no session is applied', () => {
			renderFacts(createJob(), { appliedSession: null });
			expect(screen.queryByText('Session', { selector: 'dt' })).toBeNull();
		});
	});
});
