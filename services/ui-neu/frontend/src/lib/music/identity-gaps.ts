// What a CD not yet identified still lacks, as the job page says it.
import type { CdIdentityGaps } from '$lib/types/api.gen';

// "a", "a and b", "a, b and c".
function joinList(items: string[]): string {
	return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items[items.length - 1]}`;
}

/** The missing parts of a CD's identity as one phrase, e.g. "the artist and the title of track 4". */
export function cdIdentityMissing(gaps: CdIdentityGaps): string {
	const parts: string[] = [];
	if (gaps.album) parts.push('the album');
	if (gaps.artist) parts.push('the artist');
	const tracks = gaps.untitled_tracks.map(String);
	if (tracks.length === 1) parts.push(`the title of track ${tracks[0]}`);
	else if (tracks.length > 1) parts.push(`titles for tracks ${joinList(tracks)}`);
	return joinList(parts);
}
