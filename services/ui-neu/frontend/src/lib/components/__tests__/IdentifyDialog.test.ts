import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import IdentifyDialog from '../IdentifyDialog.svelte';
import { createJob } from '../__fixtures__/job';
import { resolveJob, searchMetadata } from '$lib/api/jobs';
import type { ResolveResponse } from '$lib/types/api.gen';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return { role: { subscribe: _role.subscribe }, isAdmin: derived(_role, (r) => r === 'admin') };
});

vi.mock('$lib/stores/config', async () => {
	const { writable } = await import('svelte/store');
	return {
		searchProviders: writable({ movie: 'tmdb', tv: 'tmdb' }),
		keyedSources: writable({ tmdb: true, omdb: true, tvdb: true })
	};
});

vi.mock('$lib/api/jobs', () => ({
	resolveJob: vi.fn(),
	searchMetadata: vi.fn(),
	fetchMediaDetail: vi.fn(),
	updateJobTitle: vi.fn(() => Promise.resolve())
}));

const resolveJobMock = vi.mocked(resolveJob);
const searchMock = vi.mocked(searchMetadata);

function makeResp(): ResolveResponse {
	return { job: createJob({ status: 'identified' }), fan_out: [] };
}

describe('IdentifyDialog', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('video job', () => {
		it('renders title + year inputs and submits title/year with no music', async () => {
			resolveJobMock.mockResolvedValue(makeResp());
			const onidentified = vi.fn();
			const job = createJob({
				id: 'job_v',
				disc_type: 'bluray',
				status: 'awaiting_user_id',
				title: '',
				year: null
			});
			renderComponent(IdentifyDialog, {
				props: { job, onclose: vi.fn(), onidentified }
			});

			const titleInput = screen.getByTestId('identify-title') as HTMLInputElement;
			const yearInput = screen.getByTestId('identify-year') as HTMLInputElement;
			expect(titleInput).toBeInTheDocument();
			expect(yearInput).toBeInTheDocument();

			await fireEvent.input(titleInput, { target: { value: 'Blade Runner' } });
			await fireEvent.input(yearInput, { target: { value: '1982' } });
			await fireEvent.click(screen.getByTestId('identify-submit'));

			await waitFor(() => {
				expect(resolveJobMock).toHaveBeenCalledWith('job_v', {
					title: 'Blade Runner',
					year: 1982,
					music: undefined
				});
				expect(onidentified).toHaveBeenCalledTimes(1);
			});
		});
	});

	describe('search first (video)', () => {
		const warning = "Without a search result ARM has no show id, so episodes can't be matched automatically.";

		it('shows the search and the manual caption for a video disc', () => {
			const job = createJob({ disc_type: 'bluray', status: 'awaiting_user_id' });
			renderComponent(IdentifyDialog, { props: { job, onclose: vi.fn(), onidentified: vi.fn() } });
			expect(screen.getByRole('button', { name: 'Search' })).toBeInTheDocument();
			expect(screen.getByText('Or enter the title yourself')).toBeInTheDocument();
			expect(screen.getByTestId('identify-title')).toBeInTheDocument();
		});

		it('applies a search result with ids and reports the response', async () => {
			const resp = makeResp();
			resolveJobMock.mockResolvedValue(resp);
			searchMock.mockResolvedValue({
				candidates: [
					{
						title: 'Firefly',
						year: 2002,
						kind: 'tv',
						poster_url: null,
						provider_id: '1437',
						external_ids: { tmdb_series_id: 1437 }
					}
				]
			} as never);
			const onidentified = vi.fn();
			const job = createJob({
				id: 'job_s',
				disc_type: 'dvd',
				status: 'awaiting_user_id',
				media_type: 'tv',
				title: 'firefly'
			});
			renderComponent(IdentifyDialog, { props: { job, onclose: vi.fn(), onidentified } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await waitFor(() => expect(screen.getByText('Firefly')).toBeInTheDocument());
			await fireEvent.click(screen.getByText('Firefly'));
			await fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
			await waitFor(() => expect(onidentified).toHaveBeenCalledWith(resp));
			expect(onidentified).toHaveBeenCalledTimes(1);
			expect(resolveJobMock).toHaveBeenCalledTimes(1);
			expect(resolveJobMock).toHaveBeenCalledWith(
				'job_s',
				expect.objectContaining({ media_type: 'tv', external_ids: { tmdb_series_id: 1437 } })
			);
		});

		it('Search on a movie job does not resolve', async () => {
			searchMock.mockResolvedValue({ candidates: [] } as never);
			const job = createJob({ disc_type: 'bluray', status: 'awaiting_user_id', media_type: 'movie', title: 'Alien' });
			renderComponent(IdentifyDialog, { props: { job, onclose: vi.fn(), onidentified: vi.fn() } });
			await fireEvent.click(screen.getByRole('button', { name: 'Search' }));
			await waitFor(() => expect(searchMock).toHaveBeenCalledTimes(1));
			expect(resolveJobMock).not.toHaveBeenCalled();
		});

		it('Enter in the search title searches once and does not resolve', async () => {
			searchMock.mockResolvedValue({ candidates: [] } as never);
			const job = createJob({ disc_type: 'bluray', status: 'awaiting_user_id', media_type: 'movie', title: 'Alien' });
			const { container } = renderComponent(IdentifyDialog, {
				props: { job, onclose: vi.fn(), onidentified: vi.fn() }
			});
			const input = container.ownerDocument.querySelector('input[type="text"]') as HTMLInputElement;
			expect(input.form).toBeNull();
			await fireEvent.keyDown(input, { key: 'Enter' });
			await waitFor(() => expect(searchMock).toHaveBeenCalledTimes(1));
			expect(resolveJobMock).not.toHaveBeenCalled();
		});

		it('episodic job: manual submit warns and resolves only on Save without a match', async () => {
			resolveJobMock.mockResolvedValue(makeResp());
			const onidentified = vi.fn();
			const job = createJob({
				id: 'job_e',
				disc_type: 'dvd',
				status: 'awaiting_user_id',
				media_type: 'tv',
				title: 'Firefly'
			});
			renderComponent(IdentifyDialog, { props: { job, onclose: vi.fn(), onidentified } });
			expect(screen.queryByText(warning)).not.toBeInTheDocument();
			await fireEvent.click(screen.getByTestId('identify-submit'));
			expect(screen.getByText(warning)).toBeInTheDocument();
			expect(resolveJobMock).not.toHaveBeenCalled();
			await fireEvent.click(screen.getByRole('button', { name: 'Save without a match' }));
			await waitFor(() => expect(resolveJobMock).toHaveBeenCalledTimes(1));
			expect(onidentified).toHaveBeenCalledTimes(1);
		});

		it('looks_episodic job warns too', async () => {
			const job = createJob({ disc_type: 'dvd', status: 'awaiting_user_id', looks_episodic: true, title: 'X' });
			renderComponent(IdentifyDialog, { props: { job, onclose: vi.fn(), onidentified: vi.fn() } });
			await fireEvent.click(screen.getByTestId('identify-submit'));
			expect(screen.getByText(warning)).toBeInTheDocument();
			expect(resolveJobMock).not.toHaveBeenCalled();
		});

		it('movie job: manual submit resolves on the first click', async () => {
			resolveJobMock.mockResolvedValue(makeResp());
			const job = createJob({
				disc_type: 'bluray',
				status: 'awaiting_user_id',
				media_type: 'movie',
				looks_episodic: false,
				title: 'Alien'
			});
			renderComponent(IdentifyDialog, { props: { job, onclose: vi.fn(), onidentified: vi.fn() } });
			await fireEvent.click(screen.getByTestId('identify-submit'));
			await waitFor(() => expect(resolveJobMock).toHaveBeenCalledTimes(1));
		});

		it('CD dialog has no search', () => {
			const job = createJob({ disc_type: 'cd', status: 'awaiting_user_id' });
			renderComponent(IdentifyDialog, { props: { job, onclose: vi.fn(), onidentified: vi.fn() } });
			expect(screen.queryByRole('button', { name: 'Search' })).not.toBeInTheDocument();
			expect(screen.queryByText('Or enter the title yourself')).not.toBeInTheDocument();
		});
	});

	describe('music job', () => {
		it('renders album + artist + per-track inputs and submits the music shape', async () => {
			resolveJobMock.mockResolvedValue(makeResp());
			const onidentified = vi.fn();
			const job = createJob({
				id: 'job_cd',
				disc_type: 'cd',
				status: 'awaiting_user_id',
				title: '',
				year: null,
				metadata_json: {
					scan_result: {
						disc_type: 'cd',
						titles: [
							{ index: 0, duration_seconds: 0 },
							{ index: 1, duration_seconds: 0 }
						]
					}
				}
			});
			renderComponent(IdentifyDialog, {
				props: { job, onclose: vi.fn(), onidentified }
			});

			const albumInput = screen.getByTestId('identify-album') as HTMLInputElement;
			const artistInput = screen.getByTestId('identify-artist') as HTMLInputElement;
			expect(albumInput).toBeInTheDocument();
			expect(artistInput).toBeInTheDocument();

			const track1 = screen.getByTestId('identify-track-1') as HTMLInputElement;
			const track2 = screen.getByTestId('identify-track-2') as HTMLInputElement;
			expect(track1).toBeInTheDocument();
			expect(track2).toBeInTheDocument();

			await fireEvent.input(albumInput, { target: { value: 'Dark Side' } });
			await fireEvent.input(artistInput, { target: { value: 'Pink Floyd' } });
			await fireEvent.input(track1, { target: { value: 'Speak to Me' } });
			await fireEvent.input(track2, { target: { value: 'Breathe' } });
			await fireEvent.click(screen.getByTestId('identify-submit'));

			await waitFor(() => {
				expect(resolveJobMock).toHaveBeenCalledWith('job_cd', {
					title: 'Dark Side',
					year: null,
					music: {
						artist: 'Pink Floyd',
						album: 'Dark Side',
						tracks: [{ title: 'Speak to Me' }, { title: 'Breathe' }]
					}
				});
				expect(onidentified).toHaveBeenCalledTimes(1);
			});
		});

		it('shows the helper text and no track inputs when scan_result has no titles', () => {
			const job = createJob({
				id: 'job_cd0',
				disc_type: 'cd',
				status: 'awaiting_user_id',
				metadata_json: {}
			});
			renderComponent(IdentifyDialog, {
				props: { job, onclose: vi.fn(), onidentified: vi.fn() }
			});
			expect(screen.queryByTestId('identify-track-1')).not.toBeInTheDocument();
			expect(screen.getByText(/Track count couldn't be determined/i)).toBeInTheDocument();
		});
	});

	describe('button label', () => {
		it('reads "Identify disc" for awaiting_user_id', () => {
			const job = createJob({ disc_type: 'bluray', status: 'awaiting_user_id' });
			renderComponent(IdentifyDialog, {
				props: { job, onclose: vi.fn(), onidentified: vi.fn() }
			});
			expect(screen.getByTestId('identify-submit')).toHaveTextContent('Identify disc');
		});

		it('reads "Edit identity" for a post-rip status (ripped)', () => {
			const job = createJob({ disc_type: 'bluray', status: 'ripped' });
			renderComponent(IdentifyDialog, {
				props: { job, onclose: vi.fn(), onidentified: vi.fn() }
			});
			expect(screen.getByTestId('identify-submit')).toHaveTextContent('Edit identity');
		});
	});

	describe('canSubmit', () => {
		it('disables submit for video when title is empty', () => {
			const job = createJob({ disc_type: 'bluray', status: 'awaiting_user_id', title: '' });
			renderComponent(IdentifyDialog, {
				props: { job, onclose: vi.fn(), onidentified: vi.fn() }
			});
			expect(screen.getByTestId('identify-submit')).toBeDisabled();
		});

		it('disables submit for music until both album and artist are filled', async () => {
			const job = createJob({
				disc_type: 'cd',
				status: 'awaiting_user_id',
				title: '',
				metadata_json: { scan_result: { disc_type: 'cd', titles: [] } }
			});
			renderComponent(IdentifyDialog, {
				props: { job, onclose: vi.fn(), onidentified: vi.fn() }
			});
			const submit = screen.getByTestId('identify-submit');
			expect(submit).toBeDisabled();
			await fireEvent.input(screen.getByTestId('identify-album'), { target: { value: 'A' } });
			expect(submit).toBeDisabled();
			await fireEvent.input(screen.getByTestId('identify-artist'), { target: { value: 'B' } });
			expect(submit).not.toBeDisabled();
		});
	});

	describe('error handling', () => {
		it('shows the thrown error message inline', async () => {
			resolveJobMock.mockRejectedValue(new Error('boom'));
			const job = createJob({ disc_type: 'bluray', status: 'awaiting_user_id', title: 'X' });
			renderComponent(IdentifyDialog, {
				props: { job, onclose: vi.fn(), onidentified: vi.fn() }
			});
			await fireEvent.click(screen.getByTestId('identify-submit'));
			await waitFor(() => expect(screen.getByText('boom')).toBeInTheDocument());
		});
	});

	describe('cancel', () => {
		it('fires onclose', async () => {
			const onclose = vi.fn();
			const job = createJob({ disc_type: 'bluray', status: 'awaiting_user_id' });
			renderComponent(IdentifyDialog, {
				props: { job, onclose, onidentified: vi.fn() }
			});
			await fireEvent.click(screen.getByText('Cancel'));
			expect(onclose).toHaveBeenCalledTimes(1);
		});
	});
});
