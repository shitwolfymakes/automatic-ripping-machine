import { describe, it, expect, beforeEach, vi } from 'vitest';

const KEY = 'arm_session_list_filters';

beforeEach(() => {
	sessionStorage.clear();
	vi.resetModules();
});

describe('sessionListFilters', () => {
	it('starts each list unfiltered', async () => {
		const { listFilters } = await import('../sessionListFilters.svelte');
		for (const list of ['sessions', 'rip', 'transcode'] as const) {
			const f = listFilters(list);
			expect([f.type, f.source, f.search, f.transcode]).toEqual(['all', 'all', '', 'any']);
		}
	});

	it('keeps each list apart', async () => {
		const { listFilters } = await import('../sessionListFilters.svelte');
		listFilters('rip').search = 'dvd';
		listFilters('transcode').type = 'music';
		expect(listFilters('rip').type).toBe('all');
		expect(listFilters('transcode').search).toBe('');
		expect(listFilters('sessions').search).toBe('');
	});

	it('saves to session storage and reads it back on a fresh load', async () => {
		const { listFilters } = await import('../sessionListFilters.svelte');
		const s = listFilters('sessions');
		s.search = 'plex';
		s.type = 'tv';
		s.source = 'custom';
		s.transcode = 'has';
		expect(JSON.parse(sessionStorage.getItem(KEY)!).sessions).toEqual({
			type: 'tv',
			source: 'custom',
			search: 'plex',
			transcode: 'has'
		});
		vi.resetModules();
		const fresh = (await import('../sessionListFilters.svelte')).listFilters('sessions');
		expect([fresh.type, fresh.source, fresh.search, fresh.transcode]).toEqual(['tv', 'custom', 'plex', 'has']);
	});

	it('drops unknown or corrupt stored values back to unfiltered', async () => {
		sessionStorage.setItem(
			KEY,
			JSON.stringify({ rip: { type: 'laserdisc', source: 'custom', search: 7, transcode: 'maybe' } })
		);
		const { listFilters } = await import('../sessionListFilters.svelte');
		const rip = listFilters('rip');
		expect([rip.type, rip.source, rip.search, rip.transcode]).toEqual(['all', 'custom', '', 'any']);

		sessionStorage.setItem(KEY, '{not json');
		vi.resetModules();
		const fresh = (await import('../sessionListFilters.svelte')).listFilters('rip');
		expect(fresh.source).toBe('all');
	});

	it.each([
		['type', 'movie'],
		['source', 'builtin'],
		['search', 'bluray']
	] as const)('saves a lone %s change across a reload', async (field, value) => {
		const { listFilters } = await import('../sessionListFilters.svelte');
		(listFilters('rip') as unknown as Record<string, string>)[field] = value;
		vi.resetModules();
		const fresh = (await import('../sessionListFilters.svelte')).listFilters('rip');
		expect(fresh[field]).toBe(value);
	});

	it('treats a stored JSON null as nothing saved', async () => {
		sessionStorage.setItem(KEY, 'null');
		const { listFilters } = await import('../sessionListFilters.svelte');
		const s = listFilters('sessions');
		expect([s.type, s.source, s.search, s.transcode]).toEqual(['all', 'all', '', 'any']);
	});

	it('resetListFilters clears every list and the stored copy', async () => {
		const { listFilters, resetListFilters } = await import('../sessionListFilters.svelte');
		listFilters('sessions').search = 'x';
		resetListFilters();
		expect(listFilters('sessions').search).toBe('');
		expect(sessionStorage.getItem(KEY)).toBeNull();
	});
});
