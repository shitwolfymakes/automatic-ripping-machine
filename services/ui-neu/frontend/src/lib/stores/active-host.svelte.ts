// Selected-host tab state for the per-container stats panels. Backend host is
// preferred as the default; if the selected host drops out of the live list,
// the reader resets to the first available host (see resolveActiveHost).

let selected = $state<string | null>(null);

export function setActiveHost(hostname: string): void {
	selected = hostname;
}

/** Given the live host list, return the hostname to render:
 *  the current selection if still present, else the first host (backend-first
 *  ordering is the caller's responsibility), else null. Resets the stored
 *  selection when it has gone stale. */
export function resolveActiveHost(hostnames: string[]): string | null {
	if (selected && hostnames.includes(selected)) return selected;
	selected = hostnames[0] ?? null;
	return selected;
}
