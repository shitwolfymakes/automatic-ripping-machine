import { describe, it, expect } from 'vitest';

import {
	scanFolder, createFolderJob, createIsoJob, fetchIngressDirectory, fetchIngressRoot
} from '../api/import-jobs';

// Folder import + ingress browser + ISO job creation are MISSING in v3 — these
// functions are stubs that reject before any fetch. The Import wizard screen is
// feature-flagged OFF.
describe('import-jobs MISSING stubs', () => {
	it('scanFolder rejects', async () => {
		await expect(scanFolder('/media/movies/MyMovie')).rejects.toThrow(/not yet available in v3/);
	});

	it('createFolderJob rejects', async () => {
		await expect(
			createFolderJob({
				source_path: '/media/ingress/MyMovie',
				title: 'My Movie',
				year: '2024',
				video_type: 'movie',
				disctype: 'bluray',
				imdb_id: 'tt1234567',
				poster_url: null,
				season: null,
				disc_number: null,
				disc_total: null
			})
		).rejects.toThrow(/not yet available in v3/);
	});

	it('createIsoJob rejects', async () => {
		await expect(
			createIsoJob({
				source_path: '/media/ingress/MyMovie.iso',
				title: 'My Movie',
				year: '2024',
				video_type: 'movie',
				disctype: 'bluray',
				imdb_id: null,
				poster_url: null,
				season: null,
				disc_number: null,
				disc_total: null
			})
		).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchIngressDirectory rejects', async () => {
		await expect(fetchIngressDirectory('/media/ingress')).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchIngressRoot rejects', async () => {
		await expect(fetchIngressRoot()).rejects.toThrow(/not yet available in v3/);
	});
});
