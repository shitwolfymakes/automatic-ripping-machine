// What the import panel shows and enables for its current state: which step
// it is on, what the buttons allow, and how each preset in the file reads.
import type { HandbrakeSchemaSlimView, ImportedPresetView } from '$lib/types/api.gen';

interface ImportPanelInput {
	presets: readonly ImportedPresetView[] | null;
	schema: HandbrakeSchemaSlimView | null;
	text: string;
	loading: boolean;
}

interface ImportPanelView {
	step: 1 | 2;
	showVersionLine: boolean;
	versionTag: string;
	canRead: boolean;
	readLabel: string;
	showPicks: boolean;
	showSingleReason: boolean;
	singleReason: string;
	picks: PresetPickView[];
}

interface PresetPickView {
	label: string;
	disabled: boolean;
	reason: string | null;
}

function hasUnimportableOnlyPreset(presets: readonly ImportedPresetView[]): boolean {
	const only = presets[0];
	return presets.length <= 1 && only !== undefined && !only.importable;
}

/** The step the panel is on, and the flags its buttons and notes follow. */
export function importPanelView(input: ImportPanelInput): ImportPanelView {
	const { presets, schema, text, loading } = input;
	const reviewing = presets !== null;
	const showSingleReason = reviewing && hasUnimportableOnlyPreset(presets);
	return {
		step: reviewing ? 2 : 1,
		showVersionLine: schema !== null,
		versionTag: schema?.handbrake_tag ?? '',
		canRead: text.trim() !== '' && !loading,
		readLabel: loading ? 'Importing...' : 'Import',
		showPicks: reviewing && presets.length > 1,
		showSingleReason,
		singleReason: showSingleReason ? (presets[0]?.reason ?? '') : '',
		picks: reviewing ? presets.map(presetPickView) : []
	};
}

/** One preset in the file's pick list: its path and name, whether it can
 * be chosen, and the reason it cannot. */
export function presetPickView(preset: ImportedPresetView): PresetPickView {
	return {
		label: [...preset.path, preset.name].join(' / '),
		disabled: !preset.importable,
		reason: !preset.importable && preset.reason ? preset.reason : null
	};
}
