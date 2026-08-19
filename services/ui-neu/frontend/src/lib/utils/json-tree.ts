export type JsonKind = 'object' | 'array' | 'string' | 'number' | 'boolean' | 'null';

export interface JsonEntry {
	key: string;
	value: unknown;
}

export interface ClassifiedJson {
	kind: JsonKind;
	isContainer: boolean;
	preview: string;
	entries: JsonEntry[];
}

/**
 * Describe any JSON value for the tree viewer: its kind, whether it has a
 * disclosure row (non-empty object/array), a collapsed-summary preview, and
 * its child entries (object pairs, or array index/value pairs). Scalars and
 * empty containers have no entries. Never throws; `undefined` (not valid JSON)
 * is treated as null defensively.
 */
export function classifyJsonValue(value: unknown): ClassifiedJson {
	if (value === null || value === undefined) {
		return { kind: 'null', isContainer: false, preview: 'null', entries: [] };
	}
	if (Array.isArray(value)) {
		const entries: JsonEntry[] = value.map((item, i) => ({ key: String(i), value: item }));
		return {
			kind: 'array',
			isContainer: entries.length > 0,
			preview: entries.length > 0 ? `[${entries.length}]` : '[]',
			entries
		};
	}
	if (typeof value === 'object') {
		const entries: JsonEntry[] = Object.entries(value as Record<string, unknown>).map(
			([key, v]) => ({ key, value: v })
		);
		return {
			kind: 'object',
			isContainer: entries.length > 0,
			preview: entries.length > 0 ? '{…}' : '{}',
			entries
		};
	}
	if (typeof value === 'number') {
		return { kind: 'number', isContainer: false, preview: String(value), entries: [] };
	}
	if (typeof value === 'boolean') {
		return { kind: 'boolean', isContainer: false, preview: value ? 'true' : 'false', entries: [] };
	}
	// string (and any other primitive) → rendered as-is
	return { kind: 'string', isContainer: false, preview: String(value), entries: [] };
}
