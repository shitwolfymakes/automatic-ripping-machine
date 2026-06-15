import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	apiFetch: vi.fn().mockResolvedValue({})
}));

import { apiFetch } from '$lib/api/client';
import {
	fetchJobs, fetchJob, abandonJob, deleteJob, bulkDeleteJobs,
	searchMetadata, fetchMediaDetail, searchMusicMetadata, fetchMusicDetail,
	updateJobTitle, updateJobConfig,
	// MISSING in v3
	cancelWaitingJob, startWaitingJob, pauseWaitingJob, fixJobPermissions,
	skipAndFinalize, forceComplete, submitToCrcDb, fetchCrcLookup,
	fetchJobProgress, updateJobTranscodeConfig, retranscodeJob, setJobTracks
} from '../api/jobs';

const mockApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
	mockApiFetch.mockClear();
});

describe('fetchJobs', () => {
	it('calls /api/jobs with no params', async () => {
		await fetchJobs();
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs');
	});

	it('builds query string from v3 params', async () => {
		await fetchJobs({ status: 'ripping', drive_id: 'drv_1', limit: 10, offset: 20 });
		const url = mockApiFetch.mock.calls[0][0] as string;
		expect(url).toContain('status=ripping');
		expect(url).toContain('drive_id=drv_1');
		expect(url).toContain('limit=10');
		expect(url).toContain('offset=20');
	});

	it('omits empty status but keeps explicit zero offset/limit', async () => {
		await fetchJobs({ status: '', limit: 0, offset: 0 });
		const url = mockApiFetch.mock.calls[0][0] as string;
		expect(url).not.toContain('status');
		expect(url).toContain('limit=0');
		expect(url).toContain('offset=0');
	});
});

describe('simple job endpoints (EXISTS in v3)', () => {
	it('fetchJob GETs /api/jobs/{id}', async () => {
		await fetchJob('job_42');
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs/job_42');
	});

	it('abandonJob POSTs /api/jobs/{id}/abandon', async () => {
		await abandonJob('job_1');
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs/job_1/abandon', { method: 'POST' });
	});

	it('deleteJob DELETEs /api/jobs/{id}', async () => {
		await deleteJob('job_1');
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs/job_1', { method: 'DELETE' });
	});

	it('deleteJob passes delete_raw query', async () => {
		await deleteJob('job_1', true);
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs/job_1?delete_raw=true', { method: 'DELETE' });
	});

	it('bulkDeleteJobs DELETEs /api/jobs with job_ids/status body', async () => {
		await bulkDeleteJobs({ job_ids: ['job_1', 'job_2'], status: 'failed' });
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs', {
			method: 'DELETE',
			body: JSON.stringify({ job_ids: ['job_1', 'job_2'], status: 'failed' })
		});
	});
});

describe('metadata search (EXISTS in v3)', () => {
	it('searchMetadata uses v3 title param', async () => {
		await searchMetadata('Matrix');
		const url = mockApiFetch.mock.calls[0][0] as string;
		expect(url).toContain('/api/metadata/search?');
		expect(url).toContain('title=Matrix');
	});

	it('searchMetadata includes type and provider when given', async () => {
		await searchMetadata('Matrix', 'movie', 'tmdb');
		const url = mockApiFetch.mock.calls[0][0] as string;
		expect(url).toContain('type=movie');
		expect(url).toContain('provider=tmdb');
	});

	it('fetchMediaDetail looks up by imdb_id', async () => {
		await fetchMediaDetail('tt0133093');
		const url = mockApiFetch.mock.calls[0][0] as string;
		expect(url).toContain('/api/metadata/lookup?');
		expect(url).toContain('imdb_id=tt0133093');
	});

	it('searchMusicMetadata uses v3 query param', async () => {
		await searchMusicMetadata('Beatles');
		const url = mockApiFetch.mock.calls[0][0] as string;
		expect(url).toContain('/api/metadata/music/search?');
		expect(url).toContain('query=Beatles');
	});

	it('fetchMusicDetail GETs the release detail path', async () => {
		await fetchMusicDetail('abc-123');
		expect(mockApiFetch).toHaveBeenCalledWith('/api/metadata/music/abc-123');
	});
});

describe('job/track edits via bulk-PATCH (EXISTS in v3)', () => {
	it('updateJobTitle PATCHes /api/jobs/{id} with poster_url_manual', async () => {
		await updateJobTitle('job_1', { poster_url_manual: 'http://x/p.jpg' });
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs/job_1', {
			method: 'PATCH',
			body: JSON.stringify({ poster_url_manual: 'http://x/p.jpg' })
		});
	});

	it('updateJobConfig PATCHes /api/jobs/{id}', async () => {
		await updateJobConfig('job_1', { poster_url_manual: null });
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs/job_1', {
			method: 'PATCH',
			body: JSON.stringify({ poster_url_manual: null })
		});
	});
});

describe('MISSING in v3 — reject before any fetch', () => {
	it.each([
		['cancelWaitingJob', () => cancelWaitingJob('job_1')],
		['startWaitingJob', () => startWaitingJob('job_1')],
		['pauseWaitingJob', () => pauseWaitingJob('job_1', true)],
		['fixJobPermissions', () => fixJobPermissions('job_1')],
		['skipAndFinalize', () => skipAndFinalize('job_1')],
		['forceComplete', () => forceComplete('job_1')],
		['submitToCrcDb', () => submitToCrcDb('job_1')],
		['fetchCrcLookup', () => fetchCrcLookup('job_1')],
		['fetchJobProgress', () => fetchJobProgress('job_1')],
		['updateJobTranscodeConfig', () => updateJobTranscodeConfig('job_1', {})],
		['retranscodeJob', () => retranscodeJob('job_1')],
		['setJobTracks', () => setJobTracks('job_1', [])]
	])('%s rejects with /not yet available in v3/', async (_name, call) => {
		await expect(call()).rejects.toThrow(/not yet available in v3/);
		expect(mockApiFetch).not.toHaveBeenCalled();
	});
});
