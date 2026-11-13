import { describe, it, expect } from 'vitest';
import {
	discsSummary,
	drivesSummary,
	makemkvSummary,
	metadataSummary,
	notificationsSummary,
	setupSummaries,
	systemSummary,
	transcodingSummary,
	type SummaryInputs
} from '../setup-summaries';
import type { ConfigView, DriveView, GpuView, SetupView } from '$lib/types/api.gen';

const drive = (over: Partial<DriveView>): DriveView =>
	({ id: 'd1', lifecycle: 'enrolled', kind: 'physical', ...over }) as unknown as DriveView;

const gpu = (over: Partial<GpuView>): GpuView => ({ id: 'g1', enabled: true, ...over }) as unknown as GpuView;

const config = (over: Partial<ConfigView>): ConfigView =>
	({
		tmdb_api_key: null,
		omdb_api_key: null,
		tvdb_api_key: null,
		makemkv_key: null,
		makemkv_key_valid: false,
		auto_rip_on_insert: true,
		hold_for_review: false,
		search_provider_movie: 'tmdb',
		...over
	}) as unknown as ConfigView;

const setupView = (progress: SetupView['progress'] = {}): SetupView => ({ progress }) as unknown as SetupView;

describe('drivesSummary', () => {
	it('counts enrolled and ignored drives', () => {
		const drives = [drive({ id: 'a' }), drive({ id: 'b' }), drive({ id: 'c', lifecycle: 'ignored' })];
		expect(drivesSummary(drives)).toBe('2 enrolled, 1 ignored');
	});

	it('leaves a virtual enrolled drive out of the enrolled count', () => {
		expect(drivesSummary([drive({ kind: 'virtual' }), drive({ id: 'b' })])).toBe('1 enrolled, 0 ignored');
	});

	it('reports zero for no drives', () => {
		expect(drivesSummary([])).toBe('0 enrolled, 0 ignored');
	});
});

describe('systemSummary', () => {
	it('asks for a fix when the system step needs attention', () => {
		expect(systemSummary(setupView({ system: { state: 'attention' } }))).toBe(
			'Needs a fix on the server, see System check.'
		);
	});

	it('says all checks pass when the system step is done', () => {
		expect(systemSummary(setupView({ system: { state: 'done' } }))).toBe('All checks pass.');
	});

	it('says all checks pass when the system step has no recorded progress', () => {
		expect(systemSummary(setupView())).toBe('All checks pass.');
	});
});

describe('notificationsSummary', () => {
	it('says inbox only for no channels', () => {
		expect(notificationsSummary(0)).toBe('Inbox only');
	});

	it('uses the singular for one channel', () => {
		expect(notificationsSummary(1)).toBe('1 channel');
	});

	it('uses the plural for several channels', () => {
		expect(notificationsSummary(3)).toBe('3 channels');
	});
});

describe('makemkvSummary', () => {
	it('names a free beta key', () => {
		expect(makemkvSummary(config({}))).toBe('Free beta key');
	});

	it('names a purchased key', () => {
		expect(makemkvSummary(config({ makemkv_key: 'T-abc' }))).toBe('Purchased key');
	});

	it('adds valid when the key is valid', () => {
		expect(makemkvSummary(config({ makemkv_key: 'T-abc', makemkv_key_valid: true }))).toBe('Purchased key, valid');
	});
});

describe('metadataSummary', () => {
	it('says no lookup key yet when none is saved', () => {
		expect(metadataSummary(config({}))).toBe('No lookup key yet');
	});

	it('counts one key in the singular and names the provider', () => {
		expect(metadataSummary(config({ tmdb_api_key: 'k' }))).toBe('1 key saved. Titles looked up with TMDb.');
	});

	it('counts several keys in the plural', () => {
		expect(metadataSummary(config({ tmdb_api_key: 'k', omdb_api_key: 'o', tvdb_api_key: 't' }))).toBe(
			'3 keys saved. Titles looked up with TMDb.'
		);
	});

	it('uses the chosen movie provider when it is keyed', () => {
		expect(metadataSummary(config({ omdb_api_key: 'o', search_provider_movie: 'omdb' }))).toBe(
			'1 key saved. Titles looked up with OMDb.'
		);
	});

	it('leaves out the lookup sentence for a TVDb key only', () => {
		expect(metadataSummary(config({ tvdb_api_key: 't' }))).toBe('1 key saved.');
	});
});

describe('discsSummary', () => {
	it('says manual when auto rip is off', () => {
		expect(discsSummary(config({ auto_rip_on_insert: false, hold_for_review: true }))).toBe('Manual');
	});

	it('says review first when rips are held for review', () => {
		expect(discsSummary(config({ hold_for_review: true }))).toBe('Review first');
	});

	it('says fully automatic otherwise', () => {
		expect(discsSummary(config({}))).toBe('Fully automatic');
	});
});

describe('transcodingSummary', () => {
	it('says ripper only when the transcoder is off', () => {
		expect(transcodingSummary(false, [gpu({})])).toBe('Ripper only');
	});

	it('says CPU encoding when no graphics device is enabled', () => {
		expect(transcodingSummary(true, [gpu({ enabled: false })])).toBe('CPU encoding');
	});

	it('says CPU encoding when there are no graphics devices', () => {
		expect(transcodingSummary(true, [])).toBe('CPU encoding');
	});

	it('uses the singular for one enabled graphics device', () => {
		expect(transcodingSummary(true, [gpu({}), gpu({ id: 'g2', enabled: false })])).toBe('1 graphics device enabled');
	});

	it('uses the plural for several enabled graphics devices', () => {
		expect(transcodingSummary(true, [gpu({}), gpu({ id: 'g2' })])).toBe('2 graphics devices enabled');
	});
});

describe('setupSummaries', () => {
	const inputs = (over: Partial<SummaryInputs>): SummaryInputs => ({
		view: setupView(),
		drives: [drive({})],
		config: config({ makemkv_key: 'T-abc', tmdb_api_key: 'k' }),
		gpus: [gpu({})],
		channelCount: 2,
		transcoderEnabled: true,
		...over
	});

	it('builds every line in step order when a config is loaded', () => {
		const out = setupSummaries(inputs({}));
		expect(Object.keys(out)).toEqual([
			'account',
			'system',
			'drives',
			'notifications',
			'makemkv',
			'metadata',
			'discs',
			'transcoding'
		]);
		expect(out).toEqual({
			account: 'Password changed.',
			system: 'All checks pass.',
			drives: '1 enrolled, 0 ignored',
			notifications: '2 channels',
			makemkv: 'Purchased key',
			metadata: '1 key saved. Titles looked up with TMDb.',
			discs: 'Fully automatic',
			transcoding: '1 graphics device enabled'
		});
	});

	it('leaves out the makemkv, metadata and discs lines without a config', () => {
		const out = setupSummaries(inputs({ config: null, transcoderEnabled: false }));
		expect(Object.keys(out)).toEqual(['account', 'system', 'drives', 'notifications', 'transcoding']);
		expect(out.transcoding).toBe('Ripper only');
	});
});
