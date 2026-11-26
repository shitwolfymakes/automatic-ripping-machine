import { describe, it, expect, vi } from 'vitest';
import { get } from 'svelte/store';

vi.mock('$app/environment', () => ({ browser: false }));
vi.mock('$lib/api/dashboard', () => ({
	fetchDashboardSnapshot: vi.fn(() => Promise.resolve({ db_available: true, arm_online: true })),
	STICKY_FIELDS: ['notification_count']
}));

import { fetchDashboardSnapshot } from '$lib/api/dashboard';
import { dashboard } from '../dashboard';

async function poll(reading: Record<string, unknown>): Promise<any> {
	vi.mocked(fetchDashboardSnapshot).mockResolvedValueOnce(reading as any);
	await dashboard.refresh();
	return get(dashboard);
}

describe('dashboard store', () => {
	it('exports a polling store with subscribe', () => {
		expect(dashboard).toBeDefined();
		expect(typeof dashboard.subscribe).toBe('function');
	});

	it('has initial empty dashboard data', () => {
		let value: any;
		const unsub = dashboard.subscribe((v) => (value = v));
		expect(value.db_available).toBe(true);
		expect(value.active_jobs).toEqual([]);
		unsub();
	});

	it('holds a sticky field that reads null or undefined and takes a fresh one', async () => {
		expect((await poll({ notification_count: 4 })).notification_count).toBe(4);
		expect((await poll({ notification_count: null })).notification_count).toBe(4);
		expect((await poll({})).notification_count).toBe(4);
		expect((await poll({ notification_count: 0 })).notification_count).toBe(0);
	});

	it('shows a single false reading as online and surfaces the second', async () => {
		expect((await poll({ arm_online: true, transcoder_online: true })).arm_online).toBe(true);
		const first = await poll({ arm_online: false, transcoder_online: true });
		expect(first.arm_online).toBe(true);
		const second = await poll({ arm_online: false, transcoder_online: true });
		expect(second.arm_online).toBe(false);
	});

	it('resets the false streak when a field reads true again', async () => {
		await poll({ arm_online: false });
		await poll({ arm_online: true });
		expect((await poll({ arm_online: false })).arm_online).toBe(true);
	});
});
