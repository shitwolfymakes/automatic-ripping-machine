import { describe, expect, it } from 'vitest';
import { buildDeploymentReport } from '../deployment-report';
import type { DiagnosticsServiceView, SystemDiagnosticsResponse, SystemEnvironmentResponse } from '$lib/types/api.gen';

const now = new Date('2026-11-20T12:00:00Z');

function makeEnv(tokenSet = true): SystemEnvironmentResponse {
	return {
		version: 'v3.1.0',
		summary: { host_paths_set: true, transcode_capable: true, gpus: ['nvidia'] },
		groups: [
			{
				name: 'Paths',
				vars: [{ key: 'RAW_ROOT', value: '/raw', secret: false, is_set: false, source: 'default' }]
			},
			{
				name: 'Security',
				vars: [
					{
						key: 'ARM_SERVICE_TOKEN',
						value: null,
						secret: true,
						is_set: tokenSet,
						source: 'env'
					}
				]
			},
			{
				name: 'Transcoding',
				vars: [
					{
						key: 'MAX_PARALLEL_TRANSCODES',
						value: '2',
						secret: false,
						is_set: true,
						source: 'env',
						effective: { value: '4', setting_key: 'max_parallel_transcodes', tab: 'Transcoding' }
					},
					{
						key: 'ARM_GPUS',
						value: 'all',
						secret: false,
						is_set: false,
						source: 'default',
						effective: { value: 'nvidia', setting_key: 'gpus', tab: 'Transcoding' }
					}
				]
			}
		],
		containers: [
			{
				kind: 'ripper',
				label: 'Pioneer BDR',
				state: 'enrolled, online',
				image: 'arm-ripper:3.1',
				network: 'arm',
				docker_host: null,
				mounts: [{ host: '/mnt/raw', container: '/raw', mode: 'rw' }],
				devices: ['/dev/sr0'],
				env: [
					{ key: 'LOG_LEVEL', value: 'debug', secret: false },
					{ key: 'TOKEN', value: null, secret: true }
				]
			},
			{
				kind: 'transcode',
				label: 'job 7',
				state: null,
				image: 'arm-transcoder:3.1',
				network: null,
				docker_host: 'tcp://gpu:2375',
				mounts: [],
				devices: [],
				env: []
			}
		]
	};
}

const health: SystemDiagnosticsResponse = {
	status: 'warning',
	checks: [
		{ name: 'config', status: 'ok' },
		{ name: 'makemkv_key', status: 'error', detail: 'key expired' }
	],
	paths: []
};

const logLevels: DiagnosticsServiceView[] = [{ name: 'arm-ripper', log_level: 'debug' }];

describe('buildDeploymentReport', () => {
	it('starts with version and timestamp', () => {
		expect(buildDeploymentReport(makeEnv(), null, [], now).split('\n')[0]).toBe(
			'## ARM deployment report — v3.1.0 — 2026-11-20T12:00:00.000Z'
		);
	});

	it('renders a summary', () => {
		const md = buildDeploymentReport(makeEnv(), null, [], now);
		expect(md).toContain('**Summary**');
		expect(md).toContain('- Transcode capable: yes');
		expect(md).toContain('- GPUs: nvidia');
	});

	it('one ### section per group, KEY=value lines in a code block, defaults marked', () => {
		const md = buildDeploymentReport(makeEnv(), null, [], now);
		expect(md).toContain('### Paths\n```\nRAW_ROOT=/raw  (default)\n');
		expect(md).toContain('### Security');
	});

	it('secrets render as set / not set', () => {
		expect(buildDeploymentReport(makeEnv(), null, [], now)).toContain('ARM_SERVICE_TOKEN=<set>');
		expect(buildDeploymentReport(makeEnv(false), null, [], now)).toContain('ARM_SERVICE_TOKEN=<not set>');
	});

	it('seed-only vars show the value in use', () => {
		const md = buildDeploymentReport(makeEnv(), null, [], now);
		expect(md).toContain('MAX_PARALLEL_TRANSCODES=2  · in use: 4 (Settings → Transcoding)');
		expect(md).toContain('ARM_GPUS=all  (default)  · in use: nvidia (Settings → Transcoding)');
	});

	it('containers render as <details> with image, mounts, devices, env', () => {
		const md = buildDeploymentReport(makeEnv(), null, [], now);
		expect(md).toMatch(/<details><summary>ripper — Pioneer BDR \(enrolled, online\)<\/summary>/);
		expect(md).toContain('image: arm-ripper:3.1');
		expect(md).toContain('/mnt/raw → /raw (rw)');
		expect(md).toContain('/dev/sr0');
		expect(md).toContain('LOG_LEVEL=debug');
		expect(md).toContain('TOKEN=<secret>');
		expect(md).toContain('<details><summary>transcode — job 7</summary>');
		expect(md).toContain('docker host: tcp://gpu:2375');
		expect(md).toContain('</details>');
	});

	it('health renders pass/fail list; omitted section when health is null', () => {
		const md = buildDeploymentReport(makeEnv(), health, [], now);
		expect(md).toContain('### Health');
		expect(md).toContain('- ✅ Configuration');
		expect(md).toContain('- ❌ MakeMKV key: key expired');
		expect(buildDeploymentReport(makeEnv(), null, [], now)).not.toContain('### Health');
	});

	it('log levels appear under Logging, appended when no Logging group exists', () => {
		const md = buildDeploymentReport(makeEnv(), null, logLevels, now);
		expect(md).toContain('### Logging');
		expect(md).toContain('- arm-ripper: debug');
	});
});
