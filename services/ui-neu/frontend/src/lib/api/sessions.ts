import type { SessionView } from '$lib/types/api.gen';
import { get } from './client';

// Read-only for Tier 1 (the apply-session picker). Full CRUD = Tier 2.
export function fetchSessions(): Promise<SessionView[]> {
	return get<SessionView[]>('/api/sessions');
}
