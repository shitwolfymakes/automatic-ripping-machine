import { describe, it, expect } from 'vitest';
import { PASSWORD_MIN_LENGTH, passwordProblem } from '$lib/utils/password';

const DIFFER = 'New password must differ from the current password';
const SHORT = `New password must be at least ${PASSWORD_MIN_LENGTH} characters`;
const MISMATCH = 'Passwords do not match';

describe('passwordProblem', () => {
	it('reports a new password equal to the current one', () => {
		expect(passwordProblem('longenough1', 'longenough1', 'longenough1')).toBe(DIFFER);
	});

	it('reports a password shorter than the minimum', () => {
		expect(passwordProblem('old', 'short', 'short')).toBe(SHORT);
	});

	it('accepts a password exactly the minimum length', () => {
		const next = 'a'.repeat(PASSWORD_MIN_LENGTH);
		expect(passwordProblem('old', next, next)).toBeNull();
	});

	it('reports a password that does not match its confirmation', () => {
		expect(passwordProblem('old', 'longenough1', 'longenough2')).toBe(MISMATCH);
	});

	it('reports an empty confirmation as not matching', () => {
		expect(passwordProblem('old', 'longenough1', '')).toBe(MISMATCH);
	});

	it('returns null when all three rules hold', () => {
		expect(passwordProblem('old', 'longenough1', 'longenough1')).toBeNull();
	});

	it('reports the must-differ rule before the length rule', () => {
		expect(passwordProblem('short', 'short', 'short')).toBe(DIFFER);
	});
});
