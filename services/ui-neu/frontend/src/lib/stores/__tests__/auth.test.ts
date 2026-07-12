import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import {
	isAuthenticated,
	passwordMustChange,
	role,
	isAdmin,
	isGuest,
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
		applyLogin({ access_token: 'tok-1', expires_at: 'x', password_must_change: true, role: 'admin' });
		expect(getToken()).toBe('tok-1');
		expect(get(isAuthenticated)).toBe(true);
		expect(get(passwordMustChange)).toBe(true);
	});

	it('logoutLocal clears the token and resets state', () => {
		applyLogin({ access_token: 'tok-2', expires_at: 'x', password_must_change: false, role: 'admin' });
		logoutLocal();
		expect(getToken()).toBeNull();
		expect(get(isAuthenticated)).toBe(false);
		expect(get(passwordMustChange)).toBe(false);
	});

	it('initAuth reflects a pre-existing token as authenticated', () => {
		applyLogin({ access_token: 'tok-3', expires_at: 'x', password_must_change: false, role: 'admin' });
		initAuth();
		expect(get(isAuthenticated)).toBe(true);
	});

	it('clearPasswordMustChange flips the flag (after a successful change)', () => {
		applyLogin({ access_token: 'tok-4', expires_at: 'x', password_must_change: true, role: 'admin' });
		clearPasswordMustChange();
		expect(get(passwordMustChange)).toBe(false);
	});

	it('applyLogin stores the role and derives isAdmin', () => {
		applyLogin({ access_token: 'tok-5', expires_at: 'x', password_must_change: false, role: 'admin' });
		expect(get(role)).toBe('admin');
		expect(get(isAdmin)).toBe(true);
		expect(get(isGuest)).toBe(false);
	});

	it('guest role derives isGuest', () => {
		applyLogin({ access_token: 'tok-6', expires_at: 'x', password_must_change: false, role: 'guest' });
		expect(get(role)).toBe('guest');
		expect(get(isGuest)).toBe(true);
		expect(get(isAdmin)).toBe(false);
	});

	it('initAuth restores persisted role', () => {
		applyLogin({ access_token: 'tok-7', expires_at: 'x', password_must_change: false, role: 'guest' });
		initAuth();
		expect(get(isGuest)).toBe(true);
	});

	it('logoutLocal clears role', () => {
		applyLogin({ access_token: 'tok-8', expires_at: 'x', password_must_change: false, role: 'admin' });
		logoutLocal();
		expect(get(role)).toBeNull();
		expect(get(isAdmin)).toBe(false);
	});
});
