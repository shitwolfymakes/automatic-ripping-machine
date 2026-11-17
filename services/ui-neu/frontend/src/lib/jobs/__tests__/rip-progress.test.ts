import { describe, expect, it } from 'vitest';
import { ripProgressFromTracks } from '../rip-progress';

describe('ripProgressFromTracks', () => {
	it('counts done, failed and total and finds the current track', () => {
		const summary = ripProgressFromTracks([
			{ id: 't3', index: 3, status: 'queued' },
			{ id: 't1', index: 1, status: 'done' },
			{ id: 't4', index: 4, status: 'failed' },
			{ id: 't2', index: 2, status: 'in_progress' }
		]);
		expect(summary).toEqual({
			tracks_total: 4,
			tracks_done: 1,
			tracks_failed: 1,
			current_track_id: 't2',
			current_track_index: 2
		});
	});

	it('has no current track when none is in progress', () => {
		const summary = ripProgressFromTracks([{ id: 't1', index: 1, status: 'done' }]);
		expect(summary.current_track_id).toBeNull();
		expect(summary.current_track_index).toBeNull();
	});

	it('an empty list is all zeros', () => {
		expect(ripProgressFromTracks([])).toEqual({
			tracks_total: 0,
			tracks_done: 0,
			tracks_failed: 0,
			current_track_id: null,
			current_track_index: null
		});
	});
});
