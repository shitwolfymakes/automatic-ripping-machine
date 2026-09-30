/** Change detection for a schema-driven config form (SchemaConfigForm.svelte).
 *  A ranked/string[] field's value is an array, and Svelte's $state deep-
 *  proxies it, so an untouched value is never === its raw counterpart in the
 *  saved config - compare arrays element by element instead. Every other
 *  field type stays primitive (string/number/boolean), where === already
 *  means unchanged. */
export function unchanged(a: unknown, b: unknown): boolean {
	if (Array.isArray(a) && Array.isArray(b)) {
		return a.length === b.length && a.every((v, i) => v === b[i]);
	}
	return a === b;
}
