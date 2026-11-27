// The Include box on the Match Episodes rows: its title and state follow the rip plan.
import { describe, it, expect, afterEach } from 'vitest';
import { renderComponent, screen, cleanup } from '$lib/testing/render';
import EpisodeRows from '../EpisodeRows.svelte';
import type { EpisodeRow } from '../../../episodes/episode-model';
import type { TrackStatus } from '$lib/types/api.gen';
import { createJob } from '../../../__fixtures__/job';

afterEach(cleanup);

const row = (status: TrackStatus): EpisodeRow => ({
	trackId: 'trk_0',
	ref: 't00',
	length: '10:00',
	code: 'S01E01',
	name: 'Pilot',
	origin: { kind: 'none', source: null },
	confidence: null,
	proposed: null,
	changed: false,
	handSet: false,
	season: 1,
	seconds: 600,
	excluded: status === 'skipped',
	status,
	pickValue: ''
});

function box(status: TrackStatus, job: Parameters<typeof createJob>[0]): HTMLElement {
	renderComponent(EpisodeRows, {
		job: createJob(job),
		rows: [row(status)],
		fileNames: new Map(),
		onexclude: () => {}
	});
	return screen.getAllByRole('checkbox', { name: 'Include t00' })[0];
}

describe('EpisodeRows include box', () => {
	it('rips and transcodes in per-title mode before the rip', () => {
		const b = box('queued', { status: 'awaiting_review', rip_invocation: 'per_title' });
		expect(b).toHaveAttribute('title', 'Rip and transcode this title');
		expect(b).toBeEnabled();
	});

	it('only includes the title in the transcode in mkv all mode', () => {
		expect(box('queued', { status: 'awaiting_review', rip_invocation: 'mkv_all' })).toHaveAttribute(
			'title',
			'Include this title in the transcode'
		);
	});

	it('is disabled for a title that was not ripped', () => {
		const b = box('skipped', { status: 'ripped', rip_invocation: 'per_title' });
		expect(b).toBeDisabled();
		expect(b).toHaveAttribute('title', 'Not ripped: it was unticked when the rip started');
	});
});
