import { describe, it, expect } from 'vitest';
import {
	CONFIG_GROUP_TABS,
	SCREEN_TABS,
	fieldFromHash,
	fieldTab,
	orderedConfigGroups,
	settingsTabLabel,
	tabFromHash
} from '../tabs';
import type { SettingsGroup } from '$lib/types/api.gen';

const group = (name: string, keys: string[] = []) =>
	({ name, fields: keys.map((key) => ({ key })) }) as unknown as SettingsGroup;

describe('orderedConfigGroups', () => {
	it('puts the groups in the page tab order, not the schema order', () => {
		const out = orderedConfigGroups([group('Ripping'), group('Identification'), group('Keys')]);
		expect(out.map((g) => g.name)).toEqual(['Keys', 'Identification', 'Ripping']);
	});

	it('drops groups that are not config-group tabs', () => {
		const out = orderedConfigGroups([group('System'), group('Ripping'), group('Transcoding')]);
		expect(out.map((g) => g.name)).toEqual(['Ripping']);
	});

	it('keeps only the groups that are present', () => {
		const out = orderedConfigGroups([group('Ripping'), group('Keys')]);
		expect(out.map((g) => g.name)).toEqual(['Keys', 'Ripping']);
	});
});

describe('settingsTabLabel', () => {
	it.each([
		['sessions', 'Sessions'],
		['transcoding', 'Transcoding'],
		['notifications', 'Notifications'],
		['interface', 'Interface'],
		['themes', 'Themes'],
		['drives', 'Drives'],
		['users', 'Users'],
		['system', 'System']
	])('labels the %s screen tab %s', (id, label) => {
		expect(settingsTabLabel(id)).toBe(label);
	});

	it('uses the group label for Keys', () => {
		expect(settingsTabLabel('Keys')).toBe('API Keys');
	});

	it('uses the group name for another group', () => {
		expect(settingsTabLabel('Ripping')).toBe('Ripping');
	});
});

describe('tabFromHash', () => {
	it('falls back to Identification for an empty hash', () => {
		expect(tabFromHash('')).toBe('Identification');
	});

	it.each([...SCREEN_TABS])('opens the %s screen tab', (tab) => {
		expect(tabFromHash(`#${tab}`)).toBe(tab);
	});

	it.each([...CONFIG_GROUP_TABS])('opens the %s config group tab', (tab) => {
		expect(tabFromHash(`#${tab}`)).toBe(tab);
	});

	it('ignores the field part', () => {
		expect(tabFromHash('#Keys/makemkv_key')).toBe('Keys');
	});

	it('maps the retired #Metadata to Identification', () => {
		expect(tabFromHash('#Metadata/tmdb_api_key')).toBe('Identification');
	});

	it('maps the retired #appearance to themes', () => {
		expect(tabFromHash('#appearance')).toBe('themes');
	});

	it('falls back to Identification for an unknown tab', () => {
		expect(tabFromHash('#music')).toBe('Identification');
	});
});

describe('fieldFromHash', () => {
	it('is null with no field part', () => {
		expect(fieldFromHash('#Keys')).toBeNull();
	});

	it('returns the field part', () => {
		expect(fieldFromHash('#Keys/makemkv_key')).toBe('makemkv_key');
	});

	it('is null for an empty field part', () => {
		expect(fieldFromHash('#Keys/')).toBeNull();
	});

	it('decodes a URL-encoded field part', () => {
		expect(fieldFromHash('#Keys/a%20b')).toBe('a b');
	});
});

describe('fieldTab', () => {
	const groups = [group('Keys', ['makemkv_key']), group('Webhooks', ['hook_url'])];
	const visible = ['Keys', 'sessions'];

	it('returns the tab of the group that owns a key on a visible tab', () => {
		expect(fieldTab(groups, 'makemkv_key', visible)).toBe('Keys');
	});

	it('is undefined when the owning tab is not visible', () => {
		expect(fieldTab(groups, 'hook_url', visible)).toBeUndefined();
	});

	it('is undefined for a key no group owns', () => {
		expect(fieldTab(groups, 'nope', visible)).toBeUndefined();
	});

	it('is undefined with no groups', () => {
		expect(fieldTab(undefined, 'makemkv_key', visible)).toBeUndefined();
	});
});
