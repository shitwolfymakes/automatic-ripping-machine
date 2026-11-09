import { describe, expect, it, vi } from 'vitest';
import { loadPhase, type LoadInputs } from '../load-state';

function inputs<T>(over: Partial<LoadInputs<T>> = {}): LoadInputs<T> {
	return { data: undefined, loading: false, error: null, delayElapsed: false, ...over };
}

describe('loadPhase', () => {
	it('error wins over loading and data', () => {
		const error = new Error('boom');
		expect(loadPhase(inputs({ error, loading: true, delayElapsed: true, data: [1] }))).toBe('error');
		expect(loadPhase(inputs({ error, data: [1] }))).toBe('error');
	});

	it('loading with the delay elapsed is loading', () => {
		expect(loadPhase(inputs({ loading: true, delayElapsed: true }))).toBe('loading');
	});

	it('loading before the delay elapsed is waiting', () => {
		expect(loadPhase(inputs({ loading: true }))).toBe('waiting');
	});

	it('not loading with null or undefined data is loading', () => {
		expect(loadPhase(inputs({ data: null }))).toBe('loading');
		expect(loadPhase(inputs({ data: undefined }))).toBe('loading');
	});

	it('an empty array is empty by default', () => {
		expect(loadPhase(inputs({ data: [] }))).toBe('empty');
	});

	it('a non-empty array, an object, 0 and an empty string are ready by default', () => {
		expect(loadPhase(inputs({ data: [1] }))).toBe('ready');
		expect(loadPhase(inputs({ data: { a: 1 } }))).toBe('ready');
		expect(loadPhase(inputs({ data: 0 }))).toBe('ready');
		expect(loadPhase(inputs({ data: '' }))).toBe('ready');
	});

	it('a custom isEmpty is called with the data and decides', () => {
		const isEmpty = vi.fn(() => true);
		expect(loadPhase(inputs({ data: [1], isEmpty }))).toBe('empty');
		expect(isEmpty).toHaveBeenCalledWith([1]);
		expect(loadPhase(inputs({ data: [], isEmpty: () => false }))).toBe('ready');
	});
});
