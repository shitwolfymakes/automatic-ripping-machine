import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/test-utils';
import JobDetailPage from '../[id]/+page.svelte';
import { createJob, createTrack } from '$lib/components/__fixtures__/job';
import type { JobView, JobDetailView, SessionView, ApplySessionResponse } from '$lib/types/api.gen';

vi.mock('$app/stores', async () => {
	const { readable } = await import('svelte/store');
	return { page: readable({ params: { id: 'job_1' } }) };
});

vi.mock('$app/navigation', () => ({
	goto: vi.fn()
}));

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		// Test-only helper — not part of the real module's public API.
		__setRole: (r: string | null) => _role.set(r)
	};
});

const { buildDetail } = vi.hoisted(() => {
	return {
		buildDetail: (jobOverrides: Partial<JobView> = {}): JobDetailView => ({
			job: createJob({
				id: 'job_1',
				title: 'Test Movie',
				status: 'ripped',
				year: 2024,
				disc_type: 'bluray',
				...jobOverrides
			}),
			tracks: [
				createTrack({
					id: 'trk_1',
					index: 1,
					source_ref: 'title_01.mkv',
					status: 'done'
				})
			],
			fingerprints: []
		})
	};
});

vi.mock('$lib/api/jobs', () => ({
	fetchJob: vi.fn(() => Promise.resolve(buildDetail())),
	fetchNamingPreview: vi.fn(() => Promise.resolve({ job_output_dir: '', job_output_name: '', items: [] })),
	updateTrack: vi.fn(() => Promise.resolve()),
	resolveJob: vi.fn(() => Promise.resolve({ job: {}, fan_out: [] })),
	applySession: vi.fn(() => Promise.resolve({ session_application: {}, tasks: [], collisions: [], idempotent: false }))
}));

vi.mock('$lib/api/sessions', () => ({
	fetchSessions: vi.fn(() => Promise.resolve([]))
}));

vi.mock('$lib/api/logs', () => ({
	fetchStructuredLogContent: vi.fn(() => Promise.resolve({ entries: [] })),
	fetchStructuredTranscoderLogContent: vi.fn(() => Promise.resolve({ entries: [] })),
	fetchTranscoderLogForArmJob: vi.fn(() => Promise.resolve(null)),
	fetchJobLog: vi.fn(() => Promise.resolve([])),
	jobLogDownloadUrl: (id: string) => `/api/logs/${id}.zip`
}));

// The job log panel opens its own WS subscription for an active job (this
// suite's fixture job is 'ripped', a terminal status, so it never
// subscribes) - stub the client so no real WebSocket gets created in jsdom.
vi.mock('$lib/api/ws', () => ({
	wsClient: { subscribe: vi.fn(() => vi.fn()), start: vi.fn(), stop: vi.fn() }
}));

vi.mock('$lib/api/settings', () => ({
	fetchSettings: vi.fn(() => Promise.resolve({ transcoder_config: { config: {} } }))
}));

describe('Job Detail Page', () => {
	afterEach(() => cleanup());

	describe('rendering', () => {
		it('renders job title after loading', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByRole('heading', { name: 'Test Movie' })).toBeInTheDocument();
			});
		});

		it('renders breadcrumb navigation', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByText('Dashboard')).toBeInTheDocument();
			});
		});

		it('renders disc type', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByText('Blu-ray')).toBeInTheDocument();
			});
		});

		it('renders tracks table', async () => {
			renderComponent(JobDetailPage);
			// Source column was replaced by Kind + Filename; assert on the Kind header.
			await waitFor(() => {
				expect(screen.getByRole('columnheader', { name: 'Kind' })).toBeInTheDocument();
			});
		});

		it('renders without crashing', () => {
			const { container } = renderComponent(JobDetailPage);
			expect(container).toBeInTheDocument();
		});

		it('shows the poster/metadata-search tab for video discs', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByRole('button', { name: /Poster & metadata search/ })).toBeInTheDocument();
			});
		});

		it('hides the poster/metadata-search tab for non-video discs', async () => {
			const { fetchJob } = await import('$lib/api/jobs');
			const detail = buildDetail({ id: 'job_2', title: 'Data Disc', disc_type: 'data' });
			detail.tracks = [];
			vi.mocked(fetchJob).mockResolvedValueOnce(detail as never);

			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByRole('heading', { name: 'Data Disc' })).toBeInTheDocument();
			});
			expect(screen.queryByRole('button', { name: /Poster & metadata search/ })).not.toBeInTheDocument();
		});

		it('shows Edit identity on a held review disc', async () => {
			const { fetchJob } = await import('$lib/api/jobs');
			vi.mocked(fetchJob).mockResolvedValueOnce(buildDetail({ status: 'awaiting_review' }));
			renderComponent(JobDetailPage);
			await waitFor(() => expect(screen.getByTestId('identify-open')).toHaveTextContent('Edit identity'));
		});

		it('shows Apply session for a ripped disc awaiting identification', async () => {
			const { fetchJob } = await import('$lib/api/jobs');
			vi.mocked(fetchJob).mockResolvedValueOnce(buildDetail({ status: 'ripped_awaiting_identify' }));
			renderComponent(JobDetailPage);
			await waitFor(() => expect(screen.getByTestId('apply-open')).toBeInTheDocument());
		});

		it('shows the Identify (resolve) and Apply session buttons for a resolvable status', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByTestId('identify-open')).toBeInTheDocument();
			});
			expect(screen.getByTestId('apply-open')).toBeInTheDocument();
		});
	});

	describe('error handling', () => {
		it('redirects to home on 404', async () => {
			const { fetchJob } = await import('$lib/api/jobs');
			const { goto } = await import('$app/navigation');
			vi.mocked(fetchJob).mockRejectedValueOnce(new Error('404 Not Found'));

			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(goto).toHaveBeenCalledWith('/');
			});
		});
	});

	describe('guest write-control gating', () => {
		afterEach(async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('admin');
		});

		it('hides Identify, Apply session, and Delete for guests', async () => {
			const auth = (await import('$lib/stores/auth')) as unknown as {
				__setRole: (r: string | null) => void;
			};
			auth.__setRole('guest');
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByRole('heading', { name: 'Test Movie' })).toBeInTheDocument();
			});
			expect(screen.queryByTestId('identify-open')).not.toBeInTheDocument();
			expect(screen.queryByTestId('apply-open')).not.toBeInTheDocument();
			expect(screen.queryByText('Delete')).not.toBeInTheDocument();
		});

		it('shows Identify, Apply session, and Delete for admins', async () => {
			renderComponent(JobDetailPage);
			await waitFor(() => {
				expect(screen.getByTestId('identify-open')).toBeInTheDocument();
			});
			expect(screen.getByTestId('apply-open')).toBeInTheDocument();
			expect(screen.getByText('Delete')).toBeInTheDocument();
		});
	});

	describe('apply note', () => {
		const session: SessionView = {
			id: 'ses_1',
			name: 'My Plex',
			media_type: 'movie',
			is_builtin: false,
			rip_preset_id: 'rpr_1',
			transcode_preset_id: null,
			output_path_template: '{title}/{title}.mkv',
			overrides_json: null,
			created_by_user_id: null,
			created_at: null,
			updated_at: null
		};

		async function applyVia(resp: ApplySessionResponse) {
			const { applySession } = await import('$lib/api/jobs');
			const { fetchSessions } = await import('$lib/api/sessions');
			vi.mocked(fetchSessions).mockResolvedValue([session]);
			vi.mocked(applySession).mockResolvedValueOnce(resp);
			renderComponent(JobDetailPage);
			await waitFor(() => expect(screen.getByTestId('apply-open')).toBeInTheDocument());
			await fireEvent.click(screen.getByTestId('apply-open'));
			const select = await screen.findByTestId('apply-session-select');
			await waitFor(() => expect(select.querySelector('option[value="ses_1"]')).not.toBeNull());
			await fireEvent.change(select, { target: { value: 'ses_1' } });
			await waitFor(() => expect(screen.getByTestId('apply-session-apply')).not.toBeDisabled());
			await fireEvent.click(screen.getByTestId('apply-session-apply'));
		}

		afterEach(async () => {
			const { fetchSessions } = await import('$lib/api/sessions');
			vi.mocked(fetchSessions).mockResolvedValue([]);
		});

		it('says the session is parked until the rip finishes when a held disc parks', async () => {
			const { fetchJob } = await import('$lib/api/jobs');
			vi.mocked(fetchJob).mockResolvedValue(buildDetail({ status: 'awaiting_review' }));
			try {
				await applyVia({
					session_application: { id: 'sap_1', session_id: 'ses_1', job_id: 'job_1', status: 'waiting_identify' },
					tasks: [],
					collisions: [],
					idempotent: false
				} as unknown as ApplySessionResponse);
				await waitFor(() =>
					expect(screen.getByText('Session parked; applies when the rip finishes')).toBeInTheDocument()
				);
				expect(screen.queryByText(/transcode tasks? queued/)).not.toBeInTheDocument();
			} finally {
				vi.mocked(fetchJob).mockImplementation(() => Promise.resolve(buildDetail()));
			}
		});

		it('does not promise a rip-complete fan-out when a ripped job parks', async () => {
			const { fetchJob } = await import('$lib/api/jobs');
			vi.mocked(fetchJob).mockResolvedValue(buildDetail({ status: 'ripped_awaiting_identify' }));
			try {
				await applyVia({
					session_application: { id: 'sap_1', session_id: 'ses_1', job_id: 'job_1', status: 'waiting_identify' },
					tasks: [],
					collisions: [],
					idempotent: false
				} as unknown as ApplySessionResponse);
				await waitFor(() => expect(screen.getByText('Session parked; waiting')).toBeInTheDocument());
			} finally {
				vi.mocked(fetchJob).mockImplementation(() => Promise.resolve(buildDetail()));
			}
		});

		it('counts queued transcode tasks when the apply fans out', async () => {
			await applyVia({
				session_application: { id: 'sap_1', session_id: 'ses_1', job_id: 'job_1', status: 'queued' },
				tasks: [{ id: 'tsk_1' }, { id: 'tsk_2' }],
				collisions: [],
				idempotent: false
			} as unknown as ApplySessionResponse);
			await waitFor(() => expect(screen.getByText('2 transcode tasks queued')).toBeInTheDocument());
		});
	});

	describe('refresh', () => {
		beforeEach(async () => {
			const { stopRipperEvents } = await import('$lib/stores/ripperEvents.svelte');
			stopRipperEvents();
		});
		afterEach(() => vi.useRealTimers());

		it('keeps refreshing a ripped job while it transcodes', async () => {
			vi.useFakeTimers();
			const { fetchJob } = await import('$lib/api/jobs');
			vi.mocked(fetchJob).mockResolvedValue(
				buildDetail({
					status: 'ripped',
					transcode_progress: { state: 'transcoding', tasks_total: 1, tasks_done: 0, tasks_failed: 0, percent: 5 }
				})
			);
			renderComponent(JobDetailPage);
			await vi.advanceTimersByTimeAsync(0);
			const before = vi.mocked(fetchJob).mock.calls.length;
			await vi.advanceTimersByTimeAsync(15000);
			expect(vi.mocked(fetchJob).mock.calls.length).toBeGreaterThanOrEqual(before + 3);
		});

		it('stops fetching once the transcode is done, and resumes if it goes live again', async () => {
			vi.useFakeTimers();
			const { fetchJob } = await import('$lib/api/jobs');
			const done = buildDetail({
				status: 'ripped',
				transcode_progress: { state: 'done', tasks_total: 1, tasks_done: 1, tasks_failed: 0, percent: 100 }
			});
			const live = buildDetail({
				status: 'ripped',
				transcode_progress: { state: 'transcoding', tasks_total: 2, tasks_done: 1, tasks_failed: 0, percent: 50 }
			});
			vi.mocked(fetchJob).mockResolvedValue(done);
			renderComponent(JobDetailPage);
			await vi.advanceTimersByTimeAsync(0);
			const settled = vi.mocked(fetchJob).mock.calls.length;
			await vi.advanceTimersByTimeAsync(15000);
			expect(vi.mocked(fetchJob).mock.calls.length).toBe(settled);

			// A WS event (e.g. a new apply) reloads the job; it is live again.
			vi.mocked(fetchJob).mockResolvedValue(live);
			const { wsClient } = await import('$lib/api/ws');
			const handler = vi.mocked(wsClient.subscribe).mock.calls.find(([topic]) => topic === 'transcode.events')?.[1] as (
				e: unknown
			) => void;
			handler({
				op: 'event',
				event_id: 'evt_1',
				event_type: 'session.queued',
				emitted_at: '2026-09-29T00:00:00Z',
				topic: 'transcode.events',
				job_id: 'job_1',
				track_id: null,
				payload: {}
			});
			await vi.advanceTimersByTimeAsync(400);
			const afterEvent = vi.mocked(fetchJob).mock.calls.length;
			await vi.advanceTimersByTimeAsync(10000);
			expect(vi.mocked(fetchJob).mock.calls.length).toBeGreaterThanOrEqual(afterEvent + 2);
		});
	});
});
