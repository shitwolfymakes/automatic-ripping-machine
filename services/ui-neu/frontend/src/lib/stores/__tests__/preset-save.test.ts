import { describe, it, expect, vi } from 'vitest';
import { PresetSave } from '../preset-save.svelte';

describe('PresetSave', () => {
	it('is idle with no error before a run', () => {
		const save = new PresetSave();
		expect(save.submitting).toBe(false);
		expect(save.error).toBeNull();
	});

	it('is submitting while the save is pending and idle after it succeeds', async () => {
		const save = new PresetSave();
		let resolve!: (v: string) => void;
		const pending = new Promise<string>((r) => (resolve = r));
		const done = save.run(() => pending, vi.fn());
		expect(save.submitting).toBe(true);
		resolve('ok');
		await done;
		expect(save.submitting).toBe(false);
	});

	it('passes the result to onsaved once and keeps error null on success', async () => {
		const save = new PresetSave();
		const onsaved = vi.fn();
		await save.run(() => Promise.resolve({ id: 1 }), onsaved);
		expect(onsaved).toHaveBeenCalledTimes(1);
		expect(onsaved).toHaveBeenCalledWith({ id: 1 });
		expect(save.error).toBeNull();
	});

	it('keeps an Error message, skips onsaved, and is idle after a failure', async () => {
		const save = new PresetSave();
		const onsaved = vi.fn();
		await save.run(() => Promise.reject(new Error('boom')), onsaved);
		expect(save.error).toBe('boom');
		expect(onsaved).not.toHaveBeenCalled();
		expect(save.submitting).toBe(false);
	});

	it('reports "Save failed" for a rejection that is not an Error', async () => {
		const save = new PresetSave();
		await save.run(() => Promise.reject('nope'), vi.fn());
		expect(save.error).toBe('Save failed');
	});

	it('catches a throw from onsaved as the error', async () => {
		const save = new PresetSave();
		await save.run(
			() => Promise.resolve(1),
			() => {
				throw new Error('onsaved broke');
			}
		);
		expect(save.error).toBe('onsaved broke');
		expect(save.submitting).toBe(false);
	});

	it('clears the previous error when a second run starts', async () => {
		const save = new PresetSave();
		await save.run(() => Promise.reject(new Error('first')), vi.fn());
		expect(save.error).toBe('first');
		let resolve!: (v: number) => void;
		const pending = new Promise<number>((r) => (resolve = r));
		const done = save.run(() => pending, vi.fn());
		expect(save.error).toBeNull();
		resolve(1);
		await done;
		expect(save.error).toBeNull();
	});
});
