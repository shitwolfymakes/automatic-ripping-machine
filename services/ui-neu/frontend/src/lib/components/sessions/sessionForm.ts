// What the session builder makes of its form: the overrides field read
// as JSON.

/** The overrides field's value: null when it is blank, its JSON
 * otherwise. Throws a SyntaxError when the text is not JSON. */
export function parseOverrides(text: string): Record<string, unknown> | null {
	return text.trim() ? JSON.parse(text) : null;
}
