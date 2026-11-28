// Version sets on the review card: a title the disc holds more than once (another angle, a copy
// without chapters, a 2D/3D twin, a copy with an extra intro). The pick and the alternates that
// point at it are one set; the card shows the set as one choice. Pure: components render these.
import type { TrackEditRequest, TrackView } from '$lib/types/api.gen';
import { formatMinSec, formatTrackDuration } from '$lib/utils/format';
import type { DecoyGroup } from './title-class';
import type { ReviewRow } from './review-rows';

/** A title ref `00334.mpls` or `00334.mpls:2` (angle 2) split in two; null for a ref that is neither. */
export function parseTitleRef(ref: string): { source: string; angle: number | null } | null {
	const [source, angle, ...rest] = ref.split(':');
	if (!source || rest.length > 0) return null;
	if (angle === undefined) return { source, angle: null };
	if (!/^\d+$/.test(angle) || Number(angle) < 1) return null;
	return { source, angle: Number(angle) };
}

export type View = '2d' | '3d';
export type VersionKind = 'pick' | 'angle' | 'subset' | 'variant' | 'view';

export interface VersionMember {
	row: ReviewRow;
	kind: VersionKind;
	view: View;
	/** The angle the ref names, null for a playlist without angles. */
	angle: number | null;
}

export interface VersionSet {
	versionSet: true;
	pickRef: string;
	/** What a decoy group looks for to sit after this set. */
	sourceRef: string;
	/** The pick first, then the alternates in row order. */
	members: VersionMember[];
}

export function isVersionSet<T extends object>(item: T | VersionSet): item is VersionSet {
	return 'versionSet' in item;
}

const ALTERNATE_KINDS: Record<string, VersionKind> = {
	angle: 'angle',
	subset: 'subset',
	variant: 'variant',
	view: 'view'
};

function memberOf(row: ReviewRow, kind: VersionKind): VersionMember {
	return { row, kind, view: row.stereo3d ? '3d' : '2d', angle: row.angle };
}

function alternatesOf(rows: readonly ReviewRow[]): Map<string, ReviewRow[]> {
	const byPick = new Map<string, ReviewRow[]>();
	for (const row of rows) {
		if (!row.titleClass || !(row.titleClass in ALTERNATE_KINDS) || !row.classRef) continue;
		byPick.set(row.classRef, [...(byPick.get(row.classRef) ?? []), row]);
	}
	return byPick;
}

/**
 * Folds each pick and the alternates that point at it into one set, placed where the pick stood. An
 * alternate whose pick is not among the rows stays an ordinary row; decoy groups pass through.
 */
export function groupVersions(
	items: readonly (ReviewRow | DecoyGroup<ReviewRow>)[]
): (ReviewRow | DecoyGroup<ReviewRow> | VersionSet)[] {
	const rows = items.filter((i): i is ReviewRow => !('decoyGroup' in i));
	const picks = new Map(rows.map((r) => [r.sourceRef, r]));
	const alternates = alternatesOf(rows);
	const folded = new Set<ReviewRow>();
	const sets = new Map<string, VersionSet>();
	for (const [ref, members] of alternates) {
		const pick = picks.get(ref);
		if (!pick) continue;
		members.forEach((m) => folded.add(m));
		const found = members.map((m) => memberOf(m, ALTERNATE_KINDS[m.titleClass as string]));
		sets.set(ref, { versionSet: true, pickRef: ref, sourceRef: ref, members: [memberOf(pick, 'pick'), ...found] });
	}
	const out: (ReviewRow | DecoyGroup<ReviewRow> | VersionSet)[] = [];
	for (const item of items) {
		if ('decoyGroup' in item) out.push(item);
		else if (sets.has(item.sourceRef)) out.push(sets.get(item.sourceRef) as VersionSet);
		else if (!folded.has(item)) out.push(item);
	}
	return out;
}

/** Whether the disc holds a film more than once: an alternate title points at a title that is listed. */
export function hasVersionSets(
	tracks: readonly Pick<TrackView, 'source_ref' | 'title_class' | 'title_class_ref'>[]
): boolean {
	const refs = new Set(tracks.map((t) => t.source_ref));
	return tracks.some(
		(t) => !!t.title_class && t.title_class in ALTERNATE_KINDS && !!t.title_class_ref && refs.has(t.title_class_ref)
	);
}

// The members a view or an angle choice can land on; a subset or a variant is a version of its own.
const GRID_KINDS = new Set<VersionKind>(['pick', 'angle', 'view']);

function gridMembers(set: VersionSet): VersionMember[] {
	return set.members.filter((m) => GRID_KINDS.has(m.kind));
}

/** The members that are neither an angle nor a view of the pick: a copy without chapters, a longer cut. */
export function otherMembers(set: VersionSet): VersionMember[] {
	return set.members.filter((m) => !GRID_KINDS.has(m.kind));
}

/** The views the set offers, in the order they first appear. */
export function viewsOf(set: VersionSet): View[] {
	return [...new Set(gridMembers(set).map((m) => m.view))];
}

/** The angles a view offers, ascending; a playlist without angles stands as angle 1. */
export function anglesFor(set: VersionSet, view: View): number[] {
	const angles = gridMembers(set)
		.filter((m) => m.view === view)
		.map((m) => m.angle ?? 1);
	return [...new Set(angles)].sort((a, b) => a - b);
}

/** The member at a view and angle, or null. */
export function gridMember(set: VersionSet, view: View, angle: number): VersionMember | null {
	return gridMembers(set).find((m) => m.view === view && (m.angle ?? 1) === angle) ?? null;
}

/**
 * Where a view or an angle choice lands from the current member. The view and the angle are
 * independent: a new view keeps the angle when it has it, else takes its first angle.
 */
export function targetFor(
	set: VersionSet,
	current: VersionMember,
	pick: { view?: View; angle?: number }
): VersionMember | null {
	const angle = current.angle ?? 1;
	if (pick.angle !== undefined) return gridMember(set, current.view, pick.angle);
	if (pick.view === undefined) return current;
	return gridMember(set, pick.view, angle) ?? gridMember(set, pick.view, anglesFor(set, pick.view)[0]);
}

/** The chips of a member: its angle when it names one, and its view when the set mixes views or is 3D. */
export function versionChips(set: VersionSet, member: VersionMember): string[] {
	const chips: string[] = [];
	if (member.angle !== null) chips.push(`Angle ${member.angle}`);
	if (member.view === '3d') chips.push('3D');
	else if (set.members.some((m) => m.view === '3d')) chips.push('2D');
	return chips;
}

function gap(set: VersionSet, member: VersionMember): number {
	const pick = set.members[0].row.durationSeconds;
	const own = member.row.durationSeconds;
	return pick == null || own == null ? 0 : Math.abs(own - pick);
}

function withGap(text: string, seconds: number, word: 'shorter' | 'longer'): string {
	return seconds > 0 ? `${text}, ${formatMinSec(seconds, 1)} ${word}` : text;
}

/** One sentence on how the member differs from the pick. */
export function versionLine(set: VersionSet, member: VersionMember): string {
	switch (member.kind) {
		case 'pick':
			return 'Main version';
		case 'angle':
			return 'Same film, other angle';
		case 'subset':
			return withGap('Same film', gap(set, member), 'shorter');
		case 'variant':
			return withGap('Same film with an extra intro', gap(set, member), 'longer');
		case 'view':
			return `Same film in ${member.view === '3d' ? '3D' : '2D'}`;
	}
}

/** The members whose box is ticked. */
export function tickedMembers(set: VersionSet): VersionMember[] {
	return set.members.filter((m) => !m.row.excluded);
}

/** The disclosure row's text: how many versions, and which one is kept. */
export function versionSummary(set: VersionSet): string {
	const head = `${set.members.length} versions of the film`;
	const kept = tickedMembers(set);
	if (kept.length === 0) return `${head}: none kept`;
	if (kept.length > 1) return `${head}: keeping ${kept.map((m) => `#${m.row.index}`).join(', ')}`;
	const [only] = kept;
	const chips = versionChips(set, only);
	const named = chips.length ? ` (${chips.join(', ')})` : '';
	const length = formatTrackDuration(only.row.durationSeconds);
	return `${head}: keeping #${only.row.index}${named} ${length}, ${only.row.sizeLabel}`;
}

/** One edit list for the whole set: the chosen tracks ticked, every other member unticked. */
export function choiceEdits(set: VersionSet, chosenIds: readonly string[]): TrackEditRequest[] {
	return set.members.map((m) => ({
		track_id: m.row.trackId as string,
		excluded: !chosenIds.includes(m.row.trackId as string)
	}));
}
