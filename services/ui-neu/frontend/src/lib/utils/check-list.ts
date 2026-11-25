// The rules behind a set field in Settings: a list of checkboxes whose value
// is the ticked entries, always in the field's own order.

/** The known entries that are ticked, in the field's own order. Anything
 *  that is not a list ticks nothing. */
export function checkedEntries(value: unknown, known: readonly string[]): string[] {
	return Array.isArray(value) ? known.filter((v) => (value as unknown[]).includes(v)) : [];
}

/** The ticked entries after `entry` is ticked (`on`) or unticked, in the
 *  field's own order. */
export function setChecked(value: unknown, known: readonly string[], entry: string, on: boolean): string[] {
	const ticked = checkedEntries(value, known);
	return known.filter((v) => (v === entry ? on : ticked.includes(v)));
}
