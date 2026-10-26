import type {
	EpisodeSummary,
	IdentityView,
	JobView,
	MatchPreview,
	TrackIdentityView,
	TrackView
} from '$lib/types/api.gen';

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

/** The Re-run form. An empty season or disc is null (unknown); a season of
 * 'scan' asks the source to try every season. */
export interface RerunForm {
	source: 'tmdb' | 'tvmaze' | 'tvdb';
	season: number | 'scan' | null;
	disc: number | null;
	/** Empty means the backend's default. */
	tolerance: number | null;
}

export const SOURCE_LABEL: Record<string, string> = {
	episodes_tmdb: 'TMDb',
	episodes_tvmaze: 'TVmaze',
	episodes_tvdb: 'TVDB'
};
const EPISODE_PREFIX = 'episodes_';
const RAN = new Set(['ok', 'miss', 'skipped', 'error']);
const NON_EPISODE: Record<string, string> = { extra: 'Extra', trailer: 'Trailer', other: 'Other' };

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

/** The episode source the resolver applied, in its order: the pin, then the
 * source the tracks' provenance names (what actually won), then the first ok
 * clean source, then the first ok held source (applied as a guess). */
export function activeSource(identity: IdentityView): string | null {
	const pinned = identity.pin?.episode;
	if (pinned) return pinned.startsWith(EPISODE_PREFIX) ? pinned : `${EPISODE_PREFIX}${pinned}`;
	const sources = identity.sources ?? {};
	const ok = Object.keys(sources).filter((id) => id.startsWith(EPISODE_PREFIX) && sources[id]?.status === 'ok');
	const counts = new Map<string, number>();
	for (const t of identity.tracks ?? []) {
		for (const src of Object.values(t.identity_provenance ?? {})) {
			if (ok.includes(src)) counts.set(src, (counts.get(src) ?? 0) + 1);
		}
	}
	let applied: string | null = null;
	for (const [src, n] of counts) if (applied === null || n > (counts.get(applied) ?? 0)) applied = src;
	return applied ?? ok.find((id) => !sources[id]?.suggestion) ?? ok[0] ?? null;
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
	const configured = ran.filter((s) => !(s?.status === 'skipped' && /not configured/i.test(s?.detail ?? '')));
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

/** Rows with a placement on the track: an episode (sure or a guess) or a
 * non-episode role, the same rule the Home card's Episodes row uses. */
export function placedCount(rows: EpisodeRow[]): number {
	return rows.filter((r) => r.code !== 'Not placed').length;
}

/** Why a held (suggestion) result was not applied, by the backend's
 * `extra.hold_reasons` code (design spec 2026-10-23 section 4.2 E). */
export const HOLD_REASON_TEXT: Record<string, string> = {
	ambiguous: 'The titles fit equally well one episode earlier or later.',
	near_tie: 'Another season fits about as well.',
	low_coverage: 'Fewer than half the titles found an episode.',
	low_confidence: 'The runtimes are a loose fit.',
	thin_win: 'The best season wins by a thin margin.',
	nominal_runtimes: 'The source lists rounded runtimes, not real ones.',
	sibling_conflict: 'Another disc of this season already holds some of these episodes, or its disc number is unknown.',
	auto_apply_off: 'Automatic apply is off in Settings.'
};

export interface SeasonCandidate {
	season: number;
	matches: number;
	total: number;
}

export function holdReasons(identity: IdentityView, source: string | null): string[] {
	const codes = source ? identity.sources?.[source]?.extra?.hold_reasons : null;
	if (!Array.isArray(codes)) return [];
	return codes.map((c) => HOLD_REASON_TEXT[String(c)]).filter((t): t is string => !!t);
}

/** The one-line reading of a held result: the season the source guessed and
 * its strongest reason, with the other reasons kept for a disclosure. */
export function holdHeadline(
	identity: IdentityView,
	source: string | null,
	season: number | null
): { line: string; more: string[] } {
	const reasons = holdReasons(identity, source);
	const subject = season == null ? 'This match' : season === 0 ? 'Specials' : `Season ${season}`;
	const [first, ...more] = reasons;
	const line = first
		? `${subject} is a guess: ${first.charAt(0).toLowerCase()}${first.slice(1)}`
		: `${subject} is a guess.`;
	return { line, more };
}

/** The other seasons the source's scan found a fit in, best first. Each
 * total is the number of titles that season was matched over (its matches
 * over its coverage); `fallback` stands in when the coverage is unknown. */
export function seasonAlternatives(identity: IdentityView, source: string | null, fallback = 0): SeasonCandidate[] {
	const alts = source ? (identity.sources?.[source]?.alternatives ?? []) : [];
	return alts
		.filter((a) => typeof a.season === 'number')
		.map((a) => {
			const matches = Number(a.matches ?? 0);
			const coverage = Number(a.coverage ?? 0);
			const total = coverage > 0 ? Math.round(matches / coverage) : fallback;
			return { season: a.season as number, matches, total };
		});
}

/** The season the source's own (held) result placed the tracks in, by its
 * per-track proposals; null when it proposed no episode. */
export function heldSeason(identity: IdentityView, source: string | null, total = 0): SeasonCandidate | null {
	if (!source) return null;
	const counts = new Map<number, number>();
	for (const t of identity.tracks ?? []) {
		const p = t.proposals?.[source];
		if (p?.season != null && p.episode != null) counts.set(p.season, (counts.get(p.season) ?? 0) + 1);
	}
	let best: SeasonCandidate | null = null;
	for (const [season, matches] of counts) if (!best || matches > best.matches) best = { season, matches, total };
	return best;
}
