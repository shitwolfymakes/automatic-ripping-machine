import { describe, it, expect } from 'vitest';
import type { SettingIssue, TranscodePresetView } from '$lib/types/api.gen';
import { CPU_HERE_NOTE, footerNote, issuesFor, rowFlags, schemaLoadError, sidebarTitle, usageLabel } from '../display';

const issue = (over: Partial<SettingIssue>): SettingIssue => ({
	key: 'VideoQualitySlider',
	encoder: null,
	code: 'out_of_range',
	message: 'Too high',
	...over
});

function preset(over: Partial<TranscodePresetView> = {}): TranscodePresetView {
	return {
		id: 't1',
		name: 'Movies',
		media_type: 'tv',
		is_builtin: false,
		tool: 'handbrake',
		preset_ref: 'Fast 1080p30',
		handbrake_settings: { common: { PictureWidth: 1280 }, encoders: { x264: { VideoPreset: 'slow' } } },
		issues: [],
		host_notes: [],
		container: 'mp4',
		encoder: 'any_h264',
		extra_args: '--x',
		created_by_user_id: null,
		created_at: null,
		updated_at: null,
		...over
	};
}

describe('footerNote', () => {
	it('is the CPU note only with the host note', () => {
		expect(footerNote(preset({ host_notes: ['encodes_on_cpu_here'] }))).toBe(CPU_HERE_NOTE);
		expect(CPU_HERE_NOTE).toBe('Encodes on CPU on this host: no verified non-AMD GPU for this codec');
		expect(footerNote(preset({ host_notes: [] }))).toBeNull();
		expect(footerNote(preset({ host_notes: undefined }))).toBeNull();
		expect(footerNote(null)).toBeNull();
	});
});

describe('rowFlags', () => {
	it('names the settings count, issues and the CPU note', () => {
		expect(rowFlags(preset({ issues: [issue({})], host_notes: ['encodes_on_cpu_here'] }))).toEqual({
			settings: '2 settings',
			needsReview: true,
			cpuHere: true
		});
		expect(rowFlags(preset({ handbrake_settings: { common: { A: 1 } } })).settings).toBe('1 setting');
	});

	it('is empty for a plain preset or none', () => {
		const empty = { settings: null, needsReview: false, cpuHere: false };
		expect(rowFlags(preset({ handbrake_settings: null, issues: undefined }))).toEqual(empty);
		expect(rowFlags(null)).toEqual(empty);
	});
});

describe('sidebarTitle and usageLabel', () => {
	it('names each mode', () => {
		expect(sidebarTitle('new')).toBe('New transcode preset');
		expect(sidebarTitle('edit')).toBe('Edit transcode preset');
		expect(sidebarTitle('view')).toBe('View transcode preset');
	});

	it('pluralises sessions', () => {
		expect(usageLabel(0)).toBe('Used by 0 sessions');
		expect(usageLabel(1)).toBe('Used by 1 session');
		expect(usageLabel(3)).toBe('Used by 3 sessions');
	});
});

describe('issues', () => {
	const list = [
		issue({ key: 'PictureWidth', message: 'w' }),
		issue({ key: 'VideoPreset', encoder: 'x264', message: 'p' }),
		issue({ key: 'preset_ref', message: 'ref' }),
		issue({ key: 'handbrake_settings', message: 'whole' }),
		issue({ key: 'NotAKey', message: 'unknown' }),
		issue({ key: 'AudioMixdown', message: 'mix' }),
		issue({ key: 'bit_depth', encoder: 'x265', message: 'depth' })
	];

	it('finds the issue of a common or preset-block field', () => {
		expect(issuesFor(list, 'PictureWidth')?.message).toBe('w');
		expect(issuesFor(list, 'VideoPreset')).toBeUndefined();
		expect(issuesFor(list, 'VideoPreset', 'x264')?.message).toBe('p');
		expect(issuesFor(list, 'preset_ref')?.message).toBe('ref');
	});
});

describe('schemaLoadError', () => {
	it('is an Error only while unavailable', () => {
		expect(schemaLoadError('unavailable', 'boom')?.message).toBe('boom');
		expect(schemaLoadError('unavailable', null)?.message).toBe('No HandBrake schema loaded yet');
		expect(schemaLoadError('ready', 'boom')).toBeNull();
	});
});
