import { describe, expect, it } from 'vitest';
import { errorMessage } from '../errors';

describe('errorMessage', () => {
	it('returns the message of an Error', () => {
		expect(errorMessage(new Error('boom'), 'fallback')).toBe('boom');
	});

	it('returns the caller fallback for anything else', () => {
		expect(errorMessage('x', 'Unknown error')).toBe('Unknown error');
		expect(errorMessage(undefined, 'Save failed')).toBe('Save failed');
	});
});
