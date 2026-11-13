import { describe, it, expect } from 'vitest';
import { PendingKeys } from '../../../settings/pending-keys.svelte';

function deferred<T>() {
	let resolve!: (v: T) => void;
	let reject!: (e: unknown) => void;
	const promise = new Promise<T>((res, rej) => {
		resolve = res;
		reject = rej;
	});
	return { promise, resolve, reject };
}

describe('PendingKeys', () => {
	it('has is false for a key never run', () => {
		expect(new PendingKeys().has('a')).toBe(false);
	});

	it('has is true while the task is pending and false once it resolves', async () => {
		const pending = new PendingKeys();
		const d = deferred<number>();
		const done = pending.run('a', () => d.promise);
		expect(pending.has('a')).toBe(true);
		d.resolve(1);
		await done;
		expect(pending.has('a')).toBe(false);
	});

	it('run returns the value the task resolves with', async () => {
		expect(await new PendingKeys().run('a', async () => 42)).toBe(42);
	});

	it('run rethrows the task error and clears the key', async () => {
		const pending = new PendingKeys();
		const boom = new Error('boom');
		await expect(
			pending.run('a', async () => {
				throw boom;
			})
		).rejects.toBe(boom);
		expect(pending.has('a')).toBe(false);
	});

	it('tracks two keys in flight apart', async () => {
		const pending = new PendingKeys();
		const a = deferred<void>();
		const b = deferred<void>();
		const doneA = pending.run('a', () => a.promise);
		const doneB = pending.run('b', () => b.promise);
		expect(pending.has('a')).toBe(true);
		expect(pending.has('b')).toBe(true);
		a.resolve();
		await doneA;
		expect(pending.has('a')).toBe(false);
		expect(pending.has('b')).toBe(true);
		b.resolve();
		await doneB;
		expect(pending.has('b')).toBe(false);
	});
});
