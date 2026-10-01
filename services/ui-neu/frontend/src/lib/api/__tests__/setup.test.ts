import { describe, it, expect, vi, beforeEach } from 'vitest';

const get = vi.fn(() => Promise.resolve({}));
const post = vi.fn(() => Promise.resolve({}));
const put = vi.fn(() => Promise.resolve({}));
vi.mock('../client', () => ({
	get: (...a: unknown[]) => get(...(a as [])),
	post: (...a: unknown[]) => post(...(a as [])),
	put: (...a: unknown[]) => put(...(a as []))
}));

import {
	fetchSetupStatus,
	fetchSetup,
	putSetupStep,
	completeSetup,
	restartSetup,
	dismissSetupChecklist,
	fetchDiscRoutes
} from '../setup';

describe('setup api', () => {
	beforeEach(() => vi.clearAllMocks());

	it('hits each setup route', async () => {
		await fetchSetupStatus();
		await fetchSetup();
		await fetchDiscRoutes();
		expect(get.mock.calls.map((c) => (c as unknown[])[0])).toEqual([
			'/api/setup/status',
			'/api/setup',
			'/api/setup/disc-routes'
		]);
		await putSetupStep('drives', 'attention');
		expect(put).toHaveBeenCalledWith('/api/setup/steps/drives', { state: 'attention' });
		await completeSetup();
		await restartSetup();
		await dismissSetupChecklist();
		expect(post.mock.calls.map((c) => (c as unknown[])[0])).toEqual([
			'/api/setup/complete',
			'/api/setup/restart',
			'/api/setup/checklist/dismiss'
		]);
	});
});
