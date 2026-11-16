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
