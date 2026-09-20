import { describe, it, expect } from 'vitest';
import { sortTranscodeTasks } from '$lib/utils/transcode-sort';

const t = (status: string, created_at: string) => ({ status, created_at }) as any;

describe('sortTranscodeTasks', () => {
	it('in_progress floats above others', () => {
		const arr = [t('done', '2026-01-02'), t('in_progress', '2026-01-01'), t('queued', '2026-01-03')];
		arr.sort(sortTranscodeTasks);
		expect(arr[0].status).toBe('in_progress');
	});
	it('within a group, newest created_at first', () => {
		const arr = [t('done', '2026-01-01'), t('done', '2026-01-03'), t('done', '2026-01-02')];
		arr.sort(sortTranscodeTasks);
		expect(arr.map((x) => x.created_at)).toEqual(['2026-01-03', '2026-01-02', '2026-01-01']);
	});
});
