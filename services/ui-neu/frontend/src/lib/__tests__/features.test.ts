import { describe, it, expect } from 'vitest';
import { features, isScreenEnabled } from '../features';

describe('features', () => {
	it('enables screens v3 supports (including files)', () => {
		expect(features.dashboard).toBe(true);
		expect(features.notifications).toBe(true);
		expect(features.settings).toBe(true);
		expect(features.logs).toBe(true); // job-scoped log browser
		expect(features.files).toBe(true); // file browser — v3 backend landed
	});

	it('isScreenEnabled maps a nav href to its flag', () => {
		expect(isScreenEnabled('/files')).toBe(true);
		expect(isScreenEnabled('/setup')).toBe(true); // the first-run walkthrough has a v3 backend now
		expect(isScreenEnabled('/logs')).toBe(true);
		expect(isScreenEnabled('/')).toBe(true);
	});

	it('disables in-screen features whose v3 backend is MISSING (maintenance)', () => {
		expect(features.maintenance).toBe(false);
	});

	it('in-screen flags are not route flags', () => {
		expect(isScreenEnabled('/maintenance')).toBe(true);
	});

	it('isScreenEnabled defaults unknown routes to enabled', () => {
		expect(isScreenEnabled('/something-new')).toBe(true);
	});
});
