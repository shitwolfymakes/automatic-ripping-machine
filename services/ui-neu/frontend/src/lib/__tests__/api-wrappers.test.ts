import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	apiFetch: vi.fn().mockResolvedValue({})
}));

import { apiFetch } from '$lib/api/client';
import { setRippingEnabled } from '../api/dashboard';

const mockApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
	mockApiFetch.mockClear();
});

// fetchDashboard is no longer a thin BFF wrapper — v3 has no /api/dashboard
// endpoint, so it composes client-side by fanning out across the drives/jobs/
// transcoder/notifications/config modules (each routes through its own get/post
// helper, not the mocked apiFetch here). Its composition + sticky-merge
// behaviour is covered by dashboard-store.test.ts. Only setRippingEnabled still
// routes through the client helper, so that's all this block asserts.
describe('dashboard API', () => {
	it('setRippingEnabled PATCHes /api/config with ripping_paused=false, hold_for_review=false when enabled', async () => {
		await setRippingEnabled(true);
		expect(mockApiFetch).toHaveBeenCalledWith('/api/config', {
			method: 'PATCH',
			body: JSON.stringify({ ripping_paused: false, hold_for_review: false })
		});
	});

	it('setRippingEnabled PATCHes /api/config with ripping_paused=true, hold_for_review=true when disabled', async () => {
		await setRippingEnabled(false);
		expect(mockApiFetch).toHaveBeenCalledWith('/api/config', {
			method: 'PATCH',
			body: JSON.stringify({ ripping_paused: true, hold_for_review: true })
		});
	});
});

// drives API is covered by drives-api.test.ts (repointed to v3: get/patch
// helpers, DriveView, string ids). It was removed from this wrapper test
// because drives.ts no longer routes through the mocked `apiFetch`.
//
// notifications API is covered by notifications-api.test.ts (repointed to v3:
// get/patch/post helpers, NotificationInboxView, string ids). It was removed
// here because notifications.ts no longer routes through the mocked `apiFetch`.
