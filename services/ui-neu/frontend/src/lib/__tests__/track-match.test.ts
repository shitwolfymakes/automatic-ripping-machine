import { describe, it, expect } from 'vitest';
import { matchIndicator } from '../utils/track-match';

describe('matchIndicator', () => {
	it('match when within 3s', () => {
		expect(matchIndicator(180000, 181)).toBe('match'); // 1s diff
		expect(matchIndicator(180000, 183)).toBe('match'); // 3s diff
	});
	it('close when within 10s', () => {
		expect(matchIndicator(180000, 188)).toBe('close'); // 8s diff
	});
	it('mismatch beyond 10s', () => {
		expect(matchIndicator(180000, 200)).toBe('mismatch'); // 20s diff
	});
	it('unknown when either side is null/undefined', () => {
		expect(matchIndicator(null, 180)).toBe('unknown');
		expect(matchIndicator(180000, null)).toBe('unknown');
		expect(matchIndicator(undefined, undefined)).toBe('unknown');
	});
});
