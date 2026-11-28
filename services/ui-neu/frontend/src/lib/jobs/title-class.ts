import type { TitleClass, TrackView } from '$lib/types/api.gen';
import { formatTrackDuration } from '$lib/utils/format';
import { parseTitleRef } from './version-sets';

/** A disc with at least this many decoy rows collapses them into one disclosure row. */
export const DECOY_GROUP_MIN = 3;

export interface TitleClassLabel {
	text: string;
	tone: 'info' | 'muted';
}

type LabelTrack = Pick<
	TrackView,
	| 'title_class'
	| 'title_class_ref'
	| 'source_ref'
	| 'source_file'
	| 'playlist_name'
	| 'duration_seconds'
	| 'expected_duration_seconds'
	| 'stereo_3d'
>;

/** The label of a title MakeMKV's list does not hold: it is on the disc but cannot be ripped. */
export const UNRIPPABLE_LABEL = "MakeMKV can't rip this";

/** A primary title at least this long is the main feature; a shorter one is an extra. */
const MAIN_FEATURE_MIN_SECONDS = 45 * 60;

// The classes a title of its own can have: its row says whether it is the feature or an extra.
const OWN_CLASSES = new Set<TitleClass | null | undefined>([null, undefined, 'primary', 'edition']);

/** "Main feature" or "Extra" for a title that stands on its own, by its length; null when unknown or classed. */
export function featureLabel(
	track: Pick<TrackView, 'title_class' | 'duration_seconds' | 'expected_duration_seconds'>
): string | null {
	const secs = track.duration_seconds ?? track.expected_duration_seconds;
	if (!secs || !OWN_CLASSES.has(track.title_class)) return null;
	return secs >= MAIN_FEATURE_MIN_SECONDS ? 'Main feature' : 'Extra';
}

/** Maps a `title_class_ref` (the kept title's source_ref) to the row number the table shows, or null. */
export type RefIndex = (ref: string) => number | null;

export interface DecoyGroup<T> {
	decoyGroup: true;
	ref: string | null;
	members: T[];
}

interface Classed {
	titleClass: TitleClass | null;
	classRef: string | null;
	sourceRef: string;
}

/** The lookup `titleClassLabel` needs, built from the tracks of one job. */
export function refIndexOf(tracks: readonly Pick<TrackView, 'source_ref' | 'index'>[]): RefIndex {
	const byRef = new Map(tracks.map((t) => [t.source_ref, t.index]));
	return (ref) => byRef.get(ref) ?? null;
}

/** How a label names the title a copy points at: `#N`, else "title <ref>", else "another title". */
export function refText(ref: string | null | undefined, refIndex: RefIndex): string {
	if (ref == null) return 'another title';
	const n = refIndex(ref);
	return n == null ? `title ${ref}` : `#${n}`;
}

/** A source_file ending ".m2ts" with no playlist: the raw stream file rather than a playlist. */
export function isRawStream(track: Pick<TrackView, 'source_file' | 'playlist_name'>): boolean {
	return !track.playlist_name && !!track.source_file?.toLowerCase().endsWith('.m2ts');
}

function editionText(track: LabelTrack): string {
	const secs = track.duration_seconds ?? track.expected_duration_seconds;
	return secs ? `Edition (${formatTrackDuration(secs)})` : 'Edition';
}

/** The chip a row carries for what the classifier made of it; null for a plain title. */
export function titleClassLabel(track: LabelTrack, refIndex: RefIndex): TitleClassLabel | null {
	const of = refText(track.title_class_ref, refIndex);
	switch (track.title_class) {
		case 'edition':
			return { text: editionText(track), tone: 'info' };
		case 'duplicate':
			return { text: isRawStream(track) ? `Copy of ${of} (stream file)` : `Copy of ${of}`, tone: 'muted' };
		case 'decoy':
			return { text: `Decoy playlist of ${of}`, tone: 'muted' };
		case 'variant':
			return { text: `${of} with an extra intro`, tone: 'muted' };
		case 'angle': {
			const angle = parseTitleRef(track.source_ref)?.angle;
			return { text: angle ? `Angle ${angle} of ${of}` : `Other angle of ${of}`, tone: 'muted' };
		}
		case 'subset':
			return { text: `Shorter cut of ${of}`, tone: 'muted' };
		case 'view':
			return { text: `${track.stereo_3d ? '3D' : '2D'} version of ${of}`, tone: 'muted' };
		default:
			return null;
	}
}

/**
 * What the Source column names: the ripped file, else the whole ref of an angle (`00334.mpls:2`, so two
 * angles of one playlist differ), else the playlist, the stream file, the ref.
 */
export function sourceName(
	track: Pick<TrackView, 'playlist_name' | 'source_file' | 'output_path' | 'source_ref'>
): string {
	if (track.output_path) return track.output_path;
	if (parseTitleRef(track.source_ref)?.angle) return track.source_ref;
	return track.playlist_name || track.source_file || track.source_ref;
}

/** The disclosure row's text: "298 decoy playlists of #0 (unticked)", or "(N ticked)" when some are on. */
export function decoyGroupText(count: number, ticked: number, of: string): string {
	const noun = count === 1 ? 'decoy playlist' : 'decoy playlists';
	return `${count} ${noun} of ${of} (${ticked > 0 ? `${ticked} ticked` : 'unticked'})`;
}

export function isDecoyGroup<T>(item: T | DecoyGroup<T>): item is DecoyGroup<T> {
	return (item as DecoyGroup<T>).decoyGroup === true;
}

function decoyCounts<T extends Classed>(rows: readonly T[]): Map<string | null, T[]> {
	const byRef = new Map<string | null, T[]>();
	for (const row of rows) {
		if (row.titleClass !== 'decoy') continue;
		byRef.set(row.classRef, [...(byRef.get(row.classRef) ?? []), row]);
	}
	return byRef;
}

/**
 * Collapses the decoys that copy one title into a single group once there are
 * `min` or more of them. The group sits right after the title it copies, else
 * at the end; smaller sets stay as ordinary rows.
 */
export function groupDecoys<T extends Classed>(rows: readonly T[], min: number): (T | DecoyGroup<T>)[] {
	const groups = new Map<string | null, DecoyGroup<T>>();
	for (const [ref, members] of decoyCounts(rows)) {
		if (members.length >= min) groups.set(ref, { decoyGroup: true, ref, members });
	}
	const out: (T | DecoyGroup<T>)[] = [];
	const placed = new Set<string | null>();
	for (const row of rows) {
		if (row.titleClass === 'decoy' && groups.has(row.classRef)) continue;
		out.push(row);
		const group = groups.get(row.sourceRef);
		if (group) {
			out.push(group);
			placed.add(row.sourceRef);
		}
	}
	for (const [ref, group] of groups) if (!placed.has(ref)) out.push(group);
	return out;
}
