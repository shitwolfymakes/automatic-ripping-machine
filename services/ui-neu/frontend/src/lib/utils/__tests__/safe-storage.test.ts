import { describe, it, expect, vi, afterEach } from 'vitest';
import { readStorage, writeStorage, removeStorage } from '../safe-storage';

function blockStorage() {
	const blocked = () => {
		throw new DOMException('blocked', 'SecurityError');
	};
	vi.spyOn(Storage.prototype, 'getItem').mockImplementation(blocked);
	vi.spyOn(Storage.prototype, 'setItem').mockImplementation(blocked);
	vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(blocked);
}

afterEach(() => {
	vi.restoreAllMocks();
	localStorage.clear();
});

describe('safe storage with localStorage available', () => {
	it('writes, reads and removes through localStorage', () => {
		writeStorage('k', 'v');
		expect(localStorage.getItem('k')).toBe('v');
		expect(readStorage('k')).toBe('v');
		removeStorage('k');
		expect(localStorage.getItem('k')).toBeNull();
		expect(readStorage('k')).toBeNull();
	});
});

describe('safe storage with localStorage blocked', () => {
	it('reads null for a key never written', () => {
		blockStorage();
		expect(readStorage('missing')).toBeNull();
	});

	it('keeps a written value in memory for this page load', () => {
		blockStorage();
		writeStorage('k', 'v');
		expect(readStorage('k')).toBe('v');
	});

	it('removes the in-memory value', () => {
		blockStorage();
		writeStorage('k', 'v');
		removeStorage('k');
		expect(readStorage('k')).toBeNull();
	});
});

describe('safe storage when writes fail but reads still work', () => {
	function failWrites() {
		return vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
			throw new DOMException('full', 'QuotaExceededError');
		});
	}

	it('reads back the value whose write failed, not the older stored one', () => {
		localStorage.setItem('k', 'old');
		failWrites();
		writeStorage('k', 'new');
		expect(readStorage('k')).toBe('new');
		// the stale copy is gone, so a reload cannot bring it back
		expect(localStorage.getItem('k')).toBeNull();
		removeStorage('k');
	});

	it('lets a later successful write replace the in-memory value', () => {
		const writes = failWrites();
		writeStorage('k', 'new');
		writes.mockRestore();
		writeStorage('k', 'newer');
		expect(readStorage('k')).toBe('newer');
		removeStorage('k');
	});

	it('keeps a new sign-in token instead of the stored old one', async () => {
		const { setToken, getToken, clearToken } = await import('$lib/api/client');
		localStorage.setItem('arm_token', 'old-token');
		failWrites();
		setToken('new-token');
		expect(getToken()).toBe('new-token');
		clearToken();
	});
});
