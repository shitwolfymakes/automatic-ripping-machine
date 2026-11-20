import { describe, it, expect } from 'vitest';
import { entryGroup, logService, serviceLabel } from './log-service';

describe('logService', () => {
	it('maps arm-backend to backend', () => {
		expect(logService('arm-backend')).toBe('backend');
	});

	it('maps arm-ripper-<serial> to ripper', () => {
		expect(logService('arm-ripper-ABCD1234')).toBe('ripper');
	});

	it('maps arm-transcode-<task> to transcode', () => {
		expect(logService('arm-transcode-task_01')).toBe('transcode');
	});

	it('maps anything else to other', () => {
		expect(logService('some-unknown-service')).toBe('other');
		expect(logService('')).toBe('other');
	});
});

describe('serviceLabel', () => {
	it('labels each service key', () => {
		expect(serviceLabel('backend')).toBe('Backend');
		expect(serviceLabel('ripper')).toBe('Ripper');
		expect(serviceLabel('transcode')).toBe('Transcode');
		expect(serviceLabel('other')).toBe('Other');
	});
});

describe('entryGroup', () => {
	const line = (service: string, event: string | null) => ({ service, event });

	it('groups a milestone by the stage its event names, whichever service wrote it', () => {
		expect(entryGroup(line('arm-backend', 'transcode.started'))).toBe('transcode');
		expect(entryGroup(line('arm-backend', 'transcode.completed'))).toBe('transcode');
		expect(entryGroup(line('arm-backend', 'session.applied'))).toBe('transcode');
		expect(entryGroup(line('arm-backend', 'session.completed'))).toBe('transcode');
		expect(entryGroup(line('arm-backend', 'track.ripped'))).toBe('ripper');
		expect(entryGroup(line('arm-backend', 'rip.completed'))).toBe('ripper');
		expect(entryGroup(line('arm-ripper-ABCD', 'rip.started'))).toBe('ripper');
		expect(entryGroup(line('arm-ripper-ABCD', 'title.started'))).toBe('ripper');
		expect(entryGroup(line('arm-backend', 'identify.resolved'))).toBe('backend');
		expect(entryGroup(line('arm-backend', 'episodes.matched'))).toBe('backend');
	});

	it('falls back to the writing service for a line with no event or an unknown one', () => {
		expect(entryGroup(line('arm-transcode-task_01', null))).toBe('transcode');
		expect(entryGroup(line('arm-ripper-ABCD', null))).toBe('ripper');
		expect(entryGroup(line('arm-backend', 'something.else'))).toBe('backend');
	});
});
