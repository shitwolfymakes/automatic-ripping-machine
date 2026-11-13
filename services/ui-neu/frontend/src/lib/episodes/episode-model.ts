import type {
	EpisodeSummary,
	IdentityView,
	JobView,
	MatchPreview,
	TrackIdentityView,
	TrackView
} from '$lib/types/api.gen';
import { activeSource, EPISODE_PREFIX, notConfigured, SOURCE_LABEL } from '$lib/episodes/sources';

export type PanelState = 'noseries' | 'matching' | 'unavailable' | 'nomatch' | 'unsure' | 'applied';
/** `guess`: placed by a source whose result was held; shown amber, never auto-started. */
export type Origin = { kind: 'auto' | 'guess' | 'you' | 'none'; source: string | null };
export interface EpisodeRow {
	trackId: string;
	ref: string;
	length: string;
	code: string;
	name: string;
	origin: Origin;
	confidence: number | null;
	proposed: { code: string; name: string; confidence: number | null } | null;
	changed: boolean;
	handSet: boolean;
	/** The track's saved season; null when none is set (never assumed). */
	season: number | null;
	seconds: number | null;
	/** Left out of the transcode output (the disc still rips in full). */
	excluded: boolean;
	/** The picker option that is this row's current placement ('' when none): a
	 * role value, or `s<season>e<episode>` as `pickerOptions` values them. */
	pickValue: string;
}

const RAN = new Set(['ok', 'miss', 'skipped', 'error']);
const NON_EPISODE: Record<string, string> = { extra: 'Extra', trailer: 'Trailer', other: 'Other' };
const ROLES = ['extra', 'trailer', 'other'] as const;

const pad = (n: number) => String(n).padStart(2, '0');

function episodeCode(
	season: number | null | undefined,
	ep: number | null | undefined,
	end?: number | null
): string | null {
	if (ep == null) return null;
	const span = end != null && end !== ep ? `-E${pad(end)}` : '';
	// A seasonless episode shows no season rather than an assumed one.
	return `S${season == null ? '-' : pad(season)}E${pad(ep)}${span}`;
}

export function formatLength(seconds: number | null | undefined): string {
	if (seconds == null) return '-';
	const m = Math.floor(seconds / 60);
	return `${m}:${pad(seconds % 60)}`;
}

export function failedSources(identity: IdentityView): { id: string; label: string; detail: string | null }[] {
	return Object.entries(identity.sources ?? {})
		.filter(([id, s]) => id.startsWith(EPISODE_PREFIX) && s?.status === 'error')
		.map(([id, s]) => ({ id, label: SOURCE_LABEL[id] ?? id, detail: s?.detail ?? null }));
}

export function panelState(job: JobView, identity: IdentityView | null, matching: boolean): PanelState {
	if (!job.has_series) return 'noseries';
	if (matching) return 'matching';
	const sources = identity?.sources ?? {};
	const ran = Object.entries(sources)
		.filter(([id, s]) => id.startsWith(EPISODE_PREFIX) && RAN.has(s?.status ?? 'ok'))
		.map(([, s]) => s);
	if (!identity) return 'unavailable';
	// Every episode source skipped as not configured: nothing can ever place
	// these tracks. No episode source at all (cleared, or not yet run) is a
	// plain no match, so Fix match is at hand.
	const configured = ran.filter((s) => !notConfigured(s));
	if (ran.length > 0 && configured.length === 0) return 'unavailable';
	if (!ran.some((s) => (s?.status ?? 'ok') === 'ok')) return 'nomatch';
	// The resolver's own word: the winning placement came from a held result.
	if (job.episodes_unsure) return 'unsure';
	return 'applied';
}

function origin(t: TrackIdentityView, identity: IdentityView, unsure: boolean): Origin {
	const prov = t.identity_provenance ?? {};
	if (Object.values(prov).includes('manual')) return { kind: 'you', source: null };
	const src = prov.episode_number ?? prov.role ?? null;
	if (src && src.startsWith(EPISODE_PREFIX)) {
		// The job's own flag decides: a source may be held while the job was resolved sure.
		return { kind: unsure && identity.sources?.[src]?.suggestion ? 'guess' : 'auto', source: src };
	}
	return { kind: 'none', source: null };
}

export function buildRows(
	tracks: TrackView[],
	identity: IdentityView,
	preview: MatchPreview | null,
	unsure = false
): EpisodeRow[] {
	const byTrack = new Map((identity.tracks ?? []).map((t) => [t.track_id, t]));
	const active = activeSource(identity);
	const matches = new Map((preview?.outcomes?.[0]?.matches ?? []).map((m) => [m.source_ref, m]));
	return tracks.map((track) => {
		const t = byTrack.get(track.id);
		const o: Origin = t ? origin(t, identity, unsure) : { kind: 'none', source: null };
		const proposal = t && active ? t.proposals?.[active] : undefined;
		let code: string | null = null;
		let name = '';
		if (t?.role && NON_EPISODE[t.role]) code = NON_EPISODE[t.role];
		if (!code && t) {
			code = episodeCode(t.season, t.episode_number, t.episode_number_end);
			name = t.episode_name ?? '';
		}
		const m = matches.get(track.source_ref);
		const proposed = m
			? {
					code: episodeCode(m.season, m.episode, m.episode_end) ?? 'Not placed',
					name: m.episode_name ?? '',
					confidence: m.confidence ?? null
				}
			: null;
		const current = code ?? 'Not placed';
		let pickValue = '';
		if (t?.role && NON_EPISODE[t.role]) pickValue = t.role;
		else if (t?.episode_number != null) pickValue = `s${t.season ?? 0}e${t.episode_number}`;
		return {
			trackId: track.id,
			ref: track.source_ref,
			length: formatLength(track.duration_seconds ?? track.expected_duration_seconds),
			code: current,
			name,
			origin: o,
			confidence: proposal?.confidence ?? null,
			proposed,
			changed: proposed !== null && proposed.code !== current,
			handSet: o.kind === 'you',
			season: t?.season ?? track.season ?? null,
			seconds: track.duration_seconds ?? track.expected_duration_seconds ?? null,
			excluded: track.excluded ?? false,
			pickValue
		};
	});
}

export const ROLE_OPTIONS = Object.entries(NON_EPISODE).map(([value, label]) => ({ value, label }));

/** The episode numbers the other tracks of a season already hold, a
 * two-part episode's whole span included: `pickerOptions` marks them
 * used. */
export function usedEpisodeNumbers(tracks: Iterable<TrackIdentityView>, season: number, trackId: string): Set<number> {
	const used = new Set<number>();
	for (const t of tracks) {
		if (t.track_id === trackId || t.season !== season || t.episode_number == null) continue;
		for (let n = t.episode_number; n <= (t.episode_number_end ?? t.episode_number); n++) used.add(n);
	}
	return used;
}

/** The by-hand choices for one track in one season: its episodes, closest
 * runtime to the track's length first (unknown runtimes last, ties by number),
 * the episodes other tracks already hold after the rest and marked used, then
 * the roles. A special (or any episode of season 0) is valued as season 0. */
export function pickerOptions(
	episodes: EpisodeSummary[],
	season: number,
	seconds: number | null,
	used: Set<number>
): { value: string; label: string }[] {
	const fit = (e: EpisodeSummary) =>
		seconds == null || e.runtime_s == null ? Infinity : Math.abs(e.runtime_s - seconds);
	const items = episodes.map((e) => {
		const special = !!e.special || season === 0;
		// A special in a regular season's list is numbered in season 0, so the
		// season's used numbers do not apply to it.
		const isUsed = (season === 0 || !e.special) && used.has(e.number);
		const code = special ? `S00E${pad(e.number)}` : `E${pad(e.number)}`;
		const parts = [[code, e.name].filter(Boolean).join(' ')];
		if (e.runtime_s != null) parts.push(`${Math.round(e.runtime_s / 60)}m`);
		if (special) parts.push('special');
		const label = parts.join(', ') + (isUsed ? ' (used)' : '');
		return { e, isUsed, value: `s${special ? 0 : season}e${e.number}`, label };
	});
	items.sort((a, b) => +a.isUsed - +b.isUsed || fit(a.e) - fit(b.e) || a.e.number - b.e.number);
	return [...items.map(({ value, label }) => ({ value, label })), ...ROLE_OPTIONS];
}

/** A picker value read back: a role, or an episode by its season and
 * number. */
export type HandPick = { role: (typeof ROLES)[number] } | { season: number; episode: number };

/** Reads a value `pickerOptions` gave back; null for any other value. */
export function parseHandPick(value: string): HandPick | null {
	const role = ROLES.find((r) => r === value);
	if (role) return { role };
	const m = /^s(\d+)e(\d+)$/.exec(value);
	if (!m) return null;
	return { season: Number(m[1]), episode: Number(m[2]) };
}

/** The name of the picked episode in its season's list, or null when
 * the list does not hold it. A pick in season 0 matches a special (or
 * any episode of a season 0 list), and only those. */
export function pickedEpisodeName(
	list: EpisodeSummary[],
	listSeason: number | null,
	season: number,
	episode: number
): string | null {
	return list.find((e) => e.number === episode && (!!e.special || listSeason === 0) === (season === 0))?.name ?? null;
}

/** Rows with a placement on the track: an episode (sure or a guess) or a
 * non-episode role, the same rule the Home card's Episodes row uses. */
export function placedCount(rows: EpisodeRow[]): number {
	return rows.filter((r) => r.code !== 'Not placed').length;
}
