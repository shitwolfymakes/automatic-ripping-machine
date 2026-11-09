// Path string helpers.

/**
 * The last segment of a path once trailing slashes are dropped.
 * Returns '' for a missing or empty path.
 */
export function pathBasename(path: string | null | undefined): string {
	if (!path) return '';
	const parts = path.replace(/\/+$/, '').split('/');
	return parts[parts.length - 1] ?? '';
}
