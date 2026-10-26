import { describe, it, expect } from 'vitest';
import { formatFps } from './fps';

describe('formatFps', () => {
	it('shows the live rate with the average in brackets', () => {
		expect(formatFps(45.67, 23.46)).toBe('45.7 fps (avg 23.5)');
	});

	it('omits the average when the engine does not report one', () => {
		expect(formatFps(45.67, null)).toBe('45.7 fps');
		expect(formatFps(45.67)).toBe('45.7 fps');
	});

	it('is null until a rate has been reported', () => {
		expect(formatFps(null, 23.46)).toBeNull();
		expect(formatFps(undefined)).toBeNull();
	});
});
