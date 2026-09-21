export type MatchKind = 'match' | 'close' | 'mismatch' | 'unknown';

// Compare a MusicBrainz track length (ms) to a disc track's scanned length (s).
// ≤3s → match, ≤10s → close, else mismatch; null/undefined either side → unknown.
export function matchIndicator(
	releaseLenMs: number | null | undefined,
	discLenSec: number | null | undefined
): MatchKind {
	if (releaseLenMs == null || discLenSec == null) return 'unknown';
	const diff = Math.abs(releaseLenMs / 1000 - discLenSec);
	if (diff <= 3) return 'match';
	if (diff <= 10) return 'close';
	return 'mismatch';
}
