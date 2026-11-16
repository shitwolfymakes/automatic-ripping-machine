// Site storage that copes with a browser blocking it. When localStorage
// throws (site data blocked, a locked-down browser), each value is kept in
// memory instead, so it lasts for this page load.

const memory = new Map<string, string>();

/** The stored value, or null when there is none. */
export function readStorage(key: string): string | null {
	try {
		return localStorage.getItem(key);
	} catch {
		return memory.get(key) ?? null;
	}
}

/** Stores the value. */
export function writeStorage(key: string, value: string): void {
	try {
		localStorage.setItem(key, value);
	} catch {
		memory.set(key, value);
	}
}

/** Removes the value. */
export function removeStorage(key: string): void {
	memory.delete(key);
	try {
		localStorage.removeItem(key);
	} catch {
		/* storage unavailable: the in-memory copy is already gone */
	}
}
