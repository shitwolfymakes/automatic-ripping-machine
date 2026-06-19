import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import IdentifyDialog from '../IdentifyDialog.svelte';
import { createJob } from '../__fixtures__/job';
import { resolveJob } from '$lib/api/jobs';
import type { ResolveResponse } from '$lib/types/api.gen';

vi.mock('$lib/api/jobs', () => ({
	resolveJob: vi.fn()
}));

const resolveJobMock = vi.mocked(resolveJob);

function makeResp(): ResolveResponse {
	return { job: createJob({ status: 'identified' }), fan_out: [] };
}

describe('IdentifyDialog', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	describe('video job', () => {
		it('renders title + year inputs and submits title/year with no metadata', async () => {
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
					metadata: undefined
				});
				expect(onidentified).toHaveBeenCalledTimes(1);
			});
		});
	});

	describe('music job', () => {
		it('renders album + artist + per-track inputs and submits the music metadata shape', async () => {
			resolveJobMock.mockResolvedValue(makeResp());
			const onidentified = vi.fn();
			const job = createJob({
				id: 'job_cd',
				disc_type: 'cd',
				status: 'awaiting_user_id',
				title: '',
				year: null,
				metadata_json: { scan_result: { titles: [{}, {}] } }
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
					metadata: {
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
				metadata_json: { scan_result: { titles: [] } }
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
