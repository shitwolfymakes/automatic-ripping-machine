import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent, within } from '$lib/test-utils';
import DashboardPage from '../+page.svelte';
import { createJob } from '$lib/__fixtures__/job';
import { fetchDashboard } from '$lib/api/dashboard';
import { fetchJobsPage, bulkDeleteJobs, abandonJob, deleteJob } from '$lib/api/jobs';
import { setTranscoderEnabled } from '$lib/stores/config';
import type { JobView } from '$lib/types/api.gen';

// Hoisted so the module mocks below can share them with the tests.
const h = vi.hoisted(() => ({
	ripperListeners: [] as Array<(ids: Set<string>, types: Map<string, Set<string>>) => void>,
	offRipperEvents: vi.fn(),
	startRipperEvents: vi.fn(),
	startWS: vi.fn(),
	stopWS: vi.fn(),
	reconcileSubscriptions: vi.fn(),
	ripProgress: { value: {} as Record<string, unknown> }
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

// jsdom cannot run Web Animations; a transition with no duration finishes at once.
vi.mock('svelte/transition', () => ({
	fade: () => ({ duration: 0 }),
	slide: () => ({ duration: 0 })
}));

vi.mock('$lib/stores/rips.svelte', () => ({
	ripProgress: h.ripProgress,
	startWS: h.startWS,
	stopWS: h.stopWS,
	reconcileSubscriptions: h.reconcileSubscriptions
}));

vi.mock('$lib/stores/ripper-events.svelte', () => ({
	startRipperEvents: h.startRipperEvents,
	// The review cards register listeners of their own besides the page's.
	onRipperEvent: (cb: (ids: Set<string>, types: Map<string, Set<string>>) => void) => {
		h.ripperListeners.push(cb);
		return h.offRipperEvents;
	}
}));

vi.mock('$lib/api/dashboard', () => ({ fetchDashboard: vi.fn() }));

vi.mock('$lib/api/jobs', () => ({
	fetchJobsPage: vi.fn(),
	bulkDeleteJobs: vi.fn(),
	// The review card loads its own detail; failing keeps the job it was given.
	fetchJob: vi.fn(() => Promise.reject(new Error('no detail'))),
	fetchNamingPreview: vi.fn(() => Promise.reject(new Error('no preview'))),
	abandonJob: vi.fn(() => Promise.resolve({})),
	deleteJob: vi.fn(() => Promise.resolve()),
	startWaitingJob: vi.fn(),
	pauseWaitingJob: vi.fn(),
	resolveJob: vi.fn()
}));

vi.mock('$lib/api/sessions', () => ({ fetchSessions: vi.fn(() => Promise.resolve([])) }));
vi.mock('$lib/api/iso', () => ({ cancelIsoRip: vi.fn(() => Promise.resolve()) }));
vi.mock('$lib/api/setup', () => ({
	fetchSetup: vi.fn(() => Promise.reject(new Error('no setup'))),
	dismissSetupChecklist: vi.fn()
}));
vi.mock('$lib/api/logs', () => ({ fetchStructuredLogContent: vi.fn(() => Promise.resolve({ entries: [] })) }));

const AT = '2026-10-02T14:00:00Z';

type DashOverrides = Record<string, unknown>;

function dash(overrides: DashOverrides = {}) {
	return {
		db_available: true,
		arm_online: true,
		active_jobs: [] as JobView[],
		drives_online: 1,
		drive_names: { drv_1: 'Main Drive' },
		iso_sources: {},
		iso_source_kinds: {},
		preparing: [],
		notification_count: 0,
		ripping_enabled: true,
		makemkv_key_valid: null,
		makemkv_key_checked_at: null,
		transcoder_online: true,
		transcoder_stats: null,
		active_transcodes: [],
		...overrides
	};
}

function job(id: string, status: string | null, extra: Partial<JobView> = {}): JobView {
	return createJob({ id, status: status as JobView['status'], title: `Title ${id}`, drive_id: null, ...extra });
}

function listed(id: string, title = `Listed ${id}`): JobView {
	return createJob({ id, title, status: 'failed' });
}

function prepare(driveId: string, isoName: string) {
	return { drive_id: driveId, phase: 'scanning', updated_at: AT, iso_name: isoName, iso_kind: 'iso' };
}

function transcode(id: string, name: string) {
	return { id, status: 'queued', output_path: `/out/${name}`, created_at: AT };
}

function setDashboard(value: unknown) {
	vi.mocked(fetchDashboard).mockResolvedValue(value as Awaited<ReturnType<typeof fetchDashboard>>);
}

function setJobs(jobs: JobView[], total = jobs.length) {
	vi.mocked(fetchJobsPage).mockResolvedValue({ jobs, total });
}

function deferred<T>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

async function setRole(role: string | null) {
	const auth = (await import('$lib/stores/auth')) as unknown as { __setRole: (r: string | null) => void };
	auth.__setRole(role);
}

async function renderPage() {
	const view = renderComponent(DashboardPage);
	await waitFor(() => expect(screen.getByText('Dashboard')).toBeInTheDocument());
	return view;
}

async function renderTable() {
	const view = await renderPage();
	await fireEvent.click(screen.getByText('Table'));
	await waitFor(() => expect(screen.getByText('Title')).toBeInTheDocument());
	return view;
}

/** Runs every registered ripper-event listener, as a WS burst would. */
function fireRipperEvent() {
	for (const listener of [...h.ripperListeners]) listener(new Set(), new Map());
}

/** Deletes the first ripped review card through its confirm dialog. */
async function deleteFirstReviewCard() {
	const [del] = await screen.findAllByRole('button', { name: 'Delete' });
	await fireEvent.click(del);
	await fireEvent.click(within(screen.getByRole('dialog')).getByRole('button', { name: 'Delete' }));
}

beforeEach(() => {
	vi.clearAllMocks();
	h.ripperListeners = [];
	h.ripProgress.value = {};
	setDashboard(dash());
	setJobs([listed('l1')]);
	vi.mocked(bulkDeleteJobs).mockResolvedValue({ deleted_ids: [], skipped_non_terminal: [] });
});

afterEach(async () => {
	cleanup();
	vi.useRealTimers();
	vi.restoreAllMocks();
	setTranscoderEnabled(true);
	await setRole('admin');
});

describe('Dashboard sections', () => {
	describe('labels', () => {
		it.each([
			['one disc', 1, 'WAITING FOR REVIEW - 1 DISC'],
			['two discs', 2, 'WAITING FOR REVIEW - 2 DISCS']
		])('WAITING FOR REVIEW with %s', async (_name, count, label) => {
			setDashboard(dash({ active_jobs: Array.from({ length: count }, (_, i) => job(`w${i}`, 'awaiting_user_id')) }));
			await renderPage();
			await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument());
		});

		it.each([
			['one ISO', 1, 'PREPARING - 1 ISO'],
			['two ISOs', 2, 'PREPARING - 2 ISOS']
		])('PREPARING with %s', async (_name, count, label) => {
			setDashboard(dash({ preparing: Array.from({ length: count }, (_, i) => prepare(`drv_p${i}`, `disc${i}.iso`)) }));
			await renderPage();
			await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument());
		});

		it.each([
			['one disc', 1, 'SCANNING - 1 DISC'],
			['two discs', 2, 'SCANNING - 2 DISCS']
		])('SCANNING with %s', async (_name, count, label) => {
			setDashboard(dash({ active_jobs: Array.from({ length: count }, (_, i) => job(`s${i}`, 'created')) }));
			await renderPage();
			await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument());
		});

		it('ACTIVE RIPS counts the ripping jobs', async () => {
			setDashboard(dash({ active_jobs: [job('r1', 'ripping'), job('r2', 'ripping')] }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('ACTIVE RIPS - 2 IN PROGRESS')).toBeInTheDocument());
		});

		it.each([
			['one job', 1, 'FINISHING - 1 JOB'],
			['two jobs', 2, 'FINISHING - 2 JOBS']
		])('FINISHING with %s (the ripped cards were dismissed)', async (_name, count, label) => {
			setDashboard(dash({ active_jobs: Array.from({ length: count }, (_, i) => job(`f${i}`, 'ripped')) }));
			await renderPage();
			for (let n = 1; n <= count; n++) {
				await deleteFirstReviewCard();
				await waitFor(() => expect(deleteJob).toHaveBeenCalledTimes(n));
			}
			await waitFor(() => expect(screen.getByText(label)).toBeInTheDocument());
			expect(screen.queryByText(/WAITING FOR REVIEW/)).toBeNull();
		});

		it('TRANSCODING shows while the transcoder is enabled', async () => {
			setDashboard(dash({ active_transcodes: [transcode('tx_1', 'Encode One.mkv')] }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('TRANSCODING - 1 ACTIVE')).toBeInTheDocument());
			expect(screen.getByText('Encode One.mkv')).toBeInTheDocument();
		});

		it('TRANSCODING is hidden while the transcoder is disabled', async () => {
			setTranscoderEnabled(false);
			setDashboard(dash({ active_transcodes: [transcode('tx_1', 'Encode One.mkv')] }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('1 job')).toBeInTheDocument());
			expect(screen.queryByText(/TRANSCODING/)).toBeNull();
			expect(screen.queryByText('Encode One.mkv')).toBeNull();
		});

		it('shows no section when the dashboard has nothing active', async () => {
			await renderPage();
			await waitFor(() => expect(screen.getByText('No active rips or transcodes')).toBeInTheDocument());
			for (const label of [/WAITING/, /PREPARING/, /SCANNING/, /ACTIVE RIPS/, /FINISHING/, /TRANSCODING/]) {
				expect(screen.queryByText(label)).toBeNull();
			}
		});
	});

	describe('sections leave as the dashboard empties', () => {
		const ids = (n: number) => Array.from({ length: n }, (_, i) => `x${i}`);
		const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);
		const sections: Array<[string, (n: number) => unknown, (n: number) => string, RegExp]> = [
			[
				'WAITING FOR REVIEW',
				(n) => dash({ active_jobs: ids(n).map((id) => job(id, 'awaiting_user_id')) }),
				(n) => `WAITING FOR REVIEW - ${n} ${plural(n, 'DISC', 'DISCS')}`,
				/WAITING FOR REVIEW/
			],
			[
				'PREPARING',
				(n) => dash({ preparing: ids(n).map((id) => prepare(`drv_${id}`, `${id}.iso`)) }),
				(n) => `PREPARING - ${n} ${plural(n, 'ISO', 'ISOS')}`,
				/PREPARING/
			],
			[
				'SCANNING',
				(n) => dash({ active_jobs: ids(n).map((id) => job(id, 'created')) }),
				(n) => `SCANNING - ${n} ${plural(n, 'DISC', 'DISCS')}`,
				/SCANNING/
			],
			[
				'ACTIVE RIPS',
				(n) => dash({ active_jobs: ids(n).map((id) => job(id, 'ripping')) }),
				(n) => `ACTIVE RIPS - ${n} IN PROGRESS`,
				/ACTIVE RIPS/
			],
			[
				'TRANSCODING',
				(n) => dash({ active_transcodes: ids(n).map((id) => transcode(id, `${id}.mkv`)) }),
				(n) => `TRANSCODING - ${n} ACTIVE`,
				/TRANSCODING/
			]
		];

		it.each(sections)('%s gains a row, drops it, then the whole section', async (_name, build, label, pattern) => {
			setDashboard(build(1));
			await renderPage();
			await waitFor(() => expect(screen.getByText(label(1))).toBeInTheDocument());
			setDashboard(build(2));
			fireRipperEvent();
			await waitFor(() => expect(screen.getByText(label(2))).toBeInTheDocument());
			setDashboard(build(1));
			fireRipperEvent();
			await waitFor(() => expect(screen.getByText(label(1))).toBeInTheDocument());
			setDashboard(build(0));
			fireRipperEvent();
			await waitFor(() => expect(screen.queryByText(pattern)).toBeNull());
		});

		it('FINISHING drops a row, then the whole section', async () => {
			const rippedJobs = (n: number) => ids(n).map((id) => job(id, 'ripped'));
			setDashboard(dash({ active_jobs: rippedJobs(2) }));
			await renderPage();
			await deleteFirstReviewCard();
			await waitFor(() => expect(deleteJob).toHaveBeenCalledTimes(1));
			await deleteFirstReviewCard();
			await waitFor(() => expect(screen.getByText('FINISHING - 2 JOBS')).toBeInTheDocument());
			setDashboard(dash({ active_jobs: rippedJobs(1) }));
			fireRipperEvent();
			await waitFor(() => expect(screen.getByText('FINISHING - 1 JOB')).toBeInTheDocument());
			setDashboard(dash());
			fireRipperEvent();
			await waitFor(() => expect(screen.queryByText(/FINISHING/)).toBeNull());
		});
	});

	describe('which job lands where', () => {
		it('sorts each status into its section', async () => {
			setDashboard(
				dash({
					active_jobs: [
						job('a_created', 'created'),
						job('a_ripping', 'ripping'),
						job('a_awaiting_user_id', 'awaiting_user_id'),
						job('a_ripped_awaiting_identify', 'ripped_awaiting_identify'),
						job('a_awaiting_review', 'awaiting_review'),
						job('a_identified', 'identified'),
						job('a_ripped', 'ripped'),
						job('a_ripped_partial', 'ripped_partial')
					]
				})
			);
			await renderPage();
			await waitFor(() => expect(screen.getByText('WAITING FOR REVIEW - 6 DISCS')).toBeInTheDocument());
			expect(screen.getByText('SCANNING - 1 DISC')).toBeInTheDocument();
			expect(screen.getByText('ACTIVE RIPS - 1 IN PROGRESS')).toBeInTheDocument();
			expect(screen.queryByText(/FINISHING/)).toBeNull();
		});

		it('leaves a job with no status and a job past ripping out of every section', async () => {
			setDashboard(dash({ active_jobs: [job('a_none', null), job('a_failed', 'failed')] }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('No active rips or transcodes')).toBeInTheDocument());
		});

		it('treats status case-insensitively', async () => {
			setDashboard(dash({ active_jobs: [job('a_upper', 'CREATED')] }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('SCANNING - 1 DISC')).toBeInTheDocument());
		});

		it('keeps a ripped job with an applied session out of WAITING and FINISHING', async () => {
			const transcoding = job('a_tx', 'ripped', {
				transcode_progress: { state: 'transcoding', tasks_total: 2, tasks_done: 0 }
			} as Partial<JobView>);
			setDashboard(dash({ active_jobs: [transcoding] }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('No active rips or transcodes')).toBeInTheDocument());
		});

		it('shows a dashboard without active_jobs or preparing as idle', async () => {
			setDashboard(dash({ active_jobs: undefined, preparing: undefined }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('No active rips or transcodes')).toBeInTheDocument());
		});
	});

	describe('sticky review', () => {
		it('keeps the card when a later poll reports the job as identified, until it is dismissed', async () => {
			setDashboard(dash({ active_jobs: [job('rev', 'awaiting_review')] }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('WAITING FOR REVIEW - 1 DISC')).toBeInTheDocument());

			const polls = vi.mocked(fetchDashboard).mock.calls.length;
			setDashboard(dash({ active_jobs: [job('rev', 'identified')] }));
			fireRipperEvent();
			await waitFor(() => expect(fetchDashboard).toHaveBeenCalledTimes(polls + 1));
			expect(screen.getByText('WAITING FOR REVIEW - 1 DISC')).toBeInTheDocument();

			await fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));
			await waitFor(() => expect(abandonJob).toHaveBeenCalledWith('rev'));
			await waitFor(() => expect(screen.queryByText(/WAITING FOR REVIEW/)).toBeNull());

			const afterDismiss = vi.mocked(fetchDashboard).mock.calls.length;
			fireRipperEvent();
			await waitFor(() => expect(vi.mocked(fetchDashboard).mock.calls.length).toBeGreaterThan(afterDismiss));
			await new Promise((r) => setTimeout(r, 0));
			expect(screen.queryByText(/WAITING FOR REVIEW/)).toBeNull();
		});

		it('drops a card that was never sticky once its dismissal is reported', async () => {
			setDashboard(dash({ active_jobs: [job('done', 'ripped')] }));
			await renderPage();
			await deleteFirstReviewCard();
			await waitFor(() => expect(deleteJob).toHaveBeenCalledWith('done'));
			await waitFor(() => expect(screen.queryByText(/WAITING FOR REVIEW/)).toBeNull());
		});

		it('keeps a sticky job out of WAITING once it moves on to ripping', async () => {
			setDashboard(dash({ active_jobs: [job('mv', 'awaiting_review')] }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('WAITING FOR REVIEW - 1 DISC')).toBeInTheDocument());
			setDashboard(dash({ active_jobs: [job('mv', 'ripping')] }));
			fireRipperEvent();
			await waitFor(() => expect(screen.getByText('ACTIVE RIPS - 1 IN PROGRESS')).toBeInTheDocument());
			expect(screen.queryByText(/WAITING FOR REVIEW/)).toBeNull();
		});
	});

	describe('ISO sources and live progress', () => {
		const sources = {
			iso_sources: { drv_iso: 'Movie.iso', drv_folder: 'Disc One' },
			iso_source_kinds: { drv_folder: 'folder' }
		};

		it.each([
			['SCANNING', 'created'],
			['ACTIVE RIPS', 'ripping']
		])('%s rows carry the ISO or folder chip of their drive', async (_section, status) => {
			setDashboard(
				dash({
					...sources,
					active_jobs: [
						job('on_iso', status, { drive_id: 'drv_iso' }),
						job('on_folder', status, { drive_id: 'drv_folder' }),
						job('on_disc', status, { drive_id: 'drv_1' }),
						job('no_drive', status, { drive_id: null })
					]
				})
			);
			await renderPage();
			await waitFor(() => expect(screen.getByLabelText('ISO file Movie.iso')).toBeInTheDocument());
			expect(screen.getByLabelText('Disc folder Disc One')).toBeInTheDocument();
			expect(screen.getAllByLabelText(/^(ISO file|Disc folder) /)).toHaveLength(2);
		});

		it('hands the ISO sources and kinds to a waiting review card', async () => {
			setDashboard(
				dash({
					...sources,
					active_jobs: [
						job('w_iso', 'awaiting_user_id', { drive_id: 'drv_iso' }),
						job('w_folder', 'awaiting_user_id', { drive_id: 'drv_folder' })
					]
				})
			);
			await renderPage();
			await waitFor(() => expect(screen.getByTitle('Movie.iso')).toHaveTextContent('Movie.iso'));
			expect(screen.getByTitle('Disc One')).toHaveTextContent('Disc One');
			expect(screen.getByText('Folder')).toBeInTheDocument();
		});

		it('falls back to an ISO chip when the drive has a source but no kind', async () => {
			setDashboard(
				dash({
					iso_sources: { drv_iso: 'Movie.iso' },
					iso_source_kinds: undefined,
					active_jobs: [job('a', 'ripping', { drive_id: 'drv_iso' })]
				})
			);
			await renderPage();
			await waitFor(() => expect(screen.getByLabelText('ISO file Movie.iso')).toBeInTheDocument());
		});

		it('shows no chip when the dashboard has no ISO sources at all', async () => {
			setDashboard(
				dash({
					iso_sources: undefined,
					iso_source_kinds: undefined,
					active_jobs: [job('c', 'created', { drive_id: 'drv_1' }), job('a', 'ripping', { drive_id: 'drv_1' })]
				})
			);
			await renderPage();
			await waitFor(() => expect(screen.getByText('SCANNING - 1 DISC')).toBeInTheDocument());
			expect(screen.queryByLabelText(/^(ISO file|Disc folder) /)).toBeNull();
		});

		it('passes the live rip progress to an active row', async () => {
			h.ripProgress.value = {
				live_job: {
					track_id: 't1',
					progress_pct: 42,
					eta_seconds: 600,
					bytes_done: 1024 * 1024 * 512,
					bytes_total: 1024 * 1024 * 1024,
					rate_bps: 1024 * 1024
				}
			};
			setDashboard(dash({ active_jobs: [job('live_job', 'ripping'), job('quiet_job', 'ripping')] }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('42%')).toBeInTheDocument());
			expect(screen.getByText('10m left')).toBeInTheDocument();
			expect(screen.getByText('512 MB of 1 GB · 1 MB/s')).toBeInTheDocument();
			expect(screen.getAllByText('42%')).toHaveLength(1);
		});

		it('subscribes the live progress to the ripping jobs only', async () => {
			setDashboard(dash({ active_jobs: [job('r1', 'ripping'), job('c1', 'created')] }));
			await renderPage();
			await waitFor(() => expect(h.reconcileSubscriptions).toHaveBeenLastCalledWith(['r1']));
		});

		it('lists preparing ISO rows with their file name', async () => {
			setDashboard(dash({ preparing: [prepare('drv_p0', 'Prep.iso')] }));
			await renderPage();
			await waitFor(() => expect(screen.getByLabelText('ISO file Prep.iso')).toBeInTheDocument());
			expect(screen.getByText('Scanning image')).toBeInTheDocument();
		});
	});

	describe('idle panel', () => {
		it('shows once both loads are done and every section is empty', async () => {
			await renderPage();
			await waitFor(() => expect(screen.getByText('No active rips or transcodes')).toBeInTheDocument());
			expect(screen.getByText(/Insert a disc to get started - 1 drive online/)).toBeInTheDocument();
		});

		it('waits for the dashboard load', async () => {
			vi.mocked(fetchDashboard).mockReturnValue(new Promise(() => {}));
			await renderPage();
			await waitFor(() => expect(screen.getByText('Listed l1')).toBeInTheDocument());
			expect(screen.queryByText('No active rips or transcodes')).toBeNull();
		});

		it('waits for the jobs load', async () => {
			vi.mocked(fetchJobsPage).mockReturnValue(new Promise(() => {}));
			await renderPage();
			await waitFor(() => expect(fetchDashboard).toHaveBeenCalled());
			await new Promise((r) => setTimeout(r, 20));
			expect(screen.queryByText('No active rips or transcodes')).toBeNull();
		});

		it.each([
			['a preparing ISO', { preparing: [prepare('drv_p0', 'a.iso')] }],
			['a scanning job', { active_jobs: [job('x', 'created')] }],
			['a waiting job', { active_jobs: [job('x', 'awaiting_review')] }],
			['an active rip', { active_jobs: [job('x', 'ripping')] }],
			['a transcode', { active_transcodes: [transcode('tx_1', 'e.mkv')] }]
		])('stays away with %s', async (_name, overrides) => {
			setDashboard(dash(overrides));
			await renderPage();
			await waitFor(() => expect(screen.getByText('1 job')).toBeInTheDocument());
			expect(screen.queryByText('No active rips or transcodes')).toBeNull();
		});

		it('stays away with a finishing job (a dismissed ripped card)', async () => {
			setDashboard(dash({ active_jobs: [job('x', 'ripped')] }));
			await renderPage();
			await deleteFirstReviewCard();
			await waitFor(() => expect(screen.getByText('FINISHING - 1 JOB')).toBeInTheDocument());
			expect(screen.queryByText('No active rips or transcodes')).toBeNull();
		});
	});

	describe('banners', () => {
		it('shows the pause banner once loaded while ripping is paused', async () => {
			setDashboard(dash({ ripping_enabled: false }));
			await renderPage();
			await waitFor(() => expect(screen.getByText('Ripping Paused')).toBeInTheDocument());
			expect(screen.getByText("New discs won't start ripping while paused.")).toBeInTheDocument();
		});

		it('hides the pause banner while ripping is enabled', async () => {
			await renderPage();
			await waitFor(() => expect(screen.getByText('1 job')).toBeInTheDocument());
			expect(screen.queryByText('Ripping Paused')).toBeNull();
		});

		it('hides the pause banner while the dashboard is still loading', async () => {
			vi.mocked(fetchDashboard).mockReturnValue(new Promise(() => {}));
			await renderPage();
			await waitFor(() => expect(screen.getByText('1 job')).toBeInTheDocument());
			expect(screen.queryByText('Ripping Paused')).toBeNull();
		});

		it('shows the backend error message from an Error', async () => {
			vi.mocked(fetchDashboard).mockRejectedValue(new Error('connection refused'));
			await renderPage();
			await waitFor(() => expect(screen.getByText(/Failed to reach backend: connection refused/)).toBeInTheDocument());
		});

		it('shows "Unknown error" when the rejection is not an Error', async () => {
			vi.mocked(fetchDashboard).mockRejectedValue('boom');
			await renderPage();
			await waitFor(() => expect(screen.getByText(/Failed to reach backend: Unknown error/)).toBeInTheDocument());
		});

		it('clears the backend error once a later poll succeeds', async () => {
			vi.mocked(fetchDashboard).mockRejectedValueOnce(new Error('blip'));
			await renderPage();
			await waitFor(() => expect(screen.getByText(/Failed to reach backend: blip/)).toBeInTheDocument());
			fireRipperEvent();
			await waitFor(() => expect(screen.queryByText(/Failed to reach backend/)).toBeNull());
		});
	});
});

describe('Dashboard All Jobs list', () => {
	describe('count and views', () => {
		it.each([
			[0, '0 jobs'],
			[1, '1 job'],
			[7, '7 jobs']
		])('says %i as "%s"', async (total, text) => {
			setJobs([listed('l1')], total);
			await renderPage();
			await waitFor(() => expect(screen.getByText(text)).toBeInTheDocument());
		});

		it('lists the jobs as cards, then as a table', async () => {
			setJobs([listed('l1'), listed('l2')]);
			await renderPage();
			await waitFor(() => expect(screen.getByText('Listed l1')).toBeInTheDocument());
			expect(screen.getByText('Cards')).toHaveAttribute('aria-pressed', 'true');
			expect(screen.queryByRole('table')).toBeNull();
			await fireEvent.click(screen.getByText('Table'));
			expect(screen.getByText('Table')).toHaveAttribute('aria-pressed', 'true');
			expect(screen.getByRole('table')).toBeInTheDocument();
			expect(screen.getByText('Listed l2')).toBeInTheDocument();
			await fireEvent.click(screen.getByText('Cards'));
			expect(screen.queryByRole('table')).toBeNull();
		});

		it('shows a skeleton card grid while loading in the card view', async () => {
			vi.mocked(fetchJobsPage).mockReturnValue(new Promise(() => {}));
			const { container } = await renderPage();
			await waitFor(() => expect(container.querySelector('.dashboard-jobs-grid')).not.toBeNull());
			expect(container.querySelector('.dashboard-jobs-grid')!.children).toHaveLength(6);
		});

		it('shows a skeleton table while loading in the table view', async () => {
			vi.mocked(fetchJobsPage).mockReturnValue(new Promise(() => {}));
			await renderPage();
			await fireEvent.click(screen.getByText('Table'));
			await waitFor(() => expect(screen.getAllByRole('row', { hidden: true })).toHaveLength(13));
			expect(screen.queryAllByRole('checkbox', { hidden: true })).toHaveLength(0);
		});

		it('shows the empty state', async () => {
			setJobs([], 0);
			await renderPage();
			await waitFor(() => expect(screen.getByText('No jobs found.')).toBeInTheDocument());
		});

		it('shows the load error message from an Error', async () => {
			vi.mocked(fetchJobsPage).mockRejectedValue(new Error('server down'));
			await renderPage();
			await waitFor(() => expect(screen.getByText('Failed to load: server down')).toBeInTheDocument());
		});

		it('shows a generic load error when the rejection is not an Error', async () => {
			vi.mocked(fetchJobsPage).mockRejectedValue('nope');
			await renderPage();
			await waitFor(() => expect(screen.getByText('Failed to load: Failed to load jobs')).toBeInTheDocument());
		});

		it('keeps the list on screen while a reload is in flight', async () => {
			await renderPage();
			await waitFor(() => expect(screen.getByText('Listed l1')).toBeInTheDocument());
			vi.mocked(fetchJobsPage).mockReturnValue(new Promise(() => {}));
			fireRipperEvent();
			await waitFor(() => expect(fetchJobsPage).toHaveBeenCalledTimes(2));
			expect(screen.getByText('Listed l1')).toBeInTheDocument();
		});
	});

	describe('paging', () => {
		it('asks for the page the pager picks', async () => {
			setJobs([listed('l1')], 100);
			await renderPage();
			await waitFor(() => expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 1–48 of 100'));
			await fireEvent.click(screen.getByText('3'));
			await waitFor(() => expect(fetchJobsPage).toHaveBeenLastCalledWith({ status: undefined, limit: 48, offset: 96 }));
		});

		it('steps back to the last page when the page it is on comes back empty', async () => {
			let total = 100;
			vi.mocked(fetchJobsPage).mockImplementation((params) => {
				const offset = params?.offset;
				if (offset && offset > 0) {
					total = 48;
					return Promise.resolve({ jobs: [], total });
				}
				return Promise.resolve({ jobs: [listed('l1')], total });
			});
			await renderPage();
			await waitFor(() => expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 1–48 of 100'));
			await fireEvent.click(screen.getByText('2'));
			await waitFor(() => expect(screen.getByTestId('jobs-pagination')).toHaveTextContent('Showing 1–48 of 48'));
			expect(fetchJobsPage).toHaveBeenLastCalledWith({ status: undefined, limit: 48, offset: 0 });
			expect(screen.getByText('Listed l1')).toBeInTheDocument();
		});

		it('shows the empty state when page one itself is empty', async () => {
			setJobs([], 0);
			await renderPage();
			await waitFor(() => expect(screen.getByText('No jobs found.')).toBeInTheDocument());
			expect(fetchJobsPage).toHaveBeenCalledTimes(1);
		});

		it('drops a slower, older response that succeeds after a newer one', async () => {
			await renderPage();
			await waitFor(() => expect(screen.getByText('Listed l1')).toBeInTheDocument());
			const stale = deferred<{ jobs: JobView[]; total: number }>();
			vi.mocked(fetchJobsPage).mockReturnValueOnce(stale.promise);
			fireRipperEvent();
			vi.mocked(fetchJobsPage).mockResolvedValueOnce({ jobs: [listed('fresh', 'Fresh Job')], total: 1 });
			fireRipperEvent();
			await waitFor(() => expect(screen.getByText('Fresh Job')).toBeInTheDocument());
			stale.resolve({ jobs: [listed('old', 'Stale Job')], total: 1 });
			await new Promise((r) => setTimeout(r, 0));
			expect(screen.queryByText('Stale Job')).toBeNull();
			expect(screen.getByText('Fresh Job')).toBeInTheDocument();
		});

		it('drops a slower, older response that fails after a newer one', async () => {
			await renderPage();
			await waitFor(() => expect(screen.getByText('Listed l1')).toBeInTheDocument());
			const stale = deferred<{ jobs: JobView[]; total: number }>();
			vi.mocked(fetchJobsPage).mockReturnValueOnce(stale.promise);
			fireRipperEvent();
			vi.mocked(fetchJobsPage).mockResolvedValueOnce({ jobs: [listed('fresh', 'Fresh Job')], total: 1 });
			fireRipperEvent();
			await waitFor(() => expect(screen.getByText('Fresh Job')).toBeInTheDocument());
			stale.reject(new Error('stale failure'));
			await new Promise((r) => setTimeout(r, 0));
			expect(screen.queryByText(/stale failure/)).toBeNull();
			expect(screen.getByText('Fresh Job')).toBeInTheDocument();
		});
	});

	describe('status filter', () => {
		it('goes back to page 1 with the new status and clears the selection', async () => {
			setJobs([listed('l1')], 100);
			await renderTable();
			await fireEvent.click(screen.getByText('2'));
			await waitFor(() => expect(fetchJobsPage).toHaveBeenLastCalledWith({ status: undefined, limit: 48, offset: 48 }));
			const [, rowCheckbox] = screen.getAllByRole('checkbox');
			await fireEvent.click(rowCheckbox);
			await screen.findByTestId('jobs-selection-bar');
			await fireEvent.change(screen.getByDisplayValue('All Status'), { target: { value: 'failed' } });
			await waitFor(() => expect(fetchJobsPage).toHaveBeenLastCalledWith({ status: 'failed', limit: 48, offset: 0 }));
			await waitFor(() => expect(screen.queryByTestId('jobs-selection-bar')).toBeNull());
		});
	});

	describe('selection', () => {
		beforeEach(() => setJobs([listed('l1'), listed('l2')]));

		it('selects and unselects a row', async () => {
			await renderTable();
			const [, first] = screen.getAllByRole('checkbox');
			await fireEvent.click(first);
			expect(await screen.findByTestId('jobs-selection-bar')).toHaveTextContent('1 selected');
			await fireEvent.click(screen.getAllByRole('checkbox')[1]);
			await waitFor(() => expect(screen.queryByTestId('jobs-selection-bar')).toBeNull());
		});

		it('selects all rows and clears them again from the header checkbox', async () => {
			await renderTable();
			await fireEvent.click(screen.getAllByRole('checkbox')[0]);
			expect(await screen.findByTestId('jobs-selection-bar')).toHaveTextContent('2 selected');
			expect(screen.getAllByRole('checkbox')[0]).toBeChecked();
			await fireEvent.click(screen.getAllByRole('checkbox')[0]);
			await waitFor(() => expect(screen.queryByTestId('jobs-selection-bar')).toBeNull());
		});

		it('clears the selection from Clear selection', async () => {
			await renderTable();
			await fireEvent.click(screen.getAllByRole('checkbox')[0]);
			await screen.findByTestId('jobs-selection-bar');
			await fireEvent.click(screen.getByText('Clear selection'));
			await waitFor(() => expect(screen.queryByTestId('jobs-selection-bar')).toBeNull());
		});

		it('clears the selection when the page changes', async () => {
			setJobs([listed('l1')], 100);
			await renderTable();
			await fireEvent.click(screen.getAllByRole('checkbox')[1]);
			await screen.findByTestId('jobs-selection-bar');
			await fireEvent.click(screen.getByText('2'));
			await waitFor(() => expect(screen.queryByTestId('jobs-selection-bar')).toBeNull());
		});

		it('drops selected rows that are no longer on the page after a reload', async () => {
			await renderTable();
			await fireEvent.click(screen.getAllByRole('checkbox')[0]);
			expect(await screen.findByTestId('jobs-selection-bar')).toHaveTextContent('2 selected');
			setJobs([listed('l1')]);
			fireRipperEvent();
			await waitFor(() => expect(screen.getByTestId('jobs-selection-bar')).toHaveTextContent('1 selected'));
		});

		it('hides the selection bar when the viewer is no longer an admin', async () => {
			await renderTable();
			await fireEvent.click(screen.getAllByRole('checkbox')[0]);
			await screen.findByTestId('jobs-selection-bar');
			await setRole('guest');
			await waitFor(() => expect(screen.queryByTestId('jobs-selection-bar')).toBeNull());
			expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
		});

		it('shows no checkboxes over an empty list in the table view', async () => {
			setJobs([], 0);
			await renderPage();
			await fireEvent.click(screen.getByText('Table'));
			await waitFor(() => expect(screen.getByText('No jobs found.')).toBeInTheDocument());
			expect(screen.queryAllByRole('checkbox')).toHaveLength(0);
			expect(screen.queryByTestId('jobs-selection-bar')).toBeNull();
		});
	});

	describe('bulk delete', () => {
		async function selectBoth() {
			setJobs([listed('l1'), listed('l2')]);
			await renderTable();
			await fireEvent.click(screen.getAllByRole('checkbox')[0]);
			await screen.findByTestId('jobs-selection-bar');
		}

		it('does nothing when the confirmation is cancelled', async () => {
			const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
			await selectBoth();
			await fireEvent.click(screen.getByText('Delete selected'));
			expect(confirmSpy).toHaveBeenCalledWith('Are you sure you want to delete 2 selected job(s)?');
			expect(bulkDeleteJobs).not.toHaveBeenCalled();
			expect(screen.getByTestId('jobs-selection-bar')).toBeInTheDocument();
			expect(screen.queryByText(/^Deleted/)).toBeNull();
		});

		it('deletes the selected jobs, reports the count, clears the selection and reloads', async () => {
			vi.spyOn(window, 'confirm').mockReturnValue(true);
			vi.mocked(bulkDeleteJobs).mockResolvedValue({ deleted_ids: ['l1', 'l2'], skipped_non_terminal: [] });
			await selectBoth();
			const before = vi.mocked(fetchJobsPage).mock.calls.length;
			await fireEvent.click(screen.getByText('Delete selected'));
			await waitFor(() => expect(bulkDeleteJobs).toHaveBeenCalledWith({ job_ids: ['l1', 'l2'] }));
			const feedback = await screen.findByText('Deleted 2 job(s)');
			expect(feedback.closest('[data-tone]')).toHaveAttribute('data-tone', 'success');
			await waitFor(() => expect(screen.queryByTestId('jobs-selection-bar')).toBeNull());
			expect(vi.mocked(fetchJobsPage).mock.calls.length).toBeGreaterThan(before);
		});

		it('names the in-flight jobs the backend skipped', async () => {
			vi.spyOn(window, 'confirm').mockReturnValue(true);
			vi.mocked(bulkDeleteJobs).mockResolvedValue({ deleted_ids: ['l1'], skipped_non_terminal: ['l2'] });
			await selectBoth();
			await fireEvent.click(screen.getByText('Delete selected'));
			const feedback = await screen.findByText('Deleted 1, skipped 1 in-flight job(s)');
			expect(feedback.closest('[data-tone]')).toHaveAttribute('data-tone', 'error');
		});

		it('shows the message of an API Error and keeps the selection', async () => {
			vi.spyOn(window, 'confirm').mockReturnValue(true);
			vi.mocked(bulkDeleteJobs).mockRejectedValue(new Error('forbidden'));
			await selectBoth();
			await fireEvent.click(screen.getByText('Delete selected'));
			const feedback = await screen.findByText('forbidden');
			expect(feedback.closest('[data-tone]')).toHaveAttribute('data-tone', 'error');
			expect(screen.getByTestId('jobs-selection-bar')).toBeInTheDocument();
		});

		it('shows a generic message when the rejection is not an Error', async () => {
			vi.spyOn(window, 'confirm').mockReturnValue(true);
			vi.mocked(bulkDeleteJobs).mockRejectedValue('nope');
			await selectBoth();
			await fireEvent.click(screen.getByText('Delete selected'));
			expect(await screen.findByText('Bulk action failed')).toBeInTheDocument();
		});

		it('disables Delete selected while the request is in flight', async () => {
			vi.spyOn(window, 'confirm').mockReturnValue(true);
			const pending = deferred<{ deleted_ids: string[]; skipped_non_terminal: string[] }>();
			vi.mocked(bulkDeleteJobs).mockReturnValue(pending.promise);
			await selectBoth();
			await fireEvent.click(screen.getByText('Delete selected'));
			await waitFor(() => expect(screen.getByText('Delete selected')).toBeDisabled());
			pending.resolve({ deleted_ids: ['l1', 'l2'], skipped_non_terminal: [] });
			await screen.findByText('Deleted 2 job(s)');
		});

		it('Dismiss removes the feedback', async () => {
			vi.spyOn(window, 'confirm').mockReturnValue(true);
			vi.mocked(bulkDeleteJobs).mockResolvedValue({ deleted_ids: ['l1', 'l2'], skipped_non_terminal: [] });
			await selectBoth();
			await fireEvent.click(screen.getByText('Delete selected'));
			await screen.findByText('Deleted 2 job(s)');
			await fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
			expect(screen.queryByText('Deleted 2 job(s)')).toBeNull();
		});

		it('runs the Actions menu bulk delete by status', async () => {
			const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
			vi.mocked(bulkDeleteJobs).mockResolvedValue({ deleted_ids: [], skipped_non_terminal: [] });
			await renderPage();
			await fireEvent.click(screen.getByText(/Actions/));
			await fireEvent.click(await screen.findByText('Delete All Failed'));
			expect(confirmSpy).toHaveBeenCalledWith('Are you sure you want to delete all failed jobs?');
			await waitFor(() => expect(bulkDeleteJobs).toHaveBeenCalledWith({ status: 'failed' }));
			expect(await screen.findByText('Deleted 0 job(s)')).toBeInTheDocument();
		});
	});

	describe('guests', () => {
		it('shows no selection bar, bulk menu or checkboxes', async () => {
			await setRole('guest');
			await renderTable();
			expect(screen.queryByTestId('jobs-selection-bar')).toBeNull();
			expect(screen.queryByText(/Actions/)).toBeNull();
			expect(within(screen.getByRole('table')).queryAllByRole('checkbox')).toHaveLength(0);
		});
	});
});

describe('Dashboard lifecycle', () => {
	it('starts the WebSocket and ripper events on mount', async () => {
		await renderPage();
		expect(h.startWS).toHaveBeenCalledTimes(1);
		expect(h.startRipperEvents).toHaveBeenCalledTimes(1);
		expect(h.ripperListeners.length).toBeGreaterThan(0);
	});

	it('refreshes both the dashboard and the jobs on a ripper event', async () => {
		await renderPage();
		await waitFor(() => expect(screen.getByText('Listed l1')).toBeInTheDocument());
		const dashCalls = vi.mocked(fetchDashboard).mock.calls.length;
		const jobCalls = vi.mocked(fetchJobsPage).mock.calls.length;
		fireRipperEvent();
		await waitFor(() => expect(fetchDashboard).toHaveBeenCalledTimes(dashCalls + 1));
		expect(fetchJobsPage).toHaveBeenCalledTimes(jobCalls + 1);
	});

	it('polls the dashboard every 5s and the jobs every 10s, and stops on unmount', async () => {
		vi.useFakeTimers();
		const { unmount } = renderComponent(DashboardPage);
		await vi.advanceTimersByTimeAsync(0);
		expect(fetchDashboard).toHaveBeenCalledTimes(1);
		expect(fetchJobsPage).toHaveBeenCalledTimes(1);

		await vi.advanceTimersByTimeAsync(5000);
		expect(fetchDashboard).toHaveBeenCalledTimes(2);
		expect(fetchJobsPage).toHaveBeenCalledTimes(1);

		await vi.advanceTimersByTimeAsync(5000);
		expect(fetchDashboard).toHaveBeenCalledTimes(3);
		expect(fetchJobsPage).toHaveBeenCalledTimes(2);

		unmount();
		expect(h.offRipperEvents).toHaveBeenCalledTimes(1);
		expect(h.stopWS).toHaveBeenCalledTimes(1);
		await vi.advanceTimersByTimeAsync(30000);
		expect(fetchDashboard).toHaveBeenCalledTimes(3);
		expect(fetchJobsPage).toHaveBeenCalledTimes(2);
	});
});
