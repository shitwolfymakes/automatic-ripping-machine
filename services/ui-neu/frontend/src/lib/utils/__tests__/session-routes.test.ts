import { describe, it, expect } from 'vitest';
import type { SessionRouteView, SessionView } from '$lib/types/api.gen';
import {
	DISC_SCOPES,
	MEDIA_TYPES,
	discLabel,
	otherRouteView,
	otherRoutes,
	routeCellView,
	routeFor,
	rowKey,
	sessionNameFor,
	sessionOptionLabel,
	sessionsFor,
	withRoute
} from '../session-routes';

function route(over: Partial<SessionRouteView>): SessionRouteView {
	return {
		id: 'r1',
		media_type: 'movie',
		disc_type: 'dvd',
		session_id: 's1',
		created_at: null,
		updated_at: null,
		...over
	};
}

function session(over: Partial<SessionView>): SessionView {
	return { id: 's1', name: 'Movie session', media_type: 'movie', ...over } as SessionView;
}

describe('MEDIA_TYPES', () => {
	it('lists the four media types', () => {
		expect(MEDIA_TYPES.map((m) => m.key)).toEqual(['movie', 'tv', 'music', 'data']);
	});
});

describe('DISC_SCOPES', () => {
	it('lists four scopes, the Any disc wildcard first', () => {
		expect(DISC_SCOPES).toHaveLength(4);
		expect(DISC_SCOPES[0]).toEqual({ key: null, label: 'Any disc' });
	});
});

describe('rowKey', () => {
	it('joins the media and disc type', () => {
		expect(rowKey('movie', 'dvd')).toBe('movie/dvd');
	});

	it('names a null disc type any', () => {
		expect(rowKey('tv', null)).toBe('tv/any');
	});
});

describe('routeFor', () => {
	const routes = [route({ id: 'a' }), route({ id: 'b', disc_type: null })];

	it('finds the route for a media and disc type', () => {
		expect(routeFor(routes, 'movie', 'dvd')?.id).toBe('a');
	});

	it('finds a wildcard route', () => {
		expect(routeFor(routes, 'movie', null)?.id).toBe('b');
	});

	it('returns undefined when there is none', () => {
		expect(routeFor(routes, 'tv', 'dvd')).toBeUndefined();
	});
});

describe('withRoute', () => {
	it('puts the saved route last in place of the one for its row', () => {
		const old = route({ id: 'old' });
		const other = route({ id: 'other', media_type: 'tv' });
		const saved = route({ id: 'new', session_id: 's2' });
		expect(withRoute([old, other], 'movie', 'dvd', saved)).toEqual([other, saved]);
	});

	it('keeps the other routes in order, the wildcard included', () => {
		const a = route({ id: 'a', disc_type: null });
		const old = route({ id: 'old' });
		const b = route({ id: 'b', disc_type: 'bluray' });
		const saved = route({ id: 'new' });
		expect(withRoute([a, old, b], 'movie', 'dvd', saved)).toEqual([a, b, saved]);
	});

	it('just adds the saved route when its row had none', () => {
		const a = route({ id: 'a', media_type: 'tv' });
		const saved = route({ id: 'new' });
		expect(withRoute([a], 'movie', 'dvd', saved)).toEqual([a, saved]);
	});
});

describe('sessionsFor', () => {
	const movie = session({ id: 'm', media_type: 'movie' });
	const music = session({ id: 'c', media_type: 'music' });

	it('offers the compatible sessions only', () => {
		expect(sessionsFor([movie, music], 'movie', undefined)).toEqual([movie]);
	});

	it('puts the routed session first when it is not compatible', () => {
		const result = sessionsFor([movie, music], 'movie', route({ session_id: 'c' }));
		expect(result.map((s) => s.id)).toEqual(['c', 'm']);
	});

	it('adds nothing when the routed session is already offered', () => {
		const result = sessionsFor([movie, music], 'movie', route({ session_id: 'm' }));
		expect(result).toEqual([movie]);
	});

	it('adds nothing when the routed session no longer exists', () => {
		const result = sessionsFor([movie, music], 'movie', route({ session_id: 'gone' }));
		expect(result).toEqual([movie]);
	});
});

describe('otherRoutes', () => {
	it('keeps routes with no grid cell and drops grid-covered ones', () => {
		const covered = route({ id: 'a' });
		const wildcard = route({ id: 'b', disc_type: null });
		const iso = route({ id: 'c', media_type: 'iso' });
		const data = route({ id: 'd', disc_type: 'data' });
		expect(otherRoutes([covered, wildcard, iso, data]).map((r) => r.id)).toEqual(['c', 'd']);
	});
});

describe('sessionNameFor', () => {
	it("returns a session's name", () => {
		expect(sessionNameFor([session({ id: 'x', name: 'Named' })], 'x')).toBe('Named');
	});

	it('returns the id itself for a session that no longer exists', () => {
		expect(sessionNameFor([], 'gone')).toBe('gone');
	});
});

describe('discLabel', () => {
	it('returns a disc type as itself', () => {
		expect(discLabel('bluray')).toBe('bluray');
	});

	it('labels null as Any disc', () => {
		expect(discLabel(null)).toBe('Any disc');
	});
});

describe('routeCellView', () => {
	it('is the set class, the session id and enabled for an admin with a route', () => {
		expect(routeCellView(route({}), 2, false, true)).toEqual({
			value: 's1',
			className: 'routing-cell routing-cell-set',
			disabled: false
		});
	});

	it('is the empty class and a blank value with no route', () => {
		expect(routeCellView(undefined, 2, false, true)).toEqual({
			value: '',
			className: 'routing-cell routing-cell-empty',
			disabled: false
		});
	});

	it('is disabled for a non-admin', () => {
		expect(routeCellView(route({}), 2, false, false).disabled).toBe(true);
	});

	it('is disabled while the row is in flight', () => {
		expect(routeCellView(route({}), 2, true, true).disabled).toBe(true);
	});

	it('is disabled with no session on offer', () => {
		expect(routeCellView(undefined, 0, false, true).disabled).toBe(true);
	});
});

describe('sessionOptionLabel', () => {
	it('is the name alone for a custom session', () => {
		expect(sessionOptionLabel(session({ name: 'Mine', is_builtin: false }))).toBe('Mine');
	});

	it('marks a built-in session', () => {
		expect(sessionOptionLabel(session({ name: 'Movie', is_builtin: true }))).toBe('Movie (built-in)');
	});
});

describe('otherRouteView', () => {
	it('labels the route and names its session', () => {
		expect(otherRouteView(route({ media_type: 'iso', disc_type: 'data' }), [session({})])).toEqual({
			label: 'ISO / data',
			name: 'Movie session'
		});
	});

	it('labels the wildcard disc and falls back to the session id', () => {
		expect(otherRouteView(route({ media_type: 'iso', disc_type: null, session_id: 'gone' }), [])).toEqual({
			label: 'ISO / Any disc',
			name: 'gone'
		});
	});
});
