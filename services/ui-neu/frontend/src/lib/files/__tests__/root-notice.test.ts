import { describe, expect, it } from 'vitest';
import { readonlyNotice } from '../root-notice';

describe('readonlyNotice', () => {
	it('explains that staging is managed by ARM', () => {
		expect(readonlyNotice('STAGING')).toContain('managed by ARM');
	});
	it('blames the mount for any other read-only root', () => {
		expect(readonlyNotice('LOG')).toBe('This directory is on a read-only mount. File operations are disabled.');
	});
});
