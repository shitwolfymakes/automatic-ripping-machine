import { describe, it, expect } from 'vitest';
import { logService, serviceLabel } from './log-service';

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
