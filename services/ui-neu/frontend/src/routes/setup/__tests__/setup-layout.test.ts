// Unit tests for the setup walkthrough's +layout.ts `load` guard: sign in
// first, and only the admin gets in.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { isRedirect } from '@sveltejs/kit';
import { load } from '../+layout';

const getTokenMock = vi.fn<() => string | null>(() => null);
vi.mock('$lib/api/client', () => ({
	getToken: () => getTokenMock()
}));

function redirectLocation(): string | undefined {
	try {
		load();
	} catch (e) {
		return isRedirect(e) ? e.location : undefined;
	}
	return undefined;
}

describe('setup +layout.ts load guard', () => {
	beforeEach(() => {
		getTokenMock.mockReset();
		getTokenMock.mockReturnValue(null);
		localStorage.clear();
	});

	afterEach(() => {
		vi.restoreAllMocks();
	});

	it('no token goes to /login', () => {
		localStorage.setItem('arm_role', 'admin');
		expect(redirectLocation()).toBe('/login');
	});

	it('a token with a non-admin stored role goes to /', () => {
		getTokenMock.mockReturnValue('tok');
		localStorage.setItem('arm_role', 'viewer');
		expect(redirectLocation()).toBe('/');
	});

	it('a token with no stored role goes to /', () => {
		getTokenMock.mockReturnValue('tok');
		expect(redirectLocation()).toBe('/');
	});

	it('an admin gets an empty load result', () => {
		getTokenMock.mockReturnValue('tok');
		localStorage.setItem('arm_role', 'admin');
		expect(load()).toEqual({});
	});

	it('a storage read that throws counts as no role', () => {
		getTokenMock.mockReturnValue('tok');
		vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
			throw new Error('storage blocked');
		});
		expect(redirectLocation()).toBe('/');
	});
});
