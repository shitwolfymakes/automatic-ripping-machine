import { describe, it, expect } from 'vitest';
import { versionChipView, withV } from '../version-chip';

describe('withV', () => {
	it('adds a v prefix', () => expect(withV('2.10.1')).toBe('v2.10.1'));
	it('does not double a leading v', () => expect(withV('v2.10.1')).toBe('v2.10.1'));
});

describe('versionChipView', () => {
	it('returns null when the fetch failed', () => expect(versionChipView(null)).toBeNull());

	it('is up to date when update_available is false and latest is known', () => {
		expect(versionChipView({ version: '2.10.1', latest_version: '2.10.1', update_available: false })).toEqual({
			version: 'v2.10.1',
			state: 'up-to-date',
			releaseUrl: '',
			latestVersion: '2.10.1'
		});
	});

	it('offers an update with the release url', () => {
		expect(
			versionChipView({
				version: '2.10.1',
				latest_version: '2.11.0',
				update_available: true,
				release_url: 'https://example.test/r'
			})
		).toEqual({ version: 'v2.10.1', state: 'update', releaseUrl: 'https://example.test/r', latestVersion: '2.11.0' });
	});

	it('falls back to version-only when an update has no release url', () => {
		expect(versionChipView({ version: '1', latest_version: '2', update_available: true })?.state).toBe('version-only');
	});

	it('falls back to version-only when an update has no latest version', () => {
		expect(versionChipView({ version: '1', update_available: true, release_url: 'u' })?.state).toBe('version-only');
	});

	it('is version-only when not yet checked', () => {
		expect(versionChipView({ version: '1', latest_version: null, update_available: null })?.state).toBe('version-only');
	});

	it('is version-only when up to date but latest is unknown', () => {
		expect(versionChipView({ version: '1', update_available: false })?.state).toBe('version-only');
	});
});
