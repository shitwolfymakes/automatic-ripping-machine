import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import IdentitySuggestionBanner from '../IdentitySuggestionBanner.svelte';
import { createJob } from '../__fixtures__/job';
import { ApiError, NETWORK_ERROR_MESSAGE } from '$lib/api/client';
import type { JobView } from '$lib/types/api.gen';
import { posterSrc } from '$lib/utils/poster';

vi.mock('$lib/api/jobs', () => ({
	acceptIdentitySuggestion: vi.fn(() => Promise.resolve({ job: {}, fan_out: [] }))
}));

import { acceptIdentitySuggestion } from '$lib/api/jobs';
const mockAccept = vi.mocked(acceptIdentitySuggestion);

const SUGGESTION = {
	provider: 'tmdb',
	title: 'Iron Man',
	year: 2008 as number | null,
	kind: 'movie',
	poster_url: 'https://image.tmdb.org/t/p/w500/abc.jpg' as string | null,
	external_ids: {},
	overview: null,
	payload: {},
	suggested_at: '2026-10-15T10:00:00Z'
};

function heldJob(suggestion: Partial<typeof SUGGESTION> | null = {}): JobView {
	return createJob({
		id: 'job_held',
		status: 'awaiting_review',
		title: 'MY_DISC',
		wait_start_time: null,
		metadata_json: {
			...(suggestion ? { identity_suggestion: { ...SUGGESTION, ...suggestion } } : {}),
			flags: { unidentified: true }
		} as never
	});
}

function renderBanner(job: JobView, canAct = true) {
	const onaccepted = vi.fn();
	const onsearch = vi.fn();
	renderComponent(IdentitySuggestionBanner, { props: { job, canAct, onaccepted, onsearch } });
	return { onaccepted, onsearch };
}

describe('IdentitySuggestionBanner', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('shows the match, the source and the poster', () => {
		renderBanner(heldJob());
		expect(screen.getByTestId('identity-suggestion')).toBeInTheDocument();
		expect(screen.getByText('ARM found a match')).toBeInTheDocument();
		expect(screen.getByText('Iron Man (2008)')).toBeInTheDocument();
		expect(screen.getByText('from TMDb')).toBeInTheDocument();
		const img = screen.getByRole('img', { name: 'Iron Man' });
		expect(img).toHaveAttribute('src', posterSrc('https://image.tmdb.org/t/p/w500/abc.jpg'));
		expect(screen.getByRole('button', { name: 'Use this title' })).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Search instead' })).toBeInTheDocument();
	});

	it('shows the title alone without a year, an unknown provider id as is, and no poster when absent', () => {
		renderBanner(heldJob({ year: null, provider: 'elsewhere', poster_url: null }));
		expect(screen.getByText('Iron Man')).toBeInTheDocument();
		expect(screen.getByText('from elsewhere')).toBeInTheDocument();
		expect(screen.queryByRole('img')).toBeNull();
	});

	it('Use this title accepts the suggestion, then calls onaccepted', async () => {
		const { onaccepted } = renderBanner(heldJob());
		await fireEvent.click(screen.getByRole('button', { name: 'Use this title' }));
		await waitFor(() => expect(mockAccept).toHaveBeenCalledWith('job_held'));
		await waitFor(() => expect(onaccepted).toHaveBeenCalledWith({ job: {}, fan_out: [] }));
	});

	it('disables Use this title while the request is in flight and keeps it disabled after success', async () => {
		let release: (v: unknown) => void = () => {};
		mockAccept.mockImplementationOnce(() => new Promise((r) => (release = r)) as never);
		const { onaccepted } = renderBanner(heldJob());
		const btn = screen.getByRole('button', { name: 'Use this title' });
		await fireEvent.click(btn);
		await waitFor(() => expect(btn).toBeDisabled());
		release({ job: {}, fan_out: [] });
		await waitFor(() => expect(onaccepted).toHaveBeenCalled());
		// The banner goes once the parent refreshes the job; until then a second
		// click would only meet a 409 (the suggestion is already applied).
		expect(btn).toBeDisabled();
	});

	it('a rejected accept shows the detail inline and keeps the banner', async () => {
		mockAccept.mockRejectedValueOnce(new ApiError(409, 'job x has no identity suggestion to accept', null));
		const { onaccepted } = renderBanner(heldJob());
		await fireEvent.click(screen.getByRole('button', { name: 'Use this title' }));
		expect(await screen.findByText('job x has no identity suggestion to accept')).toBeInTheDocument();
		expect(screen.getByTestId('identity-suggestion')).toBeInTheDocument();
		expect(screen.getByRole('button', { name: 'Use this title' })).not.toBeDisabled();
		expect(onaccepted).not.toHaveBeenCalled();
	});

	it('a network failure shows the network message', async () => {
		mockAccept.mockRejectedValueOnce(new TypeError('Failed to fetch'));
		renderBanner(heldJob());
		await fireEvent.click(screen.getByRole('button', { name: 'Use this title' }));
		expect(await screen.findByText(NETWORK_ERROR_MESSAGE)).toBeInTheDocument();
	});

	it('Search instead calls onsearch', async () => {
		const { onsearch } = renderBanner(heldJob());
		await fireEvent.click(screen.getByRole('button', { name: 'Search instead' }));
		expect(onsearch).toHaveBeenCalledTimes(1);
		expect(mockAccept).not.toHaveBeenCalled();
	});

	it('a guest sees the banner text but no buttons', () => {
		renderBanner(heldJob(), false);
		expect(screen.getByText('Iron Man (2008)')).toBeInTheDocument();
		expect(screen.queryByRole('button', { name: 'Use this title' })).toBeNull();
		expect(screen.queryByRole('button', { name: 'Search instead' })).toBeNull();
	});

	it('renders nothing without a suggestion', () => {
		renderBanner(heldJob(null));
		expect(screen.queryByTestId('identity-suggestion')).toBeNull();
	});
});
