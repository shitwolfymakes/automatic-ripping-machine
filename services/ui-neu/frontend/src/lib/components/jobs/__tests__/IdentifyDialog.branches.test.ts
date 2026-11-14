import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import IdentifyDialog from '../IdentifyDialog.svelte';
import { createJob } from '../../../__fixtures__/job';
import { resolveJob } from '$lib/api/jobs';
import type { ResolveResponse } from '$lib/types/api.gen';

// Branch pins for IdentifyDialog, beside IdentifyDialog.test.ts. Every branch
// of the dialog is reachable from the rendered form, so nothing here is left
// unpinned.

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

function makeResp(): ResolveResponse {
	return { job: createJob({ status: 'identified' }), fan_out: [] };
}

const helperLine = /Track count couldn't be determined/i;
const warning = "Without a search result ARM has no show id, so episodes can't be matched automatically.";

function renderDialog(overrides: Parameters<typeof createJob>[0], onidentified = vi.fn()) {
	const job = createJob({ status: 'awaiting_user_id', ...overrides });
	return renderComponent(IdentifyDialog, { props: { job, onclose: vi.fn(), onidentified } });
}

describe('IdentifyDialog branches', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('submitting the form with required fields empty', () => {
		it('sends nothing and shows no warning for a video job', async () => {
			const { container } = renderDialog({ disc_type: 'dvd', title: '', media_type: 'tv' });
			await fireEvent.submit(container.querySelector('form') as HTMLFormElement);
			expect(resolveJobMock).not.toHaveBeenCalled();
			expect(screen.queryByText(warning)).not.toBeInTheDocument();
		});

		it('sends nothing and shows no warning for a CD job', async () => {
			const { container } = renderDialog({ disc_type: 'cd', title: '', looks_episodic: true });
			await fireEvent.submit(container.querySelector('form') as HTMLFormElement);
			expect(resolveJobMock).not.toHaveBeenCalled();
			expect(screen.queryByText(warning)).not.toBeInTheDocument();
		});
	});

	describe('CD resolve request', () => {
		it('sends the typed year', async () => {
			resolveJobMock.mockResolvedValue(makeResp());
			renderDialog({ id: 'job_y', disc_type: 'cd', title: 'Album', year: null });
			await fireEvent.input(screen.getByTestId('identify-artist'), { target: { value: 'Artist' } });
			await fireEvent.input(screen.getByTestId('identify-year'), { target: { value: '1973' } });
			await fireEvent.click(screen.getByTestId('identify-submit'));
			await waitFor(() => expect(resolveJobMock).toHaveBeenCalledTimes(1));
			expect(resolveJobMock).toHaveBeenCalledWith('job_y', expect.objectContaining({ year: 1973 }));
		});

		it('trims album, artist and track titles and sends a blank track as an empty string', async () => {
			resolveJobMock.mockResolvedValue(makeResp());
			renderDialog({
				id: 'job_t',
				disc_type: 'cd',
				title: '',
				year: null,
				metadata_json: {
					scan_result: {
						disc_type: 'cd',
						titles: [0, 1, 2].map((index) => ({ index, duration_seconds: 0 }))
					}
				}
			});
			await fireEvent.input(screen.getByTestId('identify-album'), { target: { value: '  Album  ' } });
			await fireEvent.input(screen.getByTestId('identify-artist'), { target: { value: '  Artist ' } });
			await fireEvent.input(screen.getByTestId('identify-track-1'), { target: { value: '  One ' } });
			await fireEvent.input(screen.getByTestId('identify-track-3'), { target: { value: ' Three' } });
			await fireEvent.click(screen.getByTestId('identify-submit'));
			await waitFor(() => expect(resolveJobMock).toHaveBeenCalledTimes(1));
			expect(resolveJobMock).toHaveBeenCalledWith('job_t', {
				title: 'Album',
				year: null,
				music: {
					artist: 'Artist',
					album: 'Album',
					tracks: [{ title: 'One' }, { title: '' }, { title: 'Three' }]
				}
			});
		});

		it('never asks for the no-match confirmation, even when looks_episodic is true', async () => {
			resolveJobMock.mockResolvedValue(makeResp());
			renderDialog({ disc_type: 'cd', title: 'Album', looks_episodic: true, media_type: 'tv' });
			await fireEvent.input(screen.getByTestId('identify-artist'), { target: { value: 'Artist' } });
			await fireEvent.click(screen.getByTestId('identify-submit'));
			await waitFor(() => expect(resolveJobMock).toHaveBeenCalledTimes(1));
			expect(screen.queryByText(warning)).not.toBeInTheDocument();
		});
	});

	describe('failure that is not an Error', () => {
		it('shows "Identify failed"', async () => {
			resolveJobMock.mockRejectedValue('nope');
			renderDialog({ disc_type: 'bluray', title: 'X' });
			await fireEvent.click(screen.getByTestId('identify-submit'));
			expect(await screen.findByTestId('identify-error')).toHaveTextContent('Identify failed');
		});
	});

	describe('scan title count behind the CD track inputs', () => {
		it.each([
			['no scan_result', {}],
			['a string scan_result', { scan_result: 'oops' }],
			['a null scan_result', { scan_result: null }],
			['titles that is not an array', { scan_result: { titles: 'three' } }]
		])('shows the helper line and no track inputs for %s', (_name, metadata_json) => {
			// These shapes are malformed on purpose, so they bypass the type.
			renderDialog({ disc_type: 'cd', metadata_json: metadata_json as never });
			expect(screen.getByText(helperLine)).toBeInTheDocument();
			expect(screen.queryByTestId('identify-track-1')).not.toBeInTheDocument();
		});

		it('shows the helper line for an empty titles array', () => {
			renderDialog({ disc_type: 'cd', metadata_json: { scan_result: { disc_type: 'cd', titles: [] } } });
			expect(screen.getByText(helperLine)).toBeInTheDocument();
			expect(screen.queryByTestId('identify-track-1')).not.toBeInTheDocument();
		});
	});

	describe('submit button label', () => {
		it('reads "Identify disc" while awaiting identity', () => {
			renderDialog({ disc_type: 'bluray', status: 'awaiting_user_id' });
			expect(screen.getByTestId('identify-submit')).toHaveTextContent('Identify disc');
		});

		it('reads "Edit identity" after the rip', () => {
			renderDialog({ disc_type: 'bluray', status: 'ripped' });
			expect(screen.getByTestId('identify-submit')).toHaveTextContent('Edit identity');
		});

		it('reads "Save without a match" once the confirmation is asked for', async () => {
			renderDialog({ disc_type: 'dvd', title: 'Firefly', media_type: 'tv' });
			await fireEvent.click(screen.getByTestId('identify-submit'));
			expect(screen.getByTestId('identify-submit')).toHaveTextContent('Save without a match');
		});

		it('reads "Saving..." while the request is pending', async () => {
			let finish: (resp: ResolveResponse) => void = () => {};
			resolveJobMock.mockReturnValue(new Promise<ResolveResponse>((resolve) => (finish = resolve)));
			renderDialog({ disc_type: 'bluray', title: 'Alien', media_type: 'movie' });
			await fireEvent.click(screen.getByTestId('identify-submit'));
			expect(screen.getByTestId('identify-submit')).toHaveTextContent('Saving...');
			finish(makeResp());
			await waitFor(() => expect(screen.getByTestId('identify-submit')).toHaveTextContent('Identify disc'));
		});
	});
});
