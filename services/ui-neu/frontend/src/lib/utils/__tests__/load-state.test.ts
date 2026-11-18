import { describe, expect, it, vi } from 'vitest';
import { isPending, loadView, type LoadInputs } from '../load-state';

function inputs<T>(over: Partial<LoadInputs<T>> = {}): LoadInputs<T> {
	return { data: undefined, loading: false, error: null, skeletonShown: false, ...over };
}

describe('isPending', () => {
	it('is pending while loading or before any data', () => {
		expect(isPending({ data: [1], loading: true, error: null })).toBe(true);
		expect(isPending({ data: null, loading: false, error: null })).toBe(true);
		expect(isPending({ data: undefined, loading: false, error: null })).toBe(true);
	});

	it('is not pending once data is in, or on an error', () => {
		expect(isPending({ data: [], loading: false, error: null })).toBe(false);
		expect(isPending({ data: null, loading: true, error: new Error('x') })).toBe(false);
	});
});

describe('loadView', () => {
	it('error wins over the skeleton, loading and data, and carries the error', () => {
		const error = new Error('boom');
		expect(loadView(inputs({ error, loading: true, skeletonShown: true, data: [1] }))).toEqual({
			phase: 'error',
			error
		});
		expect(loadView(inputs({ error, data: [1] }))).toEqual({ phase: 'error', error });
	});

	it('a skeleton on screen is loading, even once the data is in', () => {
		expect(loadView(inputs({ loading: true, skeletonShown: true }))).toEqual({ phase: 'loading' });
		expect(loadView(inputs({ data: [1], skeletonShown: true }))).toEqual({ phase: 'loading' });
	});

	it('loading without the skeleton is waiting', () => {
		expect(loadView(inputs({ loading: true }))).toEqual({ phase: 'waiting' });
	});

	it('not loading with null or undefined data is waiting, not the skeleton', () => {
		expect(loadView(inputs({ data: null }))).toEqual({ phase: 'waiting' });
		expect(loadView(inputs({ data: undefined }))).toEqual({ phase: 'waiting' });
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
