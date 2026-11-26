/**
 * The message of a caught value: an Error's own message, otherwise the
 * caller's fallback text. Each call site passes the wording it already used.
 */
export function errorMessage(e: unknown, fallback: string): string {
	return e instanceof Error ? e.message : fallback;
}
