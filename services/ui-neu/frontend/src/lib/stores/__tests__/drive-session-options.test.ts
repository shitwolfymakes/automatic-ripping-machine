import { describe, it, expect, vi, beforeEach } from 'vitest';

const fetchSessionsMock = vi.fn();
const fetchTranscodePresetsMock = vi.fn();
vi.mock('$lib/api/sessions', () => ({
	fetchSessions: (...a: unknown[]) => fetchSessionsMock(...a)
}));
vi.mock('$lib/api/transcode-presets', () => ({
	fetchTranscodePresets: (...a: unknown[]) => fetchTranscodePresetsMock(...a)
}));

import { DriveSessionOptions } from '$lib/stores/drive-session-options.svelte';

const SESSIONS = [{ id: 's1' }, { id: 's2' }];
const PRESETS = [{ id: 'p1' }];

beforeEach(() => {
	fetchSessionsMock.mockReset();
	fetchTranscodePresetsMock.mockReset();
});

describe('DriveSessionOptions', () => {
	it('starts with no sessions and no presets', () => {
		const options = new DriveSessionOptions();
		expect(options.sessions).toEqual([]);
		expect(options.transcodePresets).toEqual([]);
	});

	it('load sets the sessions and the presets', async () => {
		fetchSessionsMock.mockResolvedValue(SESSIONS);
		fetchTranscodePresetsMock.mockResolvedValue(PRESETS);
		const options = new DriveSessionOptions();
		await options.load();
		expect(options.sessions).toEqual(SESSIONS);
		expect(options.transcodePresets).toEqual(PRESETS);
	});

	it('a second load after sessions arrived makes no request', async () => {
		fetchSessionsMock.mockResolvedValue(SESSIONS);
		fetchTranscodePresetsMock.mockResolvedValue(PRESETS);
		const options = new DriveSessionOptions();
		await options.load();
		await options.load();
		expect(fetchSessionsMock).toHaveBeenCalledTimes(1);
		expect(fetchTranscodePresetsMock).toHaveBeenCalledTimes(1);
	});

	it('a load whose fetch returned no sessions fetches again next time', async () => {
		fetchSessionsMock.mockResolvedValue([]);
		fetchTranscodePresetsMock.mockResolvedValue(PRESETS);
		const options = new DriveSessionOptions();
		await options.load();
		await options.load();
		expect(fetchSessionsMock).toHaveBeenCalledTimes(2);
		expect(fetchTranscodePresetsMock).toHaveBeenCalledTimes(2);
	});

	it('keeps the sessions and leaves the presets empty when the presets fetch fails', async () => {
		fetchSessionsMock.mockResolvedValue(SESSIONS);
		fetchTranscodePresetsMock.mockRejectedValue(new Error('boom'));
		const options = new DriveSessionOptions();
		await options.load();
		expect(options.sessions).toEqual(SESSIONS);
		expect(options.transcodePresets).toEqual([]);
	});

	it('keeps the presets and leaves the sessions empty when the sessions fetch fails', async () => {
		fetchSessionsMock.mockRejectedValue(new Error('boom'));
		fetchTranscodePresetsMock.mockResolvedValue(PRESETS);
		const options = new DriveSessionOptions();
		await options.load();
		expect(options.sessions).toEqual([]);
		expect(options.transcodePresets).toEqual(PRESETS);
	});

	it('leaves both empty when both fetches fail', async () => {
		fetchSessionsMock.mockRejectedValue(new Error('boom'));
		fetchTranscodePresetsMock.mockRejectedValue(new Error('boom'));
		const options = new DriveSessionOptions();
		await options.load();
		expect(options.sessions).toEqual([]);
		expect(options.transcodePresets).toEqual([]);
	});
});
