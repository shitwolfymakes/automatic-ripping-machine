import { describe, it, expect, beforeEach, vi } from 'vitest';

vi.mock('$app/environment', () => ({ browser: false }));

const KEY = 'arm_session_list_filters';
const SAVED = JSON.stringify({ sessions: { type: 'tv', source: 'custom', search: 'plex', transcode: 'has' } });

beforeEach(() => {
	sessionStorage.clear();
	vi.resetModules();
});

describe('sessionListFilters outside the browser', () => {
	it('ignores session storage when loading, saving and resetting', async () => {
		sessionStorage.setItem(KEY, SAVED);
		const { listFilters, resetListFilters } = await import('../session-list-filters.svelte');
		const s = listFilters('sessions');
		expect([s.type, s.source, s.search, s.transcode]).toEqual(['all', 'all', '', 'any']);

		s.search = 'dvd';
		expect(s.search).toBe('dvd');
		expect(sessionStorage.getItem(KEY)).toBe(SAVED);

		resetListFilters();
		expect(s.search).toBe('');
		expect(sessionStorage.getItem(KEY)).toBe(SAVED);
	});
});
