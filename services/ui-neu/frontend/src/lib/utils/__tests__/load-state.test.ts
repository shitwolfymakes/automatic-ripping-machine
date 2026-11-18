import { describe, expect, it, vi } from 'vitest';
import { loadView, type LoadInputs } from '../load-state';

function inputs<T>(over: Partial<LoadInputs<T>> = {}): LoadInputs<T> {
	return { data: undefined, loading: false, error: null, delayElapsed: false, ...over };
}

describe('loadView', () => {
	it('error wins over loading and data, and carries the error', () => {
		const error = new Error('boom');
		expect(loadView(inputs({ error, loading: true, delayElapsed: true, data: [1] }))).toEqual({
			phase: 'error',
			error
		});
		expect(loadView(inputs({ error, data: [1] }))).toEqual({ phase: 'error', error });
	});

	it('loading with the delay elapsed is loading', () => {
		expect(loadView(inputs({ loading: true, delayElapsed: true }))).toEqual({ phase: 'loading' });
	});

	it('loading before the delay elapsed is waiting', () => {
		expect(loadView(inputs({ loading: true }))).toEqual({ phase: 'waiting' });
	});

	it('not loading with null or undefined data is loading', () => {
		expect(loadView(inputs({ data: null }))).toEqual({ phase: 'loading' });
		expect(loadView(inputs({ data: undefined }))).toEqual({ phase: 'loading' });
	});

	it('an empty array is empty by default', () => {
		expect(loadView(inputs({ data: [] }))).toEqual({ phase: 'empty' });
	});

	it('a non-empty array, an object, 0 and an empty string are ready by default, and carry the data', () => {
		expect(loadView(inputs({ data: [1] }))).toEqual({ phase: 'ready', data: [1] });
		expect(loadView(inputs({ data: { a: 1 } }))).toEqual({ phase: 'ready', data: { a: 1 } });
		expect(loadView(inputs({ data: 0 }))).toEqual({ phase: 'ready', data: 0 });
		expect(loadView(inputs({ data: '' }))).toEqual({ phase: 'ready', data: '' });
	});

	it('a custom isEmpty is called with the data and decides', () => {
		const isEmpty = vi.fn(() => true);
		expect(loadView(inputs({ data: [1], isEmpty }))).toEqual({ phase: 'empty' });
		expect(isEmpty).toHaveBeenCalledWith([1]);
		expect(loadView(inputs({ data: [], isEmpty: () => false }))).toEqual({ phase: 'ready', data: [] });
	});
});
