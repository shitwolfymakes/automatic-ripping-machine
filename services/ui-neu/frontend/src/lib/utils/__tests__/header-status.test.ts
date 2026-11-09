import { describe, it, expect } from 'vitest';
import { transcoderDotStatus, makemkvKeyTitle } from '../header-status';

type Input = Parameters<typeof transcoderDotStatus>[0];

describe('transcoderDotStatus', () => {
	it('is ok when online and the worker is running', () => {
		expect(
			transcoderDotStatus({
				transcoder_online: true,
				transcoder_stats: { worker_running: true }
			} as Input)
		).toBe('ok');
	});

	it('is ok when online and worker_running is absent', () => {
		expect(transcoderDotStatus({ transcoder_online: true, transcoder_stats: {} } as Input)).toBe('ok');
	});

	it('is ok when online and there are no stats', () => {
		expect(transcoderDotStatus({ transcoder_online: true, transcoder_stats: null } as Input)).toBe('ok');
	});

	it('is warn when online but the worker is stopped', () => {
		expect(
			transcoderDotStatus({
				transcoder_online: true,
				transcoder_stats: { worker_running: false }
			} as Input)
		).toBe('warn');
	});

	it('is off when offline', () => {
		expect(transcoderDotStatus({ transcoder_online: false, transcoder_stats: null } as Input)).toBe('off');
	});

	it('is ok when online and worker_running is null', () => {
		expect(
			transcoderDotStatus({
				transcoder_online: true,
				transcoder_stats: { worker_running: null }
			} as unknown as Input)
		).toBe('ok');
	});

	it('is ok when online and the stats are missing', () => {
		expect(transcoderDotStatus({ transcoder_online: true } as Input)).toBe('ok');
	});

	it.each([true, false, null, undefined])('is off when offline with worker_running %s', (running) => {
		expect(
			transcoderDotStatus({
				transcoder_online: false,
				transcoder_stats: { worker_running: running }
			} as unknown as Input)
		).toBe('off');
	});

	it('is off when offline with empty stats', () => {
		expect(transcoderDotStatus({ transcoder_online: false, transcoder_stats: {} } as Input)).toBe('off');
	});
});

describe('makemkvKeyTitle', () => {
	const checked = '2024-05-06T07:08:09Z';

	it('says valid with the checked time when valid and checked', () => {
		expect(makemkvKeyTitle(true, checked)).toBe(`MakeMKV key valid - checked ${new Date(checked).toLocaleString()}`);
	});

	it('says valid with no suffix when never checked', () => {
		expect(makemkvKeyTitle(true, null)).toBe('MakeMKV key valid');
	});

	it('says invalid when the key is invalid', () => {
		expect(makemkvKeyTitle(false, checked)).toBe('MakeMKV key invalid - click to update');
	});

	it('says not checked when validity is unknown', () => {
		expect(makemkvKeyTitle(null, null)).toBe('MakeMKV key not checked yet');
	});
});
