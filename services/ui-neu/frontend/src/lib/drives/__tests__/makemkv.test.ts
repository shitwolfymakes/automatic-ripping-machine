import { describe, it, expect } from 'vitest';
import { makemkvKeyStatus } from '../makemkv';
import { driveTitle } from '../drives';
import type { ConfigView, DriveView } from '$lib/types/api.gen';

const cfg = (over: Record<string, unknown> = {}) => ({ ...over }) as unknown as ConfigView;
const drive = (over: Record<string, unknown> = {}) =>
	({
		id: 'drv_1',
		lifecycle: 'enrolled',
		kind: 'optical',
		display_name: 'Bay 1',
		device_path: '/dev/sr0',
		...over
	}) as unknown as DriveView;

describe('makemkvKeyStatus', () => {
	it('is null before the config loads', () => {
		expect(makemkvKeyStatus(null, [drive()])).toBeNull();
	});

	it('names the drive that checked a valid key', () => {
		const d = drive();
		expect(makemkvKeyStatus(cfg({ makemkv_key_valid: true, makemkv_key_checked_by_drive_id: 'drv_1' }), [d])).toEqual({
			tone: 'ok',
			title: `Valid, checked by ${driveTitle(d)}`,
			message: null
		});
	});

	it('says plain Valid with no checker id', () => {
		expect(makemkvKeyStatus(cfg({ makemkv_key_valid: true }), [drive()])).toEqual({
			tone: 'ok',
			title: 'Valid',
			message: null
		});
	});

	it('says plain Valid when the checker is not listed', () => {
		const c = cfg({ makemkv_key_valid: true, makemkv_key_checked_by_drive_id: 'gone' });
		expect(makemkvKeyStatus(c, [drive()])?.title).toBe('Valid');
	});

	it('reports the state of a key that was not accepted', () => {
		expect(makemkvKeyStatus(cfg({ makemkv_key_valid: false, makemkv_key_state: 'expired' }), [])).toEqual({
			tone: 'danger',
			title: 'Key not accepted',
			message: 'expired'
		});
	});

	it('has no message for a rejected key with no reported state', () => {
		expect(makemkvKeyStatus(cfg({ makemkv_key_valid: false }), [])?.message).toBeNull();
	});

	it('waits for an enrolled drive to check a key with no verdict', () => {
		expect(makemkvKeyStatus(cfg({ makemkv_key_valid: null }), [drive()])).toEqual({
			tone: 'busy',
			title: 'Waiting for a drive to check the key...',
			message: null
		});
	});

	it.each([
		['virtual', drive({ kind: 'virtual' })],
		['not enrolled', drive({ lifecycle: 'pending' })]
	])('waits for a drive to be enrolled when the only drive is %s', (_name, d) => {
		expect(makemkvKeyStatus(cfg({ makemkv_key_valid: null }), [d])).toEqual({
			tone: 'muted',
			title: 'Will be checked when you enroll a drive',
			message: null
		});
	});
});
