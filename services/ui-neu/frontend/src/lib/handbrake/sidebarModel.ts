// The transcode preset sidebar's decisions: the editable draft, the request
// bodies it saves as, which fields and cards show, and how a failed save reads.
// Pure functions; the sidebar component does the I/O.

import { ApiError, saveErrorMessage } from '$lib/api/client';
import type {
	ContainerFormat,
	EncoderAvailabilityView,
	HandbrakeSchemaSlimView,
	HandbrakeSettings,
	MediaType,
	SettingIssue,
	SlimFamily,
	SlimKey,
	TranscodePresetCreateRequest,
	TranscodePresetUpdateRequest,
	TranscodePresetView,
	TranscodeTool
} from '$lib/types/api.gen';
import { encoderCards, type EncoderCard } from './encoderCards';
import { keysForTab, type TabId } from './fields';
import { pruneUnreachable, toPayload } from './settingsEdit';
import { fieldVisible, type Context } from './dependencyRules';

export type SidebarMode = 'new' | 'edit' | 'view';
export type BaseValues = Record<string, unknown> | null;
// The built-in presets loaded so far, by name.
export type Bases = Record<string, Record<string, unknown>>;
export type FilterState = { text: string; changedOnly: boolean };
export type PresetField = 'name' | 'media_type' | 'tool' | 'preset_ref' | 'container' | 'encoder' | 'extra_args';

export interface Draft {
	name: string;
	media_type: MediaType;
	tool: TranscodeTool;
	preset_ref: string | null;
	container: ContainerFormat;
	encoder: string;
	extra_args: string;
	settings: HandbrakeSettings;
}

export const CPU_HERE_NOTE = 'Encodes on CPU on this host: no verified non-AMD GPU for this codec';
export const VAAPI_NOTE =
	'HandBrake settings do not apply to AMD VAAPI encoders. Only the container and extra args are used.';
export const AMD_NOTE =
	'AMD devices encode with ffmpeg, which cannot apply these settings. Because this preset has HandBrake settings, it skips AMD devices and uses another GPU or the CPU.';
export const CLEARED_NOTE = "This preset's HandBrake settings will be cleared when you save.";
export const MARKED_ISSUES_MESSAGE = 'Fix the marked settings and save again.';

const PRESET_ENCODER = 'preset';
const LOCKED_TOOLS = new Set<TranscodeTool>(['abcde', 'none']);
const DEFAULT_DEPTH = 8;
const TITLES: Record<SidebarMode, string> = {
	new: 'New transcode preset',
	edit: 'Edit transcode preset',
	view: 'View transcode preset'
};

function settingsOf(s: HandbrakeSettings | null): Required<HandbrakeSettings> {
	return { common: s?.common ?? {}, encoders: s?.encoders ?? {} };
}

export function initialDraft(preset: TranscodePresetView | null): Draft {
	return {
		name: preset?.name ?? '',
		media_type: preset?.media_type ?? 'movie',
		tool: preset?.tool ?? 'handbrake',
		preset_ref: preset?.preset_ref ?? null,
		container: preset?.container ?? 'mkv',
		encoder: preset?.encoder ?? PRESET_ENCODER,
		extra_args: preset?.extra_args ?? '',
		settings: settingsOf(preset?.handbrake_settings ?? null)
	};
}

// vaapi_* catalog ids are the ffmpeg_vaapi engine: HandBrake settings do not apply to them.
export function isVaapiEncoder(encoderId: string): boolean {
	return encoderId.startsWith('vaapi_');
}

export function showTabs(d: Draft): boolean {
	return d.tool === 'handbrake' && !isVaapiEncoder(d.encoder);
}

// The draft holds settings the save will drop because the tabs no longer apply.
export function clearsSettings(d: Draft): boolean {
	return !showTabs(d) && settingsCount(d.settings) > 0;
}

// Settings the tabs cannot show are not sent: the encoder would ignore them.
function settingsPayload(d: Draft): HandbrakeSettings | null {
	return showTabs(d) ? toPayload(d.settings) : null;
}

function presetFields(d: Draft) {
	return {
		name: d.name,
		tool: d.tool,
		preset_ref: d.preset_ref,
		container: d.container,
		encoder: d.encoder,
		extra_args: d.extra_args || null,
		handbrake_settings: settingsPayload(d)
	};
}

export function draftToUpdate(d: Draft): TranscodePresetUpdateRequest {
	return presetFields(d);
}

export function draftToCreate(d: Draft): TranscodePresetCreateRequest {
	return { ...presetFields(d), media_type: d.media_type };
}

// abcde and none run their own encoder, so a codec encoder would 422.
export function onToolChange(d: Draft, tool: TranscodeTool): Draft {
	return { ...d, tool, encoder: LOCKED_TOOLS.has(tool) ? PRESET_ENCODER : d.encoder };
}

// Drops the blocks of families the new encoder can never reach (Review Focus 4).
export function onEncoderChange(
	d: Draft,
	encoderId: string,
	schema: HandbrakeSchemaSlimView,
	baseEncoder: string | null = null
): Draft {
	const reachable = encoderCards(encoderId, d.preset_ref, schema, [], baseEncoder).map((c) => c.family);
	return { ...d, encoder: encoderId, settings: pruneUnreachable(d.settings, reachable) };
}

function baseEncoderOf(bases: Bases, presetRef: string | null): string | null {
	return baseVideoEncoder(presetRef === null ? null : (bases[presetRef] ?? null));
}

// The preset encoder reaches only its base's family, so a new base drops the blocks it no longer reaches.
// A base whose values have not loaded cannot be resolved yet; its blocks stay until it loads.
export function onBaseChange(
	d: Draft,
	presetRef: string | null,
	schema: HandbrakeSchemaSlimView | null,
	bases: Bases
): Draft {
	const next = { ...d, preset_ref: presetRef };
	if (!schema || d.encoder !== PRESET_ENCODER) return next;
	if (presetRef !== null && !(presetRef in bases)) return next;
	return onEncoderChange(next, PRESET_ENCODER, schema, baseEncoderOf(bases, presetRef));
}

// One preset-block edit; `bases` holds the built-in presets loaded so far, by name. Without a schema the
// blocks cannot be pruned, so an encoder change only sets the id.
export function applyField(
	d: Draft,
	field: PresetField,
	value: string,
	schema: HandbrakeSchemaSlimView | null,
	bases: Bases
): Draft {
	if (field === 'tool') return onToolChange(d, value as TranscodeTool);
	if (field === 'encoder') {
		return schema ? onEncoderChange(d, value, schema, baseEncoderOf(bases, d.preset_ref)) : { ...d, encoder: value };
	}
	if (field === 'preset_ref') return onBaseChange(d, value || null, schema, bases);
	return { ...d, [field]: value };
}

export function footerNote(preset: TranscodePresetView | null): string | null {
	return preset?.host_notes?.includes('encodes_on_cpu_here') ? CPU_HERE_NOTE : null;
}

export function settingsCount(s: HandbrakeSettings | null): number {
	const n = settingsOf(s);
	return Object.keys(n.common).length + Object.values(n.encoders).reduce((sum, b) => sum + Object.keys(b).length, 0);
}

export interface RowFlags {
	settings: string | null;
	needsReview: boolean;
	cpuHere: boolean;
}

function settingsLabel(count: number): string | null {
	if (count === 0) return null;
	return `${count} ${count === 1 ? 'setting' : 'settings'}`;
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
	return `Used by ${count} ${count === 1 ? 'session' : 'sessions'}`;
}

export function commonOf(s: HandbrakeSettings): Record<string, unknown> {
	return s.common ?? {};
}

export function blockOf(s: HandbrakeSettings, family: string): Record<string, unknown> {
	return s.encoders?.[family] ?? {};
}

// The audio output tracks in effect: the preset's own list, else the base's, else none.
export function audioListValue(key: SlimKey, s: HandbrakeSettings, base: BaseValues): Record<string, unknown>[] {
	const common = commonOf(s);
	const list = key.name in common ? common[key.name] : inheritedValue(key, base);
	return Array.isArray(list) ? list : [];
}

export function inheritedValue(key: SlimKey, base: BaseValues): unknown {
	return base && key.name in base ? base[key.name] : key.default;
}

// The value of every key in effect: the preset's, else the base preset's, else the schema default.
export function panelContext(schema: HandbrakeSchemaSlimView, s: HandbrakeSettings, base: BaseValues): Context {
	return { ...Object.fromEntries(schema.keys.map((k) => [k.name, k.default])), ...base, ...commonOf(s) };
}

export function baseVideoEncoder(base: BaseValues): string | null {
	return typeof base?.VideoEncoder === 'string' ? base.VideoEncoder : null;
}

// R2: the base's VideoEncoder depth when it is this family, else 8.
export function inheritedDepth(family: SlimFamily, base: BaseValues): { depth: number; source: 'base' | 'default' } {
	const encoder = baseVideoEncoder(base);
	const variant = family.variants.find((v) => v.encoder === encoder);
	return variant ? { depth: variant.depth, source: 'base' } : { depth: DEFAULT_DEPTH, source: 'default' };
}

// Neither ARM-owned, encoder-specific nor hidden: a field of the preset's common settings.
function isCommonKey(schema: HandbrakeSchemaSlimView, name: string): boolean {
	return (
		!schema.arm_owned_keys.includes(name) &&
		!schema.encoder_specific_keys.includes(name) &&
		!schema.hidden_keys.includes(name)
	);
}

export function commonKeys(schema: HandbrakeSchemaSlimView, tab: TabId): SlimKey[] {
	return keysForTab(schema, tab).filter((k) => isCommonKey(schema, k.name));
}

export function keyShown(key: SlimKey, stored: boolean, f: FilterState, ctx: Context): boolean {
	return fieldVisible(key.name, key.label, f, stored, ctx);
}

// The audio track list holds inputs rather than being one. Under Changed only it shows when the preset
// stores its own list; while filtering, when a track still shows a field.
export function audioListShown(f: FilterState, listStored: boolean, tracks: SlimKey[][]): boolean {
	if (f.changedOnly && !listStored) return false;
	return f.text.trim() === '' || tracks.some((keys) => keys.length > 0);
}

// The encoder cards the Video tab renders for this encoder, base preset and host.
export function panelCards(
	schema: HandbrakeSchemaSlimView,
	encoder: string,
	presetRef: string | null,
	availability: EncoderAvailabilityView[],
	base: BaseValues
): Array<{ card: EncoderCard; family: SlimFamily }> {
	return cardFamilies(encoderCards(encoder, presetRef, schema, availability, baseVideoEncoder(base)), schema);
}

// Each card with its schema family; a card for a family this HandBrake build lacks has nothing to edit.
export function cardFamilies(
	cards: EncoderCard[],
	schema: HandbrakeSchemaSlimView
): Array<{ card: EncoderCard; family: SlimFamily }> {
	return cards.flatMap((card) => {
		const family = schema.families.find((f) => f.name === card.family);
		return family ? [{ card, family }] : [];
	});
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

export interface SaveFailure {
	issues: SettingIssue[] | null;
	message: string;
	schemaMissing: boolean;
}

function issueList(body: unknown): SettingIssue[] | null {
	const detail = (body as { detail?: { issues?: unknown } } | null)?.detail;
	return Array.isArray(detail?.issues) ? (detail.issues as SettingIssue[]) : null;
}

export function saveFailure(e: unknown): SaveFailure {
	const issues = e instanceof ApiError && e.status === 422 ? issueList(e.body) : null;
	if (issues) return { issues, message: MARKED_ISSUES_MESSAGE, schemaMissing: false };
	const schemaMissing = e instanceof ApiError && e.status === 503;
	return { issues: null, message: saveErrorMessage(e), schemaMissing };
}
