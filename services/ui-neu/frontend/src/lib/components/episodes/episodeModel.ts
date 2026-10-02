import type { IdentityView, JobView, MatchPreview, TrackIdentityView, TrackView } from '$lib/types/api.gen';

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
	return `S${pad(season ?? 1)}E${pad(ep)}${span}`;
}

export function formatLength(seconds: number | null | undefined): string {
	if (seconds == null) return '—';
	const m = Math.floor(seconds / 60);
	return `${m}:${pad(seconds % 60)}`;
}

export function activeSource(identity: IdentityView): string | null {
	const pinned = identity.pin?.episode;
	if (pinned) return pinned.startsWith(EPISODE_PREFIX) ? pinned : `${EPISODE_PREFIX}${pinned}`;
	const sources = identity.sources ?? {};
	return Object.keys(sources).find((id) => id.startsWith(EPISODE_PREFIX) && sources[id]?.status === 'ok') ?? null;
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
	const src = prov.episode_number ?? prov.role ?? null;
	if (src === 'manual') return { kind: 'you', source: null };
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
		if (!code && proposal && o.kind !== 'you' && identity.sources?.[active ?? '']?.suggestion) {
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
			handSet: o.kind === 'you'
		};
	});
}

export function placedCount(rows: EpisodeRow[]): number {
	return rows.filter((r) => r.code !== 'Not placed').length;
}
