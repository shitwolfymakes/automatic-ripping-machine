// Open arm the coverage tool reports that is Svelte's, not the component's: the failed
// stage's `{stage.last_error ?? 'unknown error'}` text compiles to a second `?? ''` that a string never reaches.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderComponent, screen, cleanup, waitFor, fireEvent } from '$lib/testing/render';
import TrackStageRowHarness from './TrackStageRowHarness.svelte';
import { retryTrackStage } from '$lib/api/jobs';
import { jobLive } from '$lib/stores/job-live.svelte';
import * as authStore from '$lib/stores/auth';
import type { TrackStageView } from '$lib/types/api.gen';

vi.mock('$lib/stores/auth', async () => {
	const { derived, writable } = await import('svelte/store');
	const _role = writable<string | null>('admin');
	return {
		role: { subscribe: _role.subscribe },
		isAdmin: derived(_role, (r) => r === 'admin'),
		__setRole: (r: string | null) => _role.set(r)
	};
});
vi.mock('$lib/api/jobs', () => ({ retryTrackStage: vi.fn() }));

const followStage = vi.spyOn(jobLive, 'followStage');
const stageRead = vi.spyOn(jobLive, 'stage');
const setRole = (authStore as unknown as { __setRole: (r: string | null) => void }).__setRole;

const stageOf = (status: TrackStageView['status'], over: Partial<TrackStageView> = {}): TrackStageView => ({
	status,
	bytes_durable: 50,
	source_size: 200,
	linked: null,
	attempts: 1,
	last_error: null,
	staged_at: null,
	...over
});

function renderRow(stage: TrackStageView, onretried = vi.fn()) {
	renderComponent(
		// the row renders a <tr>, so give it a table to live in
		TrackStageRowHarness,
		{ jobId: 'job_1', trackId: 'trk_1', stage, onretried }
	);
	return onretried;
}

describe('TrackStageRow', () => {
	beforeEach(() => {
		setRole('admin');
		followStage.mockReset().mockReturnValue(() => {});
		stageRead.mockReset().mockReturnValue(null);
		vi.mocked(retryTrackStage).mockReset();
	});
	afterEach(cleanup);

	it('shows a copy in flight with its checkpoint bytes and follows its live feed', () => {
		renderRow(stageOf('copying'));
		expect(screen.getByText('Staging')).toBeTruthy();
		expect(screen.getByText('25%')).toBeTruthy();
		expect(followStage).toHaveBeenCalledWith('trk_1');
	});

	it('draws the live report over the checkpoint', () => {
		stageRead.mockReturnValue({
			pct: 80,
			etaSeconds: 30,
			fps: null,
			avgFps: null,
			pass: null,
			bytesDone: 160,
			bytesTotal: 200,
			rateBps: 10,
			phase: null,
			trackId: 'trk_1'
		});
		renderRow(stageOf('copying'));
		expect(screen.getByText('80%')).toBeTruthy();
	});

	it('waits for the stager while queued, without following a feed', () => {
		renderRow(stageOf('pending', { bytes_durable: 0, source_size: null }));
		expect(screen.getByText('Waiting to stage')).toBeTruthy();
		expect(screen.getByText('Waiting for the stager')).toBeTruthy();
		expect(followStage).not.toHaveBeenCalled();
	});

	it('shows a failed stage with its error and a Retry that reloads the job', async () => {
		vi.mocked(retryTrackStage).mockResolvedValue(stageOf('pending'));
		const onretried = renderRow(stageOf('failed', { last_error: 'No space left on device' }));
		expect(screen.getByRole('alert').textContent).toContain('Staging failed:');
		expect(screen.getByRole('alert').textContent).toContain('No space left on device');
		await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
		await waitFor(() => expect(onretried).toHaveBeenCalledTimes(1));
		expect(retryTrackStage).toHaveBeenCalledWith('job_1', 'trk_1');
	});

	it('says why when the retry fails and does not reload', async () => {
		vi.mocked(retryTrackStage).mockRejectedValue(new Error('only a failed stage can be retried'));
		const onretried = renderRow(stageOf('failed', { last_error: 'boom' }));
		await fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
		await waitFor(() => expect(screen.getByText('only a failed stage can be retried')).toBeTruthy());
		expect(onretried).not.toHaveBeenCalled();
	});

	it('names an unknown error and offers no Retry to a non-admin', () => {
		setRole('viewer');
		renderRow(stageOf('failed'));
		expect(screen.getByRole('alert').textContent).toContain('unknown error');
		expect(screen.queryByRole('button', { name: 'Retry' })).toBeNull();
	});
});
