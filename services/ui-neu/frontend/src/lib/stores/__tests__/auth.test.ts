import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import {
	isAuthenticated,
	passwordMustChange,
	applyLogin,
	logoutLocal,
	initAuth,
	clearPasswordMustChange
} from '../auth';
import { getToken } from '$lib/api/client';

beforeEach(() => {
	localStorage.clear();
	logoutLocal();
});

describe('auth store', () => {
	it('starts unauthenticated with no token', () => {
		initAuth();
		expect(get(isAuthenticated)).toBe(false);
		expect(get(passwordMustChange)).toBe(false);
	});

	it('applyLogin stores the token and sets authenticated + passwordMustChange', () => {
		applyLogin({ access_token: 'tok-1', expires_at: 'x', password_must_change: true });
		expect(getToken()).toBe('tok-1');
		expect(get(isAuthenticated)).toBe(true);
		expect(get(passwordMustChange)).toBe(true);
	});

	it('logoutLocal clears the token and resets state', () => {
		applyLogin({ access_token: 'tok-2', expires_at: 'x', password_must_change: false });
		logoutLocal();
		expect(getToken()).toBeNull();
		expect(get(isAuthenticated)).toBe(false);
		expect(get(passwordMustChange)).toBe(false);
	});

	it('initAuth reflects a pre-existing token as authenticated', () => {
		applyLogin({ access_token: 'tok-3', expires_at: 'x', password_must_change: false });
		initAuth();
		expect(get(isAuthenticated)).toBe(true);
	});

	it('clearPasswordMustChange flips the flag (after a successful change)', () => {
		applyLogin({ access_token: 'tok-4', expires_at: 'x', password_must_change: true });
		clearPasswordMustChange();
		expect(get(passwordMustChange)).toBe(false);
	});
});
