import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderComponent, screen, fireEvent, cleanup, waitFor } from '$lib/test-utils';
import ApplySessionDialog from '../ApplySessionDialog.svelte';
import { createJob } from '../__fixtures__/job';
import { fetchSessions } from '$lib/api/sessions';
import { applySession } from '$lib/api/jobs';
import { ApiError } from '$lib/api/client';
import type { SessionView, ApplySessionResponse, CollisionInfo } from '$lib/types/api.gen';

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn()
}));
vi.mock('$lib/api/jobs', () => ({
	applySession: vi.fn()
}));

const fetchSessionsMock = vi.mocked(fetchSessions);
const applySessionMock = vi.mocked(applySession);

function createSession(overrides: Partial<SessionView> = {}): SessionView {
	return {
		id: 'ses_1',
		name: 'Session 1',
		media_type: 'movie',
		is_builtin: false,
		rip_preset_id: 'rip_1',
		transcode_preset_id: 'tx_1',
		output_path_template: '{title}/{title}.mkv',
		overrides_json: null,
		created_by_user_id: null,
		created_at: null,
		updated_at: null,
		...overrides
	};
}

function makeApplyResp(): ApplySessionResponse {
	return {
		session_application: {} as ApplySessionResponse['session_application'],
		tasks: [],
		collisions: [],
		idempotent: false
	};
}

describe('ApplySessionDialog', () => {
	afterEach(() => {
		cleanup();
		vi.clearAllMocks();
	});

	it('fetches sessions on mount and lists only media-type-matching (+ tv) sessions', async () => {
		fetchSessionsMock.mockResolvedValue([
			createSession({ id: 'ses_movie', name: 'Movie MKV', media_type: 'movie' }),
			createSession({ id: 'ses_tv', name: 'TV Episodes', media_type: 'tv' }),
			createSession({ id: 'ses_music', name: 'Music FLAC', media_type: 'music' }),
			createSession({ id: 'ses_data', name: 'Data ISO', media_type: 'data' })
		]);
		const job = createJob({ id: 'job_1', disc_type: 'bluray' });
		renderComponent(ApplySessionDialog, {
			props: { job, onclose: vi.fn(), onapplied: vi.fn() }
		});

		await waitFor(() => expect(fetchSessionsMock).toHaveBeenCalledTimes(1));
		await waitFor(() => {
			expect(screen.getByText(/Movie MKV/)).toBeInTheDocument();
		});
		expect(screen.getByText(/TV Episodes/)).toBeInTheDocument();
		expect(screen.queryByText(/Music FLAC/)).not.toBeInTheDocument();
		expect(screen.queryByText(/Data ISO/)).not.toBeInTheDocument();
	});

	it('shows all sessions when the disc type maps to no media type (unknown)', async () => {
		fetchSessionsMock.mockResolvedValue([
			createSession({ id: 'ses_movie', name: 'Movie MKV', media_type: 'movie' }),
			createSession({ id: 'ses_music', name: 'Music FLAC', media_type: 'music' })
		]);
		const job = createJob({ id: 'job_u', disc_type: 'unknown' });
		renderComponent(ApplySessionDialog, {
			props: { job, onclose: vi.fn(), onapplied: vi.fn() }
		});

		await waitFor(() => {
			expect(screen.getByText(/Movie MKV/)).toBeInTheDocument();
		});
		expect(screen.getByText(/Music FLAC/)).toBeInTheDocument();
	});

	it('applies the selected session with overwrite:false and fires onapplied on success', async () => {
		fetchSessionsMock.mockResolvedValue([createSession({ id: 'ses_movie', name: 'Movie MKV' })]);
		applySessionMock.mockResolvedValue(makeApplyResp());
		const onapplied = vi.fn();
		const job = createJob({ id: 'job_1', disc_type: 'bluray' });
		renderComponent(ApplySessionDialog, {
			props: { job, onclose: vi.fn(), onapplied }
		});

		await waitFor(() => expect(screen.getByText(/Movie MKV/)).toBeInTheDocument());
		const select = screen.getByTestId('apply-session-select') as HTMLSelectElement;
		await fireEvent.change(select, { target: { value: 'ses_movie' } });
		await fireEvent.click(screen.getByTestId('apply-session-apply'));

		await waitFor(() => {
			expect(applySessionMock).toHaveBeenCalledWith('job_1', {
				session_id: 'ses_movie',
				overwrite: false
			});
			expect(onapplied).toHaveBeenCalledTimes(1);
		});
	});

	it('renders the collision rows and an Overwrite button for an on_disk collision', async () => {
		fetchSessionsMock.mockResolvedValue([createSession({ id: 'ses_movie', name: 'Movie MKV' })]);
		const collisions: CollisionInfo[] = [
			{
				output_path: '/m/x.mkv',
				existing_task_id: null,
				on_filesystem: true,
				reason: 'on_disk'
			}
		];
		applySessionMock
			.mockRejectedValueOnce(
				new ApiError(409, 'API 409: Conflict', {
					detail: { message: 'collision', collisions }
				})
			)
			.mockResolvedValueOnce(makeApplyResp());
		const onapplied = vi.fn();
		const job = createJob({ id: 'job_1', disc_type: 'bluray' });
		renderComponent(ApplySessionDialog, {
			props: { job, onclose: vi.fn(), onapplied }
		});

		await waitFor(() => expect(screen.getByText(/Movie MKV/)).toBeInTheDocument());
		await fireEvent.change(screen.getByTestId('apply-session-select'), {
			target: { value: 'ses_movie' }
		});
		await fireEvent.click(screen.getByTestId('apply-session-apply'));

		await waitFor(() => {
			expect(screen.getByText('/m/x.mkv')).toBeInTheDocument();
			expect(screen.getByText(/exists on disk/)).toBeInTheDocument();
		});

		const overwrite = screen.getByTestId('apply-session-overwrite');
		expect(overwrite).toBeInTheDocument();
		await fireEvent.click(overwrite);

		await waitFor(() => {
			expect(applySessionMock).toHaveBeenLastCalledWith('job_1', {
				session_id: 'ses_movie',
				overwrite: true
			});
			expect(onapplied).toHaveBeenCalledTimes(1);
		});
	});

	it('hides the Overwrite button and shows the explanation for a duplicate_in_request collision', async () => {
		fetchSessionsMock.mockResolvedValue([createSession({ id: 'ses_movie', name: 'Movie MKV' })]);
		const collisions: CollisionInfo[] = [
			{
				output_path: '/m/dup.mkv',
				existing_task_id: null,
				on_filesystem: false,
				reason: 'duplicate_in_request'
			}
		];
		applySessionMock.mockRejectedValue(
			new ApiError(409, 'API 409: Conflict', {
				detail: { message: 'collision', collisions }
			})
		);
		const job = createJob({ id: 'job_1', disc_type: 'bluray' });
		renderComponent(ApplySessionDialog, {
			props: { job, onclose: vi.fn(), onapplied: vi.fn() }
		});

		await waitFor(() => expect(screen.getByText(/Movie MKV/)).toBeInTheDocument());
		await fireEvent.change(screen.getByTestId('apply-session-select'), {
			target: { value: 'ses_movie' }
		});
		await fireEvent.click(screen.getByTestId('apply-session-apply'));

		await waitFor(() => {
			expect(screen.getByText('/m/dup.mkv')).toBeInTheDocument();
			expect(screen.getByText(/duplicate within this apply/)).toBeInTheDocument();
		});
		expect(screen.queryByTestId('apply-session-overwrite')).not.toBeInTheDocument();
		expect(screen.getByText(/resolve to the same output path/)).toBeInTheDocument();
	});
});
