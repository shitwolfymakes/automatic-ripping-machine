import { describe, it, expect } from 'vitest';
import { trackToRow, scanTitleToRow } from './review-rows';

describe('review-rows mappers', () => {
	it('trackToRow carries the id + editable fields', () => {
		const r = trackToRow({
			id: 'trk_9', index: 3, title: 'Main', year: 2001, episode_number: 4,
			excluded: false, duration_seconds: 60, output_path: 'o.mkv', source_ref: 's'
		} as any);
		expect(r).toEqual({
			index: 3, durationSeconds: 60, sourceLabel: 'o.mkv', trackId: 'trk_9',
			title: 'Main', year: 2001, episodeNumber: 4, excluded: false
		});
	});

	it('trackToRow falls back to source_ref when output_path is empty', () => {
		const r = trackToRow({ id: 't', index: 0, title: null, year: null, episode_number: null, excluded: false, duration_seconds: null, output_path: null, source_ref: 'B1_t00' } as any);
		expect(r.sourceLabel).toBe('B1_t00');
	});

	it('scanTitleToRow has no trackId and blank identity (read-only row)', () => {
		const r = scanTitleToRow({ index: 2, duration_seconds: 100, source_file: 'x.mkv' } as any);
		expect(r).toEqual({
			index: 2, durationSeconds: 100, sourceLabel: 'x.mkv', trackId: null,
			title: null, year: null, episodeNumber: null, excluded: false
		});
	});

	it('scanTitleToRow tolerates a missing source_file', () => {
		const r = scanTitleToRow({ index: 0, duration_seconds: 10 } as any);
		expect(r.sourceLabel).toBeNull();
	});
});
