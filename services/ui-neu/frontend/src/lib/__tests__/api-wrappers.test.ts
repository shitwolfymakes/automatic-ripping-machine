import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('$lib/api/client', () => ({
	apiFetch: vi.fn().mockResolvedValue({})
}));

import { apiFetch } from '$lib/api/client';
import { fetchDashboard, setRippingEnabled } from '../api/dashboard';

const mockApiFetch = vi.mocked(apiFetch);

beforeEach(() => {
	mockApiFetch.mockClear();
});

describe('dashboard API', () => {
	it('fetchDashboard calls /api/dashboard', async () => {
		await fetchDashboard();
		expect(mockApiFetch).toHaveBeenCalledWith('/api/dashboard');
	});

	it('setRippingEnabled POSTs enabled=true', async () => {
		await setRippingEnabled(true);
		expect(mockApiFetch).toHaveBeenCalledWith('/api/system/ripping-enabled', {
			method: 'POST',
			body: JSON.stringify({ enabled: true })
		});
	});

	it('setRippingEnabled POSTs enabled=false', async () => {
		await setRippingEnabled(false);
		expect(mockApiFetch).toHaveBeenCalledWith('/api/system/ripping-enabled', {
			method: 'POST',
			body: JSON.stringify({ enabled: false })
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
