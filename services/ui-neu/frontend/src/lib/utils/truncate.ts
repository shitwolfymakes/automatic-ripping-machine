/**
 * Middle-truncate a file name to at most `max` characters, keeping the start
 * and the end (so the extension and any disc-number suffix survive) and
 * collapsing the middle to "...". Used by IsoSourceChip for the 36-char
 * (desktop) / 26-char (mobile) ISO file name display.
 */
export function middleTruncate(name: string, max: number): string {
	if (name.length <= max) return name;
	const ellipsis = '...';
	const keep = Math.max(max - ellipsis.length, 0);
	const tailLen = Math.ceil(keep / 2);
	const headLen = keep - tailLen;
	return `${name.slice(0, headLen)}${ellipsis}${name.slice(name.length - tailLen)}`;
}

/**
 * Shorten a "/"-separated path to at most `max` characters by dropping
 * whole leading segments, so the end of the path (a box set's film, a disc
 * number) stays readable: ".../Extended (2001)/Fellowship". Falls back to
 * a plain cut from the left when the last segment alone doesn't fit. Used
 * by the "Rip from folder" list for a disc folder's parent path.
 */
export function pathTailTruncate(path: string, max: number): string {
	if (path.length <= max) return path;
	const ellipsis = '...';
	const segments = path.split('/');
	for (let i = 1; i < segments.length; i++) {
		const tail = `${ellipsis}/${segments.slice(i).join('/')}`;
		if (tail.length <= max) return tail;
	}
	return `${ellipsis}${path.slice(path.length - (max - ellipsis.length))}`;
}
