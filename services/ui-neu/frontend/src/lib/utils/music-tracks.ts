export interface MusicTrackRow {
	number: number;
	title: string;
	durationLabel: string;
}

function msToLabel(ms: unknown): string {
	if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 1) return '—';
	const total = Math.round(ms / 1000);
	const m = Math.floor(total / 60);
	const s = total % 60;
	return `${m}:${String(s).padStart(2, '0')}`;
}

// metadata_json is provider-shaped and untyped; parse defensively.
export function extractMusicTracks(metadata: Record<string, unknown> | null | undefined): MusicTrackRow[] {
	const raw = metadata?.tracks;
	if (!Array.isArray(raw)) return [];
	return raw.map((t, i) => {
		const obj = (t ?? {}) as Record<string, unknown>;
		const title = typeof obj.title === 'string' && obj.title.trim() ? obj.title : `Track ${i + 1}`;
		return { number: i + 1, title, durationLabel: msToLabel(obj.duration_ms) };
	});
}
