import { describe, it, expect } from 'vitest';
import { trackToRow, scanTitleToRow, nonEpisode } from '../review-rows';

const none = () => null;

describe('review-rows mappers', () => {
	it('trackToRow carries the id + editable fields', () => {
		const r = trackToRow(
			{
				id: 'trk_9',
				index: 3,
				title: 'Main',
				year: 2001,
				episode_number: 4,
				excluded: false,
				duration_seconds: 60,
				output_path: 'o.mkv',
				source_ref: 's'
			} as any,
			none
		);
		expect(r).toEqual({
			index: 3,
			durationSeconds: 60,
			sizeLabel: '-',
			sourceName: 'o.mkv',
			sourceRef: 's',
			titleClass: null,
			classRef: null,
			classLabel: null,
			trackId: 'trk_9',
			title: 'Main',
			year: 2001,
			episodeNumber: 4,
			episodeName: null,
			role: null,
			excluded: false,
			angle: null,
			stereo3d: false,
			unrippable: false,
			featureLabel: 'Extra'
		});
	});

	it('trackToRow reads the angle from the ref and carries 3D, unrippable and the feature label', () => {
		const r = trackToRow(
			{
				id: 't',
				index: 4,
				source_ref: '00334.mpls:2',
				source_file: '00334.mpls',
				stereo_3d: true,
				unrippable: true,
				title_class: 'primary',
				expected_duration_seconds: 9807
			} as any,
			none
		);
		expect(r).toMatchObject({
			angle: 2,
			stereo3d: true,
			unrippable: true,
			featureLabel: 'Main feature',
			sourceName: '00334.mpls:2'
		});
	});

	it('trackToRow falls back to the scan estimate before the rip and carries the role', () => {
		const r = trackToRow(
			{
				id: 'trk_1',
				index: 5,
				duration_seconds: null,
				expected_duration_seconds: 542,
				role: 'extra',
				source_ref: '5'
			} as any,
			none
		);
		expect(r.durationSeconds).toBe(542);
		expect(r.role).toBe('extra');
	});
	it('trackToRow falls back to source_ref when output_path is empty', () => {
		const r = trackToRow(
			{
				id: 't',
				index: 0,
				title: null,
				year: null,
				episode_number: null,
				excluded: false,
				duration_seconds: null,
				output_path: null,
				source_ref: 'B1_t00'
			} as any,
			none
		);
		expect(r.sourceName).toBe('B1_t00');
	});

	it('trackToRow carries the class, its ref and the label', () => {
		const r = trackToRow(
			{
				id: 'd',
				index: 4,
				source_ref: '4',
				playlist_name: '00801.mpls',
				title_class: 'decoy',
				title_class_ref: '0'
			} as any,
			(ref) => (ref === '0' ? 0 : null)
		);
		expect(r).toMatchObject({
			sourceName: '00801.mpls',
			titleClass: 'decoy',
			classRef: '0',
			classLabel: { text: 'Decoy playlist of #0', tone: 'muted' }
		});
	});

	it('scanTitleToRow names the playlist before the stream file', () => {
		const r = scanTitleToRow({
			index: 2,
			duration_seconds: 1,
			source_file: 'a.m2ts',
			playlist_name: '00800.mpls'
		} as any);
		expect(r.sourceName).toBe('00800.mpls');
	});

	it('scanTitleToRow has no trackId and blank identity (read-only row)', () => {
		const r = scanTitleToRow({ index: 2, duration_seconds: 100, source_file: 'x.mkv' } as any);
		expect(r).toEqual({
			index: 2,
			durationSeconds: 100,
			sizeLabel: '-',
			sourceName: 'x.mkv',
			sourceRef: '2',
			titleClass: null,
			classRef: null,
			classLabel: null,
			trackId: null,
			title: null,
			year: null,
			episodeNumber: null,
			episodeName: null,
			role: null,
			excluded: false,
			angle: null,
			stereo3d: false,
			unrippable: false,
			featureLabel: null
		});
	});
	it('a scanned title carries its angle and 3D flag', () => {
		const r = scanTitleToRow({ index: 2, duration_seconds: 100, angle: 2, stereo_3d: true } as any);
		expect(r).toMatchObject({ angle: 2, stereo3d: true });
	});
	it('sizes a track by its actual size, else the scan estimate', () => {
		const base = { id: 't', index: 0, source_ref: 's' };
		expect(trackToRow({ ...base, size_bytes: 2048 } as any, none).sizeLabel).toBe('2 KB');
		expect(trackToRow({ ...base, expected_size_bytes: 2048 } as any, none).sizeLabel).toBe('~2 KB');
	});
	it('sizes a scanned title by its estimate', () => {
		expect(scanTitleToRow({ index: 0, duration_seconds: 1, size_bytes: 2048 } as any).sizeLabel).toBe('~2 KB');
		expect(scanTitleToRow({ index: 0, duration_seconds: 1, size_bytes: null } as any).sizeLabel).toBe('-');
	});
	it('scanTitleToRow falls back to the title number without a source_file', () => {
		const r = scanTitleToRow({ index: 0, duration_seconds: 10 } as any);
		expect(r.sourceName).toBe('0');
	});
});

describe('nonEpisode', () => {
	it.each([
		['extra', 'Extra'],
		['trailer', 'Trailer'],
		['other', 'Other']
	])('labels a %s without an episode number', (role, label) => {
		expect(nonEpisode({ role, episodeNumber: null })).toBe(label);
	});
	it.each(['extra', 'trailer', 'other'])('gives null for %s with an episode number', (role) => {
		expect(nonEpisode({ role, episodeNumber: 3 })).toBeNull();
	});
	it('gives null for a null role', () => {
		expect(nonEpisode({ role: null, episodeNumber: null })).toBeNull();
	});
	it.each(['main', 'episode'])('gives null for %s without an episode number', (role) => {
		expect(nonEpisode({ role, episodeNumber: null })).toBeNull();
	});
});
