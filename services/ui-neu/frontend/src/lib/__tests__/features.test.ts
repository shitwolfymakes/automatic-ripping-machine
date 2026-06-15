import { describe, it, expect } from 'vitest';
import { features, isScreenEnabled } from '../features';

describe('features', () => {
	it('disables screens whose v3 backend is MISSING (files, setup, logs)', () => {
		expect(features.files).toBe(false);
		expect(features.setup).toBe(false);
		expect(features.logs).toBe(false);
	});

	it('enables screens v3 supports', () => {
		expect(features.dashboard).toBe(true);
		expect(features.notifications).toBe(true);
		expect(features.settings).toBe(true);
	});

	it('isScreenEnabled maps a nav href to its flag', () => {
		expect(isScreenEnabled('/files')).toBe(false);
		expect(isScreenEnabled('/setup')).toBe(false);
		expect(isScreenEnabled('/logs')).toBe(false);
		expect(isScreenEnabled('/')).toBe(true);
	});

	it('isScreenEnabled defaults unknown routes to enabled', () => {
		expect(isScreenEnabled('/something-new')).toBe(true);
	});
});
