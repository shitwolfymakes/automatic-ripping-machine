import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest';
import { ClipboardCopy } from '../clipboard-copy.svelte';

const original = Object.getOwnPropertyDescriptor(navigator, 'clipboard');

function stubClipboard(value: unknown): void {
	Object.defineProperty(navigator, 'clipboard', { value, configurable: true });
}

describe('ClipboardCopy', () => {
	beforeEach(() => {
		vi.useFakeTimers();
	});

	afterEach(() => {
		vi.useRealTimers();
		vi.unstubAllGlobals();
		if (original) Object.defineProperty(navigator, 'clipboard', original);
		else Reflect.deleteProperty(navigator, 'clipboard');
	});

	it('writes the text and sets copied once the write resolves', async () => {
		const writeText = vi.fn().mockResolvedValue(undefined);
		stubClipboard({ writeText });
		const c = new ClipboardCopy();
		expect(c.copied).toBe(false);
		c.copy('hello');
		expect(writeText).toHaveBeenCalledWith('hello');
		await vi.advanceTimersByTimeAsync(0);
		expect(c.copied).toBe(true);
	});

	it('clears copied 1500 ms later, not before', async () => {
		stubClipboard({ writeText: vi.fn().mockResolvedValue(undefined) });
		const c = new ClipboardCopy();
		c.copy('x');
		await vi.advanceTimersByTimeAsync(1499);
		expect(c.copied).toBe(true);
		await vi.advanceTimersByTimeAsync(1);
		expect(c.copied).toBe(false);
	});

	it('restarts the 1500 ms when copied again', async () => {
		stubClipboard({ writeText: vi.fn().mockResolvedValue(undefined) });
		const c = new ClipboardCopy();
		c.copy('x');
		await vi.advanceTimersByTimeAsync(1000);
		c.copy('y');
		await vi.advanceTimersByTimeAsync(1000);
		expect(c.copied).toBe(true);
		await vi.advanceTimersByTimeAsync(500);
		expect(c.copied).toBe(false);
	});

	it('leaves copied false and throws nothing when the write rejects', async () => {
		stubClipboard({ writeText: vi.fn().mockRejectedValue(new Error('denied')) });
		const c = new ClipboardCopy();
		c.copy('x');
		await vi.advanceTimersByTimeAsync(0);
		expect(c.copied).toBe(false);
	});

	it('writes nothing without a clipboard', async () => {
		stubClipboard(undefined);
		const c = new ClipboardCopy();
		c.copy('x');
		await vi.advanceTimersByTimeAsync(0);
		expect(c.copied).toBe(false);
	});

	it('does nothing when navigator is undefined', () => {
		vi.stubGlobal('navigator', undefined);
		const c = new ClipboardCopy();
		expect(() => c.copy('x')).not.toThrow();
		expect(c.copied).toBe(false);
	});
});
