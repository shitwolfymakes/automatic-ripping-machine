import { describe, it, expect, vi, beforeEach } from 'vitest';

const isScreenEnabled = vi.hoisted(() => vi.fn((_path: string) => true));
vi.mock('$lib/features', () => ({ isScreenEnabled }));

import { NAV_ITEMS, visibleNavItems, isActive } from '$lib/layout/nav';

const ON = { transcoderEnabled: true, isGuest: false };
const hrefs = (items: readonly { href: string }[]) => items.map((i) => i.href);

beforeEach(() => {
	isScreenEnabled.mockReset();
	isScreenEnabled.mockReturnValue(true);
});

describe('NAV_ITEMS', () => {
	it('lists the seven items in sidebar order', () => {
		expect(hrefs(NAV_ITEMS)).toEqual(['/', '/notifications', '/logs', '/files', '/transcoder', '/settings', '/help']);
	});
});

describe('visibleNavItems', () => {
	it('keeps every item when nothing is hidden', () => {
		expect(visibleNavItems(NAV_ITEMS, ON)).toEqual([...NAV_ITEMS]);
	});

	it('drops an item whose screen is disabled', () => {
		isScreenEnabled.mockImplementation((p: string) => p !== '/logs');
		expect(hrefs(visibleNavItems(NAV_ITEMS, ON))).not.toContain('/logs');
	});

	it('hides Transcoder when the transcoder is disabled', () => {
		const out = visibleNavItems(NAV_ITEMS, { ...ON, transcoderEnabled: false });
		expect(hrefs(out)).not.toContain('/transcoder');
		expect(hrefs(out)).toContain('/settings');
	});

	it('hides Settings from guests', () => {
		const out = visibleNavItems(NAV_ITEMS, { ...ON, isGuest: true });
		expect(hrefs(out)).not.toContain('/settings');
		expect(hrefs(out)).toContain('/transcoder');
	});
});

describe('isActive', () => {
	it('matches the root only on the exact root path', () => {
		expect(isActive('/', '/')).toBe(true);
		expect(isActive('/', '/logs')).toBe(false);
	});

	it('matches other items by path prefix', () => {
		expect(isActive('/logs', '/logs/42')).toBe(true);
		expect(isActive('/logs', '/files')).toBe(false);
	});
});
