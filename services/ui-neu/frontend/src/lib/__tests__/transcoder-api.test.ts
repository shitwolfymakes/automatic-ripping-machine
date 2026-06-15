import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue({}),
	post: vi.fn().mockResolvedValue({}),
	del: vi.fn().mockResolvedValue(undefined),
	buildQuery: (params: Record<string, string | number | boolean | null | undefined>) => {
		const parts: string[] = [];
		for (const [k, v] of Object.entries(params)) {
			if (v !== undefined && v !== null) parts.push(`${k}=${v}`);
		}
		return parts.length ? `?${parts.join('&')}` : '';
	}
}));

import { get, post, del } from '$lib/api/client';
import {
	fetchTranscoderStats,
	fetchTranscoderWorkers,
	fetchTranscoderJobs,
	retryTranscoderJob,
	deleteTranscoderJob,
	retranscodeTranscoderJob,
	listHandbrakePresets
} from '../api/transcoder';

const mockGet = vi.mocked(get);
const mockPost = vi.mocked(post);
const mockDel = vi.mocked(del);

beforeEach(() => {
	mockGet.mockClear();
	mockPost.mockClear();
	mockDel.mockClear();
});

describe('fetchTranscoderStats', () => {
	it('GETs /api/transcodes/stats', async () => {
		await fetchTranscoderStats();
		expect(mockGet).toHaveBeenCalledWith('/api/transcodes/stats');
	});
});

describe('fetchTranscoderWorkers', () => {
	it('GETs the bare /api/transcodes/workers array', async () => {
		await fetchTranscoderWorkers();
		expect(mockGet).toHaveBeenCalledWith('/api/transcodes/workers');
	});
});

describe('fetchTranscoderJobs', () => {
	it('GETs /api/transcodes with no params', async () => {
		await fetchTranscoderJobs();
		expect(mockGet).toHaveBeenCalledWith('/api/transcodes');
	});

	it('builds a query string from params', async () => {
		await fetchTranscoderJobs({ status: 'queued', limit: 10, offset: 20 });
		const url = mockGet.mock.calls[0][0] as string;
		expect(url).toContain('status=queued');
		expect(url).toContain('limit=10');
		expect(url).toContain('offset=20');
	});

	it('omits empty status', async () => {
		await fetchTranscoderJobs({ status: '' });
		expect(mockGet).toHaveBeenCalledWith('/api/transcodes');
	});
});

describe('retryTranscoderJob', () => {
	it('POSTs to retry with a string id', async () => {
		await retryTranscoderJob('t-3');
		expect(mockPost).toHaveBeenCalledWith('/api/transcodes/t-3/retry');
	});
});

describe('deleteTranscoderJob', () => {
	it('DELETEs the task with a string id', async () => {
		await deleteTranscoderJob('t-3');
		expect(mockDel).toHaveBeenCalledWith('/api/transcodes/t-3');
	});
});

describe('MISSING in v3', () => {
	it('retranscodeTranscoderJob rejects (no v3 endpoint; use retry)', async () => {
		await expect(retranscodeTranscoderJob('t-3')).rejects.toThrow(/not yet available in v3/);
	});

	it('listHandbrakePresets rejects (no v3 endpoint)', async () => {
		await expect(listHandbrakePresets()).rejects.toThrow(/not yet available in v3/);
	});
});
