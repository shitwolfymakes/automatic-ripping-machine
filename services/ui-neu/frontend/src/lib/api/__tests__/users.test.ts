import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	get: vi.fn().mockResolvedValue([]),
	post: vi.fn().mockResolvedValue({}),
	patch: vi.fn().mockResolvedValue({})
}));

import { get, post, patch } from '$lib/api/client';
import { fetchUsers, setUserDisabled, setUserPassword } from '../users';

const mockGet = vi.mocked(get);
const mockPost = vi.mocked(post);
const mockPatch = vi.mocked(patch);

beforeEach(() => {
	mockGet.mockClear();
	mockPost.mockClear();
	mockPatch.mockClear();
});

describe('users api module', () => {
	it('fetchUsers GETs /api/users', async () => {
		await fetchUsers();
		expect(mockGet).toHaveBeenCalledWith('/api/users');
	});

	it('fetchUsers returns the rows the client resolves', async () => {
		const rows = [{ id: 'usr_guest', username: 'guest', role: 'guest', disabled: true }];
		mockGet.mockResolvedValueOnce(rows);
		await expect(fetchUsers()).resolves.toEqual(rows);
	});

	it('setUserDisabled PATCHes /api/users/{id} with the flag', async () => {
		await setUserDisabled('usr_guest', true);
		expect(mockPatch).toHaveBeenCalledWith('/api/users/usr_guest', { disabled: true });
	});

	it('setUserDisabled sends disabled:false when re-enabling', async () => {
		await setUserDisabled('usr_guest', false);
		expect(mockPatch).toHaveBeenCalledWith('/api/users/usr_guest', { disabled: false });
	});

	it('setUserPassword POSTs /api/users/{id}/password with the snake_case body', async () => {
		await setUserPassword('usr_guest', 'newguestpass');
		expect(mockPost).toHaveBeenCalledWith('/api/users/usr_guest/password', {
			new_password: 'newguestpass'
		});
	});
});
