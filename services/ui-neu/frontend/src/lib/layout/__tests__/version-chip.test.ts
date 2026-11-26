import { describe, it, expect, vi, afterEach } from 'vitest';
import { DEFAULT_REPO_URL, versionChipView, withV, withinTimeout } from '../version-chip';

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
			latestVersion: '2.10.1',
			href: DEFAULT_REPO_URL,
			label: 'ARM v2.10.1 on GitHub (opens in a new tab)'
		});
	});

	it('offers an update with the release url', () => {
		expect(
			versionChipView({
				version: '2.10.1',
				latest_version: '2.11.0',
				update_available: true,
				release_url: 'https://github.com/o/r/releases/tag/v2.11.0'
			})
		).toEqual({
			version: 'v2.10.1',
			state: 'update',
			releaseUrl: 'https://github.com/o/r/releases/tag/v2.11.0',
			latestVersion: '2.11.0',
			href: 'https://github.com/o/r/releases/tag/v2.11.0',
			label: 'Update available: v2.11.0 (opens in a new tab)'
		});
	});

	it('falls back to version-only when an update has no release url', () => {
		expect(versionChipView({ version: '1', latest_version: '2', update_available: true })?.state).toBe('version-only');
	});

	it('falls back to version-only when an update has no latest version', () => {
		expect(
			versionChipView({ version: '1', update_available: true, release_url: 'https://github.com/o/r/releases/tag/v2' })
				?.state
		).toBe('version-only');
	});

	it('is version-only when not yet checked', () => {
		expect(versionChipView({ version: '1', latest_version: null, update_available: null })?.state).toBe('version-only');
	});

	it('is version-only when up to date but latest is unknown', () => {
		expect(versionChipView({ version: '1', update_available: false })?.state).toBe('version-only');
	});

	it('links to the backend repo_url when it is given', () => {
		const view = versionChipView({ version: '1', repo_url: 'https://github.com/me/fork' });
		expect(view?.href).toBe('https://github.com/me/fork');
	});

	it('falls back to the upstream repo when repo_url is missing', () => {
		expect(versionChipView({ version: '1' })?.href).toBe(DEFAULT_REPO_URL);
	});

	it('never doubles the v in the label', () => {
		expect(versionChipView({ version: 'v1' })?.label).toBe('ARM v1 on GitHub (opens in a new tab)');
	});
});

describe('versionChipView link targets', () => {
	it('shows the version alone when the release url is not a GitHub page', () => {
		for (const release_url of [
			'javascript:alert(document.domain)',
			'https://evil.example/r',
			'https://github.com.evil.example/r'
		]) {
			const view = versionChipView({
				version: '2.10.1',
				latest_version: '2.11.0',
				update_available: true,
				release_url
			});
			expect(view?.state).toBe('version-only');
			expect(view?.href).toBe(DEFAULT_REPO_URL);
		}
	});

	it('links to the upstream repo when repo_url is not a GitHub page', () => {
		expect(versionChipView({ version: '2.10.1', repo_url: 'javascript:alert(1)' })?.href).toBe(DEFAULT_REPO_URL);
	});
});

describe('withinTimeout', () => {
	afterEach(() => vi.useRealTimers());

	it('resolves with the value when the promise settles in time', async () => {
		await expect(withinTimeout(() => Promise.resolve('v'), 1000)).resolves.toBe('v');
	});

	it('resolves null when the loader throws before returning a promise', async () => {
		const load = (): Promise<string> => {
			throw new Error('not wired');
		};
		await expect(withinTimeout(load, 1000)).resolves.toBeNull();
	});

	it('resolves null when the promise rejects', async () => {
		await expect(withinTimeout(() => Promise.reject(new Error('down')), 1000)).resolves.toBeNull();
	});

	it('resolves null once the time runs out, and ignores a later answer', async () => {
		vi.useFakeTimers();
		let answer: (v: string) => void = () => {};
		const result = withinTimeout(() => new Promise<string>((r) => (answer = r)), 1000);
		vi.advanceTimersByTime(1000);
		await expect(result).resolves.toBeNull();
		answer('late');
		await expect(result).resolves.toBeNull();
	});
});
