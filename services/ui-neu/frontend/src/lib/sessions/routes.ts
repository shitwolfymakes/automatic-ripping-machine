// Settings > Session Routing's grid: its media and disc rows, and the rules
// that pick a row's route and the sessions it may offer.
import type { DiscType, MediaType, SessionRouteView, SessionView } from '$lib/types/api.gen';
import { humanizeMediaType } from '$lib/sessions/preset-labels';
import { mediaTypesCompatible } from '$lib/sessions/sessions';

/** The grid's media-type rows, in display order. */
export const MEDIA_TYPES: Array<{ key: MediaType; label: string }> = [
	{ key: 'movie', label: 'Movie' },
	{ key: 'tv', label: 'TV' },
	{ key: 'music', label: 'Music' },
	{ key: 'data', label: 'Data' }
];

/** The grid's disc-scope columns. A null disc_type is the "Any disc"
 * wildcard row for its media type, and comes first. */
export const DISC_SCOPES: Array<{ key: DiscType | null; label: string }> = [
	{ key: null, label: 'Any disc' },
	{ key: 'dvd', label: 'DVD' },
	{ key: 'bluray', label: 'Blu-ray' },
	{ key: 'cd', label: 'CD' }
];

// A route is grid-covered when both its media_type and disc_type appear
// among the fixed 4x4 grid's rows/columns. Anything else (media_type=iso,
// or disc_type=data/unknown) is creatable via the API and wins resolution
// (resolve_routed_session_id), but has no cell in the grid to render in;
// it must still be visible and clearable here, or it's silently stuck.
const GRID_MEDIA_TYPES = new Set(MEDIA_TYPES.map((mt) => mt.key));
const GRID_DISC_TYPES = new Set(DISC_SCOPES.map((s) => s.key));

function isGridCovered(route: SessionRouteView): boolean {
	return GRID_MEDIA_TYPES.has(route.media_type) && GRID_DISC_TYPES.has(route.disc_type);
}

/** The key that names one grid row, "any" standing for the wildcard. */
export function rowKey(mediaType: MediaType, discType: DiscType | null): string {
	return `${mediaType}/${discType ?? 'any'}`;
}

/** The stored route for a media and disc type, if there is one. */
export function routeFor(
	routes: readonly SessionRouteView[],
	mediaType: MediaType,
	discType: DiscType | null
): SessionRouteView | undefined {
	return routes.find((r) => r.media_type === mediaType && r.disc_type === discType);
}

/** The routes with `saved` in place of any route for the same media
 * and disc type, added last. */
export function withRoute(
	routes: readonly SessionRouteView[],
	mediaType: MediaType,
	discType: DiscType | null,
	saved: SessionRouteView
): SessionRouteView[] {
	const others = routes.filter((r) => !(r.media_type === mediaType && r.disc_type === discType));
	return [...others, saved];
}

/** Every session the Backend would accept for this row (same compatibility
 * rule as PUT /api/session-routes), plus the one already routed, so a live
 * route never renders as a blank select. */
export function sessionsFor(
	sessions: readonly SessionView[],
	mediaType: MediaType,
	route: SessionRouteView | undefined
): SessionView[] {
	const options = sessions.filter((s) => mediaTypesCompatible(mediaType, s.media_type));
	if (route && !options.some((s) => s.id === route.session_id)) {
		const routed = sessions.find((s) => s.id === route.session_id);
		if (routed) options.unshift(routed);
	}
	return options;
}

/** The routes that have no cell in the grid. */
export function otherRoutes(routes: readonly SessionRouteView[]): SessionRouteView[] {
	return routes.filter((r) => !isGridCovered(r));
}

/** A session's name, or the id itself when the session is gone. */
export function sessionNameFor(sessions: readonly SessionView[], sessionId: string): string {
	return sessions.find((s) => s.id === sessionId)?.name ?? sessionId;
}

/** A disc type as itself, or "Any disc" for the wildcard. */
export function discLabel(discType: DiscType | null): string {
	return discType ?? 'Any disc';
}

interface RouteCellView {
	value: string;
	className: string;
	disabled: boolean;
}

/** How one grid cell renders: the routed session id ("" for None), the class
 * that marks it set or empty, and whether it is locked (not an admin, the
 * row in flight, or no session on offer). */
export function routeCellView(
	route: SessionRouteView | undefined,
	optionCount: number,
	pending: boolean,
	isAdmin: boolean
): RouteCellView {
	return {
		value: route?.session_id ?? '',
		className: `routing-cell ${route ? 'routing-cell-set' : 'routing-cell-empty'}`,
		disabled: !isAdmin || pending || optionCount === 0
	};
}

/** The label of an option in a cell's select. */
export function sessionOptionLabel(session: SessionView): string {
	return `${session.name ?? ''}${session.is_builtin ? ' (built-in)' : ''}`;
}

interface OtherRouteView {
	label: string;
	name: string;
}

/** An Other-routes row: the "Media / Disc" label and the routed session's name. */
export function otherRouteView(route: SessionRouteView, sessions: readonly SessionView[]): OtherRouteView {
	return {
		label: `${humanizeMediaType(route.media_type)} / ${discLabel(route.disc_type)}`,
		name: sessionNameFor(sessions, route.session_id)
	};
}
