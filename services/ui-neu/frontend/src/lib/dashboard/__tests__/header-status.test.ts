import { describe, it, expect } from 'vitest';
import { transcoderDotStatus, serviceRows, makemkvKeyTitle } from '../header-status';

describe('transcoderDotStatus', () => {
	it('is ok when online', () => {
		expect(transcoderDotStatus({ transcoder_online: true })).toBe('ok');
	});

	it('is off when offline', () => {
		expect(transcoderDotStatus({ transcoder_online: false })).toBe('off');
	});
});

describe('serviceRows', () => {
	type Rows = Parameters<typeof serviceRows>[0];
	const base = {
		arm_online: true,
		db_available: true,
		transcoder_online: true,
		makemkv_key_valid: true
	} as Rows;
	const statuses = (d: Partial<Rows>) => serviceRows({ ...base, ...d }).map((r) => r.status);

	it('lists ARM, DB, Transcode and Key with their links, in order', () => {
		expect(serviceRows(base).map(({ label, href }) => ({ label, href }))).toEqual([
			{ label: 'ARM', href: '/settings#system' },
			{ label: 'DB', href: '/settings#system' },
			{ label: 'Transcode', href: '/transcoder' },
			{ label: 'Key', href: '/settings#Keys/makemkv_key' }
		]);
	});

	it('marks ARM ok when online and error when offline', () => {
		expect(statuses({})[0]).toBe('ok');
		expect(statuses({ arm_online: false })[0]).toBe('error');
	});

	it('marks DB ok when available and warn when not', () => {
		expect(statuses({})[1]).toBe('ok');
		expect(statuses({ db_available: false })[1]).toBe('warn');
	});

	it('takes the Transcode status from transcoderDotStatus', () => {
		expect(statuses({})[2]).toBe('ok');
		expect(statuses({ transcoder_online: false })[2]).toBe('off');
	});

	it('marks Key ok when true and error when false or null', () => {
		expect(statuses({})[3]).toBe('ok');
		expect(statuses({ makemkv_key_valid: false })[3]).toBe('error');
		expect(statuses({ makemkv_key_valid: null })[3]).toBe('error');
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
