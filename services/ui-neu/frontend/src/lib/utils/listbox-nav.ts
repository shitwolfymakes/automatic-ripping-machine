// Keyboard movement shared by the app's listboxes.

/** Target row for each navigation key, or null when focus stays. */
const MOVES: Record<string, (index: number, last: number) => number | null> = {
	ArrowDown: (index, last) => (index < last ? index + 1 : null),
	ArrowUp: (index) => (index > 0 ? index - 1 : null),
	Home: (_index, last) => (last >= 0 ? 0 : null),
	End: (_index, last) => (last >= 0 ? last : null)
};

/**
 * True for a key the listbox navigates with. The default of such a key is
 * always prevented, even when focus cannot move.
 */
export function isListboxNavKey(key: string): boolean {
	return Object.hasOwn(MOVES, key);
}

/**
 * The row a navigation key moves focus to in a list of `count` rows. Null when
 * focus stays: already at that end, an empty list, or not a navigation key.
 */
export function nextRowIndex(key: string, index: number, count: number): number | null {
	if (!isListboxNavKey(key)) return null;
	return MOVES[key](index, count - 1);
}
