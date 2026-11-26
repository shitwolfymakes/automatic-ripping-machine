import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { KeyCheckResponse } from '$lib/types/api.gen';
import { KeyChecks, keyToTest } from '../settings-key-checks.svelte';

const checkApiKey = vi.fn((_name: string, _value?: string): Promise<KeyCheckResponse> =>
	Promise.resolve({ name: 'tmdb', status: 'ok', detail: null, checked_at: null })
);
vi.mock('$lib/api/settings', () => ({
	checkApiKey: (name: string, value?: string) => checkApiKey(name, value)
}));

beforeEach(() => {
	checkApiKey.mockClear();
});

describe('keyToTest', () => {
	it('sends a key the operator typed', () => {
		expect(keyToTest('new-key', 'old-key')).toBe('new-key');
	});

	it('gives undefined for a value that is not a string', () => {
		expect(keyToTest(42, 'old-key')).toBeUndefined();
	});

	it('gives undefined for an empty string', () => {
		expect(keyToTest('', 'old-key')).toBeUndefined();
	});

	it('gives undefined for the saved-secret mask', () => {
		expect(keyToTest('<hidden>', 'old-key')).toBeUndefined();
	});

	it('gives undefined for a value equal to the saved one', () => {
		expect(keyToTest('same', 'same')).toBeUndefined();
	});
});

describe('KeyChecks.run', () => {
	it('does nothing for a field with no key check', async () => {
		const checks = new KeyChecks();
		await checks.run('not_a_key_field', 'abc');
		expect(checkApiKey).not.toHaveBeenCalled();
		expect(checks.running).toEqual({});
		expect(checks.results).toEqual({});
	});

	it('sends the service name and key, flags it while running and stores the result', async () => {
		const result: KeyCheckResponse = { name: 'tmdb', status: 'ok', detail: 'fine', checked_at: null };
		let resolve!: (r: KeyCheckResponse) => void;
		checkApiKey.mockReturnValueOnce(new Promise((r) => (resolve = r)));
		const checks = new KeyChecks();
		const pending = checks.run('tmdb_api_key', 'abc');
		expect(checks.running).toEqual({ tmdb_api_key: true });
		resolve(result);
		await pending;
		expect(checkApiKey).toHaveBeenCalledWith('tmdb', 'abc');
		expect(checks.running).toEqual({ tmdb_api_key: false });
		expect(checks.results).toEqual({ tmdb_api_key: result });
	});

	it('stores an error result with the message of a rejected Error', async () => {
		checkApiKey.mockRejectedValueOnce(new Error('boom'));
		const checks = new KeyChecks();
		await checks.run('omdb_api_key', undefined);
		expect(checks.results.omdb_api_key).toEqual({
			name: 'omdb',
			status: 'error',
			detail: 'boom',
			checked_at: null
		});
		expect(checks.running.omdb_api_key).toBe(false);
	});

	it('stores "check failed" when the rejection is not an Error', async () => {
		checkApiKey.mockRejectedValueOnce('nope');
		const checks = new KeyChecks();
		await checks.run('tvdb_api_key', 'k');
		expect(checks.results.tvdb_api_key).toEqual({
			name: 'tvdb',
			status: 'error',
			detail: 'check failed',
			checked_at: null
		});
		expect(checks.running.tvdb_api_key).toBe(false);
	});

	it('keeps a second field result beside the first', async () => {
		const checks = new KeyChecks();
		await checks.run('tmdb_api_key', 'a');
		await checks.run('omdb_api_key', 'b');
		expect(Object.keys(checks.results)).toEqual(['tmdb_api_key', 'omdb_api_key']);
	});
});
