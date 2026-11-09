// Path string helpers.

/**
 * The last segment of a path once trailing slashes are dropped.
 * Returns '' for a missing or empty path.
 */
export function pathBasename(path: string | null | undefined): string {
	if (!path) return '';
	return path.split('/').findLast(Boolean) ?? '';
}

/**
 * Each non-empty segment of a slash-separated path, paired with the path up
 * to and including it ('a/b' gives a -> 'a', b -> 'a/b'). Empty segments
 * (leading, trailing or doubled slashes) are dropped. '' gives [].
 */
export function pathTrail(path: string): { label: string; path: string }[] {
	const trail: { label: string; path: string }[] = [];
	let accumulated = '';
	for (const label of path.split('/').filter(Boolean)) {
		accumulated = accumulated ? `${accumulated}/${label}` : label;
		trail.push({ label, path: accumulated });
	}
	return trail;
}
