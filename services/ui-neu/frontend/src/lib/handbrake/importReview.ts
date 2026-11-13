// What the import review step shows for one parsed export entry, and how an
// accepted entry fills the sidebar draft. Pure functions; no I/O.

import type {
	EncoderAvailabilityView,
	HandbrakeSchemaSlimView,
	HandbrakeSettings,
	ImportedPresetView
} from '$lib/types/api.gen';
import { TABS, type TabId } from './fields';
import { storedCount } from './settingsEdit';
import type { Draft } from './sidebarModel';
import { plural } from '$lib/utils/plural';

export interface ImportReview {
	encoderInFile: string;
	codecDepth: string;
	encoderInArm: string;
	container: string;
	storedFor: string;
	values: [string, string][];
	copiedLine: string | null;
	copiedTo: string[];
	eightBitOnly: string[];
	tabCounts: Record<TabId, number>;
	total: number;
	notes: string[];
}

export const COPIED_NOTE = 'Only bit depth is copied. Other encoders keep their defaults.';

// The codec a HandBrake family encodes: the catalog suffix (nvenc_h264) or the CPU family name.
const CODEC_LABELS: Record<string, string> = {
	h264: 'H.264',
	x264: 'H.264',
	h265: 'H.265',
	x265: 'H.265',
	av1: 'AV1',
	svt_av1: 'AV1'
};
const BIT_DEPTH_KEY = 'bit_depth';
const DEFAULT_DEPTH = 8;
// The export names an encoder variant (x265_10bit); blocks are keyed by its family (x265).
const DEPTH_SUFFIX = /_(\d+)bit$/;

type Block = Record<string, unknown>;

// The availability label of the catalog id that matches the family, else the family id.
export function familyLabel(family: string, availability: EncoderAvailabilityView[]): string {
	return availability.find((a) => a.id === family)?.label ?? family;
}

function sourceFamily(encoder: string): string {
	return encoder.replace(DEPTH_SUFFIX, '');
}

// The block's own depth, else the variant's suffix, else HandBrake's 8-bit.
function depthOf(encoder: string, block: Block): number {
	const stored = block[BIT_DEPTH_KEY];
	if (typeof stored === 'number') return stored;
	return Number(DEPTH_SUFFIX.exec(encoder)?.[1] ?? DEFAULT_DEPTH);
}

function codecOf(family: string): string | null {
	const suffix = family.slice(family.lastIndexOf('_') + 1);
	return CODEC_LABELS[family] ?? CODEC_LABELS[suffix] ?? null;
}

function keyLabel(name: string, schema: HandbrakeSchemaSlimView): string {
	if (name === BIT_DEPTH_KEY) return 'Bit depth';
	return schema.keys.find((k) => k.name === name)?.label ?? name;
}

function blockValues(block: Block, schema: HandbrakeSchemaSlimView): [string, string][] {
	return Object.entries(block).map(([name, value]) => [keyLabel(name, schema), String(value)]);
}

function codecDepth(family: string, depth: number): string {
	return [codecOf(family), `${depth}-bit`].filter((part) => part !== null).join(', ');
}

function tabCounts(settings: HandbrakeSettings, schema: HandbrakeSchemaSlimView): Record<TabId, number> {
	const counts = {} as Record<TabId, number>;
	for (const tab of TABS) counts[tab.id] = storedCount(settings, tab.id, schema);
	return counts;
}

function notesFor(
	p: ImportedPresetView,
	schema: HandbrakeSchemaSlimView,
	sourceLabel: string,
	copiedTo: string[]
): string[] {
	const notes: string[] = [];
	if (copiedTo.length > 0) notes.push(COPIED_NOTE);
	if (p.not_imported.length > 0) {
		notes.push(`Not used by ${sourceLabel}, not imported: ${p.not_imported.join(', ')}`);
	}
	if (p.dropped_keys.length > 0) {
		const n = p.dropped_keys.length;
		notes.push(
			`${n} ${plural(n, 'key')} dropped (not in HandBrake ${schema.handbrake_tag}): ${p.dropped_keys.join(', ')}`
		);
	}
	return [...notes, ...messagesOf(p)];
}

function messagesOf(p: ImportedPresetView): string[] {
	return [...p.warnings, ...p.issues.map((issue) => issue.message)];
}

function emptyReview(p: ImportedPresetView, availability: EncoderAvailabilityView[]): ImportReview {
	const empty = {} as Record<TabId, number>;
	for (const tab of TABS) empty[tab.id] = 0;
	return {
		encoderInFile: familyLabel(sourceFamily(p.source_encoder), availability),
		codecDepth: '',
		encoderInArm: '',
		container: '',
		storedFor: '',
		values: [],
		copiedLine: null,
		copiedTo: [],
		eightBitOnly: [],
		tabCounts: empty,
		total: 0,
		notes: messagesOf(p)
	};
}

export function reviewRows(
	p: ImportedPresetView,
	schema: HandbrakeSchemaSlimView,
	availability: EncoderAvailabilityView[] = []
): ImportReview {
	const proposal = p.proposal;
	if (proposal === null) return emptyReview(p, availability);
	const family = sourceFamily(p.source_encoder);
	const block: Block = proposal.handbrake_settings.encoders?.[family] ?? {};
	const depth = depthOf(p.source_encoder, block);
	const sourceLabel = familyLabel(family, availability);
	const copiedTo = p.copied_depth_to.map((family) => familyLabel(family, availability));
	const counts = tabCounts(proposal.handbrake_settings, schema);
	return {
		encoderInFile: sourceLabel,
		codecDepth: codecDepth(family, depth),
		encoderInArm: familyLabel(proposal.encoder, availability),
		container: proposal.container,
		storedFor: sourceLabel,
		values: blockValues(block, schema),
		copiedLine: copiedTo.length > 0 ? `Bit depth ${depth} also set for ${copiedTo.join(', ')}` : null,
		copiedTo,
		eightBitOnly: p.eight_bit_only.map((family) => `${familyLabel(family, availability)}: 8-bit on this encoder`),
		tabCounts: counts,
		total: Object.values(counts).reduce((sum, n) => sum + n, 0),
		notes: notesFor(p, schema, sourceLabel, copiedTo)
	};
}

// The preset to preselect: the first that can be imported, or none.
export function defaultPick(presets: ImportedPresetView[]): number | null {
	const at = presets.findIndex((p) => p.importable);
	return at === -1 ? null : at;
}

// Fills the draft from a proposal; an existing name is kept. The proposal was
// validated with no base preset, so the base is cleared. Nothing is saved.
export function applyProposal(d: Draft, p: ImportedPresetView): Draft {
	const proposal = p.proposal;
	if (proposal === null) return d;
	return {
		...d,
		name: d.name.trim() === '' ? proposal.name : d.name,
		preset_ref: null,
		container: proposal.container,
		encoder: proposal.encoder,
		settings: proposal.handbrake_settings
	};
}
