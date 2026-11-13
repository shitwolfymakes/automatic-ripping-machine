// What the preset sidebar's panels show, as flat flags the templates branch on
// one at a time. Pure functions; the components call them inside $derived.

import type { EncoderAvailabilityView } from '$lib/types/api.gen';
import { nameErrors, type FieldErrors } from '$lib/utils/formValidation';
import { availabilityLabel } from './encoder-availability';
import { showsAmdNote } from './encoder-cards';
import type { TabId } from './fields';
import { clearsSettings, isVaapiEncoder, showTabs, type Draft } from './draft';
import type { SaveFailure } from '$lib/api/save-failure';
import type { SidebarMode } from './display';

interface SettingsPanelInput {
	tab: TabId;
	encoder: string;
	availability: EncoderAvailabilityView[];
}

interface SettingsPanelView {
	section: 'video' | 'plain';
	showAmdNote: boolean;
	encoderLabel: string;
}

export function settingsPanelView(input: SettingsPanelInput): SettingsPanelView {
	return {
		section: input.tab === 'video' ? 'video' : 'plain',
		showAmdNote: showsAmdNote(input.encoder, input.availability),
		encoderLabel: availabilityLabel(input.availability, input.encoder, 'This preset')
	};
}

// A HandBrake preset name that names a hardware encoder does nothing on its
// own: HandBrake only attaches a GPU when the Encoder field asks for one.
const HARDWARE_HINT_PATTERN = /QSV|NVENC|VCN|VCE/i;
export const HARDWARE_HINT =
	'This HandBrake preset uses a hardware encoder; choose the matching encoder above or ARM will not attach a GPU.';

export interface PresetBlockInput {
	draft: Draft;
	readonly: boolean;
	builtinNames: string[] | null;
	encodersLoading: boolean;
	encoderCount: number;
	presetEncoderId: string;
}

interface PresetBlockView {
	encoderDisabled: boolean;
	usesFfmpegVaapi: boolean;
	encoderList: 'loading' | 'empty' | 'groups';
	encoderHint: string | null;
	// HandBrake's built-in names when the base preset is a select; null for free text.
	baseNames: string[] | null;
	// A HandBrake preset links its base preset field to HandBrake's official presets page.
	showPresetsDocLink: boolean;
	extraArgsLabel: string;
	showOverrideHelp: boolean;
	showClearedNote: boolean;
}

function encoderListState(loading: boolean, count: number): PresetBlockView['encoderList'] {
	if (loading) return 'loading';
	return count === 0 ? 'empty' : 'groups';
}

function hardwareHint(draft: Draft, presetEncoderId: string): string | null {
	const hardwarePreset = HARDWARE_HINT_PATTERN.test(draft.preset_ref ?? '');
	return draft.encoder === presetEncoderId && hardwarePreset ? HARDWARE_HINT : null;
}

export function presetBlockView(input: PresetBlockInput): PresetBlockView {
	const { draft } = input;
	// abcde/none presets cannot carry a codec encoder.
	const encoderLocked = draft.tool === 'abcde' || draft.tool === 'none';
	const usesFfmpegVaapi = isVaapiEncoder(draft.encoder);
	return {
		encoderDisabled: input.readonly || encoderLocked || input.encodersLoading,
		usesFfmpegVaapi,
		encoderList: encoderListState(input.encodersLoading, input.encoderCount),
		encoderHint: hardwareHint(draft, input.presetEncoderId),
		baseNames: draft.tool === 'handbrake' ? input.builtinNames : null,
		showPresetsDocLink: draft.tool === 'handbrake',
		extraArgsLabel: usesFfmpegVaapi ? 'ffmpeg arguments' : 'Extra args',
		showOverrideHelp: showTabs(draft),
		showClearedNote: clearsSettings(draft)
	};
}

export interface PresetSidebarInput {
	mode: SidebarMode;
	importing: boolean;
	draft: Draft;
	submitting: boolean;
	cloneAvailable: boolean;
	failure: SaveFailure | null;
	unplacedCount: number;
}

interface PresetSidebarView {
	readonly: boolean;
	showImport: boolean;
	showFooter: boolean;
	showClone: boolean;
	showImportButton: boolean;
	importDisabled: boolean;
	failure: SaveFailure | null;
	showRetry: boolean;
	showUnplaced: boolean;
	settings: 'tabs' | 'vaapi-note' | 'none';
	// Save runs on an editable, idle draft; the name rule then decides whether it is sent.
	canSave: boolean;
}

function settingsArea(draft: Draft): PresetSidebarView['settings'] {
	if (showTabs(draft)) return 'tabs';
	return draft.tool === 'handbrake' ? 'vaapi-note' : 'none';
}

export function presetSidebarView(input: PresetSidebarInput): PresetSidebarView {
	const readonly = input.mode === 'view';
	return {
		readonly,
		showImport: input.importing,
		showFooter: !input.importing,
		showClone: readonly && input.cloneAvailable,
		showImportButton: !readonly,
		importDisabled: input.importing,
		failure: input.failure,
		showRetry: input.failure?.schemaMissing === true,
		showUnplaced: input.unplacedCount > 0,
		settings: settingsArea(input.draft),
		canSave: !readonly && !input.submitting
	};
}

/** The preset block's name input, the one field the sidebar checks before sending. */
export const PRESET_NAME_ID = 'tp-name';

/** What the sidebar marks on Save before any request: a blank name. */
export function presetErrors(draft: Draft): FieldErrors {
	return nameErrors(PRESET_NAME_ID, draft.name);
}
