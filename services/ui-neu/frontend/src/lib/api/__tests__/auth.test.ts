import { describe, it, expect, vi, beforeEach } from 'vitest';
import { login, logout, changePassword } from '../auth';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function jsonResponse(data: unknown, ok = true, status = 200, statusText = 'OK') {
	return { ok, status, statusText, json: () => Promise.resolve(data) };
}

beforeEach(() => {
	mockFetch.mockReset();
	localStorage.clear();
});

describe('login', () => {
	it('POSTs credentials to /api/auth/login and returns the response', async () => {
		const body = { access_token: 'tok', expires_at: '2026-01-01T00:00:00Z', password_must_change: false };
		mockFetch.mockResolvedValue(jsonResponse(body));
		const res = await login('admin', 'pw');
		expect(res).toEqual(body);
		const [path, init] = mockFetch.mock.calls[0];
		expect(path).toBe('/api/auth/login');
		expect(init.method).toBe('POST');
		expect(JSON.parse(init.body)).toEqual({ username: 'admin', password: 'pw' });
	});

	it('propagates a 401 as a thrown error', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ detail: 'invalid credentials' }, false, 401, 'Unauthorized'));
		await expect(login('admin', 'bad')).rejects.toThrow();
	});
});

describe('logout', () => {
	it('POSTs to /api/auth/logout', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		await logout();
		expect(mockFetch.mock.calls[0][0]).toBe('/api/auth/logout');
		expect(mockFetch.mock.calls[0][1].method).toBe('POST');
	});
});

describe('changePassword', () => {
	it('POSTs current+new to /api/auth/password', async () => {
		mockFetch.mockResolvedValue(jsonResponse({ ok: true }));
		await changePassword('old', 'newpassw0rd');
		const [path, init] = mockFetch.mock.calls[0];
		expect(path).toBe('/api/auth/password');
		expect(init.method).toBe('POST');
		expect(JSON.parse(init.body)).toEqual({ current_password: 'old', new_password: 'newpassw0rd' });
	});
});
