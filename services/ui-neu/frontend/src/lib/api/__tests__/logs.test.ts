import { describe, it, expect, vi, beforeEach } from 'vitest';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

// getToken is read inside fetchJobLog; stub the client module's token.
const { notifyUnauthorized, stored } = vi.hoisted(() => ({
	notifyUnauthorized: vi.fn(),
	stored: { token: 'tok-123' as string | null }
}));
vi.mock('../client', async (orig) => {
	const actual = (await orig()) as Record<string, unknown>;
	return { ...actual, getToken: () => stored.token, notifyUnauthorized };
});

function textResponse(body: string, ok = true, status = 200) {
	return { ok, status, statusText: ok ? 'OK' : 'Error', text: () => Promise.resolve(body) };
}

import { fetchJobLog, fetchJobLogIndex, jobLogDownloadUrl, toLogEntry } from '../logs';

beforeEach(() => {
	mockFetch.mockReset();
	notifyUnauthorized.mockReset();
	stored.token = 'tok-123';
});

describe('fetchJobLog', () => {
	it('GETs /api/logs/:id with a bearer token and parses NDJSON into entries', async () => {
		const ndjson =
			'{"ts":"2026-06-19T00:00:01Z","level":"info","service":"arm-backend","job_id":"job_a","msg":"start","extra":{"logger":"arm"}}\n' +
			'{"ts":"2026-06-19T00:00:02Z","level":"error","service":"arm-backend","job_id":"job_a","msg":"boom","extra":{"logger":"ripper"}}\n';
		mockFetch.mockResolvedValue(textResponse(ndjson));
		const entries = await fetchJobLog('job_01ARZ3NDEKTSV4RRFFQ69G5FAV');
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/logs/job_01ARZ3NDEKTSV4RRFFQ69G5FAV',
			expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer tok-123' }) })
		);
		expect(entries).toEqual([
			{
				timestamp: '2026-06-19T00:00:01Z',
				level: 'info',
				logger: 'arm',
				event: 'start',
				job_id: 'job_a',
				label: null,
				service: 'arm-backend'
			},
			{
				timestamp: '2026-06-19T00:00:02Z',
				level: 'error',
				logger: 'ripper',
				event: 'boom',
				job_id: 'job_a',
				label: null,
				service: 'arm-backend'
			}
		]);
	});

	it('appends ?limit= when a limit is given', async () => {
		mockFetch.mockResolvedValue(textResponse(''));
		await fetchJobLog('job_x', 500);
		expect(mockFetch).toHaveBeenCalledWith('/api/logs/job_x?limit=500', expect.any(Object));
	});

	it('skips blank and unparseable lines (defensive)', async () => {
		const ndjson =
			'{"ts":"2026-06-19T00:00:01Z","level":"info","service":"x","msg":"ok","extra":{"logger":"a"}}\n\n{not json\n   \n';
		mockFetch.mockResolvedValue(textResponse(ndjson));
		const entries = await fetchJobLog('job_x');
		expect(entries).toEqual([
			{
				timestamp: '2026-06-19T00:00:01Z',
				level: 'info',
				logger: 'a',
				event: 'ok',
				job_id: null,
				label: null,
				service: 'x'
			}
		]);
	});

	it('skips a line that parses to null or to a non-object value', async () => {
		const ndjson = 'null\n42\n"text"\n{"level":"info","service":"x","msg":"ok"}\n';
		mockFetch.mockResolvedValue(textResponse(ndjson));
		const entries = await fetchJobLog('job_x');
		expect(entries.map((e) => e.event)).toEqual(['ok']);
	});

	it('sends no Authorization header when no token is stored', async () => {
		stored.token = null;
		mockFetch.mockResolvedValue(textResponse(''));
		await fetchJobLog('job_x');
		expect(mockFetch).toHaveBeenCalledWith('/api/logs/job_x', { headers: {} });
	});

	it('falls back to service when extra.logger is absent', async () => {
		mockFetch.mockResolvedValue(
			textResponse('{"ts":"t","level":"info","service":"arm-backend","msg":"m","extra":{}}\n')
		);
		const [e] = await fetchJobLog('job_x');
		expect(e.logger).toBe('arm-backend');
		expect(e.event).toBe('m');
		expect(e.timestamp).toBe('t');
	});

	it('returns [] for an empty body (unknown/logless job — backend streams empty, not 404)', async () => {
		mockFetch.mockResolvedValue(textResponse(''));
		expect(await fetchJobLog('job_x')).toEqual([]);
	});

	it('throws ApiError on a non-ok response (e.g. 422 malformed id)', async () => {
		mockFetch.mockResolvedValue(textResponse('bad', false, 422));
		await expect(fetchJobLog('not-a-ulid')).rejects.toMatchObject({ status: 422 });
	});

	it('triggers the unauthorized handler on 401', async () => {
		mockFetch.mockResolvedValue(textResponse('nope', false, 401));
		await expect(fetchJobLog('job_x')).rejects.toMatchObject({ status: 401 });
		expect(notifyUnauthorized).toHaveBeenCalledOnce();
	});

	it('does NOT trigger the unauthorized handler on a non-401 error', async () => {
		mockFetch.mockResolvedValue(textResponse('bad', false, 422));
		await expect(fetchJobLog('job_x')).rejects.toMatchObject({ status: 422 });
		expect(notifyUnauthorized).not.toHaveBeenCalled();
	});
});

describe('jobLogDownloadUrl', () => {
	it('builds the per-job zip url', () => {
		expect(jobLogDownloadUrl('job_x')).toBe('/api/logs/job_x.zip');
	});
});

describe('toLogEntry', () => {
	it('is exported so the WS live-tail path can parse raw records the same way', () => {
		const entry = toLogEntry({
			ts: '2026-09-05T00:00:00Z',
			level: 'warning',
			service: 'arm-ripper-ABCD',
			job_id: 'job_a',
			msg: 'drive slow',
			extra: {}
		});
		expect(entry).toEqual({
			timestamp: '2026-09-05T00:00:00Z',
			level: 'warning',
			logger: 'arm-ripper-ABCD',
			event: 'drive slow',
			job_id: 'job_a',
			label: null,
			service: 'arm-ripper-ABCD'
		});
	});
});

describe('fetchJobLogIndex', () => {
	it('GETs /api/logs with a bearer token and returns the parsed JSON list', async () => {
		const rows = [{ job_id: 'job_a', size_bytes: 12, modified_at: '2026-10-16T08:18:00Z' }];
		mockFetch.mockResolvedValue({
			ok: true,
			status: 200,
			statusText: 'OK',
			headers: new Headers({ 'content-type': 'application/json' }),
			json: () => Promise.resolve(rows),
			text: () => Promise.resolve(JSON.stringify(rows))
		});
		await expect(fetchJobLogIndex()).resolves.toEqual(rows);
		expect(mockFetch.mock.calls[0][0]).toBe('/api/logs');
	});
});
