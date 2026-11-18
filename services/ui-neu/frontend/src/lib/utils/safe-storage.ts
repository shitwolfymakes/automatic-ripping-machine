// Site storage that copes with a browser blocking it or running out of room.
// When a write to localStorage throws (site data blocked, a locked-down
// browser, the quota full), the value is kept in memory instead, so it lasts
// for this page load, and reads look in memory first so it wins over any
// older stored copy.

const memory = new Map<string, string>();

/** The stored value, or null when there is none. */
export function readStorage(key: string): string | null {
	const kept = memory.get(key);
	if (kept !== undefined) return kept;
	try {
		return localStorage.getItem(key);
	} catch {
		return null;
	}
}

/** Stores the value. */
export function writeStorage(key: string, value: string): void {
	try {
		localStorage.setItem(key, value);
		memory.delete(key);
	} catch {
		memory.set(key, value);
		dropStored(key);
	}
}

/** Removes the stored copy after a failed write, so a reload cannot bring the older value back. */
function dropStored(key: string): void {
	try {
		localStorage.removeItem(key);
	} catch {
		/* storage unavailable: there is no stored copy to bring back */
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
