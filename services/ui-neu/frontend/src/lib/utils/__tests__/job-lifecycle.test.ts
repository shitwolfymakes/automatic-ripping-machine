import { describe, it, expect } from 'vitest';
import { deriveLifecycle } from '$lib/utils/job-lifecycle';
import { effectiveJobStatus } from '$lib/utils/job-status';

const job = (status: string, transcode_progress: any = null) => ({ status, transcode_progress }) as any;

describe('lifecycle via effective status', () => {
	it('a done job lights the Complete node', () => {
		const eff = effectiveJobStatus(job('ripped', { state: 'done', tasks_total: 1, tasks_done: 1, percent: 100 }));
		const nodes = deriveLifecycle(eff, null);
		expect(nodes.find((n) => n.id === 'complete')!.state).toBe('completed');
	});
	it('a transcoding job marks Transcoding active', () => {
		const eff = effectiveJobStatus(job('ripped', { state: 'transcoding', tasks_total: 1, tasks_done: 0, percent: 0 }));
		const nodes = deriveLifecycle(eff, null);
		expect(nodes.find((n) => n.id === 'transcoding')!.state).toBe('active');
	});
	it('a ripped job with no session is NOT fully pending (ripping done)', () => {
		const eff = effectiveJobStatus(job('ripped', null)); // stays 'ripped'
		const nodes = deriveLifecycle(eff, null);
		// ripped maps to the ripping stage as completed-or-active (see step 3)
		expect(nodes.find((n) => n.id === 'ripping')!.state).not.toBe('pending');
	});
});
