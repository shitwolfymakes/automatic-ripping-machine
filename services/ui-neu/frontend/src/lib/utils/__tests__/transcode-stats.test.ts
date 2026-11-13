import { describe, it, expect } from 'vitest';
import { taskCount } from '$lib/transcode/stats';
import type { TranscodeStatsView } from '$lib/types/api.gen';

describe('taskCount', () => {
	it('returns the count for a status present in tasks_by_status', () => {
		const stats = { tasks_by_status: { queued: 3 } } as unknown as TranscodeStatsView;
		expect(taskCount(stats, 'queued')).toBe(3);
	});

	it('returns 0 for a status missing from tasks_by_status', () => {
		const stats = { tasks_by_status: { queued: 3 } } as unknown as TranscodeStatsView;
		expect(taskCount(stats, 'failed')).toBe(0);
	});

	it('returns 0 when tasks_by_status is missing', () => {
		const stats = {} as unknown as TranscodeStatsView;
		expect(taskCount(stats, 'queued')).toBe(0);
	});
});
