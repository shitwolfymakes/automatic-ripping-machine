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
