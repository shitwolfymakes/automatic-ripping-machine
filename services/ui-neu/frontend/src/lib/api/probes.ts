// Anonymous probes, made with raw fetch so the API client's 401 handler
// never fires for them.

type GuestProbe = 'open' | 'closed' | 'unknown';

// One cheap guest-readable GET: ok = guest access is open, 401 = closed,
// any other status or an unreachable backend = unknown.
export async function probeGuestAccess(fetchFn: typeof fetch): Promise<GuestProbe> {
	try {
		const resp = await fetchFn('/api/system/version');
		if (resp.ok) return 'open';
		return resp.status === 401 ? 'closed' : 'unknown';
	} catch {
		return 'unknown';
	}
}

// Whether setup is unfinished; null when the backend could not say.
export async function probeFirstRun(fetchFn: typeof fetch): Promise<boolean | null> {
	try {
		const resp = await fetchFn('/api/setup/status');
		if (!resp.ok) return null;
		return (await resp.json()).first_run === true;
	} catch {
		return null;
	}
}
