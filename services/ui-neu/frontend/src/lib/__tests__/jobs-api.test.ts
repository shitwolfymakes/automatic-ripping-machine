import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	apiFetch: vi.fn().mockResolvedValue({}),
	apiFetchResponse: vi.fn().mockResolvedValue({ data: [], headers: new Headers() }),
	post: vi.fn().mockResolvedValue({})
}));

import { apiFetch, apiFetchResponse, post } from '$lib/api/client';
import {
	fetchJobs,
	fetchJobsPage,
	fetchAllJobs,
	fetchJob,
	abandonJob,
	deleteJob,
	bulkDeleteJobs,
	searchMetadata,
	fetchMediaDetail,
	searchMusicMetadata,
	fetchMusicDetail,
	updateJobTitle,
	updateJobConfig,
	triggerManual,
	startWaitingJob,
	pauseWaitingJob
} from '../api/jobs';

const mockApiFetch = vi.mocked(apiFetch);
const mockApiFetchResponse = vi.mocked(apiFetchResponse);
const mockPost = vi.mocked(post);

beforeEach(() => {
	mockApiFetch.mockClear();
	mockApiFetchResponse.mockClear();
	mockPost.mockClear();
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

	it('searchMetadata accepts the TV providers', async () => {
		await searchMetadata('Lost', 'tv', 'tvmaze');
		const url = mockApiFetch.mock.calls[0][0] as string;
		expect(url).toContain('type=tv');
		expect(url).toContain('provider=tvmaze');
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

describe('startWaitingJob (EXISTS in v3 — timed review gate Start)', () => {
	it('POSTs /api/jobs/{id}/rip-start-review', async () => {
		await startWaitingJob('job_1');
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs/job_1/rip-start-review', { method: 'POST' });
	});
});

describe('pauseWaitingJob (EXISTS in v3 — per-job review pause)', () => {
	it('POSTs review-pause?paused=true by default', async () => {
		await pauseWaitingJob('job_1');
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs/job_1/review-pause?paused=true', { method: 'POST' });
	});

	it('POSTs review-pause?paused=false to resume', async () => {
		await pauseWaitingJob('job_1', false);
		expect(mockApiFetch).toHaveBeenCalledWith('/api/jobs/job_1/review-pause?paused=false', { method: 'POST' });
	});
});

describe('triggerManual (EXISTS in v3)', () => {
	it('POSTs /api/jobs/manual with drive_id + session_id', async () => {
		await triggerManual({ drive_id: 'drv_1', session_id: 'ses_1' });
		expect(mockPost).toHaveBeenCalledWith('/api/jobs/manual', {
			drive_id: 'drv_1',
			session_id: 'ses_1'
		});
	});

	it('POSTs with session_id null when none chosen', async () => {
		await triggerManual({ drive_id: 'drv_1', session_id: null });
		expect(mockPost).toHaveBeenCalledWith('/api/jobs/manual', {
			drive_id: 'drv_1',
			session_id: null
		});
	});
});

describe('fetchJobsPage', () => {
	it('returns the page body and the X-Total-Count total', async () => {
		mockApiFetchResponse.mockResolvedValueOnce({
			data: [{ id: 'job_1' }],
			headers: new Headers({ 'X-Total-Count': '142' })
		});
		const page = await fetchJobsPage({ status: 'ripped', limit: 48, offset: 96 });
		const url = mockApiFetchResponse.mock.calls[0][0] as string;
		expect(url).toBe('/api/jobs?status=ripped&limit=48&offset=96');
		expect(page).toEqual({ jobs: [{ id: 'job_1' }], total: 142 });
	});

	it('falls back to the page length when the header is missing', async () => {
		mockApiFetchResponse.mockResolvedValueOnce({ data: [{ id: 'a' }, { id: 'b' }], headers: new Headers() });
		const page = await fetchJobsPage();
		expect(mockApiFetchResponse.mock.calls[0][0]).toBe('/api/jobs');
		expect(page.total).toBe(2);
	});
});

describe('fetchAllJobs', () => {
	const ids = (n: number, from = 0) => Array.from({ length: n }, (_, i) => ({ id: `job_${from + i}` }));

	it('pages through until the total is reached', async () => {
		mockApiFetchResponse
			.mockResolvedValueOnce({ data: ids(500), headers: new Headers({ 'X-Total-Count': '620' }) })
			.mockResolvedValueOnce({ data: ids(120, 500), headers: new Headers({ 'X-Total-Count': '620' }) });
		const all = await fetchAllJobs({ status: 'failed' });
		expect(mockApiFetchResponse.mock.calls.map((c) => c[0])).toEqual([
			'/api/jobs?status=failed&limit=500&offset=0',
			'/api/jobs?status=failed&limit=500&offset=500'
		]);
		expect(all.jobs).toHaveLength(620);
		expect(all.total).toBe(620);
	});

	it('stops on an empty page even if the total says more', async () => {
		mockApiFetchResponse
			.mockResolvedValueOnce({ data: ids(500), headers: new Headers({ 'X-Total-Count': '600' }) })
			.mockResolvedValueOnce({ data: [], headers: new Headers({ 'X-Total-Count': '500' }) });
		const all = await fetchAllJobs();
		expect(mockApiFetchResponse).toHaveBeenCalledTimes(2);
		expect(all.total).toBe(500);
	});
});
