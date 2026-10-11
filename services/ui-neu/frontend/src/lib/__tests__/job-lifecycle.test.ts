import { describe, it, expect } from 'vitest';
import { deriveLifecycle, isFolderImport, lifecycleColorVar } from '$lib/utils/job-lifecycle';

describe('deriveLifecycle - disc rip 5-step', () => {
	it('exposes the five stages in order', () => {
		const nodes = deriveLifecycle('created', 'disc');
		expect(nodes.map((n) => n.id)).toEqual(['waiting', 'identifying', 'ripping', 'transcoding', 'complete']);
	});

	it.each([
		['created', 1],
		['awaiting_review', 1],
		['identified', 1],
		['ripping', 2],
		['ripped', 2],
		['ripped_awaiting_identify', 2],
		['transcoding', 3]
	])('%s -> stage index %i active, earlier completed, later pending', (s, idx) => {
		const nodes = deriveLifecycle(s, 'disc');
		expect(nodes.slice(0, idx).every((n) => n.state === 'completed')).toBe(true);
		expect(nodes[idx].state).toBe('active');
		expect(nodes.slice(idx + 1).every((n) => n.state === 'pending')).toBe(true);
	});

	it('complete -> all completed', () => {
		expect(deriveLifecycle('complete', 'disc').every((n) => n.state === 'completed')).toBe(true);
	});
});

describe('deriveLifecycle - failure', () => {
	it.each(['failed', 'abandoned', 'transcode_failed'])('%s paints the stage before complete as failed', (s) => {
		const nodes = deriveLifecycle(s, 'disc');
		expect(nodes[3].state).toBe('failed');
		expect(nodes[4].state).toBe('pending');
		expect(nodes.slice(0, 3).every((n) => n.state === 'completed')).toBe(true);
	});

	it('folder import failure paints last non-complete stage too', () => {
		const nodes = deriveLifecycle('failed', 'folder');
		expect(nodes.map((n) => n.id)).toEqual(['waiting', 'identifying', 'ripping', 'transcoding', 'complete']);
		expect(nodes[3].state).toBe('failed');
	});
});

describe('deriveLifecycle - folder imports', () => {
	it('folder source uses the same 5-stage lifecycle as disc', () => {
		const nodes = deriveLifecycle('transcoding', 'folder');
		expect(nodes.map((n) => n.id)).toEqual(['waiting', 'identifying', 'ripping', 'transcoding', 'complete']);
		expect(nodes[3].state).toBe('active');
	});

	it('ripping on folder source paints ripping active', () => {
		const nodes = deriveLifecycle('ripping', 'folder');
		expect(nodes[2].id).toBe('ripping');
		expect(nodes[2].state).toBe('active');
	});
});

describe('deriveLifecycle - edge cases', () => {
	it('null status renders fully pending', () => {
		const nodes = deriveLifecycle(null, 'disc');
		expect(nodes.every((n) => n.state === 'pending')).toBe(true);
	});

	it('unknown status renders fully pending', () => {
		const nodes = deriveLifecycle('video_ripping', 'disc');
		expect(nodes.every((n) => n.state === 'pending')).toBe(true);
	});

	it('case-insensitive status matching', () => {
		const upper = deriveLifecycle('TRANSCODING', 'disc');
		expect(upper[3].state).toBe('active');
	});
});

describe('isFolderImport', () => {
	it('identifies folder source_type', () => {
		expect(isFolderImport('folder')).toBe(true);
		expect(isFolderImport('disc')).toBe(false);
		expect(isFolderImport(null)).toBe(false);
		expect(isFolderImport(undefined)).toBe(false);
	});
});

describe('lifecycleColorVar', () => {
	it('maps each state to a distinct CSS var', () => {
		const colors = ['completed', 'active', 'paused', 'failed', 'pending'].map((s) => lifecycleColorVar(s as never));
		// All distinct
		expect(new Set(colors).size).toBe(colors.length);
	});

	it('uses theme tokens for known statuses', () => {
		expect(lifecycleColorVar('completed')).toContain('--color-status-success');
		expect(lifecycleColorVar('failed')).toContain('--color-status-error');
		expect(lifecycleColorVar('active')).toContain('--color-status-ripping');
	});
});
