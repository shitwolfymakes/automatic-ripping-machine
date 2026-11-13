import { describe, it, expect } from 'vitest';
import { ApiError } from '$lib/api/client';
import { collisionsFromApplyError } from '$lib/sessions/apply-collisions';

const collision = { output_path: '/out/a.mkv', reason: 'on_disk' } as any;

describe('collisionsFromApplyError', () => {
	it('returns the collisions from a 409 body', () => {
		const e = new ApiError(409, 'Conflict', { detail: { collisions: [collision] } });
		expect(collisionsFromApplyError(e)).toEqual([collision]);
	});

	it('returns an empty collisions array from a 409 as it is', () => {
		const e = new ApiError(409, 'Conflict', { detail: { collisions: [] } });
		expect(collisionsFromApplyError(e)).toEqual([]);
	});

	it('returns null for a 409 whose detail has no collisions', () => {
		expect(collisionsFromApplyError(new ApiError(409, 'Conflict', { detail: {} }))).toBeNull();
	});

	it('returns null for a 409 with no detail', () => {
		expect(collisionsFromApplyError(new ApiError(409, 'Conflict', {}))).toBeNull();
	});

	it('returns null for a 409 with a null body', () => {
		expect(collisionsFromApplyError(new ApiError(409, 'Conflict', null))).toBeNull();
	});

	it('returns null for a 409 whose body is a string', () => {
		expect(collisionsFromApplyError(new ApiError(409, 'Conflict', 'nope'))).toBeNull();
	});

	it('returns null for a 500 even when the body has collisions', () => {
		const e = new ApiError(500, 'Server error', { detail: { collisions: [collision] } });
		expect(collisionsFromApplyError(e)).toBeNull();
	});

	it('returns null for a plain Error', () => {
		expect(collisionsFromApplyError(new Error('boom'))).toBeNull();
	});

	it('returns null for a non-Error', () => {
		expect(collisionsFromApplyError('boom')).toBeNull();
	});
});
