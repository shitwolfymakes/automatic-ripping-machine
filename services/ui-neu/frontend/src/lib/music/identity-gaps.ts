// What a CD not yet identified still lacks, as the job page says it.
import type { CdIdentityGaps } from '$lib/types/api.gen';

/** The missing parts of a CD's identity as one phrase: "the album", "the artist" or both. */
export function cdIdentityMissing(gaps: CdIdentityGaps): string {
	const parts: string[] = [];
	if (gaps.album) parts.push('the album');
	if (gaps.artist) parts.push('the artist');
	return parts.join(' and ');
}
