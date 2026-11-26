import type { SessionRouteUpsert, SessionRouteView } from '$lib/types/api.gen';
import { get, del, apiFetch } from './client';

export function fetchSessionRoutes(): Promise<SessionRouteView[]> {
	return get<SessionRouteView[]>('/api/session-routes');
}

export function upsertSessionRoute(body: SessionRouteUpsert): Promise<SessionRouteView> {
	return apiFetch<SessionRouteView>('/api/session-routes', {
		method: 'PUT',
		body: JSON.stringify(body)
	});
}

export function deleteSessionRoute(routeId: string): Promise<void> {
	return del(`/api/session-routes/${routeId}`);
}
