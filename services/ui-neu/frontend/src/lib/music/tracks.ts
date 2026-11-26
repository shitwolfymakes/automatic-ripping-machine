export interface MusicTrackRow {
	number: number;
	title: string;
	/** The stored title, '' when missing (`title` shows `Track N` then). */
	rawTitle: string;
	durationLabel: string;
}

function msToLabel(ms: unknown): string {
	if (typeof ms !== 'number' || !Number.isFinite(ms) || ms < 1) return '-';
	const total = Math.round(ms / 1000);
	const m = Math.floor(total / 60);
	const s = total % 60;
	return `${m}:${String(s).padStart(2, '0')}`;
}

// metadata_json is the typed JobMetadata bag; tracks live under music.tracks[].
// Rows past the stored list, up to `minCount`, are blank (a CD's scanned
// tracks that have no title yet).
export function extractMusicTracks(
	metadata: Record<string, unknown> | null | undefined,
	minCount = 0
): MusicTrackRow[] {
	const music = metadata?.music;
	const isRecord = !!music && typeof music === 'object' && !Array.isArray(music);
	const raw = isRecord ? (music as Record<string, unknown>).tracks : undefined;
	const stored = Array.isArray(raw) ? raw : [];
	const rows = stored.map((t, i) => {
		const obj = (t ?? {}) as Record<string, unknown>;
		const rawTitle = typeof obj.title === 'string' ? obj.title : '';
		const title = rawTitle.trim() ? rawTitle : `Track ${i + 1}`;
		return { number: i + 1, title, rawTitle, durationLabel: msToLabel(obj.length_ms) };
	});
	for (let n = rows.length + 1; n <= minCount; n++) {
		rows.push({ number: n, title: `Track ${n}`, rawTitle: '', durationLabel: '-' });
	}
	return rows;
}
