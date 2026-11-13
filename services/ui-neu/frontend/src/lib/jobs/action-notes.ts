// Wording of the transient note the job page flashes after an identify
// (resolve) or an apply-session lands. Pure: the page decides when to flash.
import type { ApplySessionResponse, ResolveResponse } from '$lib/types/api.gen';
import { plural } from '$lib/utils/plural';

// "N sessions resumed" when the resolve fanned out to any sessions, else null.
export function identifyNote(resp: ResolveResponse): string | null {
	if (!resp.fan_out?.length) return null;
	const n = resp.fan_out.length;
	return `${n} ${plural(n, 'session')} resumed`;
}

export function applyNote(resp: ApplySessionResponse, postRip: boolean): string {
	if (resp.session_application?.status === 'waiting_identify') {
		// Pre-rip applies park until rip-complete. A post-rip park (identity
		// still pending, or no title resolved an output) has no such
		// promise; the skip reason is not persisted, so just say waiting.
		return postRip ? 'Session parked; waiting' : 'Session parked; applies when the rip finishes';
	}
	const n = resp.tasks?.length ?? 0;
	return `${n} transcode ${plural(n, 'task')} queued`;
}
