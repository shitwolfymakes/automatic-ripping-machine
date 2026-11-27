import { describe, it, expect } from 'vitest';
import { failureReasonOf } from '$lib/jobs/failure';

describe('failureReasonOf', () => {
	it('returns the reason text', () => {
		expect(failureReasonOf({ failure_reason: 'MakeMKV could not open this disc.' })).toBe(
			'MakeMKV could not open this disc.'
		);
	});
	it('trims surrounding whitespace', () => {
		expect(failureReasonOf({ failure_reason: '  why \n' })).toBe('why');
	});
	it.each([null, undefined, '', '   '])('is null for %j', (value) => {
		expect(failureReasonOf({ failure_reason: value })).toBeNull();
	});
	it('is null without a job', () => {
		expect(failureReasonOf(null)).toBeNull();
		expect(failureReasonOf(undefined)).toBeNull();
	});
});
