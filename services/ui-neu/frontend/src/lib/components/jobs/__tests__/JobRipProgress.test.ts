import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/svelte';
import JobRipProgress from '../JobRipProgress.svelte';
import { ripProgress, type RipLiveProgress } from '$lib/stores/rips.svelte';

function progress(over: Partial<RipLiveProgress> = {}): RipLiveProgress {
	return {
		track_id: 't1',
		progress_pct: 40,
		eta_seconds: null,
		bytes_done: null,
		bytes_total: null,
		rate_bps: null,
		phase: null,
		...over
	};
}

const WAITING = 'Waiting for the first progress report from the ripper.';

afterEach(() => {
	cleanup();
	ripProgress.value = {};
});

describe('JobRipProgress', () => {
	it('shows the Ripping heading and the waiting line with no progress', () => {
		render(JobRipProgress, { jobId: 'j1' });
		expect(screen.getByTestId('job-rip-progress')).toBeInTheDocument();
		expect(screen.getByRole('heading', { name: 'Ripping' })).toBeInTheDocument();
		expect(screen.getByText(WAITING)).toBeInTheDocument();
	});

	it('keeps waiting when only another job has progress', () => {
		ripProgress.value = { other: progress() };
		render(JobRipProgress, { jobId: 'j1' });
		expect(screen.getByText(WAITING)).toBeInTheDocument();
	});

	it('shows the bar without an ETA or transfer line when neither is known', () => {
		ripProgress.value = { j1: progress() };
		render(JobRipProgress, { jobId: 'j1' });
		expect(screen.queryByText(WAITING)).not.toBeInTheDocument();
		expect(screen.queryByText(/left$/)).not.toBeInTheDocument();
		expect(screen.queryByText(/ of /)).not.toBeInTheDocument();
	});

	it('shows the ETA and the byte transfer with its rate', () => {
		ripProgress.value = {
			j1: progress({
				eta_seconds: 7200,
				bytes_done: 1048576,
				bytes_total: 2097152,
				rate_bps: 1048576
			})
		};
		render(JobRipProgress, { jobId: 'j1' });
		expect(screen.getByText('2h 0m left')).toBeInTheDocument();
		expect(screen.getByText(/ of .*\/s/)).toBeInTheDocument();
	});

	it('shows the Verifying heading in the verifying phase', () => {
		ripProgress.value = { j1: progress({ phase: 'verifying' }) };
		render(JobRipProgress, { jobId: 'j1' });
		expect(screen.getByRole('heading', { name: 'Verifying ripped files' })).toBeInTheDocument();
	});
});
