import { describe, expect, it, vi } from 'vitest';
import { isPending, loadPhase, type LoadInputs } from '../load-state';

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

describe('loadPhase', () => {
	it('error wins over the skeleton, loading and data', () => {
		const error = new Error('boom');
		expect(loadPhase(inputs({ error, loading: true, skeletonShown: true, data: [1] }))).toBe('error');
		expect(loadPhase(inputs({ error, data: [1] }))).toBe('error');
	});

	it('a skeleton on screen is loading, even once the data is in', () => {
		expect(loadPhase(inputs({ loading: true, skeletonShown: true }))).toBe('loading');
		expect(loadPhase(inputs({ data: [1], skeletonShown: true }))).toBe('loading');
	});

	it('loading without the skeleton is waiting', () => {
		expect(loadPhase(inputs({ loading: true }))).toBe('waiting');
	});

	it('not loading with null or undefined data is waiting, not the skeleton', () => {
		expect(loadPhase(inputs({ data: null }))).toBe('waiting');
		expect(loadPhase(inputs({ data: undefined }))).toBe('waiting');
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
