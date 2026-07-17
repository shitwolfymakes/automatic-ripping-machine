import { describe, it, expect, vi, beforeEach } from 'vitest';
import { skipAndFinalize } from '$lib/api/jobs';

// Mock the global fetch
const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

describe('skipAndFinalize (MISSING in v3)', () => {
	beforeEach(() => {
		vi.clearAllMocks();
	});

	it('rejects with a not-available error before any fetch', async () => {
		await expect(skipAndFinalize('job_42')).rejects.toThrow(/not yet available in v3/);
		expect(mockFetch).not.toHaveBeenCalled();
	});
});
