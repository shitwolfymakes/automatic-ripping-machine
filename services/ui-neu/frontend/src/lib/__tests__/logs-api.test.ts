import { describe, it, expect } from 'vitest';

import {
	fetchLogs, fetchLogContent, fetchStructuredLogContent,
	fetchTranscoderLogs, fetchTranscoderLogContent, fetchStructuredTranscoderLogContent,
	deleteLog, fetchTranscoderLogForArmJob, logDownloadUrl
} from '../api/logs';

// v3 logs are JOB-ID scoped; the BFF's filename-based log browser + transcoder
// feed are MISSING. Every fetch is a stub that rejects; the Logs screen and
// inline feeds are dormant. logDownloadUrl is a pure string builder.
describe('logs MISSING stubs', () => {
	it('fetchLogs rejects', async () => {
		await expect(fetchLogs()).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchLogContent rejects', async () => {
		await expect(fetchLogContent('test.log')).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchStructuredLogContent rejects', async () => {
		await expect(fetchStructuredLogContent('arm.log')).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchTranscoderLogs rejects', async () => {
		await expect(fetchTranscoderLogs()).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchTranscoderLogContent rejects', async () => {
		await expect(fetchTranscoderLogContent('transcode.log')).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchStructuredTranscoderLogContent rejects', async () => {
		await expect(fetchStructuredTranscoderLogContent('tc.log')).rejects.toThrow(/not yet available in v3/);
	});

	it('deleteLog rejects', async () => {
		await expect(deleteLog('test.log')).rejects.toThrow(/not yet available in v3/);
	});

	it('fetchTranscoderLogForArmJob rejects', async () => {
		await expect(fetchTranscoderLogForArmJob(1)).rejects.toThrow(/not yet available in v3/);
	});
});

describe('logDownloadUrl', () => {
	it('builds an encoded download URL', () => {
		expect(logDownloadUrl('my log.txt')).toBe('/api/logs/my%20log.txt/download');
	});
});
