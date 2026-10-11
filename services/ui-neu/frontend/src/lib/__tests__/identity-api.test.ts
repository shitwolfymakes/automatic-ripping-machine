import { describe, it, expect, vi, beforeEach } from 'vitest';

const get = vi.fn();
const post = vi.fn();
const del = vi.fn();
const apiFetch = vi.fn();
vi.mock('$lib/api/client', () => ({
	get: (...a: unknown[]) => get(...a),
	post: (...a: unknown[]) => post(...a),
	del: (...a: unknown[]) => del(...a),
	apiFetch: (...a: unknown[]) => apiFetch(...a)
}));

import { fetchIdentity, matchIdentity, unpinIdentity, fetchEpisodes } from '$lib/api/identity';
import { resolveJob, setJobMediaType } from '$lib/api/jobs';

beforeEach(() => vi.clearAllMocks());

describe('identity api', () => {
	it('reads the identity', async () => {
		await fetchIdentity('job_1');
		expect(get).toHaveBeenCalledWith('/api/jobs/job_1/identity');
	});
	it('previews and applies a match', async () => {
		await matchIdentity('job_1', { source: 'tvmaze', season: 1, apply: false });
		expect(post).toHaveBeenCalledWith('/api/jobs/job_1/identity/match', { source: 'tvmaze', season: 1, apply: false });
	});
	it('unpins', async () => {
		await unpinIdentity('job_1');
		expect(del).toHaveBeenCalledWith('/api/jobs/job_1/identity/pin');
	});
	it('lists a season', async () => {
		await fetchEpisodes('job_1', 'tmdb', 1);
		expect(get).toHaveBeenCalledWith('/api/jobs/job_1/identity/episodes?source=tmdb&season=1');
	});
});

describe('jobs api ids and type', () => {
	it('resolve sends the picked ids', async () => {
		const ids = { tmdb: '5084', imdb: 'tt0071003', tvdb: '77170', tmdb_kind: 'tv' as const };
		await resolveJob('job_1', { title: 'Kolchak', year: 1974, media_type: 'tv', external_ids: ids });
		expect(post).toHaveBeenCalledWith('/api/jobs/job_1/resolve', expect.objectContaining({ external_ids: ids }));
	});
	it('resolve omits ids when none were picked', async () => {
		await resolveJob('job_1', { title: 'X' });
		expect(post.mock.calls[0][1]).not.toHaveProperty('external_ids');
	});
	it('switches the media type alone', async () => {
		await setJobMediaType('job_1', 'tv');
		expect(apiFetch).toHaveBeenCalledWith('/api/jobs/job_1', {
			method: 'PATCH',
			body: JSON.stringify({ media_type: 'tv' })
		});
	});
});
