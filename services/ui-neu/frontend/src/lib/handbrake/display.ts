// What the transcode preset sidebar and the presets list say: notes, titles, row flags and setting issues.
// Pure functions; the components render the result.

import type { SettingIssue, TranscodePresetView } from '$lib/types/api.gen';
import { settingsCount } from './draft';
import { plural } from '$lib/utils/plural';

export type SidebarMode = 'new' | 'edit' | 'view';

export const CPU_HERE_NOTE = 'Encodes on CPU on this host: no verified non-AMD GPU for this codec';
export const VAAPI_NOTE =
	'HandBrake settings do not apply to AMD VAAPI encoders. Only the container and extra args are used.';
export const AMD_NOTE =
	'AMD devices encode with ffmpeg, which cannot apply these settings. Because this preset has HandBrake settings, it skips AMD devices and uses another GPU or the CPU.';
export const CLEARED_NOTE = "This preset's HandBrake settings will be cleared when you save.";

const TITLES: Record<SidebarMode, string> = {
	new: 'New transcode preset',
	edit: 'Edit transcode preset',
	view: 'View transcode preset'
};

export function footerNote(preset: TranscodePresetView | null): string | null {
	return preset?.host_notes?.includes('encodes_on_cpu_here') ? CPU_HERE_NOTE : null;
}

interface RowFlags {
	settings: string | null;
	needsReview: boolean;
	cpuHere: boolean;
}

function settingsLabel(count: number): string | null {
	if (count === 0) return null;
	return `${count} ${plural(count, 'setting')}`;
}

// What a Transcode presets list row adds to its attribute line; nothing for a rip preset (null).
export function rowFlags(preset: TranscodePresetView | null): RowFlags {
	const count = settingsCount(preset?.handbrake_settings ?? null);
	return {
		settings: settingsLabel(count),
		needsReview: (preset?.issues ?? []).length > 0,
		cpuHere: footerNote(preset) !== null
	};
}

export function sidebarTitle(mode: SidebarMode): string {
	return TITLES[mode];
}

export function usageLabel(count: number): string {
	return `Used by ${count} ${plural(count, 'session')}`;
}

export function issuesFor(
	issues: SettingIssue[],
	key: string,
	encoder: string | null = null
): SettingIssue | undefined {
	return issues.find((i) => i.key === key && (i.encoder ?? null) === encoder);
}

// What LoadState shows while the schema store is unavailable; null otherwise.
export function schemaLoadError(state: string, message: string | null): Error | null {
	return state === 'unavailable' ? new Error(message ?? 'No HandBrake schema loaded yet') : null;
}
