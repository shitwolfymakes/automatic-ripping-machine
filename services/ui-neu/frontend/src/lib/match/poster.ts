export const POSTER_PLACEHOLDER = '/img/poster-placeholder.svg';

/**
 * The poster a job should display: the operator's manual override wins over the
 * auto-identified URL. Use everywhere a job's poster is rendered so a manually
 * applied poster (TMDB/OMDb/MusicBrainz) shows on cards, rows, and detail —
 * not just inside the review widget.
 */
export function jobPoster(
	job: { poster_url?: string | null; poster_url_manual?: string | null } | null | undefined
): string | null {
	return job?.poster_url_manual ?? job?.poster_url ?? null;
}

/**
 * Proxy an external poster URL through the backend to avoid browser
 * ORB/CORS blocking (Firefox blocks m.media-amazon.com images on HTTP origins).
 * Returns placeholder for empty/null URLs.
 */
export function posterSrc(url: string | null | undefined): string {
	if (!url) return POSTER_PLACEHOLDER;
	// Only proxy external URLs — local/relative paths don't need it
	if (!url.startsWith('http://') && !url.startsWith('https://')) return url;
	return `/api/images/proxy?url=${encodeURIComponent(url)}`;
}

/** Use as onerror handler on <img> to swap broken images to placeholder */
export function posterFallback(event: Event) {
	const img = event.target as HTMLImageElement;
	if (img.src !== POSTER_PLACEHOLDER && !img.src.endsWith('poster-placeholder.svg')) {
		img.src = POSTER_PLACEHOLDER;
	}
}
