import { describe, expect, it } from 'vitest';
import { railRipProgress, ripProgressFromTracks } from '../rip-progress';

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

	it('leaves skipped tracks out of the total and the ordinals', () => {
		const summary = ripProgressFromTracks([
			{ id: 't1', index: 1, status: 'skipped' },
			{ id: 't2', index: 2, status: 'done' },
			{ id: 't3', index: 3, status: 'in_progress' }
		]);
		expect(summary).toEqual({
			tracks_total: 2,
			tracks_done: 1,
			tracks_failed: 0,
			current_track_id: 't3',
			current_track_index: 2
		});
	});

	it('counts unticked tracks that the rip still writes (mkv all): only skipped ones are left out', () => {
		// Real tracks carry `excluded`; the count ignores it and leaves out only skipped tracks.
		const tracks = [
			{ id: 't0', index: 0, status: 'queued' as const, excluded: false },
			{ id: 't1', index: 1, status: 'done' as const, excluded: true },
			{ id: 't2', index: 2, status: 'in_progress' as const, excluded: true },
			{ id: 't3', index: 3, status: 'queued' as const, excluded: true }
		];
		const summary = ripProgressFromTracks(tracks);
		expect(summary.tracks_total).toBe(4);
		expect(summary.tracks_done).toBe(1);
		expect(summary.current_track_id).toBe('t2');
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

describe('railRipProgress', () => {
	const tracks = [
		{ id: 't1', index: 1, status: 'done' as const },
		{ id: 't2', index: 2, status: 'in_progress' as const }
	];
	const sent = ripProgressFromTracks([{ id: 'x', index: 1, status: 'done' }]);

	it('derives the summary from the tracks while ripping with none sent', () => {
		expect(railRipProgress({ status: 'ripping', rip_progress: null }, tracks)).toEqual(ripProgressFromTracks(tracks));
	});

	it('keeps the sent summary while ripping', () => {
		expect(railRipProgress({ status: 'ripping', rip_progress: sent }, tracks)).toBe(sent);
	});

	it('passes the job value through for any other status', () => {
		expect(railRipProgress({ status: 'failed', rip_progress: null }, tracks)).toBeNull();
		expect(railRipProgress({ status: 'failed' }, tracks)).toBeNull();
		expect(railRipProgress({ status: 'abandoned', rip_progress: sent }, tracks)).toBe(sent);
	});
});
