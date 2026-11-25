import { describe, it, expect } from 'vitest';
import { videoTypeLabel, buildMetadataFields } from '../fields';
import { createJob } from '$lib/__fixtures__/job';

describe('videoTypeLabel', () => {
	it('maps known types', () => {
		expect(videoTypeLabel('movie')).toBe('Movie');
		expect(videoTypeLabel('series')).toBe('Series');
		expect(videoTypeLabel('music')).toBe('Music');
		expect(videoTypeLabel('data')).toBe('Data');
	});
	it('passes through unknown and falls back for empty', () => {
		expect(videoTypeLabel('anime')).toBe('anime');
		expect(videoTypeLabel(null)).toBe('Unknown');
	});
});

const fieldByLabel = (fields: ReturnType<typeof buildMetadataFields>, label: string) =>
	fields.find((f) => f.label === label);

describe('buildMetadataFields — promoted fields', () => {
	it('promotes Disc # and Disc total as two cells, each set in place', () => {
		const fields = buildMetadataFields(createJob({ disc_number: 1, disc_total: 2 }));
		expect(fieldByLabel(fields, 'Disc #')).toMatchObject({ value: '1', edit: 'disc_number', raw: '1' });
		expect(fieldByLabel(fields, 'Disc total')).toMatchObject({ value: '2', edit: 'disc_total', raw: '2' });
	});

	it('promotes Disc # without total', () => {
		const fields = buildMetadataFields(createJob({ disc_number: 1, disc_total: null }));
		expect(fieldByLabel(fields, 'Disc #')?.value).toBe('1');
		expect(fieldByLabel(fields, 'Disc total')).toBeUndefined();
	});

	it('a TV job always offers Season, Disc # and Disc total, empty as "-"', () => {
		const fields = buildMetadataFields(createJob({ media_type: 'tv', metadata_json: {} }));
		expect(fieldByLabel(fields, 'Season')).toMatchObject({ value: '-', edit: 'season', raw: '' });
		expect(fieldByLabel(fields, 'Disc #')).toMatchObject({ value: '-', edit: 'disc_number', raw: '' });
		expect(fieldByLabel(fields, 'Disc total')).toMatchObject({ value: '-', edit: 'disc_total', raw: '' });
		expect(fieldByLabel(fields, 'Year')).toMatchObject({ edit: 'year' });
	});

	it('shows Poster source Manual then Auto', () => {
		expect(
			fieldByLabel(buildMetadataFields(createJob({ poster_url_manual: 'm', poster_url: 'a' })), 'Poster')?.value
		).toBe('Manual');
		expect(
			fieldByLabel(buildMetadataFields(createJob({ poster_url_manual: null, poster_url: 'a' })), 'Poster')?.value
		).toBe('Auto');
		expect(
			fieldByLabel(buildMetadataFields(createJob({ poster_url_manual: null, poster_url: null })), 'Poster')
		).toBeUndefined();
	});

	it('promotes Type / IMDb (link) / TMDB (link) / TVDB (link) / Season from typed sections + the season column', () => {
		const fields = buildMetadataFields(
			createJob({
				season: 2,
				metadata_json: {
					identity: { provider: 'tmdb', external_ids: { imdb: 'tt1234567', tmdb: '603', tvdb: '81189' } },
					provider_raw: { arm_server: { video_type: 'series' } }
				}
			})
		);
		expect(fieldByLabel(fields, 'Type')?.value).toBe('Series');
		expect(fieldByLabel(fields, 'IMDb')?.link).toBe('https://www.imdb.com/title/tt1234567');
		expect(fieldByLabel(fields, 'TMDB')?.link).toBe('https://www.themoviedb.org/movie/603');
		expect(fieldByLabel(fields, 'TVDB')?.link).toBe('https://www.thetvdb.com/dereferrer/series/81189');
		expect(fieldByLabel(fields, 'Season')?.value).toBe('02');
	});

	it('promotes Artist / Album', () => {
		const fields = buildMetadataFields(
			createJob({ metadata_json: { music: { artist: 'The Beatles', album: 'Abbey Road' } } })
		);
		expect(fieldByLabel(fields, 'Artist')?.value).toBe('The Beatles');
		expect(fieldByLabel(fields, 'Album')?.value).toBe('Abbey Road');
	});

	it('adds Titles count only when rip_progress is absent', () => {
		const scanned = buildMetadataFields(
			createJob({
				rip_progress: null,
				metadata_json: {
					scan_result: {
						disc_type: 'bluray',
						titles: [
							{ index: 0, duration_seconds: 0 },
							{ index: 1, duration_seconds: 0 },
							{ index: 2, duration_seconds: 0 }
						]
					}
				}
			})
		);
		expect(fieldByLabel(scanned, 'Titles')?.value).toBe('3');

		const ripping = buildMetadataFields(
			createJob({
				rip_progress: {
					tracks_done: 1,
					tracks_total: 3,
					tracks_failed: 0,
					current_track_id: null,
					current_track_index: null
				},
				metadata_json: {
					scan_result: {
						disc_type: 'bluray',
						titles: [
							{ index: 0, duration_seconds: 0 },
							{ index: 1, duration_seconds: 0 },
							{ index: 2, duration_seconds: 0 }
						]
					}
				}
			})
		);
		// Base "Tracks" cell is authoritative; "Titles" not added.
		expect(fieldByLabel(ripping, 'Titles')).toBeUndefined();
		expect(fieldByLabel(ripping, 'Tracks')?.value).toBe('1 / 3');
	});

	it('promotes nothing extra for a bare job (only base cells, padded)', () => {
		const fields = buildMetadataFields(createJob({ metadata_json: {} }));
		for (const label of ['Disc #', 'Poster', 'Type', 'IMDb', 'TMDB', 'TVDB', 'Season', 'Artist', 'Album', 'Titles']) {
			expect(fieldByLabel(fields, label)).toBeUndefined();
		}
		// Length is a multiple of 4 (pad preserved).
		expect(fields.length % 4).toBe(0);
	});
});
