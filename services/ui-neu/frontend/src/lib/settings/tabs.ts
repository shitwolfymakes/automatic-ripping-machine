// The Settings page's tab rules: which tabs exist, their order and labels,
// and how the URL hash and a field key map to a tab.
import type { SettingsGroup } from '$lib/types/api.gen';
import { groupLabel, legacyTab, settingsTabFor } from '$lib/settings/sections';

// Non-config screen-tabs (their own bespoke UI).
export const SCREEN_TABS = [
	'sessions',
	'transcoding',
	'notifications',
	'interface',
	'themes',
	'drives',
	'users',
	'system'
] as const;

// Config-group tabs derived from the backend schema. Identification, Keys and
// Ripping have no bespoke screen-tab home → render as their own tabs. (Transcoding/
// Notifications single toggles fold into the existing transcoding/notifications
// tabs; System read-only rows fold into the system tab — see template.)
export const CONFIG_GROUP_TABS = ['Keys', 'Identification', 'Ripping'] as const;

export function orderedConfigGroups(groups: readonly SettingsGroup[]): SettingsGroup[] {
	return (
		groups
			.filter((g) => (CONFIG_GROUP_TABS as readonly string[]).includes(g.name))
			// Tab order is this page's, not the schema's (API Keys first).
			.sort(
				(a, b) =>
					(CONFIG_GROUP_TABS as readonly string[]).indexOf(a.name) -
					(CONFIG_GROUP_TABS as readonly string[]).indexOf(b.name)
			)
	);
}

// Nicer labels for the screen-tab ids; config-group tabs use their group name.
const TAB_LABELS: Record<string, string> = {
	sessions: 'Sessions',
	transcoding: 'Transcoding',
	notifications: 'Notifications',
	interface: 'Interface',
	themes: 'Themes',
	drives: 'Drives',
	users: 'Users',
	system: 'System'
};

export function settingsTabLabel(id: string): string {
	return TAB_LABELS[id] ?? groupLabel(id);
}

export function tabFromHash(hash: string): string {
	const stripped = hash.replace('#', '');
	// Retired names (#Metadata, #appearance) open the tab that replaced them.
	const tabPart = legacyTab(stripped.split('/')[0]);
	// Validate the hash tab against the known-valid set: the static
	// config-group tabs (group names, not knowable from the schema at parse
	// time but fixed in this file) plus the bespoke screen-tabs. A stale or
	// legacy hash (e.g. an old #music/#ripping bookmark) falls back to
	// 'Identification' instead of leaving the content pane blank.
	const allowed = [...CONFIG_GROUP_TABS, ...SCREEN_TABS] as readonly string[];
	return allowed.includes(tabPart) ? tabPart : 'Identification';
}

export function fieldFromHash(hash: string): string | null {
	const part = hash.replace('#', '').split('/')[1];
	return part ? decodeURIComponent(part) : null;
}

/** The visible tab that renders `key`'s schema group, if any. */
export function fieldTab(
	groups: readonly SettingsGroup[] | undefined,
	key: string,
	visibleTabs: readonly string[]
): string | undefined {
	const owner = groups?.find((g) => g.fields.some((f) => f.key === key));
	const tab = owner && settingsTabFor(owner.name);
	return tab && visibleTabs.includes(tab) ? tab : undefined;
}
