import { describe, it, expect } from 'vitest';
import { rippingToggleLabel } from '../ripping-toggle';

describe('rippingToggleLabel', () => {
	it('reads Auto-Start while ripping is enabled', () => {
		expect(rippingToggleLabel(true, false)).toBe('Auto-Start');
	});

	it('reads Auto-Start while enabled even with Review first on', () => {
		expect(rippingToggleLabel(true, true)).toBe('Auto-Start');
	});

	it('reads Hold for Review when paused with Review first on', () => {
		expect(rippingToggleLabel(false, true)).toBe('Hold for Review');
	});

	it('reads Paused when paused with Review first off', () => {
		expect(rippingToggleLabel(false, false)).toBe('Paused');
	});
});
