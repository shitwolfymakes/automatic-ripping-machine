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

const BASE = {
	ts: '2026-06-19T00:00:01Z',
	level: 'info',
	service: 'arm-backend',
	logger: 'arm_backend.x',
	job_id: null,
	track_id: null,
	session_application_id: null,
	event: null,
	msg: 'm',
	fields: {},
	exc: null
};
const line = (over: Record<string, unknown> = {}) => JSON.stringify({ ...BASE, ...over });
const full = (over: Record<string, unknown> = {}) => ({ ...BASE, ...over });

describe('fetchJobLog', () => {
	it('GETs /api/logs/:id with a bearer token and parses NDJSON into entries', async () => {
		const ndjson = `${line({ job_id: 'job_a', msg: 'start', logger: 'arm' })}\n${line({
			ts: '2026-06-19T00:00:02Z',
			level: 'error',
			job_id: 'job_a',
			msg: 'boom',
			logger: 'ripper',
			event: 'rip.failed',
			fields: { code: 2 },
			exc: 'Traceback'
		})}\n`;
		mockFetch.mockResolvedValue(textResponse(ndjson));
		const entries = await fetchJobLog('job_01ARZ3NDEKTSV4RRFFQ69G5FAV');
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/logs/job_01ARZ3NDEKTSV4RRFFQ69G5FAV',
			expect.objectContaining({ headers: expect.objectContaining({ Authorization: 'Bearer tok-123' }) })
		);
		expect(entries).toEqual([
			full({ job_id: 'job_a', msg: 'start', logger: 'arm' }),
			full({
				ts: '2026-06-19T00:00:02Z',
				level: 'error',
				job_id: 'job_a',
				msg: 'boom',
				logger: 'ripper',
				event: 'rip.failed',
				fields: { code: 2 },
				exc: 'Traceback'
			})
		]);
	});

	it('appends ?limit= when a limit is given', async () => {
		mockFetch.mockResolvedValue(textResponse(''));
		await fetchJobLog('job_x', 500);
		expect(mockFetch).toHaveBeenCalledWith('/api/logs/job_x?limit=500', expect.any(Object));
	});

	it('skips blank and unparseable lines (defensive)', async () => {
		const ndjson = `${line({ msg: 'ok' })}\n\n{not json\n   \n`;
		mockFetch.mockResolvedValue(textResponse(ndjson));
		const entries = await fetchJobLog('job_x');
		expect(entries).toEqual([full({ msg: 'ok' })]);
	});

	it('skips a line that parses to null or to a non-object value', async () => {
		const ndjson = 'null\n42\n"text"\n{"level":"info","service":"x","msg":"ok"}\n';
		mockFetch.mockResolvedValue(textResponse(ndjson));
		const entries = await fetchJobLog('job_x');
		expect(entries.map((e) => e.msg)).toEqual(['ok']);
	});

	it('sends no Authorization header when no token is stored', async () => {
		stored.token = null;
		mockFetch.mockResolvedValue(textResponse(''));
		await fetchJobLog('job_x');
		expect(mockFetch).toHaveBeenCalledWith('/api/logs/job_x', { headers: {} });
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
		const raw = {
			...BASE,
			level: 'warning',
			job_id: 'job_a',
			track_id: 'trk_1',
			session_application_id: 'sa_1',
			event: 'rip.started',
			fields: { a: 1 },
			exc: 'tb'
		};
		expect(toLogEntry(raw)).toEqual(raw);
	});

	it('does not accept a number as a job id', () => {
		expect(toLogEntry({ ...BASE, job_id: 5 }).job_id).toBeNull();
	});

	it('defaults fields to {} and event/exc to null when absent', () => {
		const e = toLogEntry({ level: 'info', service: 's', msg: 'm' });
		expect(e).toEqual({
			ts: null,
			level: 'info',
			service: 's',
			logger: '',
			job_id: null,
			track_id: null,
			session_application_id: null,
			event: null,
			msg: 'm',
			fields: {},
			exc: null
		});
	});

	it('treats a non-object fields value as {}', () => {
		expect(toLogEntry({ ...BASE, fields: 'x' }).fields).toEqual({});
		expect(toLogEntry({ ...BASE, fields: [1] }).fields).toEqual({});
		expect(toLogEntry({ ...BASE, fields: null }).fields).toEqual({});
	});

	it('parses an old-shape line without throwing, with no logger or event', () => {
		const e = toLogEntry({ ts: 't', level: 'info', service: 's', job_id: 'job_a', msg: 'm', extra: { logger: 'x' } });
		expect(e.logger).toBe('');
		expect(e.event).toBeNull();
		expect(e.fields).toEqual({});
	});

	it('maps non-string scalars to empty or null', () => {
		const e = toLogEntry({ ...BASE, ts: 5, level: null, msg: 7, event: 3, exc: 4 });
		expect([e.ts, e.level, e.msg, e.event, e.exc]).toEqual([null, '', '', null, null]);
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
