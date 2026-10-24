// The review card's Episodes section: the job page's episode matcher on Home.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor, within } from '$lib/test-utils';
import DiscReviewWidget from './DiscReviewWidget.svelte';
import type { IdentityView, JobView } from '$lib/types/api.gen';
import { createJob, createJobDetail } from './__fixtures__/job';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return { role: { subscribe: _role.subscribe }, isAdmin: derived(_role, (r) => r === 'admin') };
});

vi.mock('$lib/api/jobs', () => ({
	fetchJob: vi.fn(),
	setJobMediaType: vi.fn(() => Promise.resolve({})),
	resolveJob: vi.fn(() => Promise.resolve({})),
	fetchNamingPreview: vi.fn(() => Promise.resolve({ items: [] })),
	updateTrack: vi.fn(() => Promise.resolve({}))
}));

vi.mock('$lib/api/identity', () => ({
	fetchIdentity: vi.fn(() => new Promise(() => {})),
	matchIdentity: vi.fn(() => new Promise(() => {})),
	unpinIdentity: vi.fn(() => new Promise(() => {})),
	fetchEpisodes: vi.fn(() => new Promise(() => {}))
}));

vi.mock('$lib/api/sessions', () => ({ fetchSessions: vi.fn(() => Promise.resolve([])) }));

vi.mock('./TitleSearch.svelte', async () => ({
	default: (await import('./__fixtures__/TitleSearchStub.svelte')).default
}));

type RipperListener = (jobIds: Set<string>, eventTypes: Map<string, Set<string>>) => void;
const ripperListeners: RipperListener[] = [];
function fireRipperEvent(jobId: string, eventType: string) {
	ripperListeners.forEach((fn) => fn(new Set([jobId]), new Map([[jobId, new Set([eventType])]])));
}
vi.mock('$lib/stores/ripperEvents.svelte', () => ({
	startRipperEvents: vi.fn(),
	onRipperEvent: (fn: RipperListener) => {
		ripperListeners.push(fn);
		return () => ripperListeners.splice(ripperListeners.indexOf(fn), 1);
	}
}));

import { fetchJob, setJobMediaType } from '$lib/api/jobs';
import { fetchIdentity } from '$lib/api/identity';
const mockFetchJob = vi.mocked(fetchJob);

const TV: Partial<JobView> = {
	id: 'job_42',
	title: 'Kolchak',
	status: 'awaiting_review',
	disc_type: 'bluray',
	media_type: 'tv',
	has_series: true
};

function renderCard(job: Partial<JobView> = TV, detailJob: Partial<JobView> = job) {
	mockFetchJob.mockResolvedValue({ ...createJobDetail({ tracks: [] }), job: createJob(detailJob) });
	return renderComponent(DiscReviewWidget, { props: { job: createJob(job) } });
}

const episodesButton = () => screen.findByRole('button', { name: 'Episodes' });

describe('DiscReviewWidget episode matching', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
		vi.mocked(fetchIdentity).mockImplementation(() => new Promise(() => {}));
	});

	it('offers Episodes on a TV video disc only', async () => {
		renderCard();
		expect(await episodesButton()).toHaveAttribute('aria-pressed', 'false');
		cleanup();
		renderCard({ ...TV, media_type: 'movie', has_series: false });
		await screen.findByRole('button', { name: 'Search' });
		expect(screen.queryByRole('button', { name: 'Episodes' })).not.toBeInTheDocument();
		cleanup();
		renderCard({ ...TV, disc_type: 'data' });
		await screen.findByRole('button', { name: 'Info' });
		expect(screen.queryByRole('button', { name: 'Episodes' })).not.toBeInTheDocument();
	});

	it('opens the episode panel, one section at a time', async () => {
		renderCard();
		await fireEvent.click(await screen.findByRole('button', { name: 'Info' }));
		await fireEvent.click(await episodesButton());
		expect(screen.getByRole('button', { name: 'Episodes' })).toHaveAttribute('aria-pressed', 'true');
		expect(screen.getByRole('button', { name: 'Info' })).toHaveAttribute('aria-pressed', 'false');
		expect(within(screen.getByTestId('episode-panel')).getByRole('region', { name: 'Match episodes' })).toBeTruthy();
		await fireEvent.click(screen.getByRole('button', { name: 'Episodes' }));
		expect(screen.queryByTestId('episode-panel')).not.toBeInTheDocument();
	});

	it('picking a series opens Episodes and shows matching until job.identity_updated for this job', async () => {
		renderCard({ ...TV, has_series: false }, TV);
		await fireEvent.click(await screen.findByRole('button', { name: 'Search' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Pick a series' }));
		const panel = await screen.findByTestId('episode-panel');
		expect(screen.getByRole('button', { name: 'Episodes' })).toHaveAttribute('aria-pressed', 'true');
		expect(screen.queryByRole('button', { name: 'Pick a series' })).not.toBeInTheDocument();
		await waitFor(() => expect(within(panel).getByText('Matching episodes...')).toBeInTheDocument());

		vi.mocked(fetchIdentity).mockResolvedValue({ sources: {}, pin: null } as unknown as IdentityView);
		fireRipperEvent('job_other', 'job.identity_updated');
		expect(within(panel).getByText('Matching episodes...')).toBeInTheDocument();

		const fetches = mockFetchJob.mock.calls.length;
		fireRipperEvent('job_42', 'rip.identify_resolved');
		await waitFor(() => expect(mockFetchJob.mock.calls.length).toBeGreaterThan(fetches));
		await new Promise((r) => setTimeout(r, 50));
		expect(within(panel).getByText('Matching episodes...')).toBeInTheDocument();

		const identityCalls = vi.mocked(fetchIdentity).mock.calls.length;
		fireRipperEvent('job_42', 'job.identity_updated');
		await waitFor(() => expect(within(panel).queryByText('Matching episodes...')).not.toBeInTheDocument());
		expect(vi.mocked(fetchIdentity).mock.calls.length).toBeGreaterThan(identityCalls);
	});

	it('the episode status line opens the panel in place', async () => {
		renderCard({
			...TV,
			metadata_json: { flags: {}, identity_claims: { sources: { episodes_tvmaze: { status: 'ok' } } } }
		} as Partial<JobView>);
		const line = await screen.findByTestId('episode-status');
		expect(line.querySelector('a')).toBeNull();
		await fireEvent.click(within(line).getByRole('button', { name: 'Episodes matched from TVmaze' }));
		expect(await screen.findByTestId('episode-panel')).toBeInTheDocument();
	});

	it('flipping the type to TV opens Episodes with matching', async () => {
		renderCard({ ...TV, media_type: 'movie', has_series: false }, TV);
		await fireEvent.click(await screen.findByRole('radio', { name: 'TV' }));
		expect(setJobMediaType).toHaveBeenCalledWith('job_42', 'tv');
		const panel = await screen.findByTestId('episode-panel');
		await waitFor(() => expect(within(panel).getByText('Matching episodes...')).toBeInTheDocument());
	});

	it("the panel's series search opens Search looking for TV", async () => {
		renderCard({ ...TV, has_series: false });
		await fireEvent.click(await episodesButton());
		await fireEvent.click(await screen.findByRole('button', { name: 'Search for the series' }));
		expect(screen.queryByTestId('episode-panel')).not.toBeInTheDocument();
		expect(screen.getByTestId('title-initial-type')).toHaveTextContent('tv');
		// Opening Search from its own button starts with the job's type again.
		await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
		expect(screen.getByTestId('title-initial-type')).toHaveTextContent('none');
	});

	it('says the season is not set for a pre-rip TV job without one', async () => {
		renderCard();
		expect(await screen.findByText(/Season not set/)).toBeTruthy();
	});

	it('does not say it for a ripped job or when a season is known', async () => {
		renderCard({ ...TV, status: 'ripped' });
		await episodesButton();
		expect(screen.queryByText(/Season not set/)).toBeNull();
		cleanup();
		renderCard({ ...TV, season: 5 });
		await episodesButton();
		expect(screen.queryByText(/Season not set/)).toBeNull();
		expect(screen.getByText(/Season 5/)).toBeTruthy();
	});

	it('starts matching when Info saves a season on a TV job', async () => {
		renderCard();
		await fireEvent.click(await screen.findByRole('button', { name: 'Info' }));
		await fireEvent.input(await screen.findByLabelText('Season'), { target: { value: '7' } });
		await fireEvent.click(screen.getByRole('button', { name: 'Save' }));
		expect(await screen.findByText('Matching episodes...')).toBeTruthy();
	});
});
