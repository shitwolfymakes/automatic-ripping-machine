import type {
	EpisodeSummary,
	IdentityView,
	JobView,
	MatchPreview,
	TrackIdentityView,
	TrackView
} from '$lib/types/api.gen';

export type PanelState = 'noseries' | 'matching' | 'unavailable' | 'nomatch' | 'suggestion' | 'pinned' | 'applied';
export type Origin = { kind: 'auto' | 'suggestion' | 'you' | 'none'; source: string | null };
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
 * non-suggestion source (the resolver skips unpinned suggestions), then the
 * first ok suggestion (shown as a suggestion). */
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
	if (!identity || ran.length === 0) return 'unavailable';
	if (identity.pin?.episode) return 'pinned';
	const active = activeSource(identity);
	if (active && sources[active]?.suggestion) return 'suggestion';
	if (!ran.some((s) => (s?.status ?? 'ok') === 'ok')) return 'nomatch';
	return 'applied';
}

function origin(t: TrackIdentityView, identity: IdentityView): Origin {
	const prov = t.identity_provenance ?? {};
	if (Object.values(prov).includes('manual')) return { kind: 'you', source: null };
	const src = prov.episode_number ?? prov.role ?? null;
	if (src && src.startsWith(EPISODE_PREFIX)) {
		return { kind: identity.sources?.[src]?.suggestion ? 'suggestion' : 'auto', source: src };
	}
	return { kind: 'none', source: null };
}

export function buildRows(tracks: TrackView[], identity: IdentityView, preview: MatchPreview | null): EpisodeRow[] {
	const byTrack = new Map((identity.tracks ?? []).map((t) => [t.track_id, t]));
	const active = activeSource(identity);
	const matches = new Map((preview?.outcomes?.[0]?.matches ?? []).map((m) => [m.source_ref, m]));
	return tracks.map((track) => {
		const t = byTrack.get(track.id);
		const o: Origin = t ? origin(t, identity) : { kind: 'none', source: null };
		const proposal = t && active ? t.proposals?.[active] : undefined;
		let code: string | null = null;
		let name = '';
		if (t?.role && NON_EPISODE[t.role]) code = NON_EPISODE[t.role];
		if (!code && t) {
			code = episodeCode(t.season, t.episode_number, t.episode_number_end);
			name = t.episode_name ?? '';
		}
		if (!code && proposal && active && o.kind !== 'you' && identity.sources?.[active]?.suggestion) {
			code = episodeCode(proposal.season, proposal.episode, proposal.episode_end);
			name = proposal.episode_name ?? '';
			o.kind = 'suggestion';
			o.source = active;
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
		return {
			trackId: track.id,
			ref: track.source_ref,
			length: formatLength(track.duration_seconds),
			code: current,
			name,
			origin: o,
			confidence: proposal?.confidence ?? null,
			proposed,
			changed: proposed !== null && proposed.code !== current,
			handSet: o.kind === 'you',
			season: t?.season ?? track.season ?? null,
			seconds: track.duration_seconds ?? null
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
