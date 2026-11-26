// Reading the output-path collisions out of a session apply the server
// refused with a 409.
import { ApiError } from '$lib/api/client';
import type { CollisionInfo } from '$lib/types/api.gen';

/** The 409 body's `detail.collisions`, or null for any other error. */
export function collisionsFromApplyError(e: unknown): CollisionInfo[] | null {
	if (e instanceof ApiError && e.status === 409 && e.body && typeof e.body === 'object') {
		const detail = (e.body as { detail?: { collisions?: CollisionInfo[] } }).detail;
		if (detail?.collisions) {
			return detail.collisions;
		}
	}
	return null;
}
