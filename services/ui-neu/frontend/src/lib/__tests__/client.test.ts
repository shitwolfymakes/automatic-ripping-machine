import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
	apiFetch,
	apiFormPost,
	get,
	post,
	patch,
	del,
	buildQuery,
	setToken,
	clearToken,
	getToken,
	setUnauthorizedHandler,
	ApiError
} from '../api/client';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, ok = true, status = 200, statusText = 'OK') {
	return { ok, status, statusText, json: () => Promise.resolve(data) };
}

beforeEach(() => {
	mockFetch.mockReset();
	clearToken();
	setUnauthorizedHandler(() => {});
	localStorage.clear();
});

describe('apiFetch (preserved behaviors)', () => {
	it('returns parsed JSON on success', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ id: 1 }));
		expect(await apiFetch('/api/test')).toEqual({ id: 1 });
	});

	it('sends Content-Type application/json by default', async () => {
		mockFetch.mockResolvedValue(jsonResponse({}));
		await apiFetch('/api/test');
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/test',
			expect.objectContaining({
				headers: expect.objectContaining({ 'Content-Type': 'application/json' })
			})
		);
	});

	it('merges custom headers', async () => {
		mockFetch.mockResolvedValue(jsonResponse({}));
		await apiFetch('/api/test', { headers: { 'X-Custom': 'value' } });
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/test',
			expect.objectContaining({
				headers: expect.objectContaining({ 'Content-Type': 'application/json', 'X-Custom': 'value' })
			})
		);
	});

	it('passes through method and body', async () => {
		mockFetch.mockResolvedValue(jsonResponse({}));
		await apiFetch('/api/test', { method: 'POST', body: JSON.stringify({ key: 'val' }) });
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/test',
			expect.objectContaining({ method: 'POST', body: '{"key":"val"}' })
		);
	});

	it('throws with detail from error response body', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ detail: 'Not found' }, false, 404, 'Not Found'));
		await expect(apiFetch('/api/missing')).rejects.toThrow('Not found');
	});

	it('throws with status text when body has no detail', async () => {
		mockFetch.mockResolvedValue(jsonResponse({}, false, 500, 'Internal Server Error'));
		await expect(apiFetch('/api/broken')).rejects.toThrow('API 500: Internal Server Error');
	});

	it('throws with status text when response body is not JSON', async () => {
		mockFetch.mockResolvedValue({
			ok: false,
			status: 502,
			statusText: 'Bad Gateway',
			json: () => Promise.reject(new Error('not json'))
		});
		await expect(apiFetch('/api/bad')).rejects.toThrow('API 502: Bad Gateway');
	});

	it('keeps the status-text message for a non-string detail and preserves the body', async () => {
		const errorBody = { detail: [{ msg: 'bad', loc: ['body', 'x'] }] };
		mockFetch.mockResolvedValue(jsonResponse(errorBody, false, 422, 'Unprocessable'));
		await apiFetch('/api/v').then(
			() => {
				throw new Error('should have thrown');
			},
			(e) => {
				expect(e).toBeInstanceOf(ApiError);
				expect(e.message).toBe('API 422: Unprocessable');
				expect(e.body).toEqual(errorBody);
			}
		);
	});
});

describe('structured error body', () => {
	it('throws ApiError with status + parsed body on non-2xx', async () => {
		const body = { detail: { message: 'collisions', collisions: [{ output_path: '/x', reason: 'on_disk' }] } };
		mockFetch.mockResolvedValue(jsonResponse(body, false, 409, 'Conflict'));
		await apiFetch('/api/x').then(
			() => {
				throw new Error('should have thrown');
			},
			(e) => {
				expect(e).toBeInstanceOf(ApiError);
				expect(e.status).toBe(409);
				expect(e.body).toEqual(body);
			}
		);
	});

	it('string detail still yields a readable message (back-compat)', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ detail: 'Not found' }, false, 404, 'Not Found'));
		await expect(apiFetch('/api/x')).rejects.toThrow('Not found');
	});

	it('non-JSON error still throws with status-text message', async () => {
		mockFetch.mockResolvedValue({
			ok: false,
			status: 502,
			statusText: 'Bad Gateway',
			json: () => Promise.reject(new Error('x'))
		});
		await expect(apiFetch('/api/x')).rejects.toThrow('API 502: Bad Gateway');
	});
});

describe('auth: token + bearer injection', () => {
	it('attaches Authorization: Bearer when a token is set', async () => {
		setToken('tok-abc');
		mockFetch.mockResolvedValue(jsonResponse({}));
		await apiFetch('/api/test');
		expect(mockFetch).toHaveBeenCalledWith(
			'/api/test',
			expect.objectContaining({
				headers: expect.objectContaining({ Authorization: 'Bearer tok-abc' })
			})
		);
	});

	it('omits Authorization when no token', async () => {
		mockFetch.mockResolvedValue(jsonResponse({}));
		await apiFetch('/api/test');
		const init = mockFetch.mock.calls[0][1];
		expect(init.headers).not.toHaveProperty('Authorization');
	});

	it('persists the token in localStorage and reads it back', () => {
		setToken('tok-xyz');
		expect(localStorage.getItem('arm_token')).toBe('tok-xyz');
		expect(getToken()).toBe('tok-xyz');
		clearToken();
		expect(getToken()).toBeNull();
		expect(localStorage.getItem('arm_token')).toBeNull();
	});
});

describe('401 handling', () => {
	it('invokes the unauthorized handler and throws on 401', async () => {
		const on401 = vi.fn();
		setUnauthorizedHandler(on401);
		mockFetch.mockResolvedValue(jsonResponse({ detail: 'nope' }, false, 401, 'Unauthorized'));
		await expect(apiFetch('/api/secure')).rejects.toThrow();
		expect(on401).toHaveBeenCalledTimes(1);
	});
});

describe('verb helpers', () => {
	it('get issues a GET and returns JSON', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		expect(await get('/api/x')).toEqual({ ok: true });
		expect(mockFetch.mock.calls[0][1].method).toBe('GET');
	});

	it('post serializes the body and sets method', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ created: 1 }));
		await post('/api/x', { a: 1 });
		const init = mockFetch.mock.calls[0][1];
		expect(init.method).toBe('POST');
		expect(init.body).toBe('{"a":1}');
		expect(init.headers).toEqual(expect.objectContaining({ 'Content-Type': 'application/json' }));
	});

	it('post with no body sends no body', async () => {
		mockFetch.mockResolvedValue(jsonResponse({}));
		await post('/api/x');
		const init = mockFetch.mock.calls[0][1];
		expect(init.method).toBe('POST');
		expect(init.body).toBeUndefined();
	});

	it('patch serializes the body', async () => {
		mockFetch.mockResolvedValue(jsonResponse({}));
		await patch('/api/x', { b: 2 });
		const init = mockFetch.mock.calls[0][1];
		expect(init.method).toBe('PATCH');
		expect(init.body).toBe('{"b":2}');
	});

	it('del issues a DELETE and tolerates an empty (204-style) body', async () => {
		mockFetch.mockResolvedValue({
			ok: true,
			status: 204,
			statusText: 'No Content',
			json: () => Promise.reject(new Error('no body'))
		});
		await expect(del('/api/x')).resolves.toBeUndefined();
		expect(mockFetch.mock.calls[0][1].method).toBe('DELETE');
	});
});

describe('buildQuery', () => {
	it('builds a query string from defined params, prefixed with ?', () => {
		expect(buildQuery({ a: 1, b: 'two' })).toBe('?a=1&b=two');
	});

	it('omits undefined and null params', () => {
		expect(buildQuery({ a: 1, b: undefined, c: null })).toBe('?a=1');
	});

	it('returns empty string when no params remain', () => {
		expect(buildQuery({ a: undefined })).toBe('');
		expect(buildQuery({})).toBe('');
	});

	it('encodes values', () => {
		expect(buildQuery({ path: '/a b/c' })).toBe('?path=%2Fa%20b%2Fc');
	});

	it('includes falsy-but-valid values (0, false, empty string)', () => {
		expect(buildQuery({ a: 0, b: false, c: '' })).toBe('?a=0&b=false&c=');
	});
});

describe('apiFormPost', () => {
	it('attaches bearer auth but no Content-Type (lets the browser set multipart boundary)', async () => {
		setToken('tok-form');
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		const fd = new FormData();
		fd.append('file', 'x');
		await apiFormPost('/api/upload', fd);
		const init = mockFetch.mock.calls[0][1];
		expect(init.method).toBe('POST');
		expect(init.headers).toEqual(expect.objectContaining({ Authorization: 'Bearer tok-form' }));
		expect(init.headers).not.toHaveProperty('Content-Type');
		expect(init.body).toBe(fd);
	});

	it('omits Authorization when no token', async () => {
		mockFetch.mockResolvedValue(jsonResponse({}));
		await apiFormPost('/api/upload', new FormData());
		const init = mockFetch.mock.calls[0][1];
		expect(init.headers).not.toHaveProperty('Authorization');
	});
});
